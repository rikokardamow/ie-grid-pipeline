"""One exhibit per stone: what the data that stone added actually says.

Drawn to the record's chart rules (energy-forecasting docs/CHARTS.md): the title
states the finding and is computed from the data, the subtitle gives the units,
and a footer names source, licence and as-of. Colours are the record's tokens
(site/styles/tokens.css), light mode, since the same figure is exported as a PNG.

Each function returns a matplotlib figure: a notebook shows it inline, and
save() writes it to data/exhibits/<name>.png at 1650x840-odd pixels. No backend
is forced here, so Jupyter's inline display works.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import matplotlib.dates
import matplotlib.pyplot as plt

from iegrid import parse, store

TOKENS = {
    "bg": "#FFFFFF", "border": "#DCE3EC", "text": "#0B1F3A", "muted": "#5B6878",
    "series1": "#0F2A4A", "series3": "#7D8996", "accent": "#1F5FBF",
}
LICENCE = "not for publication: ESB Networks' terms (PARKING.md)"

# The lists use about 30 technology labels. These are the groups a reader knows.
TECH_GROUP = {
    "Solar": "Solar",
    "Wind": "Wind",
    "Battery": "Battery storage", "Battery Storage": "Battery storage",
    "Battery + Synchronous Condenser": "Battery storage",
    "Solar + Battery": "Hybrid (with battery)", "Wind + Battery": "Hybrid (with battery)",
    "Wind + Solar": "Hybrid (with battery)",
    "OCGT": "Gas and oil", "CCGT": "Gas and oil", "Gas": "Gas and oil",
    "Gas Fired Reciprocating Engines": "Gas and oil", "Nat. Gas": "Gas and oil",
    "CHP": "Gas and oil", "HVO": "Gas and oil", "Diesel": "Gas and oil", "Rice": "Gas and oil",
    "Interconnector": "Interconnector",
}
OTHER = "Other"


def group(technology: str) -> str:
    return TECH_GROUP.get(technology, OTHER)


def _style(fig, ax) -> None:
    fig.patch.set_facecolor(TOKENS["bg"])
    ax.set_facecolor(TOKENS["bg"])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(TOKENS["border"])
    ax.tick_params(colors=TOKENS["muted"], labelsize=10, length=0)
    ax.grid(axis="x", color=TOKENS["border"], linewidth=0.8)
    ax.set_axisbelow(True)


def _frame(fig, title: str, subtitle: str, footer: str) -> None:
    from textwrap import fill

    width_in = fig.get_size_inches()[0]
    fig.text(0.02, 0.965, title, ha="left", va="top", fontsize=15, weight="bold",
             color=TOKENS["text"])
    fig.text(0.02, 0.905, fill(subtitle, int(width_in * 12.5)), ha="left", va="top",
             fontsize=10.5, color=TOKENS["muted"], linespacing=1.4)
    fig.text(0.02, 0.02, fill(footer, int(width_in * 16)), ha="left", va="bottom",
             fontsize=8.5, color=TOKENS["muted"], linespacing=1.4)


def fmt_date(d: date) -> str:
    return f"{d:%-d %b %Y}"


EXHIBITS = store.ROOT / "data" / "exhibits"


def save(fig, name: str, out_dir: Path = EXHIBITS) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    fig.savefig(path, facecolor=fig.get_facecolor())
    return path


def _span(values: list[int]) -> str:
    lo, hi = min(values), max(values)
    return f"{lo}" if lo == hi else f"{lo}–{hi}"


# --- g1: how fresh the lists are -------------------------------------------------

def publication_lags(con) -> list[tuple[str, date, date, int]]:
    """(source_id, as_of, published, days between) for the live editions (the report
    shows the same rows)."""
    return con.execute("""
        select source_id, as_of, published_at::date,
               date_diff('day', as_of, published_at::date) as lag
        from publication where fetched_from is null
        order by lag, source_id
    """).fetchall()


def publication_lag(con):
    """Each list's as-of date against when it went up. Live editions only."""
    rows = publication_lags(con)
    lags = [r[3] for r in rows]
    tso = [r[3] for r in rows if r[0].startswith("eirgrid")]
    dso = [r[3] for r in rows if r[0].startswith("esb")]
    title = (f"EirGrid's lists go up {_span(tso)} days after their as-of date; "
             f"ESB's take {_span(dso)}")
    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=150)
    _style(fig, ax)
    labels = [r[0].split(".", 1)[1].replace("_", " ") for r in rows]
    y = range(len(rows))
    ax.hlines(y, 0, lags, color=TOKENS["border"], linewidth=2)
    ax.scatter(lags, y, s=64, color=TOKENS["series1"], zorder=3,
               edgecolors=TOKENS["bg"], linewidths=2)
    for yi, r in zip(y, rows, strict=True):
        ax.text(r[3] + 0.8, yi, f"{r[3]} days · as of {r[1]:%-d %b}, up {r[2]:%-d %b}",
                va="center", fontsize=9, color=TOKENS["text"])
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, max(lags) * 1.6)
    ax.set_xlabel("days from as-of date to publication", color=TOKENS["muted"], fontsize=9.5)
    fig.subplots_adjust(left=0.24, right=0.97, top=0.82, bottom=0.2)
    _frame(fig, title,
           "So a weekly report built on these lists shows the distribution grid about a month "
           "late. Publication = the server's Last-Modified time.",
           f"Source: EirGrid connected and contracted generators; ESB Networks generator "
           f"statistics · {LICENCE} · As of {fmt_date(max(r[2] for r in rows))}")
    return fig


