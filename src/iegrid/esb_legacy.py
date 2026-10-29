"""Layer: ESB's 2017-2023 lists, read. (docs/layers/06-esb-legacy/README.md)

The store holds 22 archived ESB editions from before the 2024 renewable / non-renewable
lists (contracted and energised, wind and non-wind, Sep 2017 to Apr 2023), unread since g3b.
Their rows are the distribution projects that signed and later withdrew, or connected before
the current energised list, and they are the missing early life of the funnel (layer 4).

Three layouts, all a real table under a header row, so the columns are found by header name:

    2017-19   Generator Reference | Project | Type | MEC (MW) | Feeding 110kV Station |
              Offer Type | Status | Estimated Connection Date
    2023-01   the same with a Feeding Station and a Conn Voltage column
    2023-04   "ESBNG Reference" and Designed_110kV_Station, as the current lists

The gate is the one the current lists pass: every ref at the start of a line in the page text
is a row read, and every row read is one. The lists print no total to tie MW to, so that is all
there is to check, and the README says so.

Rows go in their own table (esb_legacy_row), not project_row: dozens of queries select
`like '%contracted%'`, and legacy editions in project_row would move every existing number.
The layers that need them read this table explicitly.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pdfplumber

SOURCES = ("esb.dso_contracted_wind", "esb.dso_contracted_nonwind",
           "esb.dso_energised_wind", "esb.dso_energised_nonwind")
# ZG is a real ESB series, not a typo for DG: ZG937 "Anarget Wind Farm (1)" sits beside DG937
# "(2)", and ZG refs are in the current lists too
REF = re.compile(r"^(?:DG|TG|ZG)\d+[A-Za-z]{0,3}$")
LINE_REF = re.compile(r"^((?:DG|TG|ZG)\d+[A-Za-z]{0,3}) ", re.MULTILINE)
NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
NUMBER_TAIL = re.compile(r"^(.*?)(\d+(?:\.\d+)?)$")
# header text (lower-cased, spaces and underscores removed) to the field it names
COLUMNS = {
    "generatorreference": "ref", "esbngreference": "ref",
    "project": "name", "type": "technology",
    "mec(mw)": "mec", "mecmw": "mec", "mec": "mec",
    "feedingstation": "feeding", "feeding110kvstation": "station110",
    "designed110kvstation": "station110",
    "offertype": "offer", "status": "status",
    "estimatedconnectiondate": "date", "estconnectdate": "date",
    "connvoltage": "voltage",
}


STATUSES = ("Contracted", "Connected", "Energised")
# The technologies the lists use, so a cut row can be split into name and type even when no
# clean row of its own edition has that type (the edition's own are added as well)
KNOWN_TECHNOLOGIES = frozenset({
    "Wind", "Solar", "Hydro", "LFG", "Nat. Gas", "Biogas", "Diesel", "Biomass", "Biogas + AD",
    "Biogas / AD", "Battery Storage", "CHP", "Waste to Energy", "Flywheel Energy Storage",
    "OCGT", "Rice", "Gas", "Peat", "Other"})


class LegacyParseError(Exception):
    pass


def _subsequence(short: str, long: str) -> bool:
    it = iter(long)
    return all(c in it for c in short)


def normalise_status(status: str) -> tuple[str, str | None]:
    """A known status, or the one it is an overprint of ("DSCOontracted" is "DSO" printed over
    "Contracted"); refuses a status that fits none or more than one. Returns (status, note)."""
    if status in STATUSES:
        return status, None
    fits = [s for s in STATUSES if _subsequence(s, status) and len(status) - len(s) <= 3]
    if len(fits) != 1:
        raise LegacyParseError(f"unknown status {status!r}")
    return fits[0], f"status {status!r} read as {fits[0]!r} (overprinted text)"


@dataclass(frozen=True)
class LegacyRow:
    ref: str
    name: str
    technology: str
    mec_mw: Decimal | None
    feeding: str
    station110: str
    offer: str
    status: str
    date_text: str
    date_on: date | None
    voltage: str
    raw: str


def _clean(cell) -> str:
    return re.sub(r"\s+", " ", (cell or "").replace("\n", " ")).strip()


def _key(header: str) -> str:
    return re.sub(r"[\s_]+", "", header.lower())


def _date(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None


def _nospace(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _spaced_prefix(line: str, joined: str) -> str | None:
    """The start of `line` whose letters, whitespace aside, are exactly `joined`'s, or None."""
    want, got, i = _nospace(joined), "", 0
    while i < len(line) and len(got) < len(want):
        if not line[i].isspace():
            got += line[i]
        i += 1
    return line[:i].strip() if got == want else None


