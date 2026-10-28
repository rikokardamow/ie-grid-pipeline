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
is 20xx. A date with no day ("updated July 2016") is not an as-of. A file with
none of these has no as_of and is refused, never dated from its file name.
"""

from __future__ import annotations

import io
import re
from datetime import date

import pdfplumber

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

AS_OF = re.compile(
    r"(?:correct\s+as\s+of|information\s+correct\s*:?|data\s+(?:accurate\s+)?as\s+of|"
    r"as\s+of\s+the|updated)\s+(?:the\s+)?"
    r"(\d{1,2})(?:st|nd|rd|th)?(?:\s+of)?[\s/.-]+"
    r"(\d{1,2}|[A-Za-z]{3,9})\.?[\s/.-]+"
    r"(\d{4}|\d{2})\b",
    re.IGNORECASE,
)

# The phrase is on page 1 or 2 of the current lists, on the last page of some
# older ones. Searching every page costs little; the cap guards a huge file.
PAGES_TO_SEARCH = 60


def _month(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return MONTHS.get(token[:3].lower())


def as_of_from_text(text: str) -> date | None:
    """The as-of date in the text, or None. Every match must agree."""
    found = set()
    for d, m, y in AS_OF.findall(text):
        month = _month(m)
        if month is None:
            continue  # "Updated the Gate list ..." and the like: a word, not a month
        year = int(y) + 2000 if len(y) == 2 else int(y)
        try:
            found.add(date(year, month, int(d)))
        except ValueError:
            continue  # not a calendar date, so not this phrase
    if not found:
        return None
    if len(found) > 1:
        raise ValueError(f"more than one as-of date in the file: {sorted(found)}")
    return found.pop()


def pdf_text(content: bytes, pages: int = PAGES_TO_SEARCH) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages[:pages])


def as_of_from_pdf(content: bytes) -> date | None:
    return as_of_from_text(pdf_text(content))