# --- g2: what is waiting to connect ---------------------------------------------

def technology_groups(con):
    """{group: [transmission MW, distribution MW]} in display order (Other last), and the
    as-of date of each side, from the latest live contracted editions."""
    rows = con.execute(f"""
        select p.source_id like 'eirgrid%' as transmission, r.technology, p.as_of,
               sum(r.mec_mw) as mw
        from project_row r join publication p using (publication_id)
        join ({store.LATEST_LIVE}) l using (publication_id)
        where p.source_id like '%contracted%' and r.status = 'Contracted'
          and r.parser_version = {int(parse.PARSER_VERSION)}
        group by all
    """).fetchall()
    groups: dict[str, list[Decimal]] = {}
    as_of = {True: None, False: None}
    for transmission, tech, d, mw in rows:
        g = groups.setdefault(group(tech), [Decimal(0), Decimal(0)])
        g[0 if transmission else 1] += mw
        as_of[transmission] = d
    order = sorted(groups, key=lambda g: (g == OTHER, -sum(groups[g])))
    return order, groups, as_of


def contracted_by_technology(con):
    """MW with a signed connection agreement, not yet energised, latest editions."""
    order, groups, as_of = technology_groups(con)
    total = sum(sum(v) for v in groups.values())
    top = order[0]
    share = sum(groups[top]) / total
    title = (f"{total / 1000:.1f} GW has signed to connect to Ireland's grid; "
             f"{top.lower()} is {share:.0%} of it")
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=150)
    _style(fig, ax)
    y = list(range(len(order)))
    tso = [float(groups[g][0]) / 1000 for g in order]
    dso = [float(groups[g][1]) / 1000 for g in order]
    ax.barh(y, tso, height=0.62, color=TOKENS["series1"])
    ax.barh(y, dso, left=tso, height=0.62, color=TOKENS["series3"],
            edgecolor=TOKENS["bg"], linewidth=2)  # 2px surface gap between the two parts
    for yi, g, t, d in zip(y, order, tso, dso, strict=True):
        split = f"  {t:.2f} transmission · {d:.2f} distribution" if d >= 0.005 else ""
        ax.text(t + d + 0.08, yi, f"{t + d:.1f} GW{split}", va="center", fontsize=9.5,
                color=TOKENS["text"])
    ax.set_yticks(y, order)
    ax.invert_yaxis()
    ax.set_xlim(0, max(t + d for t, d in zip(tso, dso, strict=True)) * 1.75)
    ax.set_xlabel("GW (maximum export capacity)", color=TOKENS["muted"], fontsize=9.5)
    # direct legend: name the two parts on the largest bar
    ax.text(tso[0] / 2, -0.52, "transmission", ha="center", va="bottom", fontsize=9,
            color=TOKENS["series1"])
    ax.text(tso[0] + dso[0] / 2, -0.52, "distribution", ha="center", va="bottom", fontsize=9,
            color=TOKENS["muted"])
    fig.subplots_adjust(left=0.2, right=0.97, top=0.76, bottom=0.2)
    tso_mw, dso_mw = sum(g[0] for g in groups.values()), sum(g[1] for g in groups.values())
    _frame(fig, title,
           f"Signed connection agreements not yet energised: {tso_mw / 1000:.1f} GW on "
           f"transmission (EirGrid) and {dso_mw / 1000:.1f} GW on distribution (ESB Networks). "
           f"Other includes a 288 MW demand-side autoproducer.",
           f"Source: EirGrid TSO contracted wind and non-wind lists, as of "
           f"{fmt_date(as_of[True])}; ESB Networks DSO contracted renewable and non-renewable "
           f"lists, as of {fmt_date(as_of[False])} · {LICENCE}")
    return fig