def _repair(cells: list[str], header: list[str | None], lines: list[str],
            technologies: set[str]) -> dict[str, str] | None:
    """Some rows have their cell borders cut through words ('DG1814 Temp' | 'lederry
    Windfarm', or 'Battery Storag' | 'e 30.000'). The text line is intact, so rebuild the
    leading fields from it, accepting only if the cells joined without whitespace are exactly
    the start of that line. Returns None when it can't be verified."""
    if "mec" not in header or "ref" not in header or header.index("ref") != 0:
        return None
    m = header.index("mec")
    tail = NUMBER_TAIL.match(cells[m])
    if tail is None:
        return None
    joined = "".join(cells[:m]) + tail.group(1)
    ref = cells[0].split(" ")[0]
    line = next((ln for ln in lines if ln.startswith(ref + " ")
                 and _spaced_prefix(ln, joined) is not None), None)
    if line is None:
        return None
    lead = _spaced_prefix(line, joined)
    rest = lead[len(ref):].strip()
    tech = max((t for t in technologies if rest.endswith(t)), key=len, default="")
    name = rest[: len(rest) - len(tech)].strip() if tech else rest
    return {"ref": ref, "name": name, "technology": tech, "mec": tail.group(2)}


def read(content: bytes) -> tuple[list[LegacyRow], list[str]]:
    """(rows, notes), or LegacyParseError if the gate fails. Notes are what was repaired or
    dropped, never silently: a publisher's duplicate row, an overprinted status."""
    rows: list[LegacyRow] = []
    notes: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        lines = [ln.strip() for ln in text.splitlines()]
        technologies: set[str] = set()
        raw_rows: list = []
        pending: list = []
        header: list[str | None] = []
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                first = [COLUMNS.get(_key(_clean(c))) for c in table[0]] if table else []
                if "ref" in first and "mec" in first:
                    header, body = first, table[1:]
                elif header and table and REF.match(
                        (_clean(table[0][0]).split(" ") or ["-"])[0] or "-"):
                    body = table  # a later page: the header is printed once
                else:
                    continue  # the key-terms tables at the top of the first page
                for cells in body:
                    clean = [_clean(c) for c in cells]
                    row = {f: c for f, c in zip(header, clean, strict=False) if f}
                    if not row.get("ref") or row["ref"].lower().endswith("reference"):
                        continue  # a header repeated on a later page
                    if " " in row["ref"] or not NUMBER.match(row.get("mec", "")):
                        pending.append((len(raw_rows), clean, list(header), page_no))
                        raw_rows.append(None)  # filled in once every clean row's type is known
                        continue
                    if row.get("technology"):
                        technologies.add(row["technology"])
                    raw_rows.append((row, cells, page_no))
    for at, clean, hdr, page_no in pending:
        fixed = _repair(clean, hdr, lines, technologies | KNOWN_TECHNOLOGIES)
        if fixed is None:
            raise LegacyParseError(
                f"page {page_no}: a row with its cells cut through words that its text "
                f"line can't verify: {clean[:3]}")
        row = {f: c for f, c in zip(hdr, clean, strict=False) if f}
        row.update(fixed)
        raw_rows[at] = (row, clean, page_no)
    for row, cells, page_no in raw_rows:
        try:
            mec = Decimal(row.get("mec", "")) if row.get("mec") else None
        except InvalidOperation:
            raise LegacyParseError(
                f"page {page_no}: MEC {row.get('mec')!r} for {row['ref']}") from None
        dt = row.get("date", "")
        status, note = normalise_status(row.get("status", ""))
        if note:
            notes.append(f"{row['ref']}: {note}")
        rows.append(LegacyRow(
            row["ref"], row.get("name", ""), row.get("technology", ""), mec,
            row.get("feeding", ""), row.get("station110", ""), row.get("offer", ""),
            status, dt, _date(dt), row.get("voltage", ""),
            " | ".join(_clean(c) for c in cells)))
    # a ref on two rows is legitimate (DG249 and its "(extension)"). The same row twice is
    # accepted only if the page text prints that line twice too (a publisher's duplicate: DG943a
    # in the Dec 2017 energised non-wind list), then dropped and noted.
    kept: list[LegacyRow] = []
    for r in rows:
        twin = next((k for k in kept if (k.ref, k.name, k.mec_mw, k.status, k.date_text)
                     == (r.ref, r.name, r.mec_mw, r.status, r.date_text)), None)
        if twin is None:
            kept.append(r)
        elif sum(1 for ln in lines if ln.startswith(r.ref + " ") and r.name in ln) >= 2:
            notes.append(f"{r.ref} {r.name!r} is printed twice in the list; counted once")
        else:
            kept.append(r)  # not in the text twice: left for the gate below to refuse
    rows = kept
    read_refs = [r.ref for r in rows]
    page_refs = set(LINE_REF.findall(text))
    problems = []
    seen = [(r.ref, r.name, r.mec_mw, r.status) for r in rows]
    if dup := sorted({x[0] for x in seen if seen.count(x) > 1}):
        problems.append(f"the same row read twice: {dup[:5]}")
    if missed := sorted(page_refs - set(read_refs)):
        problems.append(f"refs on the page not read as rows: {missed[:6]}")
    if extra := sorted(r for r in set(read_refs) - page_refs if not REF.match(r)):
        problems.append(f"rows whose ref doesn't look like one: {extra[:6]}")
    if not rows:
        problems.append("no rows read")
    if problems:
        raise LegacyParseError("; ".join(problems))
    return rows, notes


