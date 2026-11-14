"""One exhibit per stone: what the data that stone added actually says.

Drawn in the paper format (src/iegrid/paper_style.py, docs/FIGURES.md): 7.0 in wide, serif
type between 6 and 9 pt, a label with its unit on every axis, and no title, subtitle or footer
on the image. The title (a finding computed from the data), the units, the source with its
credit and the as-of date go into the LaTeX caption written beside each figure. The record's
chart rules (energy-forecasting docs/CHARTS.md) still apply to what is drawn: the series are
named where they are drawn, not in a legend box.

Each function returns a matplotlib figure: a notebook shows it with paper_style.show, and
save() writes data/exhibits/<name>.pdf, .png (300 dpi) and .tex.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import matplotlib.dates

from iegrid import paper_style as ps
from iegrid import parse, store

NAVY, BLUE, GREY = ps.PALETTE[0], ps.PALETTE[1], ps.PALETTE[2]
TEXT, MUTED, BORDER = ps.TOKENS["text"], ps.TOKENS["text_muted"], ps.TOKENS["border"]
# The names the weekly page (report.py) reads.
TOKENS = {
    "bg": ps.TOKENS["bg"], "border": BORDER, "text": TEXT, "muted": MUTED,
    "series1": NAVY, "series3": GREY, "accent": BLUE,
}
LISTS_CREDIT = ("EirGrid contracted lists, Supported by EirGrid Group Data; ESB Networks DSO "
                "lists, \u00a9 ESB Networks, used with their permission")
LABEL = 7.0  # the size of the value labels printed on the bars, in points
SMALL = 6.5  # the smallest text the paper format allows on a chart

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


def new_figure(height: float, *, bars: bool = False, width: float = ps.FULL):
    """A paper-format figure and its one axes. `bars=True` puts the grid on the value (x) axis,
    for horizontal bars; otherwise it is horizontal, as the paper style draws it."""
    fig, axes = ps.figure(size=(width, height), sharex=False)
    ax = axes[0][0]
    if bars:
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
    return fig, ax


def _extent_in(fig, labels, axis: int) -> float:
    """The largest width (axis 0) or height (axis 1) of these tick labels, in inches."""
    renderer = fig.canvas.get_renderer()
    sizes = [(t.get_window_extent(renderer).width, t.get_window_extent(renderer).height)[axis]
             for t in labels if t.get_text()]
    return max(sizes, default=0.0) / fig.dpi


def frame_fit(fig, ax, *, title: str, source: str, asof: date | str, units: str,
              xlabel: str, ylabel: str, subtitle: str | None = None, right: float = 0.15,
              top: float = 0.12, bottom_extra: float = 0.0) -> None:
    """Caption, axis labels and margins. The left margin follows the widest y tick label and
    the bottom one the tallest x tick label, so a long category name never leaves the figure."""
    fig.canvas.draw()
    left = _extent_in(fig, ax.get_yticklabels(), 0) + 0.38
    bottom = _extent_in(fig, ax.get_xticklabels(), 1) + 0.46 + bottom_extra
    ps.frame(fig, title=title.rstrip("."), subtitle=subtitle, source=source, asof=asof,
             units=units, xlabel=xlabel, ylabel=ylabel, margins=(left, right, top, bottom))


def fmt_date(d: date) -> str:
    return f"{d:%-d %b %Y}"


EXHIBITS = store.ROOT / "data" / "exhibits"
FORMATS = ("pdf", "png", "tex")  # no svg: the repository has never committed one


def save(fig, name: str, out_dir: Path = EXHIBITS) -> Path:
    """Write <name>.pdf, .png and .tex under out_dir; returns the PNG's path."""
    written = ps.save(fig, Path(out_dir) / name, formats=FORMATS)
    return next(p for p in written if p.suffix == ".png")


def _span(values: list[int]) -> str:
    lo, hi = min(values), max(values)
    return f"{lo}" if lo == hi else f"{lo}–{hi}"


# --- g1: how fresh the lists are -------------------------------------------------

