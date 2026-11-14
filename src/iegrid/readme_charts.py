"""The README's charts, drawn with matplotlib from the newest weekly report.

    uv run python -m iegrid.readme_charts            # newest data/reports/*.json -> docs/img
    uv run python -m iegrid.readme_charts REPORT.json OUT_DIR

Every number comes from the report JSON, the same file the dashboard reads, so
the two never disagree. The figures are in the paper format (paper_style.py,
docs/FIGURES.md): 7.0 in wide, sans-serif type of 6 to 9 pt, a label with its unit on every
axis. Nothing about the finding is drawn on the image. For each chart three files are
written: <name>.pdf (vector, Type 42 fonts, for a paper), <name>.png (300 dpi, for the
README) and <name>.tex (a LaTeX figure whose caption holds the finding, units, source
with its credit, and the as-of date). The finding is computed from the data.
Transmission is navy, distribution grey, a highlight is blue; no legend boxes, the
series are named where they are drawn. The three colours passed the dataviz validator's
colour-blind and normal-vision checks (navy/grey dE 19, blue/grey 17).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import matplotlib.dates
import matplotlib.patheffects
import matplotlib.ticker
from matplotlib.patches import Polygon

from iegrid import paper_style as ps
from iegrid import store
from iegrid.exhibits import (
    BLUE,
    BORDER,
    GREY,
    LABEL,
    LISTS_CREDIT,
    MUTED,
    NAVY,
    SMALL,
    TEXT,
    fmt_date,
    frame_fit,
    new_figure,
)

OUT = store.ROOT / "docs" / "img"
REPORTS = store.ROOT / "data" / "reports"
FORMATS = ("pdf", "png", "tex")  # no svg: the repository has never committed one


def newest_report() -> Path:
    files = sorted(REPORTS.glob("*.json"))
    if not files:
        raise SystemExit(f"no report in {REPORTS}; run `uv run python -m iegrid.report` first")
    return files[-1]


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _as_of(rep) -> str:
    """Both lists' as-of dates, for a source line."""
    t = rep["queue"]["by_technology"]
    return (f"transmission list as of {fmt_date(_d(t['transmission_as_of']))}, "
            f"distribution list as of {fmt_date(_d(t['distribution_as_of']))}")


def _newest(rep) -> date:
    """The later of the two lists' as-of dates: the figure's as-of."""
    t = rep["queue"]["by_technology"]
    return max(_d(t["transmission_as_of"]), _d(t["distribution_as_of"]))


def _label(d: date) -> str:
    return fmt_date(d)


# ---------------------------------------------------------------- what is waiting

def technology(rep):
    t = rep["queue"]["by_technology"]
    groups = t["groups"]
    top = groups[0]
    topic = "Generation contracted to connect, by technology"
    finding = (f"{t['total_gw']:.2f} GW has signed to connect; {top['group'].lower()} is "
               f"{t['top_share']:.0%} of it.")
    fig, ax = new_figure(3.1, bars=True)
    y = list(range(len(groups)))
    tso = [g["transmission_gw"] for g in groups]
    dso = [g["distribution_gw"] for g in groups]
    ax.barh(y, tso, height=0.62, color=NAVY)
    ax.barh(y, dso, left=tso, height=0.62, color=GREY, edgecolor="white", linewidth=1)
    for yi, a, b in zip(y, tso, dso, strict=True):
        split = f"   {a:.2f} + {b:.2f}" if b >= 0.005 else ""
        ax.text(a + b + 0.08, yi, f"{a + b:.2f} GW{split}", va="center", fontsize=LABEL,
                color=TEXT)
    ax.set_yticks(y, [g["group"] for g in groups])
    ax.invert_yaxis()
    ax.set_xlim(0, max(a + b for a, b in zip(tso, dso, strict=True)) * 1.6)
    ax.text(tso[0] / 2, -0.55, "transmission (EirGrid)", ha="center", fontsize=LABEL, color=TEXT)
    ax.text(tso[0] + dso[0] / 2, -0.55, "distribution (ESB Networks)", ha="center",
            fontsize=LABEL, color=TEXT)
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}: GW signed but not yet connected. The figures on the right "
                       "split each bar into the large (transmission) and local (distribution) "
                       "grids.",
              source=f"{LISTS_CREDIT}; {_as_of(rep)}", asof=_newest(rep), units="GW",
              xlabel="Generation contracted, not yet energised (GW)", ylabel="Technology",
              top=0.3)
    return fig


