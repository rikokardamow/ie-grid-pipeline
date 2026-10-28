"""Checks the g1 notebook runs on the store. Read only.

The as-of date stored comes from the text inside the PDF. The file name carries
a date too, written by a different hand, so it is an independent check:
    TSO-Contracted-Wind-Report-05-08-2026.pdf        -> 2026-08-05
    ..._summary-report_01jul26.pdf                     -> 2026-07-01
    dso-..._q2_2026.pdf / q2-2026                      -> 2026-07-01 (day after the quarter)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from iegrid.sources import file_name
from iegrid.store import ROOT

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def as_of_from_name(url: str) -> date | None:
    name = file_name(url).lower()
    if m := re.search(r"(\d{2})-(\d{2})-(\d{4})\.pdf$", name):
        d, mo, y = map(int, m.groups())
        return date(y, mo, d)
    if m := re.search(r"_(\d{2})([a-z]{3})(\d{2})\.pdf$", name):
        d, mon, yy = m.groups()
        return date(2000 + int(yy), MONTHS[mon], int(d))
    if m := re.search(r"q([1-4])[_-](\d{4})\.pdf$", name):
        q, y = int(m.group(1)), int(m.group(2))
        return date(y + 1, 1, 1) if q == 4 else date(y, 3 * q + 1, 1)
    return None


@dataclass(frozen=True)
class Check:
    source_id: str
    as_of: date
    as_of_from_name: date | None
    hash_ok: bool
    published_at: datetime
    basis: str

    @property
    def as_of_ok(self) -> bool:
        return self.as_of == self.as_of_from_name


def check_publications(con, archived: bool = False) -> list[Check]:
    """Live editions by default. Archived ones (g3) are checked for their hash too, but
    their file names often carry no date, or a quarter where the text gives a real day
    ("q1-2023" against "Information correct: 20-Apr-23"), so as_of_ok is informative only."""
    where = "is not null" if archived else "is null"
    rows = con.execute(
        "select source_id, url, sha256, raw_path, as_of, published_at, published_at_basis "
        f"from publication where fetched_from {where} order by source_id, as_of"
    ).fetchall()
    out = []
    for source_id, url, sha, raw_path, as_of, published_at, basis in rows:
        path = ROOT / raw_path  # an absolute raw_path stays absolute
        hash_ok = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == sha
        out.append(Check(source_id, as_of, as_of_from_name(url), hash_ok, published_at, basis))
    return out


def table(con, sql: str) -> str:
    """A query as fixed-width text, fully fetched so the connection is free afterwards."""
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = [[("" if v is None else str(v)) for v in r] for r in cur.fetchall()]
    widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c)
              for i, c in enumerate(cols)]

    def line(vals):
        return "  ".join(v.ljust(w) for v, w in zip(vals, widths, strict=True))

    return "\n".join([line(cols), line(["-" * w for w in widths]), *map(line, rows)])


LAG_SQL = """
    select source_id, as_of, published_at::date as published,
           date_diff('day', as_of, published_at::date) as days_after_as_of
    from publication order by source_id, as_of
"""


def publication_lag(con) -> str:
    """How long after its as-of date each list went up (by Last-Modified)."""
    return table(con, LAG_SQL)


# A list ties when its rows match the text count and its MW are within
# parse.TIE_MW of the total it prints (or, for the energised renewable list,
# the summary report).


@dataclass(frozen=True)
class Tie:
    source_id: str
    as_of: date
    rows: int
    text_refs: int
    parsed_mw: Decimal
    against: str
    target_rows: int | None
    target_mw: Decimal | None
    distinct_refs: int | None = None

    @property
    def ok(self) -> bool:
        # EirGrid lists: one ref can carry two rows (a project and its extension, TG44),
        # so the refs are compared as a set, as the load's gate does
        rows = self.distinct_refs if self.source_id.startswith("eirgrid") else self.rows
        if rows != self.text_refs or self.target_mw is None:
            return False
        rows_ok = self.target_rows is None or self.rows == self.target_rows
        from iegrid.parse import TIE_MW

        return rows_ok and abs(self.parsed_mw - self.target_mw) <= TIE_MW


def ties(con) -> list[Tie]:
    """Every parse at the current parser version, against the total it should match."""
    from iegrid import parse

    found = con.execute(
        """
        select p.source_id, p.as_of, r.row_count, r.text_ref_count, r.parsed_total_mw,
               r.printed_total_mw,
               (select count(distinct q.project_ref) from project_row q
                where q.publication_id = r.publication_id and q.parser_version = r.parser_version)
        from parse_result r join publication p using (publication_id)
        where r.parser_version = ?
        order by p.source_id, p.as_of
        """,
        [parse.PARSER_VERSION],
    ).fetchall()
    summaries = {
        as_of: ROOT / raw_path for as_of, raw_path in con.execute(
            "select as_of, raw_path from publication where source_id = 'esb.renewable_summary'"
        ).fetchall()
    }
    out = []
    for source_id, as_of, rows, text_refs, parsed_mw, printed, distinct in found:
        if printed is not None:
            out.append(Tie(source_id, as_of, rows, text_refs, parsed_mw, "printed total",
                           None, printed, distinct))
        elif source_id == "esb.dso_energised_renewable" and as_of in summaries:
            n, total = parse.grid_scale_from_summary(summaries[as_of].read_bytes())
            out.append(Tie(source_id, as_of, rows, text_refs, parsed_mw,
                           "summary report, grid scale", n, total, distinct))
        else:
            out.append(Tie(source_id, as_of, rows, text_refs, parsed_mw, "nothing to tie to",
                           None, None, distinct))
    return out


HAND_COUNT_SQL = """
    select p.source_id, r.page, count(*) as rows_on_page,
           arg_min(r.project_ref, r.row_order) as first_ref,
           arg_max(r.project_ref, r.row_order) as last_ref
    from project_row r join publication p using (publication_id)
    where r.parser_version = {version} and r.page in (
        select distinct page from project_row q
        where q.publication_id = r.publication_id and q.parser_version = r.parser_version
        order by page limit 2)
    group by all order by p.source_id, r.page
