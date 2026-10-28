"""g5: how long it takes. Metrics over the stored history, nothing new stored.

    batch_dates        when each ECP batch's results were first published: the earliest
                       results file of that batch the store holds (g4's ecp_file)
    dso_burndown       per batch, distribution MW energised (ESB's energised lists give
                       the date) against MW still contracted, from the newest editions
    tso_waiting        per batch, how long the transmission projects still contracted
                       have waited, from the earliest signed month any edition gives
                       (a list's own signed month is the latest contract affecting the
                       capacity, so a relocated project would look new)
    transitions        joins and leaves between the two newest editions of each EirGrid
                       list, each confirmed against the PDFs' own text

Withdrawn projects are in no list, so a batch's share energised is of the projects still
in one: energised / (energised + still contracted).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import median

from iegrid import parse


def batch_of(text: str) -> str | None:
    """'2020-batch-(ecp-2.1)-results...' -> 'ECP-2.1'; 'ECP-2.2 - Non-Batch' -> 'ECP-2.2';
    'ECP-1' -> 'ECP-1'; 'sept-2025-batch-ecp-gss-1' -> 'GSS-1'. Non-batch offers are
    their batch's: they were processed alongside it."""
    t = text.lower()
    if m := re.search(r"gss-?(\d)", t):
        return f"GSS-{m.group(1)}"
    if m := re.search(r"ecp-?(\d)[-.](\d)(?:[-.](\d))?", t):
        return f"ECP-{m.group(1)}.{m.group(2)}" + (f".{m.group(3)}" if m.group(3) else "")
    if re.search(r"ecp-?1\b", t):
        return "ECP-1"
    return None


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
NAME_MONTH = re.compile(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-_]?(20\d{2})")


def _name_month(name: str) -> date | None:
    """'...joint-so-publication_nov2018' and '...-january-2021' -> the first of that month."""
    m = NAME_MONTH.search(name.lower())
    return date(int(m.group(2)), MONTHS[m.group(1)], 1) if m else None


def batch_dates(con) -> dict[str, date]:
    """The earliest results publication per batch: the month in its file name, else the
    archive capture date (an upper bound)."""
    out: dict[str, date] = {}
    for name, ts in con.execute("select file_name, capture_ts from ecp_file").fetchall():
        b = batch_of(name)
        if b is None or b.count(".") > 1:  # ECP-2.5.1 is ECP-2.5's second round
            continue
        d = _name_month(name)
        if d is None and ts[:1].isdigit():
            d = date(int(ts[:4]), int(ts[4:6]), 1)
        if d is not None and (b not in out or d < out[b]):
            out[b] = d
    return dict(sorted(out.items()))


def route(processing_type: str) -> str:
    """The batch, or for projects outside the ECP batches how they were processed."""
    if (b := batch_of(processing_type)) is not None:
        return b
    t = processing_type.strip()
    for pattern, label in ((r"(post |pre-)?gate\s*(\d)", None), (r"non gpa", "Non GPA"),
                           (r"t-(\d)", None), (r"pci", "PCI"), (r"lcis", "LCIS"),
                           (r"teg", "TEG"), (r"demand", "Demand")):
        if m := re.search(pattern, t, re.IGNORECASE):
            if label:
                return label
            if pattern.startswith("t-"):
                return f"T-{m.group(1)} capacity auction"
            return f"Gate {m.group(2)}"
    return "other"


def _latest(con, sources: tuple[str, ...]) -> list[int]:
    return [r[0] for r in con.execute(f"""
        select arg_max(p.publication_id, (p.as_of, p.published_at))
        from publication p join parse_result r using (publication_id)
        where r.parser_version = {int(parse.PARSER_VERSION)}
          and p.source_id in ({", ".join(repr(s) for s in sources)})
        group by p.source_id
    """).fetchall()]


@dataclass(frozen=True)
class Burndown:
    batch: str
    result: date
    energised_mw: Decimal
    contracted_mw: Decimal
    energised_n: int
    contracted_n: int
    median_months_to_energise: float | None

    @property
    def share(self) -> float:
        total = self.energised_mw + self.contracted_mw
        return float(self.energised_mw / total) if total else 0.0


