"""g3b: projects joining and leaving the EirGrid contracted lists, edition by edition.

Each list (wind, non-wind) is compared with its own previous edition:

    joined   a ref in this edition that wasn't in the last
    left     a ref in the last edition that isn't in this one (connected, withdrawn or
             moved: the contracted lists don't say which)

with three corrections the g3b review found the lists need:

    relabel  a ref that goes while another with the same name arrives in the same
             edition is the same project (Pollahoney: D74 in Feb 2025, D40d in Sep;
             Timahoe North: TG278 -> P275 -> TG278). Neither a join nor a leave.
    reuse    a ref that stays but changes name and MEC is a different project (TG166:
             Cahernagh OCGT to 2018, Kelwin Phase 2 from 2019): one leave, one join.
    shared   a ref on two rows (a project and its extension, TG44) is one project
             with their MW summed.

The first edition of each list is the starting stock, not a year of joins. Two files
for one list on one date (2020-02-10) are read as one: the one published later.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise

from iegrid import parse, region

SOURCES = ("eirgrid.tso_contracted_wind", "eirgrid.tso_contracted_nonwind")


@dataclass(frozen=True)
class Flow:
    source_id: str
    as_of: date          # the edition it was seen in
    kind: str            # 'joined', 'left' or 'relabel'
    ref: str
    name: str
    mw: Decimal
    other_ref: str = ""  # for a relabel: the ref it had before


def editions(con) -> dict[str, list[tuple[date, dict[str, tuple[str, Decimal]]]]]:
    """Per list, in date order: (as_of, {ref: (name, MW)}), one file per date."""
    rows = con.execute(f"""
        with pick as (
            select p.source_id, p.as_of, arg_max(p.publication_id, p.published_at) as pid
            from publication p join parse_result r using (publication_id)
            where r.parser_version = {int(parse.PARSER_VERSION)}
              and p.source_id in ({", ".join(repr(s) for s in SOURCES)})
            group by 1, 2)
        select k.source_id, k.as_of, r.project_ref, r.name, r.mec_mw
        from pick k join project_row r on r.publication_id = k.pid
         and r.parser_version = {int(parse.PARSER_VERSION)}
        order by 1, 2, r.row_order
    """).fetchall()
    out: dict[str, dict[date, dict[str, tuple[str, Decimal]]]] = defaultdict(dict)
    for sid, as_of, ref, name, mw in rows:
        ed = out[sid].setdefault(as_of, {})
        if ref in ed:  # shared ref: keep the first name, sum the MW
            ed[ref] = (ed[ref][0], ed[ref][1] + mw)
        else:
            ed[ref] = (name, mw)
    return {sid: sorted(eds.items()) for sid, eds in out.items()}


def _same_project(a: tuple[str, Decimal], b: tuple[str, Decimal]) -> bool:
    ka, kb = set(region.key(a[0])), set(region.key(b[0]))
    if not ka or not kb:
        return False
    return ka == kb or (bool(ka & kb) and region.mec_close(a[1], b[1]))


def flows(con) -> list[Flow]:
    out: list[Flow] = []
    for sid, eds in editions(con).items():
        for (_, prev), (as_of, cur) in pairwise(eds):
            gone = {r: v for r, v in prev.items() if r not in cur}
            new = {r: v for r, v in cur.items() if r not in prev}
            for r in set(prev) & set(cur):  # a reused ref: a different project
                if not _same_project(prev[r], cur[r]):
                    gone[r], new[r + "*"] = prev[r], cur[r]
            for g, gv in sorted(gone.items()):
                # when several share the name (TG319 and TG319a, both "Beenanaspock and
                # Tobertooreen"), the closest MEC is the same project
                same = [n for n, nv in sorted(new.items()) if _same_project(gv, nv)]
                match = min(same, key=lambda n: abs(new[n][1] - gv[1])) if same else None
                if match is not None:
                    nv = new.pop(match)
                    out.append(Flow(sid, as_of, "relabel", match.rstrip("*"), nv[0], nv[1], g))
                else:
                    out.append(Flow(sid, as_of, "left", g, gv[0], gv[1]))
            for n, nv in sorted(new.items()):
                out.append(Flow(sid, as_of, "joined", n.rstrip("*"), nv[0], nv[1]))
    return out


def by_year(con) -> dict[int, dict[str, Decimal]]:
    """{year: {'joined': MW, 'left': MW}}."""
    years: dict[int, dict[str, Decimal]] = defaultdict(lambda: {"joined": Decimal(0),
                                                                 "left": Decimal(0)})
    for f in flows(con):
        if f.kind in ("joined", "left"):
            years[f.as_of.year][f.kind] += f.mw
    return dict(sorted(years.items()))