"""


def hand_count_pages(con) -> str:
    """The first two pages with rows in each list: rows parsed, first and last ref,
    so the PDF can be counted by eye against it."""
    from iegrid import parse

    return table(con, HAND_COUNT_SQL.format(version=int(parse.PARSER_VERSION)))


def by_technology(con) -> str:
    from iegrid import parse
    from iegrid.store import LATEST_LIVE

    return table(con, f"""
        select l.source_id, r.technology, count(*) as projects,
               sum(r.mec_mw)::decimal(12,1) as mw
        from project_row r join ({LATEST_LIVE}) l using (publication_id)
        where r.parser_version = {int(parse.PARSER_VERSION)}
        group by all order by l.source_id, mw desc
    """)


def unparsed(con) -> list[tuple[str, date]]:
    """Publications of a parsed list with no parse and no recorded failure at the
    current version: a load that wasn't run, or crashed."""
    from iegrid import parse

    sources = list(parse.PARSERS)
    return con.execute(
        f"""
        select p.source_id, p.as_of from publication p
        where p.source_id in ({", ".join("?" * len(sources))})
          and not exists (select 1 from parse_result r where r.publication_id = p.publication_id
                          and r.parser_version = ?)
          and not exists (select 1 from parse_failure f where f.publication_id = p.publication_id
                          and f.parser_version = ?)
        order by 1, 2
        """,
        [*sources, parse.PARSER_VERSION, parse.PARSER_VERSION],
    ).fetchall()


def latest_parsed(con) -> list[str]:
    """Source ids whose newest edition has a parse at the current version."""
    from iegrid import parse

    return [r[0] for r in con.execute(f"""
        with newest as (select source_id, max(as_of) as as_of from publication group by 1)
        select distinct p.source_id from publication p
        join newest n on n.source_id = p.source_id and n.as_of = p.as_of
        join parse_result r on r.publication_id = p.publication_id
        where r.parser_version = {int(parse.PARSER_VERSION)} order by 1
    """).fetchall()]


@dataclass(frozen=True)
class Found:
    source_id: str | None
    outcome: str
    editions: int


def backfill_outcomes(con) -> list[Found]:
    """g3 done-when: every archived edition found, by its latest outcome."""
    rows = con.execute("""
        select source_id, outcome, count(*) from (
            select archive_digest, arg_max(source_id, found_id) as source_id,
                   arg_max(outcome, found_id) as outcome
            from backfill_found group by 1)
        group by all order by 1 nulls last, 2
    """).fetchall()
    return [Found(*r) for r in rows]


def unexplained_editions(con) -> int:
    """Editions found with neither a stored publication nor a written reason."""
    return con.execute("""
        select count(*) from (
            select archive_digest, arg_max(outcome, found_id) as outcome,
                   arg_max(publication_id, found_id) as pid, arg_max(note, found_id) as note
            from backfill_found group by 1)
        where (outcome in ('stored', 'duplicate') and pid is null)
           or (outcome not in ('stored', 'duplicate') and coalesce(note, '') = '')
    """).fetchone()[0]