def _top_groups(con, source_id: str, n: int) -> str:
    """'solar 4.5 GW, battery storage 1.9 GW, ...' for the newest live edition of a list."""
    rows = con.execute(f"""
        select r.technology, sum(r.mec_mw) from project_row r
        join ({store.LATEST_LIVE}) l using (publication_id)
        where l.source_id = ? and r.parser_version = {int(parse.PARSER_VERSION)}
        group by 1
    """, [source_id]).fetchall()
    groups: dict[str, Decimal] = {}
    for tech, mw in rows:
        groups[group(tech)] = groups.get(group(tech), Decimal(0)) + mw
    best = sorted(groups.items(), key=lambda kv: -kv[1])[:n]
    return ", ".join(f"{g.lower()} {float(mw) / 1000:.1f} GW" for g, mw in best)


# --- g3: how the queue has grown --------------------------------------------------

def ecp_results(con) -> list[tuple[date, str]]:
    """When each ECP-2 batch's results were first published, from the earliest results
    file the store holds (metrics.batch_dates). Was typed in until g5, with ECP-2.3 a
    quarter late: the store has its November 2022 edition."""
    from iegrid import metrics

    return [(d.when, b) for b, d in metrics.batch_dates(con).items() if b.startswith("ECP-2")]


def queue_series(con) -> dict[str, list[tuple[date, float]]]:
    """GW printed on each EirGrid contracted edition, per list, in date order."""
    rows = con.execute("""
        select p.source_id, p.as_of, arg_max(t.printed_mw, p.published_at) as mw
        from edition_total t join publication p using (publication_id)
        group by all order by p.as_of
    """).fetchall()
    series = {"eirgrid.tso_contracted_nonwind": [], "eirgrid.tso_contracted_wind": []}
    for sid, d, mw in rows:
        series[sid].append((d, float(mw) / 1000))
    return series