def _months(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def dso_burndown(con) -> list[Burndown]:
    dates = batch_dates(con)
    pubs = {
        "energised": _latest(con, ("esb.dso_energised_renewable", "esb.dso_energised_nonrenewable")),
        "contracted": _latest(con, ("esb.dso_contracted_renewable",
                                    "esb.dso_contracted_nonrenewable")),
    }
    mw: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    n: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    waits: dict[str, list[int]] = defaultdict(list)
    for kind, ids in pubs.items():
        rows = con.execute(f"""
            select processing_type, mec_mw, energised_on from project_row
            where parser_version = {int(parse.PARSER_VERSION)}
              and publication_id in ({", ".join(str(i) for i in ids) or "null"})
        """).fetchall()
        for ptype, m, energised_on in rows:
            b = batch_of(ptype or "")
            if b is None or b not in dates:
                continue
            mw[b][kind] += m
            n[b][kind] += 1
            if kind == "energised" and energised_on is not None and energised_on >= dates[b]:
                waits[b].append(_months(dates[b], energised_on))
    out = []
    for b in sorted(mw, key=lambda x: dates[x]):
        out.append(Burndown(b, dates[b], mw[b]["energised"], mw[b]["contracted"],
                            n[b]["energised"], n[b]["contracted"],
                            median(waits[b]) if waits[b] else None))
    return out


@dataclass(frozen=True)
class Waiting:
    batch: str
    projects: int
    mw: Decimal
    median_months: float
    longest_months: int


def tso_waiting(con, today: date | None = None) -> list[Waiting]:
    """Transmission projects in the newest contracted editions, by batch: months since
    the earliest signed month any edition gives them."""
    ids = _latest(con, ("eirgrid.tso_contracted_wind", "eirgrid.tso_contracted_nonwind"))
    as_of = today or con.execute(
        f"select max(as_of) from publication where publication_id in "
        f"({', '.join(str(i) for i in ids)})").fetchone()[0]
    rows = con.execute(f"""
        with first_signed as (
            select r.project_ref, min(r.signed_month) as first
            from project_row r join publication p using (publication_id)
            where r.parser_version = {int(parse.PARSER_VERSION)}
              and p.source_id like 'eirgrid.tso_contracted%' and r.signed_month is not null
            group by 1)
        select r.processing_type, r.mec_mw, f.first
        from project_row r left join first_signed f using (project_ref)
        where r.parser_version = {int(parse.PARSER_VERSION)}
          and r.publication_id in ({", ".join(str(i) for i in ids)})
    """).fetchall()
    by: dict[str, list[tuple[Decimal, int]]] = defaultdict(list)
    for ptype, m, first in rows:
        b = route(ptype or "")
        if first is not None:
            by[b].append((m, _months(first, as_of)))
    return [Waiting(b, len(v), sum((m for m, _ in v), start=Decimal(0)),
                    median(w for _, w in v), max(w for _, w in v))
            for b, v in sorted(by.items(), key=lambda kv: -median(w for _, w in kv[1]))]


@dataclass(frozen=True)
class Transition:
    source_id: str
    before: date
    after: date
    kind: str
    ref: str
    name: str
    mw: Decimal
    confirmed: bool    # the PDFs' own text agrees: the ref is in one and not the other


def _text_refs(con, as_of: date, source_id: str) -> set[str]:
    raw = con.execute("""
        select raw_path from publication where source_id = ? and as_of = ?
        order by published_at desc limit 1
    """, [source_id, as_of]).fetchone()[0]
    from iegrid.store import ROOT

    return parse.text_ref_set((ROOT / raw).read_bytes())


def transitions(con) -> list[Transition]:
    """Joins and leaves between the two newest editions of each EirGrid list."""
    from iegrid import flows

    out = []
    for sid, eds in flows.editions(con).items():
        if len(eds) < 2:
            continue
        (d0, _), (d1, _) = eds[-2], eds[-1]
        t0, t1 = _text_refs(con, d0, sid), _text_refs(con, d1, sid)
        for f in flows.flows(con):
            if f.source_id != sid or f.as_of != d1 or f.kind == "relabel":
                continue
            ok = (f.ref in t1 and f.ref not in t0) if f.kind == "joined" \
                else (f.ref in t0 and f.ref not in t1)
            out.append(Transition(sid, d0, d1, f.kind, f.ref, f.name, f.mw, ok))
    return out

