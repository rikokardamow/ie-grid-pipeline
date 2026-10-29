"""g6: the weekly page. One A4 page and the same content as JSON.

    uv run python -m iegrid.report      # data/reports/<date>T<HHMM>.json and .pdf

build() gathers everything into one dict, from queries in the other modules; render()
draws the page from that dict and nothing else. checks.numbers_not_from_report proves
it: it renders the page again from a copy with every number changed, and any number
that stays the same on both pages didn't come from the report (the g6 done-when).

Sections, in reading order:
    new          lists newer than the ones the last report used (first run: says so)
    queue        contracted GW now, transmission and distribution
    moved        joins and leaves between the last two EirGrid editions, and
                 distribution projects energised since ESB's edition before
    stuck        the longest-waiting large transmission projects, and each batch's
                 distribution burn-down at three years
    where        the counties with most generation waiting (g4)
    caveats      how old the lists are, what the numbers can't show
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from iegrid import parse, store

REPORTS = store.ROOT / "data" / "reports"
LARGE_MW = 50      # "large" for the stuck list
TOP = 6            # rows per list on the page
AT_YEARS = 3       # the burn-down compares batches at this age
REPORT_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{4})?\.json$")

# How each list is named on the page
LIST_NAMES = {
    "eirgrid.tso_contracted_wind": "EirGrid contracted wind",
    "eirgrid.tso_contracted_nonwind": "EirGrid contracted non-wind",
    "esb.dso_contracted_renewable": "ESB contracted renewable",
    "esb.dso_contracted_nonrenewable": "ESB contracted non-renewable",
    "esb.dso_energised_renewable": "ESB energised renewable",
    "esb.dso_energised_nonrenewable": "ESB energised non-renewable",
}


def _f(x, places: int = 3) -> float | None:
    return None if x is None else round(float(x), places)


def _editions(con) -> dict[str, date]:
    """The newest parsed edition of each list the page uses."""
    return dict(con.execute(f"""
        select p.source_id, max(p.as_of) from publication p join parse_result r using (publication_id)
        where r.parser_version = ? and p.source_id in ({", ".join(repr(s) for s in LIST_NAMES)})
        group by 1 order by 1
    """, [parse.PARSER_VERSION]).fetchall())


def _new(editions: dict[str, date], last: dict | None) -> dict:
    """Lists newer than the ones the last report used. On the first run there is no
    last report, and the page says so rather than claiming nothing changed."""
    if last is None:
        return {"first_report": True, "lists": []}
    before = last.get("editions", {})
    return {"first_report": False, "since": last.get("report_date"),
            "lists": [{"list": LIST_NAMES[s], "as_of": str(d)} for s, d in editions.items()
                      if before.get(s) is None or str(d) > before[s]]}


def _queue(con) -> dict:
    """Contracted MW in the newest parsed edition of each list (an edition the load
    refused isn't counted as an empty list: the one before it stands)."""
    from iegrid import metrics

    ids = metrics._latest(con, ("eirgrid.tso_contracted_wind", "eirgrid.tso_contracted_nonwind",
                                "esb.dso_contracted_renewable", "esb.dso_contracted_nonrenewable"))
    rows = con.execute(f"""
        select p.source_id like 'eirgrid%' as tso, coalesce(r.technology, '') = 'Interconnector',
               sum(r.mec_mw), count(*)
        from project_row r join publication p using (publication_id)
        where r.parser_version = {int(parse.PARSER_VERSION)}
          and r.publication_id in ({", ".join(str(i) for i in ids)})
        group by 1, 2
    """).fetchall()
    tso = [(link, mw, n) for t, link, mw, n in rows if t]
    dso = [(link, mw, n) for t, link, mw, n in rows if not t]
    return {"transmission_gw": _f(sum(m for _, m, _ in tso) / 1000),
            "transmission_projects": sum(n for _, _, n in tso),
            "interconnector_gw": _f(sum(m for link, m, _ in tso if link) / 1000),
            "distribution_gw": _f(sum(m for _, m, _ in dso) / 1000),
            "distribution_projects": sum(n for _, _, n in dso)}


def _dso_energised_since(con) -> dict:
    """Distribution projects on ESB's newest energised lists, each list against its own
    edition before. Energised after that edition's as-of: newly energised. Listed for the
    first time but energised earlier (or 'pre 2005'): newly listed, counted apart."""
    out_new, out_listed, spans = [], [], set()
    for sid in ("esb.dso_energised_renewable", "esb.dso_energised_nonrenewable"):
        eds = con.execute("""
            select p.as_of, arg_max(p.publication_id, p.published_at)
            from publication p join parse_result r using (publication_id)
            where r.parser_version = ? and p.source_id = ? group by 1 order by 1
        """, [parse.PARSER_VERSION, sid]).fetchall()
        if len(eds) < 2:
            continue
        (d0, p0), (d1, p1) = eds[-2], eds[-1]
        spans.add((d0, d1))

        def rows(pid):
            return {r[0]: r[1:] for r in con.execute(f"""
                select project_ref, name, mec_mw, energised_on, energised_note from project_row
                where parser_version = {int(parse.PARSER_VERSION)} and publication_id = {pid}
            """).fetchall()}

        before, after = rows(p0), rows(p1)
        for ref, (name, mw, on, note) in after.items():
            if ref in before:
                continue
            item = {"list": LIST_NAMES[sid], "ref": ref, "name": name, "mw": _f(mw),
                    "energised_on": str(on) if on else None, "note": note or None}
            (out_new if on is not None and on > d0 else out_listed).append(item)
    out_new.sort(key=lambda p: -p["mw"])
    return {"editions": [f"{a} to {b}" for a, b in sorted(spans)], "count": len(out_new),
            "mw": _f(sum(p["mw"] for p in out_new)), "projects": out_new,
            "newly_listed_count": len(out_listed), "newly_listed": out_listed}


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
        select project_ref, name, mec_mw, processing_type from project_row
        where parser_version = {int(parse.PARSER_VERSION)} and mec_mw >= {LARGE_MW}
          and publication_id in ({", ".join(str(i) for i in ids)})
    """).fetchall()
    waiting = sorted(((metrics._months(first[r[0]], as_of), r) for r in rows if r[0] in first),
                     key=lambda x: (-x[0], -x[1][2]))
    burn = [b for b in metrics.burndown(con) if b.batch.startswith("ECP")]
    at = AT_YEARS * 12
    old = [b for b in burn if b.age_months >= at]
    return {"as_of": str(as_of), "large_mw": LARGE_MW, "at_years": AT_YEARS,
            "longest_waiting": [{"ref": r[0], "name": r[1], "mw": _f(r[2]),
                                 "route": metrics.route(r[3] or ""), "months": m,
                                 "years_part": m // 12, "months_part": m % 12,
                                 "first_signed": str(first[r[0]])} for m, r in waiting],
            "burndown": [{"batch": b.batch, "results": b.result.label(), "age_months": b.age_months,
                          "share_now": _f(b.share), "share_at": _f(b.share_at(at)),
                          "projects": b.energised_n + b.contracted_n} for b in burn],
            "burndown_first": old[0].batch if old else None,
            "burndown_first_at": _f(old[0].share_at(at)) if old else None,
            "burndown_later_max_at": _f(max(b.share_at(at) for b in old[1:])) if len(old) > 1
            else None}


def _where(con) -> dict:
    from iegrid.checks import county_coverage
    from iegrid.store import build_parser_version

    pv = build_parser_version(con)
    cov = county_coverage(con)
    rows = con.execute(f"""
        select c.county, coalesce(r.technology, '') = 'Interconnector' as link, sum(c.mec_mw)
        from project_county c
        join project_row r on r.publication_id = c.publication_id and r.row_order = c.row_order
         and r.parser_version = {pv}
        where c.build_id = ? group by 1, 2
    """, [cov.build_id]).fetchall()
    gen_total = sum(m for _, link, m in rows if not link)
    gen_placed = sum(m for c, link, m in rows if c and not link)
    by = sorted(((c, m) for c, link, m in rows if c and not link), key=lambda x: -x[1])
    return {"generation_placed_share": _f(gen_placed / gen_total) if gen_total else None,
            "counties": [{"county": c, "gw": _f(m / 1000)} for c, m in by]}


def _caveats(editions: dict[str, date]) -> list[str]:
    tso = min(d for s, d in editions.items() if s.startswith("eirgrid.tso_contracted"))
    dso = min(d for s, d in editions.items() if s.startswith("esb.dso_"))
    return [
        (f"Lists as of {tso:%-d %b %Y} (transmission) and {dso:%-d %b %Y} (distribution); "
         f"ESB posts its lists about a month after their as-of date."),
        "'Left' a list means connected, withdrawn or moved: the contracted lists don't say which.",
        "Burn-down shares are of projects still on a list; withdrawn projects are on neither.",
        "Distribution burn-down only: transmission energisations need EirGrid's connected lists.",
        ("Waiting time runs from the earliest signed month printed for the project in any list "
         "since 2015, carried across relabelled refs (Rosspile: TG272, 2018)."),
        "The transmission total includes interconnectors; the county list leaves them out.",
        ("Not for publication: ESB Networks' terms forbid republishing its lists without "
         "written permission (PARKING.md)."),
    ]


# --- g7b: the earlier stones' exhibits, as data for the dashboard ---------------------

def _freshness(con) -> list[dict]:
    """g1: days from each live list's as-of date to its publication."""
    from iegrid import exhibits

    return [{"list": LIST_NAMES[s], "as_of": str(a), "published": str(p), "days": d}
            for s, a, p, d in exhibits.publication_lags(con) if s in LIST_NAMES]


def _by_technology(con) -> dict:
    """g2: contracted GW by technology group, transmission and distribution."""
    from iegrid import exhibits

    order, groups, as_of = exhibits.technology_groups(con)
    total = sum(sum(v) for v in groups.values())
    side = {k: str(v) if v is not None else None for k, v in as_of.items()}
    return {"transmission_as_of": side.get(True), "distribution_as_of": side.get(False),
            "total_gw": _f(total / 1000),
            "top_share": _f(sum(groups[order[0]]) / total) if total else None,
            "groups": [{"group": g, "transmission_gw": _f(groups[g][0] / 1000),
                        "distribution_gw": _f(groups[g][1] / 1000)} for g in order]}


def _history(con) -> dict:
    """g3: GW printed on every EirGrid contracted edition, and when each batch's results
    came out."""
    from iegrid import exhibits, metrics

    series = exhibits.queue_series(con)
    return {
        "nonwind": [{"as_of": str(d), "gw": _f(gw)} for d, gw in
                    series["eirgrid.tso_contracted_nonwind"]],
        "wind": [{"as_of": str(d), "gw": _f(gw)} for d, gw in
                 series["eirgrid.tso_contracted_wind"]],
        "batches": [{"batch": b, "results": str(d.when), "label": d.label()}
                    for b, d in metrics.batch_dates(con).items() if b.startswith("ECP-2")],
    }


def _by_year(con) -> list[dict]:
    """g3b: GW joining and leaving the transmission lists each year."""
    from iegrid import flows

    return [{"year": y, "joined_gw": _f(v["joined"] / 1000), "left_gw": _f(v["left"] / 1000)}
            for y, v in flows.by_year(con).items()]


OUTLINE = Path(__file__).parent / "data" / "ireland_outline.json"


def _grid(con) -> dict | None:
    """g7b: contracted MW at each substation, the lines, and the coast. None until the
    OpenStreetMap grid is fetched (`python -m iegrid.grid`)."""
    from iegrid import grid

    if not grid.CACHE.exists():
        return None
    out = grid.nodes(con)
    out["outline"] = json.loads(OUTLINE.read_text())["rings"]
    return out


RUNS_SHOWN = 12


def _runs(con) -> dict:
    """g8: the weekly runs logged before this report: totals, and the latest RUNS_SHOWN
    newest first."""
    try:
        total, with_new, failed, first = con.execute("""
            select count(*), count(*) filter (where new_files > 0),
                   count(*) filter (where status = 'failed'), min(started_at)
            from run_log""").fetchone()
        rows = con.execute(f"""
            select run_id, started_at, status, new_files, stored, parsed from run_log
            order by run_id desc limit {RUNS_SHOWN}""").fetchall()
    except Exception:  # noqa: BLE001 - a store from before g8 has no run_log
        return {"count": 0, "with_new_files": 0, "failed": 0, "first": None, "latest": []}
    return {"count": total, "with_new_files": with_new, "failed": failed,
            "first": first.isoformat(timespec="minutes") if first else None,
            "latest": [{"run": r, "started": s.isoformat(timespec="minutes"), "status": st,
                        "new_files": n, "stored": [x for x in stored.split("\n") if x],
                        "parsed": p} for r, s, st, n, stored, p in rows]}


def warnings(con) -> list[str]:
    """A list whose newest edition the load refused: the page shows the edition before."""
    from iegrid import load

    return load.newest_unparsed(con)


def build(con, now: datetime | None = None, last: dict | None = None) -> dict:
    now = now or datetime.now(UTC)
    editions = _editions(con)
    return {
        "report_date": str(now.date()),
        "editions": {s: str(d) for s, d in editions.items()},
        "new": _new(editions, last),
        "warnings": warnings(con),
        "queue": {**_queue(con), "by_technology": _by_technology(con),
                  "history": _history(con)},
        "moved": {"transmission": _tso_moved(con), "distribution": _dso_energised_since(con),
                  "by_year": _by_year(con)},
        "stuck": _stuck(con),
        "where": _where(con),
        "grid": _grid(con),
        "freshness": _freshness(con),
        "runs": _runs(con),
        "caveats": _caveats(editions),
    }


# --- the page ------------------------------------------------------------------------

def render(rep: dict, path: Path) -> Path:
    """One A4 page from the report dict alone."""
    from textwrap import fill

    import matplotlib.pyplot as plt

    from iegrid.exhibits import TOKENS

    fig = plt.figure(figsize=(8.27, 11.69), dpi=150)
    fig.patch.set_facecolor(TOKENS["bg"])
    y = 0.965

    def text(s, size=8.6, weight="normal", color=TOKENS["text"], x=0.06, dy=0.0165, width=110):
        nonlocal y
        lines = fill(s, width).splitlines() or [""]
        for line in lines:
            fig.text(x, y, line, fontsize=size, weight=weight, color=color, va="top")
            y -= dy

    def head(s):
        nonlocal y
        y -= 0.006
        text(s, size=10, weight="bold", dy=0.019, width=95)

    q, tso, dso = rep["queue"], rep["moved"]["transmission"], rep["moved"]["distribution"]
    st = rep["stuck"]
    text("Irish grid connection queue · weekly status", size=15, weight="bold", dy=0.03)
    text(f"Report {rep['report_date']}", color=TOKENS["muted"], dy=0.024)
    new = rep["new"]
    if new["first_report"]:
        line = "First report: no earlier report to compare with."
    elif new["lists"]:
        line = (f"New since the report of {new['since']}: "
                + "; ".join(f"{n['list']} (as of {n['as_of']})" for n in new["lists"]))
    else:
        line = f"No new list since the report of {new['since']}; figures as then."
    text(line, color=TOKENS["muted"], dy=0.018)
    for w in rep["warnings"]:
        text(f"WARNING: {w}", color=TOKENS["text"], weight="bold", dy=0.018)
    y -= 0.008

    head("Waiting to connect")
    text(f"{q['transmission_gw']:.1f} GW on transmission ({q['transmission_projects']} projects, "
         f"{q['interconnector_gw']:.1f} GW of it interconnectors) · {q['distribution_gw']:.1f} GW "
         f"on distribution ({q['distribution_projects']} projects)")

    head(f"What moved · transmission, between the last two editions ({', '.join(tso['editions'])})")
    text(f"{tso['joined_count']} joined ({tso['joined_gw']:.2f} GW) · {tso['left_count']} left "
         f"({tso['left_gw']:.2f} GW)" + ("" if tso["all_confirmed"] else
                                         " · NOT ALL CONFIRMED against the PDFs"))
    for j in tso["joined"][:TOP]:
        text(f"+ {j['name'][:58]}  {j['mw']:.0f} MW", x=0.08, dy=0.0148)
    for j in tso["left"][:3]:
        text(f"– {j['name'][:58]}  {j['mw']:.0f} MW", x=0.08, color=TOKENS["muted"], dy=0.0148)
    head(f"What moved · distribution energised, between the last two editions "
         f"({', '.join(dso['editions'])})")
    text(f"{dso['count']} projects ({dso['mw']:.1f} MW) energised since the edition before"
         + (f"; {dso['newly_listed_count']} more newly listed but energised earlier"
            if dso["newly_listed_count"] else ""))
    for p in dso["projects"][:4]:
        text(f"+ {p['name'][:50]}  {p['mw']:.1f} MW · energised {p['energised_on']}", x=0.08,
             dy=0.0148)

    head(f"What's stuck · transmission projects of {st['large_mw']} MW or more, waiting longest "
         f"(as of {st['as_of']})")
    for w in st["longest_waiting"][:TOP]:
        text(f"{w['name'][:44]}  {w['mw']:.0f} MW · {w['route']} · "
             f"{w['years_part']} y {w['months_part']} m since {w['first_signed'][:7]}",
             x=0.08, dy=0.0148)

    at = st["at_years"]
    if st["burndown_first"]:
        head(f"Distribution burn-down · at {at} years, {st['burndown_first']} had "
             f"{st['burndown_first_at']:.0%} energised, later batches at most "
             f"{st['burndown_later_max_at']:.0%}")
    else:
        head("Distribution burn-down · share of each batch's MW energised")
    ax = fig.add_axes([0.25, y - 0.125, 0.68, 0.115])
    bd = st["burndown"]
    ys = list(range(len(bd)))
    ax.barh(ys, [100 * (b["share_now"] or 0) for b in bd], height=0.55, color=TOKENS["series3"],
            label="now")
    ax.barh(ys, [100 * (b["share_at"] or 0) for b in bd], height=0.55, color=TOKENS["series1"],
            label=f"by {at} years")
    for yi, b in zip(ys, bd, strict=True):
        then = "–" if b["share_at"] is None else f"{b['share_at']:.0%}"
        ax.text(100 * (b["share_now"] or 0) + 1, yi, f"now {b['share_now']:.0%} · at {at} years "
                f"{then}", va="center", fontsize=7.5, color=TOKENS["text"])
    ax.set_yticks(ys, [f"{b['batch']} ({b['results']})" for b in bd], fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.legend(loc="lower right", fontsize=7, frameon=False)
    ax.tick_params(labelsize=7, colors=TOKENS["muted"], length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(TOKENS["border"])
    y -= 0.14

    wh = rep["where"]
    placed = wh["generation_placed_share"]  # None when nothing is placed yet
    head("Where · counties with most generation waiting"
         + (f" ({placed:.0%} of it placed)" if placed is not None else ""))
    text("  ·  ".join(f"{c['county']} {c['gw']:.1f} GW" for c in wh["counties"][:TOP]), x=0.08)

    head("Read with care")
    for c in rep["caveats"]:
        text(f"· {c}", size=7.2, color=TOKENS["muted"], dy=0.0135, width=150)
    if y < 0.05:
        raise ValueError(f"the page overflows into the footer (text ends at {y:.3f}); "
                         f"shorten a list or lower TOP")
    fig.text(0.06, 0.022, "Sources: EirGrid contracted generator lists; ESB Networks DSO lists; ECP "
             "batch results publications; OpenStreetMap and cited planning sources for counties.\n"
             "Every number on this page is computed by iegrid.report from the stored data; the "
             "same content is in the JSON beside it.", fontsize=6.5, color=TOKENS["muted"],
             linespacing=1.4)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def last_report(out_dir: Path = REPORTS) -> dict | None:
    """The newest report written here (only <date>[T<HHMM>].json names count)."""
    reports = sorted(p for p in out_dir.glob("*.json") if REPORT_NAME.match(p.name))
    for p in reversed(reports):
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            continue
    return None


def write(con, out: Path = REPORTS, now: datetime | None = None) -> Path:
    """Build the report against the last one written in out, and write it there as
    <date>T<HHMM>.json and .pdf. Returns the JSON's path."""
    now = now or datetime.now(UTC)
    rep = build(con, now, last_report(out))
    rep["generated_at"] = now.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{now:%Y-%m-%dT%H%M}"  # two runs a day keep both
    (out / f"{stem}.json").write_text(json.dumps(rep, indent=2))
    render(rep, out / f"{stem}.pdf")
    return out / f"{stem}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(REPORTS))
    parser.add_argument("--db", default=None, help="read this store instead of the snapshot")
    args = parser.parse_args(argv)
    con = store.connect_read_only(args.db)
    path = write(con, Path(args.out))
    print(f"report: {path} and .pdf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
