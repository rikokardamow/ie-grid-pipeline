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
PARSER_VERSION = 2  # g3b: older TSO layouts read by word position

# A parse is only stored if its rows equal the refs counted in the page text and,
# where the list prints a total, its MW are within this of it.
TIE_MW = 1

REF = re.compile(r"[A-Z]{1,2}\d+[A-Za-z]?")
TSO_HEADER = ("Node and Associated Voltage", "Ref", "Name", "Processing Type", "Type",
              "MEC (MW)", "Signed Date*")
TSO_NODE = re.compile(r"(.+?)\s+(\d+\s*kV)$", re.IGNORECASE)
TSO_TOTAL = re.compile(r"Total (?:TSO )?Contracted(?: Wind)?:\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
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
    target_month: date | None = None  # TSO 2015-2016 only: the target connection month


@dataclass(frozen=True)
class Parsed:
    rows: list[ProjectRow]
    printed_total_mw: Decimal | None
    layout: str = "table"   # "lines" when read line by line (parse_tso_words)
    ref_check: str = "count"  # "set": every ref parsed is in the text and the other way round


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
    """Both readers, and the one that ties: the table finder (header in one row, as in
    2026, or split over two rows, as Aug 2022 - Sep 2025) and the line reader
    (parse_tso_words; editions before Aug 2022 draw no lines between rows). A reader
    that raises or doesn't tie loses to one that does. If neither ties, the first
    with rows is returned, so the load's gate reports what it read."""
    from iegrid import parse_tso_words

    printed = printed_total(content)
    total = printed[0] if printed else None
    tries: list[Parsed] = []
    errors: list[str] = []
    try:
        tries.append(parse_tso_pages(_tables(content)))
    except ParseError as exc:
        errors.append(f"table: {exc}")
    try:
        rows = parse_tso_words.to_project_rows(parse_tso_words.read(content))
        tries.append(Parsed(rows, total, layout="lines"))
    except ParseError as exc:
        errors.append(f"lines: {exc}")
    # EirGrid lists: the set of refs, not their count (a ref that bled into a node cell
    # appears twice in the text, "... 110 kV TG495" and "TG495")
    tries = [Parsed(g.rows, g.printed_total_mw if g.printed_total_mw is not None else total,
                    g.layout, "set") for g in tries]
    text = text_ref_set(content)
    for got in tries:
        mw_sum = sum((r.mec_mw for r in got.rows), start=Decimal(0))
        if (got.rows and got.printed_total_mw is not None
                and abs(mw_sum - got.printed_total_mw) <= TIE_MW
                and {r.project_ref for r in got.rows} == text):
            return got
    with_rows = [g for g in tries if g.rows]
    if with_rows:
        return with_rows[0]
    raise ParseError("; ".join(errors) or "no rows read")


# Column labels, by how the header cell (joined over two rows) starts
TSO_COLUMNS = (
    ("node", ("node and associated", "associated voltage")),
    ("ref", ("ref",)),
    ("name", ("name", "wind farm name")),
    ("processing", ("processing",)),
    ("type", ("type",)),
    ("mec", ("mec",)),
    ("signed", ("signed",)),
)


def _tso_columns(header: list[str]) -> dict[str, int] | None:
    cols: dict[str, int] = {}
    for i, cell in enumerate(header):
        c = cell.lower()
        for field, starts in TSO_COLUMNS:
            if field not in cols and any(c.startswith(s) for s in starts):
                cols[field] = i
                break
    return cols if {"node", "ref", "name", "mec"} <= set(cols) else None


def parse_tso_pages(pages) -> Parsed:
    """pages: (page number, tables as lists of cell lists, page text), as from _tables."""
    rows: list[ProjectRow] = []
    total = None
    for page_no, tables, text in pages:
        if m := TSO_TOTAL.search(text):
            total = mw(m.group(1))
        for table in tables:
            if not table or len(table[0]) < 4:
                continue  # the finder also returns each wrapped header cell as its own table
            header = [clean(c) for c in table[0]]
            body = table[1:]
            # a header split over two rows ("Node and Associated" / "Voltage")
            if body and clean(body[0][0]).lower() == "voltage":
                header = [f"{h} {clean(c)}".strip()
                          for h, c in zip(header, body[0], strict=False)]
                body = body[1:]
            cols = _tso_columns(header)
            if cols is None:
                continue
            for raw_cells in body:
                cells = [clean(c) for c in raw_cells]
                if not any(cells) or not cells[cols["ref"]]:
                    continue

                def at(field, cells=cells, cols=cols):
                    return cells[cols[field]] if field in cols else ""

                node_v, ref, name = at("node"), at("ref").rstrip("."), at("name")
                node_v = re.sub(rf"\s+{re.escape(ref)}\.?$", "", node_v)  # "Athlone 110 kV TG495"
                ptype, tech, mec, signed = at("processing"), at("type"), at("mec"), at("signed")
                if not REF.fullmatch(ref):
                    raise ParseError(f"page {page_no}: no ref in {cells}")
                nm = TSO_NODE.fullmatch(node_v)
                if not nm:
                    raise ParseError(f"page {page_no}: node without voltage in {cells}")
                rows.append(ProjectRow(
                    row_order=len(rows) + 1, page=page_no, project_ref=ref, name=name,
                    technology=tech, mec_mw=mw(mec), node=nm.group(1), station_110kv="",
                    voltage=nm.group(2), processing_type=ptype, status="Contracted",
                    signed_month=month(signed) if signed else None, energised_on=None,
                    energised_note="", raw=json.dumps(raw_cells),
                ))
    return Parsed(rows, total)


def parse_dso(content: bytes) -> Parsed:
    return parse_dso_pages(_tables(content))


def parse_dso_pages(pages) -> Parsed:
    rows: list[ProjectRow] = []
    total = None
    for page_no, tables, _ in pages:
        for table in tables:
            if not table or not any(clean(c).startswith("ESBNG") for c in table[0]):
                continue  # page 1 is a table of definitions
            energised = "Connect_Date" in [clean(c) for c in table[0]]
            width = 10 if energised else 9
            seen_data = False
            for cells in table[1:]:
                fields = [clean(c) for c in cells if c is not None]
                if not any(fields) or fields[:1] == ["Reference"]:
                    continue  # blank rows and the second header line
                # more header lines before the first row ("Voltage", "Station / _Station",
                # 2024-2026): short, no number, before any data
                if (not seen_data and len(fields) < width
                        and not any(re.search(r"\d", f) for f in fields)):
                    continue
                seen_data = True
                if len(fields) != width:
                    raise ParseError(f"page {page_no}: {len(fields)} fields, want {width}: {cells}")
                if not fields[0]:
                    if fields[2].rstrip(":") == "Total":
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
                    elif "unavailable" in connect.lower():  # 2024-2025: "Date unavailable at this time"
                        note = "date unavailable"
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


# Word-layout TSO lists put the ref mid-line ("Athea (2) 3 TG77 20.00 Gate 2 ...").
# A ref in brackets ("(Ext to DG978)") is part of a name, not a row.
TEXT_REF_ANY = re.compile(
    r"(?<![(\w])(?:TG|DG|P|D)\d+(?:-\d+)?[A-Za-z]?\.?(?=\s|[A-Z][a-z])")


def text_ref_set(content: bytes) -> set[str]:
    """Every ref in the page text, wherever on the line (brackets within a line left out)."""
    out: set[str] = set()
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = re.sub(r"\([^)\n]*\)", " ", page.extract_text() or "")
            out |= {r.rstrip(".") for r in TEXT_REF_ANY.findall(text.replace("\n", " \n") + " ")}
    return out


def refs_in_text_any(content: bytes) -> dict[int, int]:
    out = {}
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            # brackets within a line only: "(formerly" on one line and ")" on the next
            # must not swallow the ref between them
            text = re.sub(r"\([^)\n]*\)", " ", page.extract_text() or "")
            out[page_no] = len(TEXT_REF_ANY.findall(text.replace("\n", " \n") + " "))
    return out


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