def queue_growth(con):
    """Contracted MW on transmission as EirGrid printed it, every edition since 2015."""
    series = queue_series(con)
    nonwind, wind = series["eirgrid.tso_contracted_nonwind"], series["eirgrid.tso_contracted_wind"]
    n0, n1 = nonwind[0], nonwind[-1]
    title = (f"Non-wind waiting to connect to the transmission grid: {n0[1]:.1f} GW in "
             f"{n0[0].year}, {n1[1]:.1f} GW now")
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=150)
    _style(fig, ax)
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=TOKENS["border"], linewidth=0.8)
    for d, label in ecp_results(con):
        ax.axvline(d, color=TOKENS["border"], linewidth=1, zorder=1)
        ax.text(d, n1[1] * 1.04, label, ha="center", va="bottom", fontsize=8.5,
                color=TOKENS["muted"])
    for pts, color, name in ((nonwind, TOKENS["series1"], "non-wind"),
                             (wind, TOKENS["series3"], "wind")):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        ax.plot(xs, ys, color=color, linewidth=2, zorder=3)
        ax.scatter(xs, ys, s=14, color=color, zorder=4, edgecolors=TOKENS["bg"], linewidths=1)
        ax.scatter(xs[-1:], ys[-1:], s=64, color=color, zorder=5, edgecolors=TOKENS["bg"],
                   linewidths=2)
        ax.annotate(f"{name} {ys[-1]:.1f} GW", (xs[-1], ys[-1]),
                    xytext=(8, 0), textcoords="offset points", va="center", fontsize=9.5,
                    color=TOKENS["text"])
    ax.set_ylim(0, n1[1] * 1.12)
    ax.set_xlim(date(n0[0].year, 1, 1), date(n1[0].year + 3, 1, 1))
    ax.set_xticks([date(y, 1, 1) for y in range(n0[0].year + 1, n1[0].year + 1, 2)])
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y"))
    ax.set_ylabel("GW contracted, not yet connected", color=TOKENS["muted"], fontsize=9.5)
    ax.spines["left"].set_visible(False)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.73, bottom=0.17)
    top = _top_groups(con, "eirgrid.tso_contracted_nonwind", 3)
    _frame(fig, title,
           f"Total maximum export capacity printed on each EirGrid contracted list: "
           f"{len(nonwind)} non-wind and {len(wind)} wind editions from {n0[0]:%b %Y}. Each dot "
           f"is one edition; rules mark the results of each connection batch (ECP). The largest "
           f"non-wind groups now: {top}.",
           f"Source: EirGrid TSO contracted wind and non-wind lists, read from the Internet "
           f"Archive and eirgrid.ie · {LICENCE} · As of {fmt_date(n1[0])}")
    return fig


# --- g4: where it is stuck --------------------------------------------------------

def contracted_by_county(con):
    """Contracted MW by county from the newest region build, transmission and distribution.
    Interconnectors are left out of the bars: they are links, not generation waiting
    to connect, and one (Celtic, 700 MW) alone would decide which county leads."""
    build = con.execute("select max(build_id) from region_build").fetchone()[0]
    pv = store.build_parser_version(con, build)
    rows = con.execute(f"""
        select c.county, p.source_id like 'eirgrid%' as transmission, c.basis,
               r.technology = 'Interconnector' as link, sum(c.mec_mw)
        from project_county c join publication p using (publication_id)
        join project_row r on r.publication_id = c.publication_id and r.row_order = c.row_order
         and r.parser_version = {pv}
        where c.build_id = ? group by all
    """, [build]).fetchall()
    links = sum(r[4] for r in rows if r[3])
    gen = [r for r in rows if not r[3]]
    gen_total = sum(r[4] for r in gen)
    placed = sum(r[4] for r in gen if r[0])
    share = {b: sum(r[4] for r in gen if r[2] == b) / placed
             for b in ("name", "cited", "node", "osm-node")}
    by: dict[str, list[Decimal]] = {}
    for county, transmission, _, _, mw in gen:
        if county:
            by.setdefault(county, [Decimal(0), Decimal(0)])[0 if transmission else 1] += mw
    order = sorted(by, key=lambda c: -sum(by[c]))
    top3 = sum(sum(by[c]) for c in order[:3]) / placed
    title = (f"{order[0]} has the most generation waiting to connect, "
             f"{sum(by[order[0]]) / 1000:.1f} GW; three counties hold {top3:.0%} of it placed")
    fig, ax = plt.subplots(figsize=(11, 8.4), dpi=150)
    _style(fig, ax)
    y = list(range(len(order)))
    tso = [float(by[c][0]) / 1000 for c in order]
    dso = [float(by[c][1]) / 1000 for c in order]
    ax.barh(y, tso, height=0.66, color=TOKENS["series1"])
    ax.barh(y, dso, left=tso, height=0.66, color=TOKENS["series3"],
            edgecolor=TOKENS["bg"], linewidth=2)
    for yi, t, d in zip(y, tso, dso, strict=True):
        ax.text(t + d + 0.03, yi, f"{t + d:.2f}", va="center", fontsize=8.5, color=TOKENS["text"])
    ax.set_yticks(y, order, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, max(t + d for t, d in zip(tso, dso, strict=True)) * 1.2)
    ax.set_xlabel("GW contracted, not yet connected", color=TOKENS["muted"], fontsize=9.5)
    ax.text(tso[0] / 2, -0.75, "transmission", ha="center", fontsize=9, color=TOKENS["series1"])
    if dso[0] > 0.05:
        ax.text(tso[0] + dso[0] / 2, -0.75, "distribution", ha="center", fontsize=9,
                color=TOKENS["muted"])
    fig.subplots_adjust(left=0.13, right=0.97, top=0.82, bottom=0.11)
    _frame(fig, title,
           f"Newest contracted lists: {gen_total / 1000:.1f} GW of generation and storage, of "
           f"which {placed / 1000:.2f} GW ({float(placed / gen_total):.1%}) is placed in a county "
           f"(the three-county share is of this); "
           f"{links / 1000:.1f} GW of interconnectors left out. Placed by name in an ECP results "
           f"publication {float(share['name']):.0%}, from a cited planning or developer source "
           f"{float(share['cited']):.0%}, by where the connection node's other projects are "
           f"{float(share['node']):.0%}, by the node's substation in OpenStreetMap "
           f"{float(share['osm-node']):.0%} (the substation's county).",
           f"Source: EirGrid and ESB Networks contracted lists; ECP batch results publications; "
           f"substations © OpenStreetMap contributors (ODbL) · {LICENCE}")
    return fig


