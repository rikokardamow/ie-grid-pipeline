"""g5: how long it takes. Metrics over the stored history, nothing new stored.

    batch_dates     when each ECP batch's results were first published: the earliest
                    results file of that batch the store holds. A date read only from
                    an archive capture (no month in the file name) is an upper bound,
                    marked as such.
    burndown        per batch, the distribution MW energised by each month after the
                    batch result (ESB's energised lists date each one), against the MW
                    still contracted. Batches are compared at the same age: a young
                    batch can't be judged against an old one's total.
    tso_waiting     per route, how long transmission projects still contracted have
                    waited, from the earliest signed month in the project's history
                    (following relabels, restarting where a ref was reused).
    transitions     joins and leaves between the two newest editions of each EirGrid
                    list, each checked against the PDFs by name as well as by ref.
    region_by_year  contracted MW by county and by the year first signed.
    on_hold         distribution projects ESB lists as On Hold, per edition.

Batch-proper offers only. "Non-Batch" offers (ECP-2.4 - Non-Batch) are processed as
they come, not on the batch results date, so they are left out of a batch's curve.
Withdrawn projects are on no list, so a share energised is of the projects still on
one: energised / (energised + still contracted).
"""

from __future__ import annotations

import io
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import median

import pdfplumber

from iegrid import parse

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
NAME_MONTH = re.compile(
    r"(?<![a-z])(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"(?:uary|ruary|ch|il|e|y|ust|t|tember|ember|ober)?[-_]?(20\d{2})")


def batch_of(text: str) -> str | None:
    """'2020-batch-(ecp-2.1)-results...' -> 'ECP-2.1'; 'ECP 2.3' and 'ECP2.3' too;
    'ECP-1' -> 'ECP-1'; 'sept-2025-batch-ecp-gss-1' -> 'GSS-1'; 'ECP-2.5.1' -> 'ECP-2.5'
    (its second round). A Non-Batch offer is no batch's (see the module note)."""
    t = text.lower()
    if "non-batch" in t or "non batch" in t:
        return None
    if m := re.search(r"gss-?(\d)", t):
        return f"GSS-{m.group(1)}"
    if m := re.search(r"ecp[-\s]?(\d)[-.\s](\d)", t):
        return f"ECP-{m.group(1)}.{m.group(2)}"
    if re.search(r"ecp[-\s]?1\b", t):
        return "ECP-1"
    return None


def _name_month(name: str) -> date | None:
    """'...joint-so-publication_nov2018' and '...-january-2021' -> the first of that month."""
    m = NAME_MONTH.search(name.lower())
    return date(int(m.group(2)), MONTHS[m.group(1)], 1) if m else None


@dataclass(frozen=True)
class BatchDate:
    when: date
    exact: bool   # False: only an archive capture date, so the results were out by then

    def label(self) -> str:
        return f"{self.when:%b %Y}" if self.exact else f"by {self.when:%b %Y}"


def batch_dates(con) -> dict[str, BatchDate]:
    from iegrid import ecp

    out: dict[str, BatchDate] = {}
    rows = con.execute("select file_name, capture_ts from ecp_file where reader_version = ?",
                       [ecp.READER_VERSION]).fetchall()
    for name, ts in rows:
        b = batch_of(name)
        if b is None:
            continue
        d, exact = _name_month(name), True
        if d is None and ts[:1].isdigit():
            d, exact = date(int(ts[:4]), int(ts[4:6]), 1), False
        if d is not None and (b not in out or d < out[b].when):
            out[b] = BatchDate(d, exact)
    return dict(sorted(out.items(), key=lambda kv: kv[1].when))


def route(processing_type: str) -> str:
    """The batch, or for projects outside the ECP batches how they were processed."""
    if (b := batch_of(processing_type)) is not None:
        return b
    t = processing_type.strip()
    if "non-batch" in t.lower():
        return "Non-Batch"
    if m := re.search(r"(?:post |pre-)?gate\s*(\d)", t, re.IGNORECASE):
        return f"Gate {m.group(1)}"
    if m := re.search(r"\bt-(\d)\b", t, re.IGNORECASE):
        return f"T-{m.group(1)} capacity auction"
    if re.search(r"\bt-\s", t, re.IGNORECASE):  # "T- 2027/28": the auction's digit is missing
        return "capacity auction"
    for word, label in (("non gpa", "Non GPA"), ("pci", "PCI"), ("lcis", "LCIS"),
                        ("teg", "TEG"), ("demand", "Demand")):
        if word in t.lower():
            return label
    return "other"


def _latest(con, sources: tuple[str, ...]) -> list[int]:
    return [r[0] for r in con.execute(f"""
        select arg_max(p.publication_id, (p.as_of, p.published_at))
        from publication p join parse_result r using (publication_id)
        where r.parser_version = {int(parse.PARSER_VERSION)}
          and p.source_id in ({", ".join(repr(s) for s in sources)})
        group by p.source_id
    """).fetchall()]


def _months(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


@dataclass(frozen=True)
class Burndown:
    batch: str
    result: BatchDate
    energised_mw: Decimal
    contracted_mw: Decimal
    energised_n: int
    contracted_n: int
    energised_at: tuple[tuple[int, Decimal], ...]   # (months after result, MW), sorted
    age_months: int

    @property
    def total_mw(self) -> Decimal:
        return self.energised_mw + self.contracted_mw

    @property
    def share(self) -> float:
        return float(self.energised_mw / self.total_mw) if self.total_mw else 0.0

    def share_at(self, months: int) -> float | None:
        """Share energised by this many months after the result; None if not yet that old."""
        if months > self.age_months or not self.total_mw:
            return None
        done = sum((mw for m, mw in self.energised_at if m <= months), start=Decimal(0))
        return float(done / self.total_mw)


def latest_dso_as_of(con) -> date:
    return con.execute("""
        select max(p.as_of) from publication p join parse_result r using (publication_id)
        where r.parser_version = ? and p.source_id in
          ('esb.dso_energised_renewable', 'esb.dso_energised_nonrenewable',
           'esb.dso_contracted_renewable', 'esb.dso_contracted_nonrenewable')
    """, [parse.PARSER_VERSION]).fetchone()[0]


def burndown(con, today: date | None = None) -> list[Burndown]:
    dates = batch_dates(con)
    as_of = today or latest_dso_as_of(con)
    pubs = {
        "energised": _latest(con, ("esb.dso_energised_renewable", "esb.dso_energised_nonrenewable")),
        "contracted": _latest(con, ("esb.dso_contracted_renewable",
                                    "esb.dso_contracted_nonrenewable")),
    }
    mw: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    n: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    when: dict[str, list[tuple[int, Decimal]]] = defaultdict(list)
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
            if kind == "energised" and energised_on is not None:
                when[b].append((max(0, _months(dates[b].when, energised_on)), m))
    return [Burndown(b, dates[b], mw[b]["energised"], mw[b]["contracted"], n[b]["energised"],
                     n[b]["contracted"], tuple(sorted(when[b])), _months(dates[b].when, as_of))
            for b in sorted(mw, key=lambda x: dates[x].when)]


@dataclass(frozen=True)
class Waiting:
    route: str
    projects: int
    mw: Decimal
    median_months: float
    longest_months: int


def first_signed(con) -> dict[str, date]:
    """The earliest signed month in each current ref's history: a relabel carries the
    old ref's history over (TG272 -> TG483, Rosspile, 2018), a reused ref starts again
    where it changed project (TG166: Cahernagh to 2018, Kelwin from 2019)."""
    from iegrid import flows

    rows = con.execute(f"""
        select r.project_ref, p.source_id, p.as_of, r.signed_month
        from project_row r join publication p using (publication_id)
        join parse_result x on x.publication_id = r.publication_id
         and x.parser_version = r.parser_version
        where r.parser_version = {int(parse.PARSER_VERSION)}
          and p.source_id like 'eirgrid.tso_contracted%' and r.signed_month is not null
    """).fetchall()
    fl = flows.flows(con)
    left = {(f.source_id, f.ref, f.as_of) for f in fl if f.kind == "left"}
    reuse_from = {(f.source_id, f.ref): f.as_of for f in fl
                  if f.kind == "joined" and (f.source_id, f.ref, f.as_of) in left}
    own: dict[str, date] = {}
    for ref, sid, as_of, signed in rows:
        start = reuse_from.get((sid, ref))
        if start is not None and as_of < start:
            continue  # the ref meant another project then
        if ref not in own or signed < own[ref]:
            own[ref] = signed
    # carry history along relabels, oldest first
    for f in sorted((f for f in fl if f.kind == "relabel"), key=lambda f: f.as_of):
        if f.other_ref in own:
            own[f.ref] = min(own.get(f.ref, own[f.other_ref]), own[f.other_ref])
    return own


def tso_waiting(con, today: date | None = None) -> list[Waiting]:
    ids = _latest(con, ("eirgrid.tso_contracted_wind", "eirgrid.tso_contracted_nonwind"))
    as_of = today or con.execute(
        f"select max(as_of) from publication where publication_id in "
        f"({', '.join(str(i) for i in ids)})").fetchone()[0]
    first = first_signed(con)
    rows = con.execute(f"""
        select project_ref, processing_type, mec_mw from project_row
        where parser_version = {int(parse.PARSER_VERSION)}
          and publication_id in ({", ".join(str(i) for i in ids)})
    """).fetchall()
    by: dict[str, list[tuple[Decimal, int]]] = defaultdict(list)
    for ref, ptype, m in rows:
        if ref in first:
            by[route(ptype or "")].append((m, _months(first[ref], as_of)))
    return [Waiting(r, len(v), sum((m for m, _ in v), start=Decimal(0)),
                    median(w for _, w in v), max(w for _, w in v))
            for r, v in sorted(by.items(), key=lambda kv: -median(w for _, w in kv[1]))]


@dataclass(frozen=True)
class Transition:
    source_id: str
    before: date
    after: date
    kind: str
    ref: str
    name: str
    mw: Decimal
    by_ref: bool    # the ref is in one edition's text and not the other's
    by_name: bool   # the project's name is in one edition's text and not the other's

    @property
    def confirmed(self) -> bool:
        return self.by_ref and self.by_name


def _edition_text(con, as_of: date, source_id: str) -> str:
    from iegrid.store import ROOT

    raw = con.execute("""
        select p.raw_path from publication p join parse_result r using (publication_id)
        where p.source_id = ? and p.as_of = ? and r.parser_version = ?
        order by p.published_at desc limit 1
    """, [source_id, as_of, parse.PARSER_VERSION]).fetchone()[0]
    with pdfplumber.open(io.BytesIO((ROOT / raw).read_bytes())) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _line_refs(line: str) -> set[str]:
    from iegrid.parse_tso_words import BARE_REF

    refs = {r.rstrip(".") for r in parse.TEXT_REF_ANY.findall(line + " ")}
    if not refs and (m := BARE_REF.search(line)):
        refs = {m.group(1)}
    return refs


def _name_lines(name: str, text: str) -> list[set[str]]:
    """For each line (or wrapped pair of lines) holding the name's distinctive words, the
    refs on it. A line with no ref gives an empty set."""
    from iegrid import region

    words = set(region.key(name))
    if not words:
        return []
    lines = text.splitlines()
    toks = [set(re.findall(r"[a-z]+|\d+", ln.lower())) for ln in lines]
    out = []
    for i, t in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else set()
        if words <= t or words <= (t | nxt):
            out.append(_line_refs(lines[i]) | (_line_refs(lines[i + 1])
                                               if i + 1 < len(lines) and not words <= t else set()))
    return out


def _vanished_namesake(name: str, ref: str, other_text: str, persisting: set[str]) -> bool:
    """In the other edition, a line with this project's name that belongs to no project
    present in both editions: the same project under another (or a misprinted) ref."""
    for refs in _name_lines(name, other_text):
        if ref in refs:
            continue
        if not refs or not refs & persisting:
            return True
    return False


def transitions(con) -> list[Transition]:
    """Joins and leaves between the two newest editions of each EirGrid list. Each is
    checked against the PDFs twice: by ref (the same set the load already checks) and by
    name, which no ref pattern touches: a join fails it if the older edition has a line
    with its name that belongs to a project which then vanished (a relabel the flows
    missed, or a ref the list misprinted: TG619 as '19', Sep 2025); a leave, the reverse.
    A namesake that is in both editions (Erkina beside Erkina 2) is another project."""
    from iegrid import flows

    out = []
    for sid, eds in flows.editions(con).items():
        if len(eds) < 2:
            continue
        (d0, _), (d1, _) = eds[-2], eds[-1]
        text0, text1 = _edition_text(con, d0, sid), _edition_text(con, d1, sid)
        t0 = {r for ln in text0.splitlines() for r in _line_refs(ln)}
        t1 = {r for ln in text1.splitlines() for r in _line_refs(ln)}
        persisting = t0 & t1
        fl = [f for f in flows.flows(con) if f.source_id == sid and f.as_of == d1
              and f.kind != "relabel"]
        reused = {f.ref for f in fl if f.kind == "joined"} & {f.ref for f in fl if f.kind == "left"}
        for f in fl:
            if f.ref in reused:  # same ref, a different project: only the names can tell
                by_ref = f.ref in t0 and f.ref in t1
            elif f.kind == "joined":
                by_ref = f.ref in t1 and f.ref not in t0
            else:
                by_ref = f.ref in t0 and f.ref not in t1
            other = text0 if f.kind == "joined" else text1
            by_name = not _vanished_namesake(f.name, f.ref, other, persisting - {f.ref})
            out.append(Transition(sid, d0, d1, f.kind, f.ref, f.name, f.mw, by_ref, by_name))
    return out


def region_by_year(con) -> list[tuple[str, int, Decimal]]:
    """Contracted MW in the newest g4 build by county and by the year first signed
    (transmission: the history's earliest signed month; distribution lists give none,
    so their year is 0, unknown)."""
    from iegrid.store import build_parser_version

    pv = build_parser_version(con)
    first = first_signed(con)
    rows = con.execute(f"""
        select c.county, c.project_ref, c.mec_mw
        from project_county c
        join project_row r on r.publication_id = c.publication_id and r.row_order = c.row_order
         and r.parser_version = {pv}
        where c.build_id = (select max(build_id) from region_build) and c.county is not null
    """).fetchall()
    agg: dict[tuple[str, int], Decimal] = defaultdict(Decimal)
    for county, ref, m in rows:
        agg[(county, first[ref].year if ref in first else 0)] += m
    return sorted((c, y, m) for (c, y), m in agg.items())


def on_hold(con) -> list[tuple[str, date, int, Decimal]]:
    """Distribution projects ESB lists as On Hold (at the customer's request, usually)."""
    return con.execute(f"""
        select p.source_id, p.as_of, count(*), sum(r.mec_mw)
        from project_row r join publication p using (publication_id)
        where r.parser_version = {int(parse.PARSER_VERSION)} and r.status ilike 'on hold%'
        group by all order by 1, 2
    """).fetchall()