EDITIONS_SQL = """
    select p.source_id, count(*) as editions, min(p.as_of) as first, max(p.as_of) as last,
           count(r.publication_id) as rows_parsed, count(f.publication_id) as layout_not_read,
           count(t.publication_id) as printed_total
    from publication p
    left join parse_result r on r.publication_id = p.publication_id and r.parser_version = {v}
    left join parse_failure f on f.publication_id = p.publication_id and f.parser_version = {v}
    left join edition_total t on t.publication_id = p.publication_id
    group by 1 order by 1
"""


def editions(con) -> str:
    from iegrid import parse

    return table(con, EDITIONS_SQL.format(v=int(parse.PARSER_VERSION)))


def prefixes_without_editions(con) -> list[str]:
    """Archive prefixes that contributed no edition: an index that was down, or a
    publisher that moved. backfill_found can't record what the index never listed."""
    from iegrid.sources import ARCHIVE_PREFIXES

    urls = [r[0] for r in con.execute("select original_url from backfill_found").fetchall()]
    return [p for p in ARCHIVE_PREFIXES
            if not any(p.rstrip("*").split("/", 1)[0] in u and
                       p.rstrip("*").split("/", 1)[1] in u for u in urls)]


def recheck_no_as_of(con, cache: Path | None = None) -> list[str]:
    """Re-read every 'no-as-of' edition from the archive cache with today's reader.
    A reason that no longer holds (the reader now finds a date) is listed."""
    from iegrid import asof, backfill
    from iegrid.sources import normalised_name

    cache = cache or backfill.CACHE
    rows = con.execute("""
        select archive_digest, arg_max(original_url, found_id), arg_max(outcome, found_id)
        from backfill_found group by 1
    """).fetchall()
    stale = []
    for digest, url, outcome in rows:
        if outcome != "no-as-of":
            continue
        path = cache / f"{digest}.pdf"
        if not path.exists():
            stale.append(f"{digest}: not in the cache")
            continue
        try:
            got = asof.as_of_from_pdf(path.read_bytes(), asof.date_in_name(normalised_name(url)))
        except asof.AsOfConflict:
            continue  # still refused, for a reason that still holds
        except Exception:  # noqa: BLE001, S112 - still unreadable, so the reason holds
            continue
        if got is not None:
            stale.append(f"{normalised_name(url)}: the reader now finds {got}")
    return stale


def same_as_of_pairs(con) -> str:
    """Two different files of one list with the same as-of: re-issues, or a misdated file."""
    return table(con, """
        select source_id, as_of, count(*) as files,
               string_agg(right(url, 45), ' | ') as names
        from publication group by 1, 2 having count(*) > 1 order by 1, 2
    """)


def reupload_lag(con) -> str:
    """Archived editions whose Last-Modified is over a year after the as-of: the file was
    re-uploaded (EirGrid moved its library around 2015), so publication time is unknown."""
    return table(con, """
        select source_id, count(*) as editions,
               min(date_diff('day', as_of, published_at::date)) as min_days,
               max(date_diff('day', as_of, published_at::date)) as max_days
        from publication
        where fetched_from is not null and date_diff('day', as_of, published_at::date) > 365
        group by 1 order by 1
    """)


@dataclass(frozen=True)
class Coverage:
    build_id: int
    total_mw: Decimal
    placed_mw: Decimal
    by_basis: dict[str, Decimal]

    @property
    def share(self) -> float:
        return float(self.placed_mw / self.total_mw)


def contested_mw(con) -> Decimal:
    return sum((Decimal(str(r[2])) for r in name_vs_node(con)), start=Decimal(0))


def county_coverage(con) -> Coverage:
    """g4 done-when: the share of the newest contracted MW that has a county."""
    build = con.execute("select max(build_id) from region_build").fetchone()[0]
    rows = con.execute("select basis, sum(mec_mw) from project_county where build_id = ? "
                       "group by 1", [build]).fetchall()
    by = {b: mw for b, mw in rows}
    total = sum(by.values())
    return Coverage(build, total, total - by.get("none", Decimal(0)), by)


def unplaced(con) -> str:
    """The rest, listed by name (g4 done-when)."""
    from iegrid.store import build_parser_version

    pv = build_parser_version(con)
    return table(con, f"""
        select c.project_ref, r.name, c.mec_mw, r.node, r.station_110kv
        from project_county c
        join project_row r on r.publication_id = c.publication_id and r.row_order = c.row_order
         and r.parser_version = {pv}
        where c.build_id = (select max(build_id) from region_build) and c.basis = 'none'
        order by c.mec_mw desc
    """)