# --- g3b: who joins and who leaves -------------------------------------------------

def queue_flows(con):
    """Projects joining and leaving the EirGrid contracted lists, by year, from the
    lists themselves (a project 'leaves' when an edition no longer lists it: connected,
    withdrawn or moved; the connected lists that would tell these apart are parked)."""
    from iegrid import flows

    last_date = con.execute("""
        select max(p.as_of) from publication p join parse_result r using (publication_id)
        where r.parser_version = ? and p.source_id like 'eirgrid.tso_contracted%'
    """, [parse.PARSER_VERSION]).fetchone()[0]
    per_year = flows.by_year(con)
    years = sorted(per_year)
    joined = {y: (0, float(v["joined"]) / 1000) for y, v in per_year.items()}
    left = {y: (0, float(v["left"]) / 1000) for y, v in per_year.items()}
    full = [y for y in years if y < last_date.year]
    y = full[-1]
    title = (f"{y}: {joined.get(y, (0, 0))[1]:.1f} GW joined the transmission queue, "
             f"{left.get(y, (0, 0))[1]:.1f} GW left it")
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=150)
    _style(fig, ax)
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=TOKENS["border"], linewidth=0.8)
    xs = list(range(len(years)))
    w = 0.38
    jv = [joined.get(yr, (0, 0))[1] for yr in years]
    lv = [left.get(yr, (0, 0))[1] for yr in years]
    ax.bar([x - w / 2 - 0.01 for x in xs], jv, width=w, color=TOKENS["series1"])
    ax.bar([x + w / 2 + 0.01 for x in xs], lv, width=w, color=TOKENS["series3"])
    for x, a, b in zip(xs, jv, lv, strict=True):
        if a:
            ax.text(x - w / 2, a + 0.06, f"{a:.1f}", ha="center", fontsize=8, color=TOKENS["text"])
        if b:
            ax.text(x + w / 2, b + 0.06, f"{b:.1f}", ha="center", fontsize=8, color=TOKENS["muted"])
    labels = [f"{yr}\nto {last_date:%b}" if yr == last_date.year else str(yr) for yr in years]
    ax.set_xticks(xs, labels)
    ax.set_ylabel("GW (maximum export capacity)", color=TOKENS["muted"], fontsize=9.5)
    ax.spines["left"].set_visible(False)
    top = max(jv + lv)
    ax.set_ylim(0, top * 1.18)
    ax.text(xs[0] - w / 2, top * 1.1, "joined", color=TOKENS["series1"], fontsize=9)
    ax.text(xs[0] + 0.6, top * 1.1, "left the list", color=TOKENS["muted"], fontsize=9)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.76, bottom=0.14)
    n_dates, n_ed = con.execute("""
        select count(distinct p.as_of), count(*) from publication p
        join parse_result r using (publication_id)
        where r.parser_version = ? and p.source_id like 'eirgrid.tso_contracted%'
    """, [parse.PARSER_VERSION]).fetchone()
    _frame(fig, title,
           f"Each EirGrid contracted list ({n_ed} editions on {n_dates} dates since {years[0]}) "
           f"against its previous edition. Joined: newly listed. Left: no longer listed "
           f"(connected, withdrawn or moved; the lists don't say which). A ref relabelled for the "
           f"same project (D74 to D40d) is neither. Editions are irregular, so a year collects "
           f"whatever changed since the one before.",
           f"Source: EirGrid TSO contracted wind and non-wind lists, read from the Internet "
           f"Archive and eirgrid.ie · {LICENCE} · As of {fmt_date(last_date)}")
    return fig