def history(rep):
    h = rep["queue"]["history"]
    nonwind = [(_d(p["as_of"]), p["gw"]) for p in h["nonwind"]]
    wind = [(_d(p["as_of"]), p["gw"]) for p in h["wind"]]
    n0, n1 = nonwind[0], nonwind[-1]
    topic = "Contracted capacity on the transmission grid, every list since 2015"
    finding = (f"Non-wind grew from {n0[1]:.2f} GW in {n0[0].year} to {n1[1]:.2f} GW; "
               f"wind is {wind[-1][1]:.2f} GW.")
    fig, ax = new_figure(3.5)
    top = max(max(p[1] for p in nonwind), max(p[1] for p in wind))
    for b in h["batches"]:
        d = _d(b["results"])
        ax.axvline(d, color=BORDER, linewidth=0.7, linestyle="--", zorder=1)
        ax.text(d, top * 1.04, b["batch"], ha="center", va="bottom", fontsize=SMALL, color=MUTED)
    for pts, colour, name, dash in ((nonwind, NAVY, "non-wind", "-"), (wind, GREY, "wind", "--")):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        ax.plot(xs, ys, color=colour, linewidth=1.3, linestyle=dash, zorder=3)
        ax.scatter(xs, ys, s=6, color=colour, zorder=4, edgecolors="white", linewidths=0.5)
        ax.scatter(xs[-1:], ys[-1:], s=26, color=colour, zorder=5, edgecolors="white",
                   linewidths=1)
        ax.annotate(f"{name}, {ys[-1]:.2f} GW", (xs[-1], ys[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=LABEL, color=TEXT)
    ax.set_ylim(0, top * 1.14)
    ax.set_xlim(date(n0[0].year, 1, 1), date(n1[0].year + 2, 7, 1))
    ax.set_xticks([date(y, 1, 1) for y in range(n0[0].year + 1, n1[0].year + 1, 2)])
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y"))
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}: GW printed on each EirGrid contracted list, {len(nonwind)} "
                       f"non-wind and {len(wind)} wind editions since {n0[0]:%B %Y}. Dashed "
                       "rules mark when each connection batch (ECP) got its results.",
              source="EirGrid TSO contracted wind and non-wind lists, read from eirgrid.ie and "
                     "the Internet Archive; Supported by EirGrid Group Data",
              asof=n1[0], units="GW", xlabel="List edition date (year)",
              ylabel="Contracted, not yet energised (GW)")
    return fig


# ---------------------------------------------------------------- what moved

def flows(rep):
    rows = rep["moved"]["by_year"]
    last_year = rows[-1]["year"]
    full = [r for r in rows if r["year"] < last_year]
    best = max(full, key=lambda r: r["joined_gw"])
    topic = "Capacity joining and leaving the transmission lists, by year"
    finding = (f"{best['year']} was the biggest year for joining: {best['joined_gw']:.2f} GW "
               f"joined and {best['left_gw']:.2f} GW left.")
    fig, ax = new_figure(3.3)
    xs = list(range(len(rows)))
    w = 0.38
    jv = [r["joined_gw"] for r in rows]
    lv = [r["left_gw"] for r in rows]
    ax.bar([x - w / 2 - 0.01 for x in xs], jv, width=w, color=NAVY)
    ax.bar([x + w / 2 + 0.01 for x in xs], lv, width=w, color=GREY)
    for x, a, b in zip(xs, jv, lv, strict=True):
        ax.text(x - w / 2, a + 0.06, f"{a:.1f}", ha="center", fontsize=SMALL, color=TEXT)
        ax.text(x + w / 2, b + 0.06, f"{b:.1f}", ha="center", fontsize=SMALL, color=MUTED)
    labels = [f"{r['year']}\nso far" if r["year"] == last_year else str(r["year"]) for r in rows]
    ax.set_xticks(xs, labels)
    top = max(jv + lv)
    ax.set_ylim(0, top * 1.2)
    joined = ax.text(xs[0] - w / 2, top * 1.1, "joined the list (navy)", color=TEXT,
                     fontsize=LABEL, va="bottom")
    # placed from the first label's right edge, so the gap holds whatever the font's width
    ax.annotate("left the list (grey)", xy=(1, 0), xycoords=joined, xytext=(14, 0),
                textcoords="offset points", va="bottom", color=TEXT, fontsize=LABEL)
    asof = _d(rep["queue"]["by_technology"]["transmission_as_of"])
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}: GW, each EirGrid contracted list against the one before. "
                       "A project leaves when it is connected, withdrawn or moved; the lists do "
                       "not say which.",
              source="EirGrid TSO contracted lists, Supported by EirGrid Group Data",
              asof=asof, units="GW", xlabel="Year of list edition",
              ylabel="Capacity joining or leaving (GW)")
    return fig


# ---------------------------------------------------------------- what is stuck