def editions(con) -> list[tuple[int, str, date, str]]:
    return con.execute(f"""
        select publication_id, source_id, as_of, raw_path from publication
        where source_id in ({", ".join(repr(s) for s in SOURCES)}) order by as_of, source_id
    """).fetchall()


def load(con, now) -> tuple[int, list[str], list[str]]:
    """Read every legacy edition not yet loaded. Returns (loaded, problems, notes): a
    refused edition is a problem and stores nothing."""
    from iegrid import store

    done = {r[0] for r in con.execute("select distinct publication_id from esb_legacy_row").fetchall()}
    loaded, problems, notes = 0, [], []
    for pid, sid, as_of, raw in editions(con):
        if pid in done:
            continue
        try:
            rows, ed_notes = read((store.ROOT / raw).read_bytes())
        except LegacyParseError as exc:
            problems.append(f"{sid} {as_of}: {exc}")
            continue
        notes += [f"{sid} {as_of}: {n}" for n in ed_notes]
        con.executemany(
            "insert into esb_legacy_row values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [[pid, i, r.ref, r.name, r.technology, r.mec_mw, r.feeding, r.station110, r.offer,
              r.status, r.date_text, r.date_on, r.voltage, r.raw, now]
             for i, r in enumerate(rows, 1)])
        loaded += 1
    return loaded, problems, notes


def main(argv: list[str] | None = None) -> int:
    """Read ESB's archived 2017-2023 lists into esb_legacy_row (once; re-runs add nothing)."""
    import argparse
    from datetime import UTC

    from iegrid import store

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--db", default=str(store.DEFAULT_DB))
    args = parser.parse_args(argv)
    con = store.connect(args.db)
    try:
        loaded, problems, notes = load(con, datetime.now(UTC))
    finally:
        con.close()
    print(f"ESB legacy editions loaded: {loaded}")
    for line in problems:
        print(f"  refused: {line}")
    for line in notes:
        print(f"  note: {line}")
    return 1 if problems else 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
