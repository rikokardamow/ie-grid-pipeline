"""The "correct as of" date printed inside each list.

The current lists word it three ways:
    EirGrid TSO lists        "Correct as of 05/08/2026"
    ESB DSO lists            "Information correct: 01/07/2026 Rev. 9"
    ESB summary report       "Data as of 01/07/2026"
Archived editions (g3) add, among others:
    "Correct as of 01/May/2017"          "Correct as of 18 January 2019"
    "Correct as of 01-Oct-2019"          "Correct as of the 29th of Aug 2016"
    "Data Accurate as of 1st March 2017" "As of the 19/07/2010"
    "Updated 1st December 2016"          "Information correct: 20-Apr-23 Rev. 0"
Dates are day, month, year; the month as a number or a name; a two-digit year
is 20xx. A date with no day ("updated July 2016") is not an as-of.

Two strengths. A heading or a "correct as of" line is strong. A bare "As of the
dd/mm/yyyy" is weak: in the 2009-2010 wind reports it labels a table column and
can carry the previous edition's date ("Connected Wind Report 05/08/2009" over
"As of the 25/05/2009"). Strong dates win. A weak date is used only when the file
name carries a date it agrees with.

For archived files (g3) the file name is a second witness: a text date that is
more than NAME_BEFORE_DAYS before, or NAME_AFTER_DAYS after, the date in the name
is a conflict and the file is refused rather than dated ("31th of May 2015" in a
list named 22-June-2016). Never is a file dated from its name alone.
"""

from __future__ import annotations

import io
import re
from datetime import date, timedelta

import pdfplumber

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

# day, then month (numeric needs a separator; a name may follow directly: "01Oct 2024"), year
_DATE = (r"(\d{1,2})(?:st|nd|rd|th)?(?:\s+of)?"
         r"(?:[\s/.-]+(\d{1,2})|[\s/.-]*([A-Za-z]{3,9}))\.?[\s/.-]+(\d{4}|\d{2})\b")
STRONG = re.compile(
    r"(?:correct\s+as\s+of(?:\s+the)?|information\s+correct\s*:?|"
    r"data\s+(?:accurate\s+)?as\s+of|updated(?:\s+the)?|"
    r"(?:connected|installed)\s+wind\s+report\s*[-\u2013]?)\s+" + _DATE, re.IGNORECASE)
WEAK = re.compile(r"as\s+of\s+the\s+" + _DATE, re.IGNORECASE)

# A text date may sit before the name's date (a list named for the day it went up)
# but not long after it. ESB's quarter names ("q2-2018") are read as the day after
# the quarter, and their text dates fall up to five weeks before.
NAME_BEFORE_DAYS = 60
NAME_AFTER_DAYS = 31

# The phrase is on page 1 or 2 of the current lists, on the last page of some
# older ones. Searching every page costs little; the cap guards a huge file.
PAGES_TO_SEARCH = 60


class AsOfConflict(ValueError):
    pass


def _month(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return MONTHS.get(token[:3].lower())


def _year(y: str) -> int:
    return int(y) + 2000 if len(y) == 2 else int(y)


def _dates(pattern: re.Pattern[str], text: str) -> set[date]:
    found = set()
    for d, m_num, m_name, y in pattern.findall(text):
        month = _month(m_num or m_name)
        if month is None:
            continue  # a word, not a month
        try:
            found.add(date(_year(y), month, int(d)))
        except ValueError:
            continue  # not a calendar date, so not this phrase
    return found


def agrees(text_date: date, name_date: date) -> bool:
    return (name_date - timedelta(days=NAME_BEFORE_DAYS) <= text_date
            <= name_date + timedelta(days=NAME_AFTER_DAYS))


def as_of_from_text(text: str, name_date: date | None = None) -> date | None:
    """The as-of date in the text, or None. Raises AsOfConflict when the text
    disagrees with itself or with the date in the file name."""
    strong, weak = _dates(STRONG, text), _dates(WEAK, text)
    if len(strong) > 1:
        raise AsOfConflict(f"more than one as-of date in the file: {sorted(strong)}")
    if strong:
        found = strong.pop()
    elif len(weak) == 1 and name_date is not None and agrees(next(iter(weak)), name_date):
        found = weak.pop()
    elif weak:
        raise AsOfConflict(f"only a table label date {sorted(weak)}, which the file name "
                           f"({name_date or 'no date'}) does not confirm")
    else:
        return None
    if name_date is not None and not agrees(found, name_date):
        raise AsOfConflict(f"text says {found}, file name says {name_date}")
    return found


MONTH_NAME = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"


def date_in_name(name: str) -> date | None:
    """The date in a normalised archive file name, in the dozen ways the publishers
    wrote one: 05aug09, 12jan10, 30sept09, 2june10, 16-nov-12, 23rd-july-2012,
    18thsept2015, 1th-dec-2016, 22-june-2016, 31.03.2022, 22.08.18, 21-12-2023,
    24-05-2010, 20090827, 14092009, 10-06-09, q2-2018, sept-2017. None if there is none."""
    stem = name.removesuffix(".pdf")
    patterns = (
        (rf"(\d{{1,2}})(?:st|nd|rd|th)?-?{MONTH_NAME}-?(\d{{4}}|\d{{2}})(?!\d)", "dmy_name"),
        (r"(?<!\d)(\d{1,2})[.-](\d{1,2})[.-](\d{4}|\d{2})(?!\d)", "dmy"),
        (r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", "ymd"),
        (r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)", "dmy"),
        (r"q([1-4])-(20\d{2})", "quarter"),
        (rf"(?<![a-z]){MONTH_NAME}-(20\d{{2}})", "my"),
    )
    for pattern, kind in patterns:
        m = re.search(pattern, stem)
        if not m:
            continue
        try:
            if kind == "dmy_name":
                return date(_year(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
            if kind == "dmy":
                return date(_year(m.group(3)), int(m.group(2)), int(m.group(1)))
            if kind == "ymd":
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if kind == "quarter":
                q, y = int(m.group(1)), int(m.group(2))
                return date(y + 1, 1, 1) if q == 4 else date(y, 3 * q + 1, 1)
            return date(int(m.group(2)), MONTHS[m.group(1)], 1)
        except ValueError:
            continue
    return None


def pdf_text(content: bytes, pages: int = PAGES_TO_SEARCH) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages[:pages])


def as_of_from_pdf(content: bytes, name_date: date | None = None) -> date | None:
    return as_of_from_text(pdf_text(content), name_date)