def burndown(rep):
    s = rep["stuck"]
    rows = s["burndown"]
    years = s["at_years"]
    first = rows[0]
    later = [r for r in rows[1:] if r["share_at"] is not None]
    topic = f"Share of each connection batch energised {years} years after its results"
    finding = (f"{first['batch']} had {first['share_at']:.0%} of its distribution MW energised "
               f"at that age; no later batch passed {max(r['share_at'] for r in later):.1%}.")
    fig, ax = new_figure(2.9, bars=True)
    y = list(range(len(rows)))
    for yi, r in zip(y, rows, strict=True):
        if r["share_at"] is None:
            ax.text(0.005, yi, f"too young: results {r['results']}, {r['age_months']} months ago",
                    va="center", fontsize=LABEL, color=MUTED)
        else:
            ax.barh(yi, r["share_at"], height=0.6, color=NAVY)
            ax.text(r["share_at"] + 0.004, yi, f"{r['share_at']:.1%} of {r['projects']} projects",
                    va="center", fontsize=LABEL, color=TEXT)
    ax.set_yticks(y, [f"{r['batch']}  ({r['results']})" for r in rows])
    ax.set_ylim(len(rows) - 0.4, -0.6)
    ax.set_xlim(0, max(r["share_at"] or 0 for r in rows) * 1.9)
    ax.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(0.05))
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}: by MW, local (distribution) grid only. Every batch is measured "
                       "at the same age, so older batches get no extra credit for having had "
                       "longer.",
              source="ESB Networks DSO contracted and energised lists, © ESB Networks, used "
                     "with their permission",
              asof=_d(s["as_of"]), units="% of batch MW",
              xlabel=f"Batch MW energised {years} years after results (% of batch)",
              ylabel="Connection batch (results date)")
    return fig


# ---------------------------------------------------------------- where

def counties(rep):
    rows = rep["where"]["counties"]
    top = rows[0]
    share3 = sum(r["gw"] for r in rows[:3]) / sum(r["gw"] for r in rows)
    topic = "Contracted generation by county"
    finding = (f"{top['county']} holds the most, {top['gw']:.2f} GW; three counties hold "
               f"{share3:.0%} of what is placed.")
    fig, ax = new_figure(0.9 + 0.17 * len(rows), bars=True)
    y = list(range(len(rows)))
    ax.barh(y, [r["gw"] for r in rows], height=0.66, color=NAVY)
    for yi, r in zip(y, rows, strict=True):
        ax.text(r["gw"] + 0.03, yi, f"{r['gw']:.2f}", va="center", fontsize=SMALL, color=TEXT)
    ax.set_yticks(y, [r["county"] for r in rows], fontsize=SMALL)
    ax.invert_yaxis()
    ax.set_xlim(0, top["gw"] * 1.18)
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}: GW, transmission and distribution together, interconnectors "
                       f"left out. {rep['where']['generation_placed_share']:.0%} of generation "
                       "MW is placed in a county.",
              source=f"{LISTS_CREDIT}; ECP results; substations © OpenStreetMap contributors "
                     f"(ODbL); {_as_of(rep)}",
              asof=_newest(rep), units="GW",
              xlabel="Generation contracted, not yet energised (GW)", ylabel="County")
    return fig


