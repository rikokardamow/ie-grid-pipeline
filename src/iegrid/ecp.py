"""g4: the county of each project, from the ECP batch results publications.

The joint system-operator results PDFs (ECP-1 in 2018 to ECP-2.5 and the GSS
batches, plus the "Categories B and C" lists) give each project's county,
coordinates and assumed connection node, but no TG/DG reference, and no two
share a layout: merged cells, wrapped names, an "Offer Quarter" or "Status"
column in front of some. So rows are found by position rather than by table:

    1. the header word "County" fixes the county column (several tables a page);
    2. every county name in that column below the header is one row;
    3. a row spans from halfway to the row above to halfway to the row below,
       so a name wrapped over two or three lines stays with its row;
    4. other fields are the words under their header (name, MEC, node).

What a row says is checked by the caller: it only counts when it matches a
project in the lists by name and MEC (see region.py).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import pdfplumber

# Bump when the reader changes what it reads. Rows are stored per reader version,
# so a fixed reader adds rows for files already read instead of being skipped.
READER_VERSION = 2

COUNTIES = (
    "Carlow", "Cavan", "Clare", "Cork", "Donegal", "Dublin", "Galway", "Kerry", "Kildare",
    "Kilkenny", "Laois", "Leitrim", "Limerick", "Longford", "Louth", "Mayo", "Meath",
    "Monaghan", "Offaly", "Roscommon", "Sligo", "Tipperary", "Waterford", "Westmeath",
    "Wexford", "Wicklow",
)
_COUNTY = {c.lower(): c for c in COUNTIES}
# How far a county word may sit from the County header's centre, in points.
COLUMN_SLACK = 40
# Header words that start a column, by field.
HEADERS = {
    "name": ("name", "facility", "project"),
    "applicant": ("applicant",),
    "county": ("county",),
    "coords": ("co-ordinates", "coordinates", "easting", "eastings", "eastings:", "easting:"),
    "type": ("gen", "generator", "generation", "technology"),
    "mec": ("mec",),
    "node": ("assumed", "node", "node*", "node**"),
    "pp": ("pp", "planning"),
}
HEADER_BAND = 30  # header words of one table sit within this many points of "County"
WRAP_GAP = 16     # a county split over two lines ("Roscommo" / "n") is this close
NUMBER = re.compile(r"^\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class EcpRow:
    page: int
    name: str
    county: str
    mec_mw: Decimal | None
    node: str


def _field_of(word: str) -> str | None:
    w = word.lower().strip(":*")
    for field, starts in HEADERS.items():
        if w in (s.strip(":*") for s in starts):
            return field
    return None


def _columns(words, county_word) -> dict[str, float]:
    """x0 of each header found on the County header's line."""
    cols: dict[str, float] = {}
    for w in words:
        if abs(w["top"] - county_word["top"]) > HEADER_BAND:
            continue
        field = _field_of(w["text"])
        if field and field not in cols:
            cols[field] = w["x0"]
    return cols


def _between(words, x_lo: float, x_hi: float, y_lo: float, y_hi: float) -> list[str]:
    hits = [w for w in words if x_lo - 4 <= (w["x0"] + w["x1"]) / 2 < x_hi - 4
            and y_lo <= (w["top"] + w["bottom"]) / 2 < y_hi]
    return [w["text"] for w in sorted(hits, key=lambda w: (round(w["top"]), w["x0"]))]


@dataclass(frozen=True)
class Layout:
    """A table's columns, carried onto the pages it runs over (only the first has a header)."""
    cols: dict[str, float]
    centre: float


