"""The "correct as of" date printed inside each list.

The publishers word it three ways:
    EirGrid TSO lists        "Correct as of 05/08/2026"
    ESB DSO lists            "Information correct: 01/07/2026 Rev. 9"
    ESB summary report       "Data as of 01/07/2026"
Dates are day/month/year. A file with none of these has no as_of and the
ingest refuses it.
"""

from __future__ import annotations

import io
import re
from datetime import date

import pdfplumber

AS_OF = re.compile(
    r"(?:correct\s+as\s+of|information\s+correct\s*:|data\s+as\s+of)\s*"
    r"(\d{1,2})/(\d{1,2})/(\d{4})",
    re.IGNORECASE,
)

# The phrase is on page 1 of the TSO lists and the summary, page 2 of the DSO lists.
PAGES_TO_SEARCH = 3


def as_of_from_text(text: str) -> date | None:
    """First as-of date in the text, or None. Every match must agree."""
    found = {date(int(y), int(m), int(d)) for d, m, y in AS_OF.findall(text)}
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
