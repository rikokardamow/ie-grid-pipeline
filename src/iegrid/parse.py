"""g2: the project rows in each list, read with pdfplumber's table finder.

Two layouts:

EirGrid TSO lists, 7 columns, header repeated on every page:
    Node and Associated Voltage | Ref | Name | Processing Type | Type | MEC (MW) | Signed Date*
    "Knockranny 110 kV" | TG443 | Ardderroo Wind Farm Extension | ECP-2.1 | Wind | 18.0 | Jul 2023
The last page prints "Total TSO Contracted: <MW>". The footnote says the signed
date is the latest contract that changed the capacity, not the first signing.

ESB DSO lists, 13 columns (14 with Connect_Date on the energised lists). The
table finder splits the header into extra empty columns (None), and a real empty
cell is "". Dropping the None cells leaves the fields in order:
    ref | project | type | MEC_MW | feeding station | designed 110kV station |
    offer type | status | [connect date] | conn voltage
A row with no ref and type "Total" carries the printed total (blank on the
energised renewable list).

Cells keep their line breaks in `raw`. The clean fields join lines with a space,
which is wrong for words the PDF wrapped mid-word ("Autoproduce" + "r"). That
matters only for names and stations, which g4 normalises; see PARKING.md.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import pdfplumber

# Bump when the parser changes what it reads. Re-parsing a publication under a
# new version adds rows; rows from older versions stay.
PARSER_VERSION = 1

# A parse is only stored if its rows equal the refs counted in the page text and,
# where the list prints a total, its MW are within this of it.
TIE_MW = 1

REF = re.compile(r"[A-Z]{1,2}\d+[A-Za-z]?")
TSO_HEADER = ("Node and Associated Voltage", "Ref", "Name", "Processing Type", "Type",
              "MEC (MW)", "Signed Date*")
TSO_NODE = re.compile(r"(.+?)\s+(\d+\s*kV)$", re.IGNORECASE)
TSO_TOTAL = re.compile(r"Total TSO Contracted(?: Wind)?:\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
MONTH_YEAR = re.compile(r"([A-Za-z]{3})\w*\s+(\d{4})")
DMY = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectRow:
    row_order: int          # position in the file, from 1
    page: int               # from 1
    project_ref: str
    name: str
    technology: str
    mec_mw: Decimal
    node: str               # TSO node, or DSO feeding station ("" when blank)
    station_110kv: str      # DSO designed 110 kV station; "" on TSO lists
    voltage: str            # "110 kV", "20 kV", "LV"
    processing_type: str    # ECP-2.1, Gate 2, Non GPA, Pre-Gate, T-4 2028/2029, ...
    status: str             # Contracted, On Hold, Energised
    signed_month: date | None   # TSO only, first of the month
    energised_on: date | None   # DSO energised lists only
    energised_note: str     # "pre 2005" when the list gives no date
    raw: str                # the cells as extracted, JSON


@dataclass(frozen=True)
class Parsed:
    rows: list[ProjectRow]
    printed_total_mw: Decimal | None


def clean(cell: str | None) -> str:
    return " ".join((cell or "").split())


def mw(text: str) -> Decimal:
    try:
        return Decimal(clean(text).replace(",", ""))
    except InvalidOperation as exc:
        raise ParseError(f"not a MW value: {text!r}") from exc


def month(text: str) -> date:
    m = MONTH_YEAR.fullmatch(clean(text))
    if not m or m.group(1).lower() not in MONTHS:
        raise ParseError(f"not a month: {text!r}")
    return date(int(m.group(2)), MONTHS[m.group(1).lower()], 1)


def _tables(content: bytes):
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            yield page_no, page.extract_tables(), page.extract_text() or ""


def parse_tso(content: bytes) -> Parsed:
    return parse_tso_pages(_tables(content))


def parse_tso_pages(pages) -> Parsed:
    """pages: (page number, tables as lists of cell lists, page text), as from _tables."""
    rows: list[ProjectRow] = []
    total = None
    for page_no, tables, text in pages:
        if m := TSO_TOTAL.search(text):
            total = mw(m.group(1))
        for table in tables:
            if not table or tuple(clean(c) for c in table[0]) != TSO_HEADER:
                continue  # the finder also returns each wrapped header cell as its own table
            for cells in table[1:]:
                if not any(clean(c) for c in cells):
                    continue
                node_v, ref, name, ptype, tech, mec, signed = (clean(c) for c in cells)
                if not REF.fullmatch(ref):
                    raise ParseError(f"page {page_no}: no ref in {cells}")
                nm = TSO_NODE.fullmatch(node_v)
                if not nm:
                    raise ParseError(f"page {page_no}: node without voltage in {cells}")
                rows.append(ProjectRow(
                    row_order=len(rows) + 1, page=page_no, project_ref=ref, name=name,
                    technology=tech, mec_mw=mw(mec), node=nm.group(1), station_110kv="",
                    voltage=nm.group(2), processing_type=ptype, status="Contracted",
                    signed_month=month(signed), energised_on=None, energised_note="",
                    raw=json.dumps(cells),
                ))
    return Parsed(rows, total)


def parse_dso(content: bytes) -> Parsed:
    return parse_dso_pages(_tables(content))


def parse_dso_pages(pages) -> Parsed:
    rows: list[ProjectRow] = []
    total = None
    for page_no, tables, _ in pages:
        for table in tables:
            if not table or "ESBNG" not in [clean(c) for c in table[0]]:
                continue  # page 1 is a table of definitions
            energised = "Connect_Date" in [clean(c) for c in table[0]]
            width = 10 if energised else 9
            for cells in table[1:]:
                fields = [clean(c) for c in cells if c is not None]
                if not any(fields) or fields[:1] == ["Reference"]:
                    continue  # blank rows and the second header line
                if len(fields) != width:
                    raise ParseError(f"page {page_no}: {len(fields)} fields, want {width}: {cells}")
                if not fields[0]:
                    if fields[2] == "Total":
                        total = mw(fields[3]) if fields[3] else None
                        continue
                    raise ParseError(f"page {page_no}: row without a ref: {cells}")
                ref, name, tech, mec, feeding, station, offer, status = fields[:8]
                if not REF.fullmatch(ref):
                    raise ParseError(f"page {page_no}: not a ref {ref!r}")
                energised_on, note = None, ""
                if energised:
                    connect = fields[8]
                    if m := DMY.fullmatch(connect):
                        d, mo, y = map(int, m.groups())
                        energised_on = date(y, mo, d)
                    elif "pre 2005" in connect.lower():
                        note = "pre 2005"
                    else:  # every energised row has a date or "pre 2005"; a blank is a misread
                        raise ParseError(f"page {page_no}: connect date {connect!r} for {ref}")
                rows.append(ProjectRow(
                    row_order=len(rows) + 1, page=page_no, project_ref=ref, name=name,
                    technology=tech, mec_mw=mw(mec), node=feeding, station_110kv=station,
                    voltage=fields[-1], processing_type=offer, status=status,
                    signed_month=None, energised_on=energised_on, energised_note=note,
                    raw=json.dumps(cells),
                ))
    return Parsed(rows, total)


PARSERS = {
    "eirgrid.tso_contracted_wind": parse_tso,
    "eirgrid.tso_contracted_nonwind": parse_tso,
    "esb.dso_contracted_renewable": parse_dso,
    "esb.dso_energised_renewable": parse_dso,
    "esb.dso_contracted_nonrenewable": parse_dso,
    "esb.dso_energised_nonrenewable": parse_dso,
}


# A ref starts a DSO line, and follows the node's "kV" on a TSO line.
TEXT_REF = re.compile(r"(?:^|kV )([A-Z]{1,2}\d+[A-Za-z]?) ", re.MULTILINE)


def refs_in_text(content: bytes) -> dict[int, int]:
    """Refs per page found by a regex on the page text: a count that doesn't use
    the table finder, so it can check the parse."""
    out = {}
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            out[page_no] = len(TEXT_REF.findall(text))
    return out


SUMMARY_ROW = re.compile(r"^(Renewable Grid Scale)\*?\s+([\d,]+)\s+([\d,]+)\s*$", re.MULTILINE)


def grid_scale_from_summary(content: bytes) -> tuple[int, Decimal]:
    """ESB summary report, Table 1, "Renewable Grid Scale*": (connections, MW).
    The energised renewable list is the grid-scale connections, so it ties to this."""
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = pdf.pages[0].extract_text() or ""
    m = SUMMARY_ROW.search(text)
    if not m:
        raise ParseError("no Renewable Grid Scale row in the summary report")
    return int(m.group(2).replace(",", "")), mw(m.group(3))


# g3: the total an EirGrid contracted list prints for itself, in every wording
# used since 2015: "Total Contracted: 437.4", "Total TSO Contracted: 3226.4",
# "Total TSO Contracted Wind: 1450.10 MW". Older lists print none.
PRINTED_TOTAL = re.compile(
    r"(Total (?:TSO )?Contracted(?: Wind)?):\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
TOTAL_SOURCES = ("eirgrid.tso_contracted_wind", "eirgrid.tso_contracted_nonwind")


def printed_total(content: bytes) -> tuple[Decimal, str] | None:
    from iegrid.asof import pdf_text

    found = PRINTED_TOTAL.findall(pdf_text(content))
    if not found:
        return None
    if len({mw(v) for _, v in found}) > 1:
        raise ParseError(f"more than one printed total: {found}")
    phrase, value = found[-1]
    return mw(value), phrase