def _county_anchors(words, centre: float, y_top: float, y_bottom: float) -> list[dict]:
    """County names in the County column, including ones the PDF split: two words on
    a line ("West Meath") or one word wrapped onto the next ("Roscommo" / "n").
    A joined anchor spans both pieces and carries the county's proper name."""
    col = sorted((w for w in words if abs((w["x0"] + w["x1"]) / 2 - centre) <= COLUMN_SLACK
                  and y_top < w["top"] < y_bottom), key=lambda w: (w["top"], w["x0"]))
    out, used = [], set()
    for i, w in enumerate(col):
        if i in used:
            continue
        if w["text"].lower() in _COUNTY:
            out.append({**w, "county": _COUNTY[w["text"].lower()]})
            continue
        for j, nxt in enumerate(col):
            if j == i or j in used:
                continue
            same_line = abs(nxt["top"] - w["top"]) < 3 and nxt["x0"] > w["x0"]
            wrapped = 0 < nxt["top"] - w["top"] <= WRAP_GAP and abs(nxt["x0"] - w["x0"]) <= 6
            joined = (w["text"] + nxt["text"]).lower()
            if (same_line or wrapped) and joined in _COUNTY:
                used.add(j)
                out.append({"text": joined, "county": _COUNTY[joined], "x0": w["x0"],
                            "x1": max(w["x1"], nxt["x1"]), "top": w["top"],
                            "bottom": nxt["bottom"]})
                break
    return sorted(out, key=lambda a: a["top"])


def _rows_in_region(words, page_no: int, layout: Layout, y_top: float,
                    y_bottom: float) -> list[EcpRow]:
    cols, centre = layout.cols, layout.centre
    anchors = _county_anchors(words, centre, y_top, y_bottom)
    order = sorted(cols.values())

    def span(field: str) -> tuple[float, float] | None:
        if field not in cols:
            return None
        x0 = cols[field]
        later = [x for x in order if x > x0]
        return x0, (min(later) if later else 10_000)

    out = []
    for j, a in enumerate(anchors):
        mid = (a["top"] + a["bottom"]) / 2
        prev = anchors[j - 1] if j else None
        nxt = anchors[j + 1] if j + 1 < len(anchors) else None
        y_lo = (((prev["top"] + prev["bottom"]) / 2 + mid) / 2) if prev else y_top
        y_hi = ((mid + (nxt["top"] + nxt["bottom"]) / 2) / 2) if nxt else y_bottom
        name_span = span("name")
        name = " ".join(_between(words, *name_span, y_lo, y_hi)) if name_span else ""
        name = re.sub(r"\s*Page \d+ of \d+\s*", " ", name).strip()  # a footer in the span
        mec = None
        if (s := span("mec")) is not None:
            nums = [t for t in _between(words, *s, y_lo, y_hi) if NUMBER.match(t)]
            if nums:
                try:
                    mec = Decimal(nums[0])
                except InvalidOperation:
                    mec = None
        node = " ".join(_between(words, *span("node"), y_lo, y_hi)) if span("node") else ""
        out.append(EcpRow(page_no, name, a["county"], mec, node))
    return out


def rows_on_page(words, page_no: int, page_bottom: float,
                 carry: Layout | None = None) -> tuple[list[EcpRow], Layout | None]:
    """Rows on one page, and the layout to carry onto the next page."""
    headers = sorted((w for w in words if w["text"] == "County"), key=lambda w: w["top"])
    out: list[EcpRow] = []
    first_top = headers[0]["top"] if headers else page_bottom
    if carry is not None:  # the table from the page before runs on above any new header
        out.extend(_rows_in_region(words, page_no, carry, 0, first_top - 1))
    for i, head in enumerate(headers):
        region_bottom = headers[i + 1]["top"] - 1 if i + 1 < len(headers) else page_bottom
        layout = Layout(_columns(words, head), (head["x0"] + head["x1"]) / 2)
        header_bottom = max(w["bottom"] for w in words
                            if abs(w["top"] - head["top"]) <= HEADER_BAND
                            and _field_of(w["text"]))
        out.extend(_rows_in_region(words, page_no, layout, header_bottom, region_bottom))
        carry = layout
    return out, carry


def parse_ecp(content: bytes) -> list[EcpRow]:
    rows: list[EcpRow] = []
    carry: Layout | None = None
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(keep_blank_chars=False, x_tolerance=1.5)
            got, carry = rows_on_page(words, page_no, page.height, carry)
            rows.extend(got)
    return rows
