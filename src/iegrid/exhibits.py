"""One exhibit per stone: what the data that stone added actually says.

Drawn to the record's chart rules (energy-forecasting docs/CHARTS.md): the title
states the finding and is computed from the data, the subtitle gives the units,
and a footer names source, licence and as-of. Colours are the record's tokens
(site/styles/tokens.css), light mode, since these are exported PNGs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import matplotlib
import matplotlib.dates

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from iegrid import parse

TOKENS = {
    "bg": "#FFFFFF", "border": "#DCE3EC", "text": "#0B1F3A", "muted": "#5B6878",
    "series1": "#0F2A4A", "series3": "#7D8996", "accent": "#1F5FBF",
}
LICENCE = "licence not yet checked (PARKING.md)"

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


# --- g1: how fresh the lists are -------------------------------------------------

def publication_lag(con):
    """Each list's as-of date against when it went up. Live editions only."""
    rows = con.execute("""
        select source_id, as_of, published_at::date,
               date_diff('day', as_of, published_at::date) as lag
        from publication where fetched_from is null
        order by lag, source_id
    """).fetchall()
    lags = [r[3] for r in rows]
    tso = [r[3] for r in rows if r[0].startswith("eirgrid")]
    dso = [r[3] for r in rows if r[0].startswith("esb")]
    title = (f"EirGrid's lists go up {min(tso)} days after their as-of date; "
             f"ESB's take {min(dso)}–{max(dso)}")
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

def contracted_by_technology(con):
    """MW with a signed connection agreement, not yet energised, latest editions."""
    rows = con.execute(f"""
        with latest as (
            select source_id, max(as_of) as as_of from publication
            where source_id like '%contracted%' and fetched_from is null group by 1)
        select p.source_id like 'eirgrid%' as transmission, r.technology, p.as_of,
               sum(r.mec_mw) as mw
        from project_row r join publication p using (publication_id)
        join latest l on l.source_id = p.source_id and l.as_of = p.as_of
        where r.parser_version = {int(parse.PARSER_VERSION)} and r.status = 'Contracted'
        group by all
    """).fetchall()
    groups: dict[str, list[Decimal]] = {}
    as_of = {True: None, False: None}
    for transmission, tech, d, mw in rows:
        g = groups.setdefault(group(tech), [Decimal(0), Decimal(0)])
        g[0 if transmission else 1] += mw
        as_of[transmission] = d
    order = sorted(groups, key=lambda g: (g == OTHER, -sum(groups[g])))
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


# --- g3: how the queue has grown --------------------------------------------------

# Results of each ECP batch (the joint system-operator publications, first issue).
ECP_RESULTS = (
    (date(2020, 11, 1), "ECP-2.1"), (date(2021, 11, 1), "ECP-2.2"),
    (date(2023, 4, 1), "ECP-2.3"), (date(2024, 1, 1), "ECP-2.4"),
    (date(2025, 5, 1), "ECP-2.5"),
)


def queue_growth(con):
    """Contracted MW on transmission as EirGrid printed it, every edition since 2015."""
    rows = con.execute("""
        select p.source_id, p.as_of, arg_max(t.printed_mw, p.published_at) as mw
        from edition_total t join publication p using (publication_id)
        group by all order by p.as_of
    """).fetchall()
    series = {"eirgrid.tso_contracted_nonwind": [], "eirgrid.tso_contracted_wind": []}
    for sid, d, mw in rows:
        series[sid].append((d, float(mw) / 1000))
    nonwind, wind = series["eirgrid.tso_contracted_nonwind"], series["eirgrid.tso_contracted_wind"]
    n0, n1 = nonwind[0], nonwind[-1]
    title = (f"Non-wind waiting to connect to the transmission grid: {n0[1]:.1f} GW in "
             f"{n0[0].year}, {n1[1]:.1f} GW now")
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=150)
    _style(fig, ax)
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=TOKENS["border"], linewidth=0.8)
    for d, label in ECP_RESULTS:
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
    fig.subplots_adjust(left=0.07, right=0.97, top=0.78, bottom=0.17)
    _frame(fig, title,
           f"Total maximum export capacity printed on each EirGrid contracted list, "
           f"{len(rows)} editions from {n0[0]:%b %Y}. Each dot is one edition; rules mark "
           f"the results of each connection batch (ECP). Non-wind is now mostly solar, "
           f"battery and gas.",
           f"Source: EirGrid TSO contracted wind and non-wind lists, {len(rows)} editions read "
           f"from the Internet Archive and eirgrid.ie · {LICENCE} · As of {fmt_date(n1[0])}")
    return fig
