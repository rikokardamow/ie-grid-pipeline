"""g6: the weekly page. One A4 page and the same content as JSON.

    uv run python -m iegrid.report      # data/reports/<date>.json and <date>.pdf

build() gathers everything into one dict, from queries in the other modules; render()
draws the page from that dict and nothing else, so every number on the page is one a
module computed (the g6 done-when). The JSON is that dict.

Sections, in reading order:
    new          what the publishers put out since the last report (most weeks: nothing)
    queue        contracted GW now, transmission and distribution
    moved        joins and leaves on the EirGrid lists since the edition before, and
                 distribution projects newly energised since ESB's edition before
    stuck        the longest-waiting large transmission projects, and each batch's
                 distribution burn-down at three years
    where        the counties with most capacity waiting (g4)
    caveats      how old the lists are, what the numbers can't show
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from iegrid import parse, store

REPORTS = store.ROOT / "data" / "reports"
LARGE_MW = 50      # "large" for the stuck list
TOP = 6            # rows per list on the page


def _f(x) -> float | None:
    return None if x is None else round(float(x), 2)


def _latest_editions(con) -> dict[str, date]:
    return dict(con.execute("""
        select p.source_id, max(p.as_of) from publication p join parse_result r using (publication_id)
        where r.parser_version = ? group by 1 order by 1
    """, [parse.PARSER_VERSION]).fetchall())


def _new_since(con, since: datetime | None) -> list[dict]:
    if since is None:
        return []
    return [{"source": s, "as_of": str(a), "published": str(p.date())}
            for s, a, p in con.execute("""
                select source_id, as_of, published_at from publication
                where fetched_from is null and ingested_at > ? order by source_id
            """, [since]).fetchall()]


def _queue(con) -> dict:
    rows = con.execute(f"""
        select l.source_id like 'eirgrid%' as tso, sum(r.mec_mw), count(*)
        from project_row r join ({store.LATEST_LIVE}) l using (publication_id)
        where l.source_id like '%contracted%' and r.parser_version = {int(parse.PARSER_VERSION)}
        group by 1
    """).fetchall()
    by = {("transmission" if t else "distribution"): (_f(mw / 1000), n) for t, mw, n in rows}
    return {"transmission_gw": by.get("transmission", (0, 0))[0],
            "transmission_projects": by.get("transmission", (0, 0))[1],
            "distribution_gw": by.get("distribution", (0, 0))[0],
            "distribution_projects": by.get("distribution", (0, 0))[1]}


def _dso_energised_since(con) -> dict:
    """Distribution projects on ESB's newest energised lists that weren't on the edition
    before, with the date ESB gives."""
    eds = con.execute("""
        select p.as_of, list(p.publication_id) from publication p join parse_result r using (publication_id)
        where r.parser_version = ? and p.source_id in
          ('esb.dso_energised_renewable', 'esb.dso_energised_nonrenewable')
        group by 1 order by 1
    """, [parse.PARSER_VERSION]).fetchall()
    if len(eds) < 2:
        return {"before": None, "after": None, "projects": []}
    (d0, p0), (d1, p1) = eds[-2], eds[-1]

    def refs(ids):
        return {r[0]: r[1:] for r in con.execute(f"""
            select project_ref, name, mec_mw, energised_on, technology from project_row
            where parser_version = {int(parse.PARSER_VERSION)}
              and publication_id in ({", ".join(str(i) for i in ids)})
        """).fetchall()}

    before, after = refs(p0), refs(p1)
    new = sorted(((k, *v) for k, v in after.items() if k not in before), key=lambda r: -r[2])
    return {"before": str(d0), "after": str(d1), "count": len(new),
            "mw": _f(sum((r[2] for r in new), start=Decimal(0))),
            "projects": [{"ref": k, "name": n, "mw": _f(m), "energised_on": str(e) if e else None,
                          "technology": t} for k, n, m, e, t in new]}


def _tso_moved(con) -> dict:
    from iegrid import metrics

    tr = metrics.transitions(con)
    joined = sorted((t for t in tr if t.kind == "joined"), key=lambda t: -t.mw)
    left = sorted((t for t in tr if t.kind == "left"), key=lambda t: -t.mw)
    spans = sorted({(t.before, t.after) for t in tr})
    return {"editions": [f"{a} to {b}" for a, b in spans],
            "joined_count": len(joined), "joined_gw": _f(sum(t.mw for t in joined) / 1000),
            "left_count": len(left), "left_gw": _f(sum(t.mw for t in left) / 1000),
            "all_confirmed": all(t.confirmed for t in tr),
            "joined": [{"ref": t.ref, "name": t.name, "mw": _f(t.mw)} for t in joined],
            "left": [{"ref": t.ref, "name": t.name, "mw": _f(t.mw)} for t in left]}


def _stuck(con) -> dict:
    from iegrid import metrics

    first = metrics.first_signed(con)
    ids = metrics._latest(con, ("eirgrid.tso_contracted_wind", "eirgrid.tso_contracted_nonwind"))
    as_of = con.execute(f"select max(as_of) from publication where publication_id in "
                        f"({', '.join(str(i) for i in ids)})").fetchone()[0]
    rows = con.execute(f"""
        select project_ref, name, mec_mw, processing_type, technology from project_row
        where parser_version = {int(parse.PARSER_VERSION)} and mec_mw >= {LARGE_MW}
          and publication_id in ({", ".join(str(i) for i in ids)})
    """).fetchall()
    waiting = sorted(((metrics._months(first[r[0]], as_of), r) for r in rows if r[0] in first),
                     key=lambda x: (-x[0], -x[1][2]))
    burn = []
    for b in metrics.burndown(con):
        if not b.batch.startswith("ECP"):
            continue
        burn.append({"batch": b.batch, "results": b.result.label(), "age_months": b.age_months,
                     "share_now": _f(b.share), "share_at_3y": _f(b.share_at(36)),
                     "projects": b.energised_n + b.contracted_n})
    return {"as_of": str(as_of),
            "longest_waiting": [{"ref": r[0], "name": r[1], "mw": _f(r[2]),
                                 "route": metrics.route(r[3] or ""), "months": m,
                                 "years_part": m // 12, "months_part": m % 12,
                                 "first_signed": str(first[r[0]])} for m, r in waiting],
            "burndown": burn}


def _where(con) -> dict:
    from iegrid.checks import county_coverage
    from iegrid.store import build_parser_version

    pv = build_parser_version(con)
    cov = county_coverage(con)
    rows = con.execute(f"""
        select c.county, sum(c.mec_mw) from project_county c
        join project_row r on r.publication_id = c.publication_id and r.row_order = c.row_order
         and r.parser_version = {pv}
        where c.build_id = ? and c.county is not null and r.technology <> 'Interconnector'
        group by 1 order by 2 desc
    """, [cov.build_id]).fetchall()
    return {"placed_share": _f(cov.share),
            "counties": [{"county": c, "gw": _f(m / 1000)} for c, m in rows]}


def _caveats(con, editions: dict[str, date]) -> list[str]:
    tso = min(d for s, d in editions.items() if s.startswith("eirgrid.tso_contracted"))
    dso = min(d for s, d in editions.items() if s.startswith("esb.dso_"))
    return [
        (f"Lists as of {tso:%-d %b %Y} (transmission) and {dso:%-d %b %Y} (distribution); "
         f"ESB posts its lists about a month after their as-of date."),
        "'Left' a list means connected, withdrawn or moved: the contracted lists don't say which.",
        "Burn-down shares are of projects still on a list; withdrawn projects are on neither.",
        "Distribution burn-down only: transmission energisations need EirGrid's connected lists.",
        "Waiting time runs from a project's earliest signed month in the lists since 2015.",
        "Republication terms of the source lists are not yet checked.",
    ]


def build(con, now: datetime | None = None, last_report: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    editions = _latest_editions(con)
    return {
        "report_date": str(now.date()),
        "editions": {s: str(d) for s, d in editions.items()},
        "new": _new_since(con, last_report),
        "queue": _queue(con),
        "moved": {"transmission": _tso_moved(con), "distribution": _dso_energised_since(con)},
        "stuck": _stuck(con),
        "where": _where(con),
        "caveats": _caveats(con, editions),
    }


# --- the page ------------------------------------------------------------------------

def render(rep: dict, path: Path) -> Path:
    """One A4 page from the report dict alone."""
    import matplotlib.pyplot as plt

    from iegrid.exhibits import TOKENS

    fig = plt.figure(figsize=(8.27, 11.69), dpi=150)
    fig.patch.set_facecolor(TOKENS["bg"])
    y = 0.965

    def text(s, size=9, weight="normal", color=TOKENS["text"], x=0.06, dy=0.019):
        nonlocal y
        fig.text(x, y, s, fontsize=size, weight=weight, color=color, va="top")
        y -= dy

    def head(s):
        nonlocal y
        y -= 0.008
        text(s, size=10.5, weight="bold", dy=0.022)

    q, tso, dso = rep["queue"], rep["moved"]["transmission"], rep["moved"]["distribution"]
    text("Irish grid connection queue · weekly status", size=15, weight="bold", dy=0.03)
    text(f"Report {rep['report_date']}", color=TOKENS["muted"], dy=0.024)
    new = rep["new"]
    text(("New this week: " + "; ".join(f"{n['source']} as of {n['as_of']}" for n in new))
         if new else "New this week: no new list published; figures as last week.",
         color=TOKENS["muted"], dy=0.028)

    head("Waiting to connect")
    text(f"{q['transmission_gw']:.1f} GW on transmission ({q['transmission_projects']} projects) · "
         f"{q['distribution_gw']:.1f} GW on distribution ({q['distribution_projects']} projects)")

    head(f"What moved · transmission, {', '.join(tso['editions'])}")
    text(f"{tso['joined_count']} joined ({tso['joined_gw']:.2f} GW) · {tso['left_count']} left "
         f"({tso['left_gw']:.2f} GW)" + ("" if tso["all_confirmed"] else
                                         " · NOT ALL CONFIRMED against the PDFs"))
    for j in tso["joined"][:TOP]:
        text(f"+ {j['name'][:58]}  {j['mw']:.0f} MW", x=0.08, dy=0.017)
    for j in tso["left"][:3]:
        text(f"– {j['name'][:58]}  {j['mw']:.0f} MW", x=0.08, color=TOKENS["muted"], dy=0.017)
    head(f"What moved · distribution energised, {dso['before']} to {dso['after']}")
    text(f"{dso['count']} projects ({dso['mw']:.1f} MW) newly on ESB's energised lists")
    for p in dso["projects"][:4]:
        when = p["energised_on"] or "date not given"
        text(f"+ {p['name'][:50]}  {p['mw']:.1f} MW · energised {when}", x=0.08, dy=0.017)

    st = rep["stuck"]
    head(f"What's stuck · large transmission projects waiting longest (as of {st['as_of']})")
    for w in st["longest_waiting"][:TOP]:
        text(f"{w['name'][:44]}  {w['mw']:.0f} MW · {w['route']} · "
             f"{w['years_part']} y {w['months_part']} m since {w['first_signed'][:7]}",
             x=0.08, dy=0.017)

    head("Distribution burn-down · share of each batch's MW energised")
    ax = fig.add_axes([0.25, y - 0.15, 0.68, 0.14])
    bd = [b for b in st["burndown"]]
    ys = list(range(len(bd)))
    ax.barh(ys, [100 * (b["share_now"] or 0) for b in bd], height=0.55, color=TOKENS["series3"])
    ax.barh(ys, [100 * (b["share_at_3y"] or 0) for b in bd], height=0.55, color=TOKENS["series1"])
    for yi, b in zip(ys, bd, strict=True):
        at3 = "–" if b["share_at_3y"] is None else f"{b['share_at_3y']:.0%}"
        ax.text(100 * (b["share_now"] or 0) + 1, yi,
                f"now {b['share_now']:.0%} · at 3 years {at3}", va="center", fontsize=7.5,
                color=TOKENS["text"])
    ax.set_yticks(ys, [f"{b['batch']} ({b['results']})" for b in bd], fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.tick_params(labelsize=7, colors=TOKENS["muted"], length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(TOKENS["border"])
    y -= 0.165

    wh = rep["where"]
    head(f"Where · counties with most generation waiting ({wh['placed_share']:.0%} placed)")
    text("  ·  ".join(f"{c['county']} {c['gw']:.1f} GW" for c in wh["counties"][:TOP]), x=0.08)

    head("Read with care")
    for c in rep["caveats"]:
        text(f"· {c}", size=7.5, color=TOKENS["muted"], dy=0.015)
    fig.text(0.06, 0.022, "Sources: EirGrid contracted generator lists; ESB Networks DSO lists; ECP "
             "batch results publications.\nEvery number on this page is computed by iegrid.report "
             "from the stored lists; the same content is in the JSON beside it.", fontsize=6.5,
             color=TOKENS["muted"], linespacing=1.4)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def last_report_time(out_dir: Path = REPORTS) -> datetime | None:
    reports = sorted(out_dir.glob("*.json"))
    if not reports:
        return None
    return datetime.fromisoformat(json.loads(reports[-1].read_text())["generated_at"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(REPORTS))
    args = parser.parse_args(argv)
    out = Path(args.out)
    now = datetime.now(UTC)
    con = store.connect_read_only()
    rep = build(con, now, last_report_time(out))
    rep["generated_at"] = now.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{rep['report_date']}.json").write_text(json.dumps(rep, indent=2))
    render(rep, out / f"{rep['report_date']}.pdf")
    print(f"report: {out / rep['report_date']}.json and .pdf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