def grid_map(rep):
    g = rep["grid"]
    kv = "/".join(str(k) for k in g["backbone_kv"])
    topic = "Contracted capacity by connection substation"
    finding = (f"{g['far_gw']:.2f} GW waits at {g['far_nodes']} substations {g['far_km']} km or "
               f"more from the {kv} kV network.")
    fig, axes = ps.figure(size=(ps.FULL, 5.95), sharex=False)
    ax = axes[0][0]
    ax.set_axis_off()
    for ring in g["outline"]:
        ax.add_patch(Polygon(ring, closed=True, facecolor="none", edgecolor=GREY,
                             linewidth=0.5, zorder=1))
    for line in g["lines"]:
        xs, ys = zip(*line["path"], strict=True)
        heavy = line["kv"] >= 220
        ax.plot(xs, ys, color=GREY if heavy else BORDER, linewidth=0.8 if heavy else 0.4,
                zorder=2 if heavy else 1.5, solid_capstyle="round")
    nodes = sorted(g["nodes"], key=lambda n: -n["mw"])
    far = [n for n in nodes if n["km_backbone"] >= g["far_km"]]
    near = [n for n in nodes if n["km_backbone"] < g["far_km"]]
    scale = 1.1
    for group, colour in ((near, NAVY), (far, BLUE)):
        ax.scatter([n["lon"] for n in group], [n["lat"] for n in group],
                   s=[n["mw"] * scale for n in group], color=colour, alpha=0.55,
                   edgecolors="white", linewidths=0.5, zorder=4)
    # labels of the four largest, offset so that neighbours do not overprint (points; ha)
    offsets = {"Cashla": (-6, 8, "right"), "Shannonbridge": (6, -11, "left"),
               "Arklow": (-8, 6, "right")}
    for n in nodes[:4]:
        name = n["node"].split(" ")[0]
        dx, dy, ha = offsets.get(name, (6, 4, "left"))
        ax.annotate(f"{name}  {n['mw']:.0f} MW", (n["lon"], n["lat"]),
                    xytext=(dx, dy), textcoords="offset points", fontsize=LABEL, color=TEXT,
                    ha=ha, zorder=6,
                    path_effects=[matplotlib.patheffects.withStroke(linewidth=2,
                                                                    foreground="white")])
    ax.set_aspect(1 / 0.595)  # cos(53.5 deg): a kilometre is a kilometre in both directions
    ax.set_xlim(-13.6, -5.2)
    ax.set_ylim(51.2, 55.5)
    # in-plot key, left of the island, in the Atlantic
    kx, ky = -13.5, 55.35
    for i, (colour, label) in enumerate(((NAVY, f"under {g['far_km']} km from the backbone"),
                                         (BLUE, f"{g['far_km']} km or more away"))):
        ax.scatter([kx], [ky - i * 0.15], s=22, color=colour, alpha=0.7, edgecolors="white")
        ax.text(kx + 0.14, ky - i * 0.15, label, va="center", fontsize=LABEL, color=TEXT)
    ax.plot([kx - 0.06, kx + 0.06], [ky - 0.3] * 2, color=GREY, linewidth=1.0)
    ax.text(kx + 0.14, ky - 0.3, "220, 275 and 400 kV lines", va="center", fontsize=LABEL,
            color=TEXT)
    ax.plot([kx - 0.06, kx + 0.06], [ky - 0.45] * 2, color=BORDER, linewidth=0.6)
    ax.text(kx + 0.14, ky - 0.45, "110 kV lines", va="center", fontsize=LABEL, color=TEXT)
    ax.text(kx - 0.1, ky - 0.7, "Circle area: MW waiting at the substation", va="center",
            fontsize=LABEL, color=MUTED)
    # distance bands, in the Atlantic below the key
    bx, by = -13.5, 52.2
    ax.text(bx, by, "GW waiting, by distance to the backbone", fontsize=LABEL, color=TEXT)
    for i, b in enumerate(g["bands"]):
        ax.text(bx, by - 0.14 * (i + 1), b["label"], fontsize=LABEL, color=MUTED)
        ax.text(bx + 1.5, by - 0.14 * (i + 1), f"{b['gw']:.2f} GW at {b['nodes']} substations",
                fontsize=LABEL, color=TEXT)
    ps.frame(fig, title=finding.rstrip("."),
             subtitle=f"{topic}: a bigger circle means more MW waiting at that substation. "
                      f"{g['placed_gw']:.2f} GW ({g['placed_share']:.0%}) of the queue is on the "
                      "map. A substation not yet on OpenStreetMap is drawn at the nearest "
                      "location the sources give.",
             source=f"{LISTS_CREDIT}; lines and substations © OpenStreetMap contributors "
                    f"(ODbL), fetched {g['osm_fetched_at'][:10]}; {_as_of(rep)}",
             asof=_newest(rep), units="MW", margins=(0.1, 0.1, 0.1, 0.1))
    return fig


# ---------------------------------------------------------------- how fresh

def freshness(rep):
    rows = rep["freshness"]
    tso = [r["days"] for r in rows if r["list"].startswith("EirGrid")]
    dso = [r["days"] for r in rows if r["list"].startswith("ESB")]
    topic = "Days from each list's as-of date to its publication"
    finding = (f"EirGrid posts its lists about {round(sum(tso) / len(tso))} days after their "
               f"as-of date and ESB Networks about {round(sum(dso) / len(dso))}.")
    fig, ax = new_figure(2.8, bars=True)
    y = list(range(len(rows)))
    days = [r["days"] for r in rows]
    ax.hlines(y, 0, days, color=BORDER, linewidth=1.4)
    ax.scatter(days, y, s=28, color=[NAVY if r["list"].startswith("EirGrid") else GREY
                                     for r in rows],
               zorder=3, edgecolors="white", linewidths=1)
    for yi, r in zip(y, rows, strict=True):
        ax.text(r["days"] + 0.8, yi, f"{r['days']} days · as of {fmt_date(_d(r['as_of']))}, "
                f"published {fmt_date(_d(r['published']))}", va="center", fontsize=LABEL,
                color=TEXT, path_effects=ps.halo())  # reads across the gridlines
    ax.set_yticks(y, [r["list"] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, max(days) * 1.9)
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}. So a weekly report built on these lists shows the "
                       "distribution grid about a month late. Publication is the server's "
                       "Last-Modified time.",
              source=LISTS_CREDIT, asof=_d(rep["report_date"]), units="days",
              xlabel="Delay from the list's as-of date to its publication (days)",
              ylabel="List")
    return fig


# ---------------------------------------------------------------- what became of the leavers