# --- g5: how long it takes ----------------------------------------------------------

def batch_burndown(con):
    """Share of each ECP batch's distribution MW energised, by months since its results,
    so batches are compared at the same age (g5 review: a snapshot of shares compares a
    seven-year-old batch with a one-year-old one)."""
    from iegrid import metrics

    rows = [b for b in metrics.burndown(con) if b.batch.startswith("ECP")]
    at = 36
    old = [b for b in rows if b.age_months >= at]
    later = [b.share_at(at) for b in old[1:]]
    title = (f"At three years, {old[0].batch} had {old[0].share_at(at):.0%} of its distribution MW "
             f"energised; later batches {min(later):.0%}–{max(later):.0%}")
    fig, ax = plt.subplots(figsize=(11, 5.8), dpi=150)
    _style(fig, ax)
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=TOKENS["border"], linewidth=0.8)
    ax.axvline(at, color=TOKENS["border"], linewidth=1, zorder=1)
    ax.text(at, 51, "3 years", ha="center", fontsize=8.5, color=TOKENS["muted"])
    for i, b in enumerate(rows):
        xs = list(range(b.age_months + 1))
        ys = [b.share_at(m) * 100 for m in xs]
        color = TOKENS["series1"] if i == 0 else TOKENS["series3"]
        ax.step(xs, ys, where="post", color=color, linewidth=2 if i == 0 else 1.6, zorder=3)
        ax.annotate(f"{b.batch} {ys[-1]:.0f}%", (xs[-1], ys[-1]), xytext=(5, 0),
                    textcoords="offset points", va="center", fontsize=8.5,
                    color=TOKENS["text"] if i == 0 else TOKENS["muted"])
    ax.set_xlim(0, max(b.age_months for b in rows) + 14)
    ax.set_ylim(0, 54)
    ax.set_xticks(range(0, max(b.age_months for b in rows) + 1, 12),
                  [f"{m // 12}y" for m in range(0, max(b.age_months for b in rows) + 1, 12)])
    ax.set_xlabel("time since the batch's first results publication", color=TOKENS["muted"],
                  fontsize=9.5)
    ax.set_ylabel("% of the batch's distribution MW energised", color=TOKENS["muted"],
                  fontsize=9.5)
    ax.spines["left"].set_visible(False)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.76, bottom=0.14)
    labels = "; ".join(f"{b.batch} {b.result.label()}" for b in rows)
    _frame(fig, title,
           f"Batch offers only (Non-Batch offers are processed as they come). MW on ESB's "
           f"energised lists by energisation date, against MW still on its contracted lists; "
           f"withdrawn projects are on neither, so this is a share of the projects still in "
           f"the queue. Results: {labels}.",
           f"Source: ESB Networks DSO energised and contracted lists, as of "
           f"{fmt_date(metrics.latest_dso_as_of(con))}; ECP batch results publications · {LICENCE}")
    return fig