def county_sample(con, n: int = 12) -> str:
    """A sample of placed projects with the evidence, largest first, for a hand check."""
    from iegrid.store import build_parser_version

    pv = build_parser_version(con)
    return table(con, f"""
        select c.project_ref, r.name, c.mec_mw, c.county, c.basis, c.evidence
        from project_county c
        join project_row r on r.publication_id = c.publication_id and r.row_order = c.row_order
         and r.parser_version = {pv}
        where c.build_id = (select max(build_id) from region_build) and c.basis <> 'none'
        order by c.mec_mw desc limit {int(n)}
    """)


def name_vs_node(con, min_share: float = 0.75, min_projects: int = 2) -> list[tuple]:
    """Name placements whose listed connection node clearly votes for another county
    (2+ distinct ECP projects at that node, 75% in one county): a misread ECP row, two
    projects sharing a name, or a project that moved its connection (Kilmorna, printed
    in Kerry, listed at Kinnegad in Westmeath). A different node *name* alone is no
    signal: ECP prints the applicant's assumed node, the list the one agreed.
    Nothing is changed automatically; county_coverage's caller reports their MW."""
    from collections import Counter

    from iegrid import counties, region

    votes: dict[str, Counter] = {}
    seen = set()
    for r in counties.ecp_rows(con):
        if r.node and r.mec_mw is not None and region.key(r.name):
            ident = (region.norm_node(r.node), r.county, round(float(r.mec_mw), 1))
            if ident not in seen:
                seen.add(ident)
                votes.setdefault(ident[0], Counter())[r.county] += 1
    build = con.execute("select max(build_id) from region_build").fetchone()[0]
    from iegrid.store import build_parser_version

    pv = build_parser_version(con, build)
    placed = con.execute(f"""
        select c.project_ref, r.name, c.mec_mw, coalesce(nullif(r.node, ''), r.station_110kv),
               c.county
        from project_county c
        join project_row r on r.publication_id = c.publication_id and r.row_order = c.row_order
         and r.parser_version = {pv}
        where c.build_id = ? and c.basis = 'name' order by c.mec_mw desc
    """, [build]).fetchall()
    out = []
    for ref, name, mw, node, county in placed:
        tally = votes.get(region.norm_node(node or ""))
        if not tally:
            continue
        top, n = tally.most_common(1)[0]
        total = sum(tally.values())
        if top != county and total >= min_projects and n / total >= min_share:
            out.append((ref, name, float(mw), county, node, f"{n} of {total} at {node} in {top}"))
    return out


def tso_history_ties(con) -> list[tuple]:
    """g3b done-when: every EirGrid contracted edition parsed at the current version,
    with its MW against the total it prints. An edition not parsed shows as None."""
    from iegrid import parse

    return con.execute("""
        select p.source_id, p.as_of, r.row_count, r.parsed_total_mw, r.printed_total_mw
        from publication p
        left join parse_result r on r.publication_id = p.publication_id and r.parser_version = ?
        where p.source_id in ('eirgrid.tso_contracted_wind', 'eirgrid.tso_contracted_nonwind')
        order by p.source_id, p.as_of
    """, [parse.PARSER_VERSION]).fetchall()


# A lost column leaves every row of an edition without its signed month (Feb-Mar 2022
# before the g3b review fix). A few blanks are the PDF's own: five rows in 2021-2022
# print no date at all (Celtic Interconnector, Moanvane, Firlough ...).
MAX_BLANK_SIGNED_SHARE = 0.10


def tso_rows_missing_signed(con) -> list[tuple]:
    """EirGrid contracted editions with rows that have no signed month:
    (source, as_of, rows without, rows, refs without)."""
    from iegrid import parse

    return con.execute("""
        select p.source_id, p.as_of, count(*) filter (where r.signed_month is null),
               count(*), list(r.project_ref) filter (where r.signed_month is null)
        from project_row r join publication p using (publication_id)
        where r.parser_version = ?
          and p.source_id in ('eirgrid.tso_contracted_wind', 'eirgrid.tso_contracted_nonwind')
        group by p.source_id, p.as_of, p.publication_id
        having count(*) filter (where r.signed_month is null) > 0
        order by 1, 2
    """, [parse.PARSER_VERSION]).fetchall()


def transitions_table(con, n: int | None = None) -> list[tuple]:
    """g5 done-when: joins and leaves between the two newest editions of each EirGrid
    list, each with whether the PDFs' own text confirms it."""
    from iegrid import metrics

    rows = [(t.source_id.split(".")[1], f"{t.before} -> {t.after}", t.kind, t.ref, t.name[:40],
             float(t.mw), t.confirmed) for t in metrics.transitions(con)]
    return rows[:n] if n else rows