def left(rep):
    lo = rep["left_outcomes"]
    rows = lo["by_outcome"]
    connected = sum(r["count"] for r in rows if r["outcome"].startswith("connected")
                    or "connected" in r["outcome"] and "not" not in r["outcome"])
    unknown = next(r["count"] for r in rows if r["outcome"] == "unknown")
    topic = "What became of the projects that left the contracted lists"
    finding = (f"{lo['total']} projects ({lo['total_gw']:.2f} GW) left for good: {connected} "
               f"connected one way or another, {unknown} unknown.")
    fig, ax = new_figure(3.2, bars=True)
    y = list(range(len(rows)))
    colours = [GREY if r["outcome"] in ("unknown", "not on a connected list") or
               r["outcome"].startswith("not connected") else NAVY for r in rows]
    ax.barh(y, [r["count"] for r in rows], height=0.62, color=colours)
    for yi, r in zip(y, rows, strict=True):
        ax.text(r["count"] + 0.5, yi,
                f"{r['count']} project{'' if r['count'] == 1 else 's'} · "
                f"{r['gw'] * 1000:,.0f} MW", va="center", fontsize=LABEL, color=TEXT)
    ax.set_yticks(y, ["connected, from other sources" if r["outcome"] == "connected (sourced)"
                      else r["outcome"].replace(" (sourced)", "") for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, max(r["count"] for r in rows) * 1.45)
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}: projects, by what EirGrid's connected lists say (wind only, "
                       f"to {fmt_date(_d(lo['cover_end']))}). Navy: a connection is on record. "
                       "Grey: not connected, or unknown, which is never read as not connected.",
              source="EirGrid contracted and connected lists, Supported by EirGrid Group Data; "
                     "planning sources cited in src/iegrid/data/resolutions.csv",
              asof=_d(rep["report_date"]), units="projects",
              xlabel="Projects that left the contracted lists (count)",
              ylabel="What became of them")
    return fig


# ---------------------------------------------------------------- pace

def _pace(rep, key, grid_name, source):
    p = rep["delivery_pace"][key]
    rows = p["annual"]
    cover3 = next(c for c in p["cover"] if c["window"] == 3)
    fastest = p["fastest"][0]
    topic = f"MW energised each year, {grid_name}"
    finding = (f"At the {cover3['from']}–{cover3['to']} pace the {p['queue_mw'] / 1000:.2f} GW "
               f"queue is {cover3['years']:.1f} years of delivery; at the fastest three years "
               f"({fastest['from']}–{fastest['to']}), {fastest['years']:.1f}.")
    fig, ax = new_figure(3.3)
    xs = [r["year"] for r in rows]
    ax.bar(xs, [r["mw"] for r in rows], width=0.72, color=NAVY)
    for r in rows:
        ax.text(r["year"], r["mw"] + max(x["mw"] for x in rows) * 0.015, f"{r['mw']:.0f}",
                ha="center", fontsize=SMALL, color=TEXT, zorder=6,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.5})
    mean_label = f"{cover3['from']}–{cover3['to']} mean,\n{c_pace(cover3)} MW a year"
    fast_label = f"fastest three years,\n{c_pace(fastest)} MW a year"
    for c, colour, label in ((cover3, GREY, mean_label), (fastest, BLUE, fast_label)):
        ax.hlines(c["pace_mw"], xs[0] - 0.5, xs[-1] + 0.5, color=colour, linestyle="--",
                  linewidth=1.1, zorder=4)
        ax.text(xs[-1] + 0.65, c["pace_mw"], label, va="center", fontsize=LABEL, color=TEXT)
    ax.set_xticks(xs[::2] if len(xs) > 10 else xs)
    ax.set_xlim(xs[0] - 0.6, xs[-1] + 0.6)
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}: MW, {xs[0]} to {p['through']}. This is simple division for "
                       "scale, not a forecast: most contracted MW never gets built.",
              source=source, asof=_d(p["as_of"]), units="MW",
              xlabel="Year of energisation", ylabel="Capacity energised (MW)", right=1.5)
    return fig


def c_pace(c) -> str:
    return f"{c['pace_mw']:.0f}"


def pace_dso(rep):
    return _pace(rep, "distribution", "distribution",
                 "ESB Networks DSO energised lists, © ESB Networks, used with their permission")


def pace_tso(rep):
    return _pace(rep, "transmission_wind", "transmission wind",
                 "EirGrid connected wind lists, Supported by EirGrid Group Data")


# ---------------------------------------------------------------- promises against delivery

