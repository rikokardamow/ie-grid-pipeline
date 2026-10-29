"""Layer: EirGrid's TSO connected lists, read so a project that left the contracted
lists can be called connected or not (docs/layer-connected-risk.md).

The store holds 42 connected editions from the archive (g3). Three layouts carry a
project ref on each row and are read here:

    2015-16 lines   Athea (1)a 1 TG22a 34.350 34.350 Gate 1 Athea 110 kV Oct 2013
                    name (phase) phase REF installed MEC gate node kV month
    2016-22 table   29 Wind Onshore 2 TG55a Lisheen 2 Full 23 24 May-2013 Tipperary 12 Y
                    no type [onshore] gate REF name phase Full|Partial MEC installed month

(the table's MEC comes first: Castledockrell 3 is "2.300 3.300" installed/MEC in 2015
and "3.3 2.3" in the table). The 2008-11 wind reports name projects without refs and
the non-wind lists give a name and a year only; neither is read here (risk 1).

Each edition is gated before its rows count:

    refs        every ref at a row's position in the page text is a row read, and
                every row read is one (refs in a row's notes, "Booltiagh 2 & 3
                (TG38 & TG39)", are not rows)
    numbering   table rows are numbered 1..N with no gap within each section
    MW          the rows' installed wind MW is within TIE_MW of the total the list
                prints ("Total MW", or the latest month of its monthly wind table)

A partially connected project shows only its latest increase date, not its first
energisation (the lists' own FAQ), so a connection month is "connected by", not
"first energised in".
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pdfplumber

from iegrid import parse

SOURCES = ("eirgrid.tso_connected_wind", "eirgrid.tso_connected_renewable")
REF = re.compile(r"^(?:TG|DG|P|D)\d+(?:-\d+)?[A-Za-z]{0,3}\.?$")
NUM = re.compile(r"^\d+(?:\.\d+)?$")
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTH = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[- ](\d{4})\b")
TIE_MW = Decimal(1)
WIND_KINDS = {"Wind", "Onshore", "Offshore"}


@dataclass(frozen=True)
class ConnectedRow:
    ref: str
    name: str
    mec_mw: Decimal | None
    installed_mw: Decimal | None
    connected: date | None   # month: "connected by", see the docstring
    full: bool | None        # None in the 2015-16 lines, which don't say
    kind: str                # 'Wind' or what the table's type column says
    line: str


class ConnectedParseError(Exception):
    pass


def _month(text: str) -> date | None:
    m = MONTH.search(text)
    return date(int(m.group(2)), MONTHS[m.group(1).lower()], 1) if m else None


def parse_line(line: str) -> ConnectedRow | None:
    tokens = line.split()
    at = next((i for i, t in enumerate(tokens) if REF.match(t)), None)
    if at is None:
        return None
    ref = tokens[at].rstrip(".")
    if "Full" in tokens[at:] or "Partial" in tokens[at:]:  # the 2016-22 table
        if not tokens[0].isdigit():
            return None  # a note or heading mentioning a ref, not a row
        k = next(i for i in range(at, len(tokens)) if tokens[i] in ("Full", "Partial"))
        nums = [t for t in tokens[k + 1:k + 3] if NUM.match(t)]
        if len(nums) != 2:
            return None
        name = " ".join(tokens[at + 1:k - 1])  # the token before Full is the phase
        kind = tokens[1]
        return ConnectedRow(ref, name, Decimal(nums[0]), Decimal(nums[1]),
                            _month(" ".join(tokens[k + 3:])), tokens[k] == "Full", kind, line)
    nums = [t for t in tokens[at + 1:at + 3] if NUM.match(t)]  # the 2015-16 lines
    if len(nums) == 1:  # a row with an installed MW and no MEC (Boggeragh 2 / Killavoy, DG200)
        nums.append("")
    elif len(nums) != 2:
        return None
    before = tokens[:at]
    if before and re.fullmatch(r"\d+[a-z]?", before[-1]):
        before = before[:-1]  # the phase
    name = re.sub(r"\s*\(\d+\)[a-z]?$", "", " ".join(before))
    return ConnectedRow(ref, name, Decimal(nums[1]) if nums[1] else None, Decimal(nums[0]),
                        _month(" ".join(tokens[at + 3:])), None, "Wind", line)


def _printed_wind_totals(text: str) -> list[Decimal]:
    """The wind MW the list prints: 'Total MW <a> <b>' (the MEC and installed totals, in
    an order that differs between editions: the Dec 2016 list prints 1222.555 1165.65,
    the May 2017 one has the installed total first), or else the installed wind of the
    latest row of its monthly table ('Nov-2016 212.18 1165.65 1377.83', or
    'Nov 212.18 1441.5 1653.68 - - -': hydro, wind, total)."""
    if (m := re.search(r"^Total MW ([\d.,]+) ([\d.,]+)", text, re.MULTILINE)):
        return [Decimal(m.group(1).replace(",", "")), Decimal(m.group(2).replace(",", ""))]
    rows = re.findall(r"^(?:\d{4} )?(?:[A-Z][a-z]{2}(?:-\d{4})?) ([\d.]+) ([\d.]+) ([\d.]+)\b",
                      text, re.MULTILINE)
    return [Decimal(rows[-1][1])] if rows else []


def read(content: bytes) -> tuple[list[ConnectedRow], dict]:
    """Rows and what the gate found. Raises ConnectedParseError when the gate fails."""
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    rows: list[ConnectedRow] = []
    numbering: list[int] = []
    for text in pages:
        for line in text.splitlines():
            if (r := parse_line(line.strip())) is not None:
                rows.append(r)
                if r.full is not None:
                    numbering.append(int(line.split()[0]))
    text = "\n".join(pages)
    at_row = set()
    for line in text.splitlines():
        toks = line.split()
        if toks and (toks[0].isdigit() or any(REF.match(t) for t in toks[:6])):
            at_row |= {t.rstrip(".") for t in toks[:8] if REF.match(t)}
    read_refs = {r.ref for r in rows}
    problems = []
    if missed := sorted(at_row - read_refs):
        problems.append(f"refs at a row's position not read: {missed[:6]}")
    # table numbering: 1..N within each section, restarting at 1
    sections, prev = [], 0
    for n in numbering:
        if n == 1 or n != prev + 1:
            sections.append([])
        sections[-1].append(n) if sections else None
        prev = n
    gaps = [s for s in sections if s != list(range(1, len(s) + 1))]
    if gaps:
        problems.append(f"table numbering has gaps in {len(gaps)} section(s)")
    # the wind-only lists (2016-17) say "Onshore" in the type column, the renewables list "Wind"
    wind_rows = [r for r in rows if r.kind in WIND_KINDS]
    wind = sum((r.installed_mw or 0 for r in wind_rows), Decimal(0))
    mec = sum((r.mec_mw or 0 for r in wind_rows), Decimal(0))
    printed = _printed_wind_totals(text)
    if len(printed) == 2:  # both totals, in either order
        ok = any(abs(wind - a) <= TIE_MW and abs(mec - b) <= TIE_MW
                 for a, b in (printed, printed[::-1]))
        if not ok:
            problems.append(f"installed {wind} and MEC {mec} MW against printed {printed}")
    elif printed and abs(wind - printed[0]) > TIE_MW:
        problems.append(f"installed wind {wind} MW against a printed {printed[0]} MW")
    found = {"rows": len(rows), "refs": len(read_refs), "wind_installed_mw": wind,
             "wind_mec_mw": mec, "printed_wind_mw": printed}
    if not rows:
        problems.append("no rows read")
    if problems:
        raise ConnectedParseError("; ".join(problems))
    return rows, found


def editions(con) -> list[tuple[int, str, date, str]]:
    return con.execute(f"""
        select publication_id, source_id, as_of, raw_path from publication
        where source_id in ({", ".join(repr(s) for s in SOURCES)}) order by as_of
    """).fetchall()


assert parse.TIE_MW == TIE_MW  # the same tie as the contracted lists


def load(con, now) -> tuple[int, list[str]]:
    """Read every connected edition not yet loaded; one that fails its gate is reported
    and stored as nothing. Returns (editions loaded, problems)."""
    from iegrid import store

    done = {r[0] for r in con.execute("select distinct publication_id from connected_row").fetchall()}
    loaded, problems = 0, []
    for pid, sid, as_of, raw in editions(con):
        if pid in done:
            continue
        try:
            rows, _ = read((store.ROOT / raw).read_bytes())
        except ConnectedParseError as exc:
            problems.append(f"{sid} {as_of}: {exc}")
            continue
        con.executemany(
            "insert into connected_row values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [[pid, i, r.ref, r.name, r.mec_mw, r.installed_mw, r.connected, r.full, r.kind,
              r.line, now] for i, r in enumerate(rows, 1)])
        loaded += 1
    return loaded, problems


# --- what became of a project that left the contracted list -------------------------

COVER_END = date(2022, 10, 1)   # the newest connected edition the archive has
GRACE_DAYS = 183                # left within this of the cover's end: too late to say

CONNECTED = "connected"                     # its ref is on a TSO connected list
DSO_CONNECTED = "connected on the distribution grid"  # its ref is on an ESB energised list
SIBLING = "connected as part of a sibling"  # its name is a connected project's; its ref isn't
REFUSED = "not connected: planning refused (sourced)"        # a source says it was refused
REORGANISED = "reorganised into a project that connected (sourced)"  # parts add back, one connected
NOT_LISTED = "not on a connected list"      # wind, left in time, not found by ref or name
UNKNOWN = "unknown"                         # the lists can't say (see Outcome.why)


@dataclass(frozen=True)
class History:
    """A ref across the connected editions: every name it has had (the 2015 lines say
    "Garvagh - Glebe (1a)", the 2017+ table "Garvagh"), the first edition that lists it,
    and its newest row."""
    ref: str
    names: frozenset[str]
    first_listed: date
    row: ConnectedRow


@dataclass(frozen=True)
class Outcome:
    ref: str
    name: str
    mw: Decimal
    source_id: str
    left_on: date
    outcome: str
    why: str
    first_listed: date | None = None      # the first connected edition with it: first energisation
    connected_month: date | None = None   # its newest row's month: completion, if Full
    connected_ref: str | None = None


def classify(left, history: dict[str, History], cover_end: date = COVER_END,
             first_contracted: dict[str, date] | None = None,
             dso_energised: dict[str, tuple[str, date | None]] | None = None,
             resolutions: dict[str, dict[str, str]] | None = None) -> list[Outcome]:
    """left: flows.Flow 'left' events, already reduced to each ref's final leave.
    connected: {ref: its row on the newest connected edition that lists it}.

    Rules, each from something the g-layer review found in the data:
      * a connected list only covers wind (the non-wind ones print no refs), so only a
        wind project can be 'not on a connected list';
      * a project that left less than GRACE_DAYS before the cover ends may simply not
        have connected yet: unknown;
      * a TSO-referenced project can end up on the distribution grid (DG217, "Cloghboola
        (2) Ext", is ESB's "Glantaunyalkeen Windfarm", energised Sep 2018): a ref on an
        ESB energised list is DSO_CONNECTED, ranked above the name rule, which had called
        it a phase of Cloghboola;
      * a ref on a connected list before any contracted list has it was reused for a
        different project (TG22a: Athea, connected 2013, contracted again from 2020), so
        its connected listing says nothing about this one: unknown;
      * phases connect under a sibling's ref (Athea 1b/2/3/4 into TG22a), so a
        project whose name key is a connected project's is SIBLING, not NOT_LISTED."""
    from iegrid import region

    by_key: dict[tuple[str, ...], set[str]] = {}
    for h in history.values():
        for n in h.names:
            if k := region.key(n):
                by_key.setdefault(k, set()).add(h.ref)
    out = []
    for f in left:
        wind = f.source_id.endswith("_wind")
        if (h := history.get(f.ref)) is not None:
            if first_contracted and h.first_listed < first_contracted.get(f.ref, date.min):
                out.append(Outcome(f.ref, f.name, f.mw, f.source_id, f.as_of, UNKNOWN,
                                   "ref reused: on a connected list before any contracted "
                                   f"list has it (connected from {h.first_listed}, first "
                                   f"contracted {first_contracted[f.ref]})",
                                   h.first_listed, h.row.connected, h.ref))
                continue
            out.append(Outcome(f.ref, f.name, f.mw, f.source_id, f.as_of, CONNECTED, "by ref",
                               h.first_listed, h.row.connected, h.ref))
        elif dso_energised and f.ref in dso_energised:
            name, on = dso_energised[f.ref]
            out.append(Outcome(f.ref, f.name, f.mw, f.source_id, f.as_of, DSO_CONNECTED,
                               f"on ESB's energised list as {name!r}", on, on))
        elif resolutions and f.ref in resolutions:
            r = resolutions[f.ref]
            out.append(Outcome(f.ref, f.name, f.mw, f.source_id, f.as_of,
                               REFUSED if r["verdict"] == "refused" else REORGANISED,
                               f"sourced: {r['source_name']}"))
        elif wind and region.key(f.name) and len(sib := by_key.get(region.key(f.name), ())) == 1:
            h = history[next(iter(sib))]
            out.append(Outcome(f.ref, f.name, f.mw, f.source_id, f.as_of, SIBLING,
                               f"same name as {h.ref}", h.first_listed, h.row.connected, h.ref))
        elif not wind:
            out.append(Outcome(f.ref, f.name, f.mw, f.source_id, f.as_of, UNKNOWN,
                               "non-wind: the connected lists print no refs"))
        elif (cover_end - f.as_of).days < GRACE_DAYS:
            out.append(Outcome(f.ref, f.name, f.mw, f.source_id, f.as_of, UNKNOWN,
                               "left too near the end of the connected lists"))
        else:
            out.append(Outcome(f.ref, f.name, f.mw, f.source_id, f.as_of, NOT_LISTED,
                               "no ref or name match on any connected edition"))
    return out


def final_leavers(con):
    """Each ref's last 'left' flow, for refs not on a newest contracted edition (a ref
    that left and came back is not a leaver, and flows reports its first leave too)."""
    from iegrid import flows

    newest = {sid: eds[-1][1] for sid, eds in flows.editions(con).items()}
    now_listed = {r for e in newest.values() for r in e}
    last: dict[str, flows.Flow] = {}
    for f in flows.flows(con):
        if f.kind == "left":
            last[f.ref] = f
    return sorted((f for r, f in last.items() if r not in now_listed),
                  key=lambda f: (f.as_of, f.ref))


def connected_history(con) -> dict[str, History]:
    rows = con.execute("""
        select c.project_ref, c.name, c.mec_mw, c.installed_mw, c.connected_month,
               c.full_connection, c.kind, c.raw, p.as_of
        from connected_row c join publication p using (publication_id)
        order by p.as_of, p.published_at, c.row_order
    """).fetchall()
    names: dict[str, set[str]] = {}
    first: dict[str, date] = {}
    newest: dict[str, ConnectedRow] = {}
    for ref, name, mec, inst, month, full, kind, raw, as_of in rows:
        names.setdefault(ref, set()).add(name)
        first.setdefault(ref, as_of)
        newest[ref] = ConnectedRow(ref, name, mec, inst, month, full, kind, raw)
    return {ref: History(ref, frozenset(names[ref]), first[ref], newest[ref]) for ref in newest}


def first_contracted(con) -> dict[str, date]:
    from iegrid import flows

    first: dict[str, date] = {}
    for eds in flows.editions(con).values():
        for as_of, e in eds:
            for ref in e:
                first[ref] = min(first.get(ref, as_of), as_of)
    return first


def dso_energised(con) -> dict[str, tuple[str, date | None]]:
    """{ref: (name, energised on)} over every ESB energised edition (a project may have
    been listed in an older one only)."""
    from iegrid import parse

    out: dict[str, tuple[str, date | None]] = {}
    for ref, name, on in con.execute(f"""
            select r.project_ref, r.name, r.energised_on
            from project_row r join publication p using (publication_id)
            where p.source_id like 'esb.dso_energised%'
              and r.parser_version = {int(parse.PARSER_VERSION)}
            order by p.as_of, p.published_at""").fetchall():
        out[ref] = (name, on)
    return out


def outcomes(con) -> list[Outcome]:
    from iegrid import resolutions

    return classify(final_leavers(con), connected_history(con),
                    first_contracted=first_contracted(con), dso_energised=dso_energised(con),
                    resolutions=resolutions.for_leavers())


def main(argv: list[str] | None = None) -> int:
    """Read the archived connected editions into connected_row (once; re-runs add nothing)."""
    import argparse
    from datetime import UTC, datetime

    from iegrid import store

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--db", default=str(store.DEFAULT_DB))
    args = parser.parse_args(argv)
    con = store.connect(args.db)
    try:
        loaded, problems = load(con, datetime.now(UTC))
    finally:
        con.close()
    print(f"connected editions loaded: {loaded}")
    for p in problems:
        print(f"  refused: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