def publication_lags(con) -> list[tuple[str, date, date, int]]:
    """(source_id, as_of, published, days between) for each list's newest live edition
    (the report shows the same rows)."""
    return con.execute("""
        select source_id, as_of, published_at::date,
               date_diff('day', as_of, published_at::date) as lag
        from publication where fetched_from is null
        qualify row_number() over (partition by source_id
                                   order by as_of desc, published_at desc) = 1
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
    fig, ax = new_figure(3.0, bars=True)
    labels = [r[0].split(".", 1)[1].replace("_", " ") for r in rows]
    y = range(len(rows))
    ax.hlines(y, 0, lags, color=BORDER, linewidth=1.4)
    ax.scatter(lags, y, s=26, color=NAVY, zorder=3, edgecolors=ps.TOKENS["bg"], linewidths=1)
    for yi, r in zip(y, rows, strict=True):
        ax.text(r[3] + 0.8, yi, f"{r[3]} days \u00b7 as of {r[1]:%-d %b}, up {r[2]:%-d %b}",
                va="center", fontsize=LABEL, color=TEXT)
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, max(lags) * 1.6)
    frame_fit(fig, ax, title=title,
              subtitle="So a weekly report built on these lists shows the distribution grid about "
                       "a month late. Publication is the server's Last-Modified time.",
              source=f"EirGrid connected and contracted generators; ESB Networks generator "
                     f"statistics; {LISTS_CREDIT}",
              asof=max(r[2] for r in rows), units="days",
              xlabel="Delay from as-of date to publication (days)", ylabel="List")
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
    fig, ax = new_figure(3.3, bars=True)
    y = list(range(len(order)))
    tso = [float(groups[g][0]) / 1000 for g in order]
    dso = [float(groups[g][1]) / 1000 for g in order]
    ax.barh(y, tso, height=0.62, color=NAVY)
    ax.barh(y, dso, left=tso, height=0.62, color=GREY, edgecolor=ps.TOKENS["bg"], linewidth=1)
    for yi, g, t, d in zip(y, order, tso, dso, strict=True):
        split = f"  {t:.2f} transmission \u00b7 {d:.2f} distribution" if d >= 0.005 else ""
        ax.text(t + d + 0.08, yi, f"{t + d:.1f} GW{split}", va="center", fontsize=LABEL,
                color=TEXT)
    ax.set_yticks(y, order)
    ax.invert_yaxis()
    ax.set_xlim(0, max(t + d for t, d in zip(tso, dso, strict=True)) * 1.75)
    # direct legend: name the two parts on the largest bar
    ax.text(tso[0] / 2, -0.52, "transmission", ha="center", va="bottom", fontsize=LABEL,
            color=NAVY)
    ax.text(tso[0] + dso[0] / 2, -0.52, "distribution", ha="center", va="bottom",
            fontsize=LABEL, color=MUTED)
    tso_mw, dso_mw = sum(g[0] for g in groups.values()), sum(g[1] for g in groups.values())
    frame_fit(fig, ax, title=title,
              subtitle=f"Signed connection agreements not yet energised: {tso_mw / 1000:.1f} GW on "
                       f"transmission (EirGrid) and {dso_mw / 1000:.1f} GW on distribution (ESB "
                       f"Networks). Other includes a 288 MW demand-side autoproducer.",
              source=f"EirGrid TSO contracted wind and non-wind lists, as of "
                     f"{fmt_date(as_of[True])}; ESB Networks DSO contracted renewable and "
                     f"non-renewable lists, as of {fmt_date(as_of[False])}; {LISTS_CREDIT}",
              asof=max(as_of.values()), units="GW",
              xlabel="Maximum export capacity (GW)", ylabel="Technology", top=0.28)
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
    fig, ax = new_figure(3.6)
    for d, label in ecp_results(con):
        ax.axvline(d, color=BORDER, linewidth=0.7, zorder=1)
        ax.text(d, n1[1] * 1.04, label, ha="center", va="bottom", fontsize=SMALL, color=MUTED)
    for pts, color, name, dash in ((nonwind, NAVY, "non-wind", "-"), (wind, GREY, "wind", "--")):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        ax.plot(xs, ys, color=color, linewidth=1.2, linestyle=dash, zorder=3)
        ax.scatter(xs, ys, s=5, color=color, zorder=4, edgecolors=ps.TOKENS["bg"], linewidths=0.4)
        ax.scatter(xs[-1:], ys[-1:], s=22, color=color, zorder=5, edgecolors=ps.TOKENS["bg"],
                   linewidths=1)
        ax.annotate(f"{name} {ys[-1]:.1f} GW", (xs[-1], ys[-1]),
                    xytext=(6, 0), textcoords="offset points", va="center", fontsize=LABEL,
                    color=TEXT)
    ax.set_ylim(0, n1[1] * 1.12)
    ax.set_xlim(date(n0[0].year, 1, 1), date(n1[0].year + 3, 1, 1))
    ax.set_xticks([date(y, 1, 1) for y in range(n0[0].year + 1, n1[0].year + 1, 2)])
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y"))
    top = _top_groups(con, "eirgrid.tso_contracted_nonwind", 3)
    frame_fit(fig, ax, title=title,
              subtitle=f"Total maximum export capacity printed on each EirGrid contracted list: "
                       f"{len(nonwind)} non-wind and {len(wind)} wind editions from "
                       f"{n0[0]:%b %Y}. Each dot is one edition; rules mark the results of each "
                       f"connection batch (ECP). The largest non-wind groups now: {top}.",
              source="EirGrid TSO contracted wind and non-wind lists, read from the Internet "
                     "Archive and eirgrid.ie; Supported by EirGrid Group Data",
              asof=n1[0], units="GW", xlabel="List edition date (year)",
              ylabel="Contracted, not yet connected (GW)", top=0.12)
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
    asof = con.execute("select max(p.as_of) from project_county c join publication p "
                       "using (publication_id) where c.build_id = ?", [build]).fetchone()[0]
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
    fig, ax = new_figure(6.4, bars=True)
    y = list(range(len(order)))
    tso = [float(by[c][0]) / 1000 for c in order]
    dso = [float(by[c][1]) / 1000 for c in order]
    ax.barh(y, tso, height=0.66, color=NAVY)
    ax.barh(y, dso, left=tso, height=0.66, color=GREY, edgecolor=ps.TOKENS["bg"], linewidth=0.8)
    for yi, t, d in zip(y, tso, dso, strict=True):
        ax.text(t + d + 0.03, yi, f"{t + d:.2f}", va="center", fontsize=SMALL, color=TEXT)
    ax.set_yticks(y, order, fontsize=SMALL)
    ax.invert_yaxis()
    ax.set_xlim(0, max(t + d for t, d in zip(tso, dso, strict=True)) * 1.2)
    ax.text(tso[0] / 2, -0.75, "transmission", ha="center", fontsize=LABEL, color=NAVY)
    if dso[0] > 0.05:
        ax.text(tso[0] + dso[0] / 2, -0.75, "distribution", ha="center", fontsize=LABEL,
                color=MUTED)
    frame_fit(fig, ax, title=title,
              subtitle=f"Newest contracted lists: {gen_total / 1000:.1f} GW of generation and "
                       f"storage, of which {placed / 1000:.2f} GW ({float(placed / gen_total):.1%}) "
                       f"is placed in a county (the three-county share is of this); "
                       f"{links / 1000:.1f} GW of interconnectors left out. Placed by name in an "
                       f"ECP results publication {float(share['name']):.0%}, from a cited planning "
                       f"or developer source {float(share['cited']):.0%}, by where the connection "
                       f"node's other projects are {float(share['node']):.0%}, by the node's "
                       f"substation in OpenStreetMap {float(share['osm-node']):.0%} (the "
                       f"substation's county).",
              source=f"EirGrid and ESB Networks contracted lists; ECP batch results publications; "
                     f"substations \u00a9 OpenStreetMap contributors (ODbL); {LISTS_CREDIT}",
              asof=asof, units="GW", xlabel="Contracted, not yet connected (GW)",
              ylabel="County", top=0.3)
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
    fig, ax = new_figure(3.4)
    xs = list(range(len(years)))
    w = 0.38
    jv = [joined.get(yr, (0, 0))[1] for yr in years]
    lv = [left.get(yr, (0, 0))[1] for yr in years]
    ax.bar([x - w / 2 - 0.01 for x in xs], jv, width=w, color=NAVY)
    ax.bar([x + w / 2 + 0.01 for x in xs], lv, width=w, color=GREY)
    for x, a, b in zip(xs, jv, lv, strict=True):
        if a:
            ax.text(x - w / 2, a + 0.06, f"{a:.1f}", ha="center", fontsize=SMALL, color=TEXT)
        if b:
            ax.text(x + w / 2, b + 0.06, f"{b:.1f}", ha="center", fontsize=SMALL, color=MUTED)
    labels = [f"{yr}\nto {last_date:%b}" if yr == last_date.year else str(yr) for yr in years]
    ax.set_xticks(xs, labels)
    top = max(jv + lv)
    ax.set_ylim(0, top * 1.18)
    ax.text(xs[0] - w / 2, top * 1.1, "joined", color=NAVY, fontsize=LABEL)
    ax.text(xs[0] + 0.6, top * 1.1, "left the list", color=MUTED, fontsize=LABEL)
    n_dates, n_ed = con.execute("""
        select count(distinct p.as_of), count(*) from publication p
        join parse_result r using (publication_id)
        where r.parser_version = ? and p.source_id like 'eirgrid.tso_contracted%'
    """, [parse.PARSER_VERSION]).fetchone()
    frame_fit(fig, ax, title=title,
              subtitle=f"Each EirGrid contracted list ({n_ed} editions on {n_dates} dates since "
                       f"{years[0]}) against its previous edition. Joined: newly listed. Left: no "
                       f"longer listed (connected, withdrawn or moved; the lists don't say which). "
                       f"A ref relabelled for the same project (D74 to D40d) is neither. Editions "
                       f"are irregular, so a year collects whatever changed since the one before.",
              source="EirGrid TSO contracted wind and non-wind lists, read from the Internet "
                     "Archive and eirgrid.ie; Supported by EirGrid Group Data",
              asof=last_date, units="GW", xlabel="Year of list edition",
              ylabel="Maximum export capacity (GW)")
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
    fig, ax = new_figure(3.6)
    ax.axvline(at, color=BORDER, linewidth=0.7, zorder=1)
    ax.text(at, 51, "3 years", ha="center", fontsize=SMALL, color=MUTED)
    low = []  # batches that have barely started: their lines lie on top of each other
    for i, b in enumerate(rows):
        xs = list(range(b.age_months + 1))
        ys = [b.share_at(m) * 100 for m in xs]
        color = NAVY if i == 0 else GREY
        ax.step(xs, ys, where="post", color=color, linewidth=1.3 if i == 0 else 1.0, zorder=3)
        label = f"{b.batch} {ys[-1]:.0f}%"
        if ys[-1] < 8:
            low.append(label)
        else:
            ax.annotate(label, (xs[-1], ys[-1]), xytext=(4, 0), textcoords="offset points",
                        va="center", fontsize=SMALL, color=TEXT if i == 0 else MUTED)
    if low:  # one note for the flat lines near zero, in the empty corner
        ax.text(max(b.age_months for b in rows) + 1, 4, "barely started, flat near zero:\n"
                + "\n".join(low), fontsize=SMALL, color=MUTED, ha="right", va="bottom", multialignment="left")
    ax.set_xlim(0, max(b.age_months for b in rows) + 14)
    ax.set_ylim(0, 54)
    ax.set_xticks(range(0, max(b.age_months for b in rows) + 1, 12),
                  [f"{m // 12}y" for m in range(0, max(b.age_months for b in rows) + 1, 12)])
    labels = "; ".join(f"{b.batch} {b.result.label()}" for b in rows)
    as_of = metrics.latest_dso_as_of(con)
    frame_fit(fig, ax, title=title,
              subtitle=f"Batch offers only (Non-Batch offers are processed as they come). MW on "
                       f"ESB's energised lists by energisation date, against MW still on its "
                       f"contracted lists; withdrawn projects are on neither, so this is a share "
                       f"of the projects still in the queue. Results: {labels}.",
              source=f"ESB Networks DSO energised and contracted lists, as of {fmt_date(as_of)}; "
                     f"ECP batch results publications; \u00a9 ESB Networks, used with their "
                     f"permission",
              asof=as_of, units="% of batch MW",
              xlabel="Time since the batch's first results publication (years)",
              ylabel="Distribution MW energised (% of batch)")
    return fig