def slippage(rep):
    s = rep["target_slippage"]
    rows = sorted(s["rows"], key=lambda r: r["to_completion"])
    topic = "Months from the target connection month to completion, wind projects"
    finding = (f"{s['late_to_completion']} of {s['matched']} projects with a published target "
               f"connected after it, by a median of {s['median_to_completion']:.1f} months.")
    fig, ax = new_figure(0.9 + 0.17 * len(rows), bars=True)
    y = list(range(len(rows)))
    months = [r["to_completion"] for r in rows]
    ax.hlines(y, 0, months, color=BORDER, linewidth=1.4)
    ax.scatter(months, y, s=22, color=NAVY, zorder=3, edgecolors="white", linewidths=1)
    ax.axvline(0, color=MUTED, linewidth=0.8)
    ax.spines["left"].set_visible(False)  # the rule at zero is the baseline; the axes start left of it
    ax.axvline(s["median_to_completion"], color=BLUE, linestyle="--", linewidth=1.1, zorder=1)
    ax.text(s["median_to_completion"] + 0.6, -0.9, f"median {s['median_to_completion']:.1f} months",
            color=TEXT, fontsize=LABEL)
    for yi, r in zip(y, rows, strict=True):
        ax.text(max(r["to_completion"], 0) + 1.2, yi,
                f"{r['to_completion']:+d} months · {r['mw']:.0f} MW · target {r['target']}",
                va="center", fontsize=SMALL, color=TEXT, zorder=5,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.5})
    ax.set_yticks(y, [r["name"] for r in rows], fontsize=SMALL)
    ax.invert_yaxis()
    lo, hi = min(months + [0]), max(months)
    ax.set_xlim(lo - 4, hi + 34)
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}: months between the target month EirGrid printed in its "
                       f"earliest lists and the project's connected-list entry. "
                       f"{s['with_target']} projects had a target and {s['matched']} can be "
                       "followed to a connection. A record of what happened to these projects, "
                       "not a rate to apply to others.",
              source="EirGrid contracted and connected wind lists, Supported by EirGrid Group Data",
              asof=_d(rep["report_date"]), units="months",
              xlabel="Months from the target connection month to completion (positive = late)",
              ylabel="Wind project", top=0.3)
    return fig


# ---------------------------------------------------------------- offer to list

def funnel(rep):
    rows = rep["funnel"]["batches"]
    shares = [r["share_found_mw"] for r in rows]
    topic = "Share of each connection batch's offers that reached a contracted list"
    finding = (f"{min(shares):.0%} to {max(shares):.0%} of what each batch offered has ever "
               "appeared on a list, by MW, using the offer-by-offer count.")
    fig, ax = new_figure(3.2, bars=True)
    y = list(range(len(rows)))
    for yi, r in zip(y, rows, strict=True):
        a, b = r["share_found_mw"], r["share_tagged"]
        ax.hlines(yi, min(a, b), max(a, b), color=BORDER, linewidth=2.2, zorder=1)
        ax.text(min(a, b) - 0.015, yi, f"{min(a, b):.0%}", ha="right", va="center",
                fontsize=LABEL, color=TEXT)
        ax.text(max(a, b) + 0.015, yi, f"{max(a, b):.0%}", ha="left", va="center",
                fontsize=LABEL, color=TEXT)
    ax.scatter([r["share_found_mw"] for r in rows], y, s=34, color=NAVY, zorder=3,
               edgecolors="white", linewidths=1)
    ax.scatter([r["share_tagged"] for r in rows], y, s=34, color=GREY, zorder=3,
               edgecolors="white", linewidths=1)
    # the two series are named where they are drawn, not in a legend box
    ax.text(0.02, 0.93, "\u25cf matched offer by offer", transform=ax.transAxes, ha="left",
            va="center", fontsize=LABEL, color=NAVY)
    ax.text(0.02, 0.85, "\u25cf the lists' batch tags", transform=ax.transAxes, ha="left",
            va="center", fontsize=LABEL, color=MUTED)
    ax.set_yticks(y, [f"{r['batch']}  ({r['results']})" for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 0.8)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}. Offer by offer is strict, so it is a minimum. Early batches "
                       "are undercounted, because the ESB lists kept here start after those "
                       "batches.",
              source=f"ECP batch results publications; {LISTS_CREDIT}",
              asof=_d(rep["report_date"]), units="% of batch offers",
              xlabel="Batch offers found on a list (% of the batch's offers)",
              ylabel="Connection batch (results date)")
    return fig


# ---------------------------------------------------------------- external check

def external(rep):
    c = rep["external"]["checks"][0]
    gap = abs(c["diff_mw"])
    topic = "Wind capacity on the lists against the published national total"
    finding = (f"The two publishers' lists add up to {c['ours_mw']:,.0f} MW against "
               f"{c['theirs_mw']:,.0f} MW published, {gap:.0f} MW ({abs(c['diff_pct']):.1%}) "
               f"{'short' if c['diff_mw'] < 0 else 'over'}.")
    fig, ax = new_figure(2.3, bars=True)
    ax.barh(0, c["tso_mw"], height=0.56, color=NAVY)
    ax.barh(0, c["dso_mw"], left=c["tso_mw"], height=0.56, color=GREY, edgecolor="white",
            linewidth=1)
    ax.barh(1, c["theirs_mw"], height=0.56, color=BLUE)
    ax.text(c["tso_mw"] / 2, 0, f"EirGrid {c['tso_mw']:,.0f}", ha="center", va="center",
            fontsize=LABEL, color="white")
    ax.text(c["tso_mw"] + c["dso_mw"] / 2, 0, f"ESB {c['dso_mw']:,.0f}", ha="center",
            va="center", fontsize=LABEL, color="white")
    ax.text(c["ours_mw"] + 40, 0, f"{c['ours_mw']:,.0f} MW", va="center", fontsize=LABEL,
            color=TEXT)
    ax.text(c["theirs_mw"] + 40, 1, f"{c['theirs_mw']:,.0f} MW", va="center", fontsize=LABEL,
            color=TEXT)
    ax.set_yticks([0, 1], [f"On the lists,\nend {c['as_of'][:4]}", "Published\nnational total"])
    ax.invert_yaxis()
    ax.set_xlim(0, c["theirs_mw"] * 1.25)
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}: MW, {c['label'][0].lower()}{c['label'][1:]}, "
                       f"{fmt_date(_d(c['as_of']))}. The published figure comes from SEAI, which "
                       "draws on EirGrid and ESB data, so this checks our reading of the lists, "
                       "not the lists themselves.",
              source=f"{LISTS_CREDIT}: EirGrid connected wind list ({c['tso_edition']}) and ESB "
                     f"energised renewable list ({c['dso_edition']}); {c['source']}. "
                     f"Checked {c['checked_on']}",
              asof=_d(c["checked_on"]), units="MW",
              xlabel="Installed wind capacity (MW)", ylabel="Source")
    return fig


# ---------------------------------------------------------------- what counts as capacity

def firm(rep):
    f = rep["firm_capacity"]
    classes = f["classes"]
    t = f["totals"]["latest"]
    topic = f"Share of contracted MW that counts as capacity in the {f['latest_year']} auction"
    finding = (f"{t['low_mw'] / 1000:.2f} to {t['high_mw'] / 1000:.2f} GW of the queue counts, "
               f"and gas turbines are {f['gas_share_low']:.0%} to {f['gas_share_high']:.0%} of "
               "that.")
    fig, ax = new_figure(3.3, bars=True)
    y = list(range(len(classes)))
    for yi, c in zip(y, classes, strict=True):
        lo, hi = c["latest"]["low_share"], c["latest"]["high_share"]
        ax.barh(yi, lo, height=0.6, color=NAVY)
        if hi > lo:
            ax.barh(yi, hi - lo, left=lo, height=0.6, color=BLUE, alpha=0.5)
            note = f"{lo:.0%} to {hi:.0%} by duration ({f['storage_hours']['low']} to " \
                   f"{f['storage_hours']['high']} hours)"
        else:
            note = f"{lo:.0%}"
        ax.text(hi + 0.01, yi, f"{note} · {c['nameplate_mw'] / 1000:.2f} GW on the lists, "
                f"{c['projects']} project{'' if c['projects'] == 1 else 's'}", va="center",
                fontsize=SMALL, color=TEXT)
    ax.set_yticks(y, [c["label"] for c in classes])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.7)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    frame_fit(fig, ax, title=finding,
              subtitle=f"{topic}: the capacity auction counts each MW only by how reliably it is "
                       f"available. {f['left_alone_mw'] / 1000:.2f} GW "
                       f"({f['left_alone_share']:.0%} of the queue) has no published rating: "
                       "hybrids, the interconnector to France, emergency generation, combined "
                       "heat and power and smaller technologies.",
              source=f"{LISTS_CREDIT}; SEM capacity auction de-rating factors for "
                     f"{f['latest_year']}; {_as_of(rep)}",
              asof=_newest(rep), units="% of contracted MW",
              xlabel="Contracted MW that counts as firm capacity (% of MW)",
              ylabel="Technology class")
    return fig


# ---------------------------------------------------------------- the queue against the plan

def plan(rep):
    q = rep["queue_vs_plan"]
    g, s, n = q["gas"], q["storage"], q["need"]
    bars = [
        ("Gas turbines on the lists, no emergency units", g["queue_mw"], NAVY),
        (f"Gas: awarded in auctions, not operating yet ({g['year']})", g["awarded_mw"], BLUE),
        (f"Gas: expected to deliver ({g['year']})", g["expected_mw"], BLUE),
        ("Batteries on the contracted lists", s["queue_mw"], NAVY),
        (f"Storage added, {s['from_year']} to {s['to_year']}", s["added_mw"], BLUE),
    ]
    fig, ax = new_figure(2.9, bars=True)
    y = [0, 1, 2, 3.5, 4.5]  # the gap separates gas from storage
    for yi, (_, mw, colour) in zip(y, bars, strict=True):
        ax.barh(yi, mw, height=0.6, color=colour)
        ax.text(mw + 25, yi, f"{mw:,.0f} MW", va="center", fontsize=LABEL, color=TEXT)
    ax.set_yticks(y, [b[0] for b in bars])
    ax.invert_yaxis()
    ax.set_xlim(0, max(b[1] for b in bars) * 1.18)
    title = (f"The adequacy assessment expects {g['expected_mw']:,.0f} MW of new gas and adds "
             f"{s['added_mw']:,.0f} MW of storage; the lists hold {g['queue_mw']:,.0f} MW and "
             f"{s['queue_mw']:,.0f} MW")
    frame_fit(fig, ax, title=title,
              subtitle=f"The shortfall in its cautious case, around {n['deficit_start_mw']:,.0f} "
                       f"MW to over {n['deficit_end_mw']:,.0f} MW in {n['deficit_end_year']}, is "
                       f"{n['deficit_share_low']:.0%} to {n['deficit_share_high']:.0%} of what "
                       "the queue counts for. The assessment's deliveries come from the same "
                       "projects the lists hold, so the two should not be added. Navy: on the "
                       "contracted lists; blue: what the assessment assumes.",
              source=f"{q['source']['name']}, read {q['source']['checked_on']}; {LISTS_CREDIT}; "
                     f"{_as_of(rep)}",
              asof=_newest(rep), units="MW", xlabel="Capacity (MW)", ylabel="Series")
    return fig


# ---------------------------------------------------------------- scoring the plan

def _edition(name: str) -> str:
    return name.replace("GCS", "Capacity statement").replace("AIRAA", "Adequacy assessment")


def score(rep):
    p = rep["plan_score"]
    scored = [y for y in p["years"] if y["scored"] and y["editions"]]
    y = scored[-1]
    bars = [(f"Arrived by the end of {y['year']} (a minimum)", y["observed_mw"], NAVY)]
    bars += [(f"{_edition(e['edition'])} expected", e["expected_mw"], BLUE) for e in y["editions"]]
    bars += [(f"{_edition(e['edition'])}: if all awards arrived on time", e["naive_mw"], GREY)
             for e in y["editions"] if e["naive_mw"] is not None]
    fig, ax = new_figure(2.9, bars=True)
    ys = list(range(len(bars)))
    for yi, (_, mw, colour) in zip(ys, bars, strict=True):
        ax.barh(yi, mw, height=0.6, color=colour)
        ax.text(mw + 15, yi, f"{mw:,.0f} MW", va="center", fontsize=LABEL, color=TEXT)
    ax.set_yticks(ys, [b[0] for b in bars])
    ax.invert_yaxis()
    ax.set_xlim(0, max(b[1] for b in bars) * 1.15)
    expected = [e["expected_mw"] for e in y["editions"]]
    title = (f"At least {y['observed_mw']:,.0f} MW of new conventional plant had arrived by the "
             f"end of {y['year']}; the grid operators' reports expected {min(expected):,.0f} to "
             f"{max(expected):,.0f} MW")
    open_year = next((o for o in p["years"] if not o["scored"] and o["editions"]), None)
    needs = "" if open_year is None else (
        f" By the end of {open_year['year']}, still open, the reports need "
        f"{min(e['still_needs_mw'] for e in open_year['editions']):,.0f} to "
        f"{max(e['still_needs_mw'] for e in open_year['editions']):,.0f} MW more.")
    frame_fit(fig, ax, title=title,
              subtitle="Each report is scored only on years after it was written. Arrived is a "
                       f"minimum, because EirGrid's lists can't date a transmission connection.{needs}",
              source=f"EirGrid and SONI capacity statements and adequacy assessments; "
                     f"{LISTS_CREDIT}; lists to {p['as_of']}",
              asof=_d(p["as_of"]), units="MW",
              xlabel=f"Rated capacity, cumulative from the start of {p['start_year']} (MW)",
              ylabel="Series")
    return fig


CHARTS = {
    "technology": technology, "history": history, "flows": flows, "burndown": burndown,
    "map": grid_map, "counties": counties, "freshness": freshness, "left": left,
    "pace-dso": pace_dso, "pace-tso": pace_tso, "slippage": slippage, "funnel": funnel,
    "external": external, "firm": firm, "plan": plan, "score": score,
}


def build_all(report: Path, out_dir: Path = OUT) -> list[Path]:
    """Draw every chart; write <name>.pdf, .png and .tex. Returns the PNG paths."""
    rep = json.loads(report.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, draw in CHARTS.items():
        files = ps.save(draw(rep), out_dir / name, formats=FORMATS)
        written.append(next(p for p in files if p.suffix == ".png"))
    return written


def main(argv: list[str]) -> None:
    report = Path(argv[1]) if len(argv) > 1 else newest_report()
    out_dir = Path(argv[2]) if len(argv) > 2 else OUT
    for path in build_all(report, out_dir):
        print(f"wrote {path.relative_to(store.ROOT) if path.is_relative_to(store.ROOT) else path}")


if __name__ == "__main__":
    main(sys.argv)
