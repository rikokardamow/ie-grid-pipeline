"""The README's charts, drawn with matplotlib from the newest weekly report.

    uv run python -m iegrid.readme_charts            # newest data/reports/*.json -> docs/img
    uv run python -m iegrid.readme_charts REPORT.json OUT_DIR

Every number comes from the report JSON, the same file the dashboard reads, so
the two never disagree. House style (energy-forecasting docs/charts.md): the
title states the finding and is computed from the data, the subtitle gives the
units, one muted footer names the sources and the as-of dates. Transmission is
navy, distribution grey, a highlight is blue; no legend boxes, the series are
named where they are drawn. The three colours passed the dataviz validator's
colour-blind and normal-vision checks (navy/grey dE 19, blue/grey 17).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from textwrap import fill

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates
import matplotlib.pyplot as plt
import matplotlib.ticker
from matplotlib.patches import Polygon

from iegrid import store
from iegrid.exhibits import TOKENS, _style, fmt_date

NAVY, GREY, BLUE = TOKENS["series1"], TOKENS["series3"], TOKENS["accent"]
TEXT, MUTED, BORDER = TOKENS["text"], TOKENS["muted"], TOKENS["border"]
OUT = store.ROOT / "docs" / "img"
REPORTS = store.ROOT / "data" / "reports"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 9,
    "lines.linewidth": 1.4,
    "axes.unicode_minus": True,
})

LISTS_CREDIT = ("EirGrid contracted lists, Supported by EirGrid Group Data; ESB Networks DSO "
                "lists, © ESB Networks, used with their permission")


def _frame(fig, title: str, subtitle: str, footer: str, xlabel: bool = True) -> None:
    """Title, subtitle and footer, wrapped to the figure's width; the axes' top and
    bottom margins follow from how many lines they take."""
    w, h = fig.get_size_inches()
    tw, sw, fw = fill(title, int(w * 11)), fill(subtitle, int(w * 14.5)), fill(footer, int(w * 18))
    y = 1 - 0.1 / h
    fig.text(0.02, y, tw, ha="left", va="top", fontsize=12, weight="bold", color=TEXT,
             linespacing=1.25)
    y -= (0.23 * (tw.count("\n") + 1) + 0.08) / h
    fig.text(0.02, y, sw, ha="left", va="top", fontsize=9.5, color=MUTED, linespacing=1.4)
    y -= (0.19 * (sw.count("\n") + 1) + 0.25) / h
    fig.text(0.02, 0.08 / h, fw, ha="left", va="bottom", fontsize=8, color=MUTED,
             linespacing=1.4)
    bottom = (0.08 + 0.16 * (fw.count("\n") + 1) + (0.5 if xlabel else 0.12)) / h
    fig.subplots_adjust(top=y, bottom=bottom)


def newest_report() -> Path:
    files = sorted(REPORTS.glob("*.json"))
    if not files:
        raise SystemExit(f"no report in {REPORTS}; run `uv run python -m iegrid.report` first")
    return files[-1]


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _gw(x: float) -> str:
    return f"{x:.2f} GW"


def _fig(w: float, h: float):
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    _style(fig, ax)
    return fig, ax


def _vertical(ax) -> None:
    """Horizontal grid for charts with a value y-axis."""
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=BORDER, linewidth=0.8)
    ax.spines["left"].set_visible(False)


def _as_of(rep) -> str:
    tso, dso = rep["queue"]["by_technology"]["transmission_as_of"], \
        rep["queue"]["by_technology"]["distribution_as_of"]
    return f"As of {fmt_date(_d(tso))} (transmission) and {fmt_date(_d(dso))} (distribution)"


# ---------------------------------------------------------------- what is waiting

def technology(rep):
    t = rep["queue"]["by_technology"]
    groups = t["groups"]
    top = groups[0]
    title = "Generation contracted to connect, by technology"
    finding = (f"{t['total_gw']:.2f} GW has signed to connect; {top['group'].lower()} is "
               f"{t['top_share']:.0%} of it.")
    fig, ax = _fig(10, 4.8)
    y = list(range(len(groups)))
    tso = [g["transmission_gw"] for g in groups]
    dso = [g["distribution_gw"] for g in groups]
    ax.barh(y, tso, height=0.62, color=NAVY)
    ax.barh(y, dso, left=tso, height=0.62, color=GREY, edgecolor="white", linewidth=2)
    for yi, a, b in zip(y, tso, dso, strict=True):
        split = f"   {a:.2f} + {b:.2f}" if b >= 0.005 else ""
        ax.text(a + b + 0.08, yi, f"{a + b:.2f} GW{split}", va="center", fontsize=9.5, color=TEXT)
    ax.set_yticks(y, [g["group"] for g in groups])
    ax.invert_yaxis()
    ax.set_xlim(0, max(a + b for a, b in zip(tso, dso, strict=True)) * 1.6)
    ax.set_xlabel("GW contracted, not yet energised", color=MUTED, fontsize=9.5)
    ax.text(tso[0] / 2, -0.55, "transmission (EirGrid)", ha="center", fontsize=8.5, color=TEXT)
    ax.text(tso[0] + dso[0] / 2, -0.55, "distribution (ESB Networks)", ha="center", fontsize=8.5,
            color=TEXT)
    fig.subplots_adjust(left=0.19, right=0.97)
    _frame(fig, title, f"GW of maximum export capacity not yet energised. {finding} The "
           "figures on the right split each bar into transmission and distribution.",
           f"Source: {LISTS_CREDIT}. {_as_of(rep)}.")
    return fig


def history(rep):
    h = rep["queue"]["history"]
    nonwind = [(_d(p["as_of"]), p["gw"]) for p in h["nonwind"]]
    wind = [(_d(p["as_of"]), p["gw"]) for p in h["wind"]]
    n0, n1 = nonwind[0], nonwind[-1]
    title = "Contracted capacity on the transmission grid, every list since 2015"
    finding = (f"Non-wind grew from {n0[1]:.2f} GW in {n0[0].year} to {n1[1]:.2f} GW; "
               f"wind is {wind[-1][1]:.2f} GW.")
    fig, ax = _fig(10, 5)
    _vertical(ax)
    top = max(max(p[1] for p in nonwind), max(p[1] for p in wind))
    for b in h["batches"]:
        d = _d(b["results"])
        ax.axvline(d, color=BORDER, linewidth=1, linestyle="--", zorder=1)
        ax.text(d, top * 1.04, b["batch"], ha="center", va="bottom", fontsize=8.5, color=MUTED)
    for pts, colour, name in ((nonwind, NAVY, "non-wind"), (wind, GREY, "wind")):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        ax.plot(xs, ys, color=colour, linewidth=2, zorder=3)
        ax.scatter(xs, ys, s=12, color=colour, zorder=4, edgecolors="white", linewidths=1)
        ax.scatter(xs[-1:], ys[-1:], s=60, color=colour, zorder=5, edgecolors="white",
                   linewidths=2)
        ax.annotate(f"{name}, {ys[-1]:.2f} GW", (xs[-1], ys[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=8.5, color=TEXT)
    ax.set_ylim(0, top * 1.14)
    ax.set_xlim(date(n0[0].year, 1, 1), date(n1[0].year + 2, 7, 1))
    ax.set_xticks([date(y, 1, 1) for y in range(n0[0].year + 1, n1[0].year + 1, 2)])
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y"))
    ax.set_ylabel("GW contracted, not yet energised", color=MUTED, fontsize=9.5)
    fig.subplots_adjust(left=0.07, right=0.97)
    _frame(fig, title, f"GW printed on each EirGrid contracted list, {len(nonwind)} non-wind "
           f"and {len(wind)} wind editions since {n0[0]:%B %Y}. {finding} Dashed rules mark "
           "when each connection batch (ECP) got its results.",
           "Source: EirGrid TSO contracted wind and non-wind lists, read from eirgrid.ie and the "
           f"Internet Archive. Supported by EirGrid Group Data. As of {fmt_date(n1[0])}")
    return fig


# ---------------------------------------------------------------- what moved

def flows(rep):
    rows = rep["moved"]["by_year"]
    last_year = rows[-1]["year"]
    full = [r for r in rows if r["year"] < last_year]
    best = max(full, key=lambda r: r["joined_gw"])
    title = "Capacity joining and leaving the transmission lists, by year"
    finding = (f"{best['year']} was the biggest year for joining: {best['joined_gw']:.2f} GW "
               f"joined and {best['left_gw']:.2f} GW left.")
    fig, ax = _fig(10, 4.8)
    _vertical(ax)
    xs = list(range(len(rows)))
    w = 0.38
    jv = [r["joined_gw"] for r in rows]
    lv = [r["left_gw"] for r in rows]
    ax.bar([x - w / 2 - 0.01 for x in xs], jv, width=w, color=NAVY)
    ax.bar([x + w / 2 + 0.01 for x in xs], lv, width=w, color=GREY)
    for x, a, b in zip(xs, jv, lv, strict=True):
        ax.text(x - w / 2, a + 0.06, f"{a:.1f}", ha="center", fontsize=8, color=TEXT)
        ax.text(x + w / 2, b + 0.06, f"{b:.1f}", ha="center", fontsize=8, color=MUTED)
    labels = [f"{r['year']}\nso far" if r["year"] == last_year else str(r["year"]) for r in rows]
    ax.set_xticks(xs, labels)
    ax.set_ylabel("GW", color=MUTED, fontsize=9.5)
    top = max(jv + lv)
    ax.set_ylim(0, top * 1.2)
    ax.text(xs[0] - w / 2, top * 1.1, "joined the list (navy)", color=TEXT, fontsize=8.5)
    ax.text(xs[0] + 1.6, top * 1.1, "left the list (grey)", color=TEXT, fontsize=8.5)
    fig.subplots_adjust(left=0.07, right=0.97)
    _frame(fig, title, f"GW, each EirGrid contracted list against the one before. {finding} "
           "A project leaves when it is connected, withdrawn or moved; the lists do not say which.",
           f"Source: EirGrid TSO contracted lists, Supported by EirGrid Group Data · "
           f"As of {fmt_date(_d(rep['queue']['by_technology']['transmission_as_of']))}")
    return fig


# ---------------------------------------------------------------- what is stuck

def burndown(rep):
    s = rep["stuck"]
    rows = s["burndown"]
    years = s["at_years"]
    first = rows[0]
    later = [r for r in rows[1:] if r["share_at"] is not None]
    title = f"Share of each connection batch energised {years} years after its results"
    finding = (f"{first['batch']} had {first['share_at']:.0%} of its distribution MW energised "
               f"at that age; no later batch passed {max(r['share_at'] for r in later):.0%}.")
    fig, ax = _fig(10, 4.4)
    y = list(range(len(rows)))
    for yi, r in zip(y, rows, strict=True):
        if r["share_at"] is None:
            ax.text(0.005, yi, f"too young: results {r['results']}, {r['age_months']} months ago",
                    va="center", fontsize=9, color=MUTED)
        else:
            ax.barh(yi, r["share_at"], height=0.6, color=NAVY)
            ax.text(r["share_at"] + 0.004, yi, f"{r['share_at']:.1%} of {r['projects']} projects",
                    va="center", fontsize=9.5, color=TEXT)
    ax.set_yticks(y, [f"{r['batch']}  ({r['results']})" for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, max(r["share_at"] or 0 for r in rows) * 1.9)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel(f"share of the batch's distribution MW energised {years} years after results",
                  color=MUTED, fontsize=9.5)
    fig.subplots_adjust(left=0.22, right=0.97)
    _frame(fig, title, f"By MW, distribution grid only. {finding} Comparing batches at the "
           "same age means an older batch gets no credit for having had longer.",
           f"Source: ESB Networks DSO contracted and energised lists, © ESB Networks, used with "
           f"their permission. As of {fmt_date(_d(s['as_of']))}")
    return fig


# ---------------------------------------------------------------- where

def counties(rep):
    rows = rep["where"]["counties"]
    top = rows[0]
    share3 = sum(r["gw"] for r in rows[:3]) / sum(r["gw"] for r in rows)
    title = "Contracted generation by county"
    finding = (f"{top['county']} holds the most, {top['gw']:.2f} GW; three counties hold "
               f"{share3:.0%} of what is placed.")
    fig, ax = _fig(10, 7.6)
    y = list(range(len(rows)))
    ax.barh(y, [r["gw"] for r in rows], height=0.66, color=NAVY)
    for yi, r in zip(y, rows, strict=True):
        ax.text(r["gw"] + 0.03, yi, f"{r['gw']:.2f}", va="center", fontsize=8.5, color=TEXT)
    ax.set_yticks(y, [r["county"] for r in rows], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, top["gw"] * 1.18)
    ax.set_xlabel("GW contracted, not yet energised", color=MUTED, fontsize=9.5)
    fig.subplots_adjust(left=0.12, right=0.97)
    _frame(fig, title, f"GW, transmission and distribution together, interconnectors left out. "
           f"{finding} {rep['where']['generation_placed_share']:.0%} of generation MW is placed "
           "in a county.",
           f"Source: {LISTS_CREDIT}; ECP results; substations © OpenStreetMap contributors (ODbL) "
           f"· {_as_of(rep)}")
    return fig


def grid_map(rep):
    g = rep["grid"]
    kv = "/".join(str(k) for k in g["backbone_kv"])
    title = "Contracted capacity by connection substation"
    finding = (f"{g['far_gw']:.2f} GW waits at {g['far_nodes']} substations {g['far_km']} km or "
               f"more from the {kv} kV network.")
    fig, ax = plt.subplots(figsize=(8.5, 10), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_axis_off()
    for ring in g["outline"]:
        ax.add_patch(Polygon(ring, closed=True, facecolor="none", edgecolor=GREY,
                             linewidth=0.6, zorder=1))
    for line in g["lines"]:
        xs, ys = zip(*line["path"], strict=True)
        heavy = line["kv"] >= 220
        ax.plot(xs, ys, color=GREY if heavy else BORDER, linewidth=0.9 if heavy else 0.45,
                zorder=2 if heavy else 1.5, solid_capstyle="round")
    nodes = sorted(g["nodes"], key=lambda n: -n["mw"])
    far = [n for n in nodes if n["km_backbone"] >= g["far_km"]]
    near = [n for n in nodes if n["km_backbone"] < g["far_km"]]
    scale = 1.6
    for group, colour in ((near, NAVY), (far, BLUE)):
        ax.scatter([n["lon"] for n in group], [n["lat"] for n in group],
                   s=[n["mw"] * scale for n in group], color=colour, alpha=0.55,
                   edgecolors="white", linewidths=0.8, zorder=4)
    for n in nodes[:4]:
        ax.annotate(f"{n['node'].split(' ')[0]}  {n['mw']:.0f} MW", (n["lon"], n["lat"]),
                    xytext=(6, 4), textcoords="offset points", fontsize=8, color=TEXT, zorder=6)
    ax.set_aspect(1 / 0.595)  # cos(53.5°): a kilometre is a kilometre in both directions
    ax.set_xlim(-10.8, -5.2)
    ax.set_ylim(51.3, 55.5)
    # in-plot key, top left
    kx, ky = -10.7, 55.35
    for i, (colour, label) in enumerate(((NAVY, f"substation under {g['far_km']} km from the backbone"),
                                         (BLUE, f"substation {g['far_km']} km or more away"))):
        ax.scatter([kx], [ky - i * 0.17], s=60, color=colour, alpha=0.7, edgecolors="white")
        ax.text(kx + 0.12, ky - i * 0.17, label, va="center", fontsize=9, color=TEXT)
    ax.plot([kx - 0.05, kx + 0.05], [ky - 0.34] * 2, color=GREY, linewidth=1.2)
    ax.text(kx + 0.12, ky - 0.34, "220, 275 and 400 kV lines", va="center", fontsize=9, color=TEXT)
    ax.plot([kx - 0.05, kx + 0.05], [ky - 0.51] * 2, color=BORDER, linewidth=0.7)
    ax.text(kx + 0.12, ky - 0.51, "110 kV lines", va="center", fontsize=9, color=TEXT)
    ax.text(kx, ky - 0.72, "Circle area is MW waiting at the substation", fontsize=9, color=MUTED)
    # distance bands, bottom right
    bx, by = -7.9, 52.0
    ax.text(bx, by, "GW waiting, by distance to the backbone", fontsize=9, color=TEXT)
    for i, b in enumerate(g["bands"]):
        ax.text(bx, by - 0.14 * (i + 1), f"{b['label']:<16}", fontsize=9, color=MUTED,
                family="monospace")
        ax.text(bx + 1.25, by - 0.14 * (i + 1), f"{b['gw']:.2f} GW at {b['nodes']} substations",
                fontsize=9, color=TEXT)
    fig.subplots_adjust(left=0.02, right=0.98)
    _frame(fig, title, f"Circle area is MW waiting at the substation, on OpenStreetMap's lines, "
           f"all-island. {finding} {g['placed_gw']:.2f} GW ({g['placed_share']:.0%}) of the queue "
           "is on the map; a station OpenStreetMap does not have yet is drawn at the existing "
           "station its ECP results name, at a cited site, or at its townland.",
           f"Source: {LISTS_CREDIT}; lines and substations © OpenStreetMap contributors (ODbL), "
           f"fetched {g['osm_fetched_at'][:10]}. {_as_of(rep)}.", xlabel=False)
    return fig


# ---------------------------------------------------------------- how fresh

def freshness(rep):
    rows = rep["freshness"]
    tso = [r["days"] for r in rows if r["list"].startswith("EirGrid")]
    dso = [r["days"] for r in rows if r["list"].startswith("ESB")]
    title = "Days from each list's as-of date to its publication"
    finding = (f"EirGrid posts its lists about {round(sum(tso) / len(tso))} days after their "
               f"as-of date and ESB Networks about {round(sum(dso) / len(dso))}.")
    fig, ax = _fig(10, 4)
    y = list(range(len(rows)))
    days = [r["days"] for r in rows]
    ax.hlines(y, 0, days, color=BORDER, linewidth=2)
    ax.scatter(days, y, s=64, color=[NAVY if r["list"].startswith("EirGrid") else GREY for r in rows],
               zorder=3, edgecolors="white", linewidths=2)
    for yi, r in zip(y, rows, strict=True):
        ax.text(r["days"] + 0.8, yi, f"{r['days']} days · as of {fmt_date(_d(r['as_of']))}, "
                f"published {fmt_date(_d(r['published']))}", va="center", fontsize=9, color=TEXT)
    ax.set_yticks(y, [r["list"] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, max(days) * 1.9)
    ax.set_xlabel("days from the list's as-of date to its publication", color=MUTED, fontsize=9.5)
    fig.subplots_adjust(left=0.25, right=0.97)
    _frame(fig, title, f"{finding} So a weekly report built on these lists shows the "
           "distribution grid about a month late. Publication is the server's Last-Modified time.",
           f"Source: {LISTS_CREDIT}. Report of {fmt_date(_d(rep['report_date']))}")
    return fig


# ---------------------------------------------------------------- what became of the leavers

def left(rep):
    lo = rep["left_outcomes"]
    rows = lo["by_outcome"]
    connected = sum(r["count"] for r in rows if r["outcome"].startswith("connected")
                    or "connected" in r["outcome"] and "not" not in r["outcome"])
    unknown = next(r["count"] for r in rows if r["outcome"] == "unknown")
    title = "What became of the projects that left the contracted lists"
    finding = (f"{lo['total']} projects ({lo['total_gw']:.2f} GW) left for good: {connected} "
               f"connected one way or another, {unknown} unknown.")
    fig, ax = _fig(10, 4.8)
    y = list(range(len(rows)))
    colours = [GREY if r["outcome"] in ("unknown", "not on a connected list") or
               r["outcome"].startswith("not connected") else NAVY for r in rows]
    ax.barh(y, [r["count"] for r in rows], height=0.62, color=colours)
    for yi, r in zip(y, rows, strict=True):
        ax.text(r["count"] + 0.5, yi, f"{r['count']} projects · {r['gw'] * 1000:.0f} MW",
                va="center", fontsize=9.5, color=TEXT)
    ax.set_yticks(y, [r["outcome"].replace(" (sourced)", "") for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, max(r["count"] for r in rows) * 1.45)
    ax.set_xlabel("projects", color=MUTED, fontsize=9.5)
    fig.subplots_adjust(left=0.36, right=0.97)
    _frame(fig, title, f"Projects, by what EirGrid's connected lists say (wind only, to "
           f"{fmt_date(_d(lo['cover_end']))}). {finding} Navy: a connection is on record. Grey: "
           "not connected, or unknown, which is never read as not connected.",
           f"Source: EirGrid contracted and connected lists, Supported by EirGrid Group Data; "
           f"planning sources cited in src/iegrid/data/resolutions.csv · "
           f"Report of {fmt_date(_d(rep['report_date']))}")
    return fig


# ---------------------------------------------------------------- pace

def _pace(rep, key, grid_name, source):
    p = rep["delivery_pace"][key]
    rows = p["annual"]
    cover3 = next(c for c in p["cover"] if c["window"] == 3)
    fastest = p["fastest"][0]
    title = f"MW energised each year, {grid_name}"
    finding = (f"At the {cover3['from']}–{cover3['to']} pace the {p['queue_mw'] / 1000:.2f} GW "
               f"queue is {cover3['years']:.1f} years of delivery; at the fastest three years "
               f"({fastest['from']}–{fastest['to']}), {fastest['years']:.1f}.")
    fig, ax = _fig(10, 4.8)
    _vertical(ax)
    xs = [r["year"] for r in rows]
    ax.bar(xs, [r["mw"] for r in rows], width=0.72, color=NAVY)
    for r in rows:
        ax.text(r["year"], r["mw"] + max(x["mw"] for x in rows) * 0.015, f"{r['mw']:.0f}",
                ha="center", fontsize=8, color=TEXT)
    mean_label = f"{cover3['from']}–{cover3['to']} mean, {c_pace(cover3)} MW a year"
    fast_label = f"fastest three years, {c_pace(fastest)} MW a year"
    for c, colour, label in ((cover3, GREY, mean_label), (fastest, BLUE, fast_label)):
        ax.hlines(c["pace_mw"], xs[0] - 0.5, xs[-1] + 0.5, color=colour, linestyle="--",
                  linewidth=1.5, zorder=4)
        ax.text(xs[-1] + 0.55, c["pace_mw"], label, va="center", fontsize=8.5, color=TEXT)
    ax.set_xticks(xs[::2] if len(xs) > 10 else xs)
    ax.set_xlim(xs[0] - 0.6, xs[-1] + 0.6)
    ax.set_ylabel("MW energised", color=MUTED, fontsize=9.5)
    fig.subplots_adjust(left=0.07, right=0.72)
    _frame(fig, title, f"MW, {xs[0]} to {p['through']}. {finding} Years of delivery is the "
           "contracted MW divided by the mean pace of the window, not a forecast of when the "
           "queue clears: most contracted MW never energises.",
           f"Source: {source}. As of {fmt_date(_d(p['as_of']))}")
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
    title = "Months from the target connection month to completion, wind projects"
    finding = (f"{s['late_to_completion']} of {s['matched']} projects with a published target "
               f"connected after it, by a median of {s['median_to_completion']:.0f} months.")
    fig, ax = _fig(10, 6)
    y = list(range(len(rows)))
    months = [r["to_completion"] for r in rows]
    ax.hlines(y, 0, months, color=BORDER, linewidth=2)
    ax.scatter(months, y, s=56, color=NAVY, zorder=3, edgecolors="white", linewidths=1.5)
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.axvline(s["median_to_completion"], color=BLUE, linestyle="--", linewidth=1.5)
    ax.text(s["median_to_completion"] + 0.6, -0.9, f"median {s['median_to_completion']:.1f} months",
            color=TEXT, fontsize=8.5)
    for yi, r in zip(y, rows, strict=True):
        ax.text(max(r["to_completion"], 0) + 1.2, yi,
                f"{r['to_completion']:+d} months · {r['mw']:.0f} MW · target {r['target']}",
                va="center", fontsize=8.5, color=TEXT)
    ax.set_yticks(y, [r["name"] for r in rows], fontsize=9)
    ax.invert_yaxis()
    lo, hi = min(months + [0]), max(months)
    ax.set_xlim(lo - 4, hi + 34)
    ax.set_xlabel("months from the target connection month to completion (positive = late)",
                  color=MUTED, fontsize=9.5)
    fig.subplots_adjust(left=0.27, right=0.97)
    _frame(fig, title, f"Months between the target month EirGrid printed in its earliest lists "
           f"and the project's connected-list entry. {finding} {s['with_target']} projects had a "
           f"target and {s['matched']} can be followed to a connection. A record of what happened "
           "to these projects, not a rate to apply to others.",
           "Source: EirGrid contracted and connected wind lists, Supported by EirGrid Group Data · "
           f"Report of {fmt_date(_d(rep['report_date']))}")
    return fig


# ---------------------------------------------------------------- offer to list

def funnel(rep):
    rows = rep["funnel"]["batches"]
    shares = [r["share_found_mw"] for r in rows]
    title = "Share of each connection batch's offers that reached a contracted list"
    finding = (f"{min(shares):.0%} to {max(shares):.0%} of what each batch offered has ever "
               "appeared on a list, by MW.")
    fig, ax = _fig(10, 4.8)
    y = list(range(len(rows)))
    w = 0.36
    ax.barh([yi - w / 2 - 0.01 for yi in y], [r["share_found_mw"] for r in rows], height=w,
            color=NAVY)
    ax.barh([yi + w / 2 + 0.01 for yi in y], [r["share_tagged"] for r in rows], height=w,
            color=GREY)
    for yi, r in zip(y, rows, strict=True):
        ax.text(r["share_found_mw"] + 0.01, yi - w / 2, f"{r['share_found_mw']:.0%} by MW, "
                f"{r['found']} of {r['offered']} offers matched", va="center", fontsize=8.5,
                color=TEXT)
        ax.text(r["share_tagged"] + 0.01, yi + w / 2, f"{r['share_tagged']:.0%} by the lists' own "
                "batch tags", va="center", fontsize=8.5, color=MUTED)
    ax.set_yticks(y, [f"{r['batch']}  ({r['results']})" for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.0)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("share of the batch's offers found on a list", color=MUTED, fontsize=9.5)
    fig.subplots_adjust(left=0.22, right=0.97)
    _frame(fig, title, f"{finding} Two independent counts: matching each offer to a list row by "
           "name and size (strict, so a lower bound), and the batch tags the lists print. ESB's "
           "lists in the store start long after the early batches, so those are undercounted.",
           f"Source: ECP batch results publications; {LISTS_CREDIT} · "
           f"Report of {fmt_date(_d(rep['report_date']))}")
    return fig


# ---------------------------------------------------------------- external check

def external(rep):
    c = rep["external"]["checks"][0]
    gap = abs(c["diff_mw"])
    title = "Wind capacity on the lists against the published national total"
    finding = (f"The two publishers' lists add up to {c['ours_mw']:,.0f} MW against "
               f"{c['theirs_mw']:,.0f} MW published, {gap:.0f} MW ({abs(c['diff_pct']):.1%}) "
               f"{'short' if c['diff_mw'] < 0 else 'over'}.")
    fig, ax = _fig(10, 3.6)
    ax.barh(0, c["tso_mw"], height=0.56, color=NAVY)
    ax.barh(0, c["dso_mw"], left=c["tso_mw"], height=0.56, color=GREY, edgecolor="white",
            linewidth=2)
    ax.barh(1, c["theirs_mw"], height=0.56, color=BLUE)
    ax.text(c["tso_mw"] / 2, 0, f"EirGrid {c['tso_mw']:,.0f}", ha="center", va="center",
            fontsize=9, color="white")
    ax.text(c["tso_mw"] + c["dso_mw"] / 2, 0, f"ESB {c['dso_mw']:,.0f}", ha="center", va="center",
            fontsize=9, color="white")
    ax.text(c["ours_mw"] + 40, 0, f"{c['ours_mw']:,.0f} MW", va="center", fontsize=9.5, color=TEXT)
    ax.text(c["theirs_mw"] + 40, 1, f"{c['theirs_mw']:,.0f} MW", va="center", fontsize=9.5,
            color=TEXT)
    ax.set_yticks([0, 1], [f"On the lists, end {c['as_of'][:4]}", "Published national total"])
    ax.invert_yaxis()
    ax.set_xlim(0, c["theirs_mw"] * 1.25)
    ax.set_xlabel("MW of installed wind capacity", color=MUTED, fontsize=9.5)
    fig.subplots_adjust(left=0.24, right=0.97)
    _frame(fig, title, f"MW, {c['label'].lower()}, {fmt_date(_d(c['as_of']))}. {finding} The "
           "published figure comes from SEAI, which draws on EirGrid and ESB data, so this checks "
           "our reading of the lists, not the lists themselves.",
           f"Source: EirGrid connected wind list ({c['tso_edition']}); ESB energised renewable list "
           f"({c['dso_edition']}); {c['source']}. Checked {c['checked_on']}")
    return fig


# ---------------------------------------------------------------- what counts as capacity

def firm(rep):
    f = rep["firm_capacity"]
    classes = f["classes"]
    t = f["totals"]["latest"]
    title = f"Share of contracted MW that counts as capacity in the {f['latest_year']} auction"
    finding = (f"{t['low_mw'] / 1000:.2f} to {t['high_mw'] / 1000:.2f} GW of the queue counts, "
               f"and gas turbines are {f['gas_share_low']:.0%} to {f['gas_share_high']:.0%} of that.")
    fig, ax = _fig(10, 4.4)
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
                f"{c['projects']} projects", va="center", fontsize=9, color=TEXT)
    ax.set_yticks(y, [c["label"] for c in classes])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.45)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("share of contracted MW that counts as firm capacity", color=MUTED, fontsize=9.5)
    fig.subplots_adjust(left=0.25, right=0.97)
    _frame(fig, title, f"The de-rating factors the system operators publish, applied at each "
           f"project's size. {finding} {f['left_alone_mw'] / 1000:.2f} GW "
           f"({f['left_alone_share']:.0%} of the queue) has no factor: hybrids, interconnectors, "
           "combined heat and power and smaller technologies.",
           f"Source: {LISTS_CREDIT}; SEM capacity auction de-rating factors for {f['latest_year']} · "
           f"{_as_of(rep)}")
    return fig


# ---------------------------------------------------------------- the queue against the plan

def plan(rep):
    q = rep["queue_vs_plan"]
    g, s, n = q["gas"], q["storage"], q["need"]
    bars = [
        ("Gas turbines on the contracted lists", g["queue_mw"], NAVY),
        (f"Gas: awarded in auctions, not operating yet ({g['year']})", g["awarded_mw"], BLUE),
        (f"Gas: expected to deliver ({g['year']})", g["expected_mw"], BLUE),
        ("Batteries on the contracted lists", s["queue_mw"], NAVY),
        (f"Storage added, {s['from_year']} to {s['to_year']}", s["added_mw"], BLUE),
    ]
    fig, ax = _fig(10, 4.2)
    y = list(range(len(bars)))
    for yi, (_, mw, colour) in zip(y, bars, strict=True):
        ax.barh(yi, mw, height=0.6, color=colour)
        ax.text(mw + 25, yi, f"{mw:,.0f} MW", va="center", fontsize=9, color=TEXT)
    ax.set_yticks(y, [b[0] for b in bars])
    ax.invert_yaxis()
    ax.set_xlim(0, max(b[1] for b in bars) * 1.18)
    ax.set_xlabel("MW (dark: the contracted lists; light: what the assessment assumes)", color=MUTED, fontsize=9.5)
    fig.subplots_adjust(left=0.40, right=0.97)
    title = (f"The adequacy assessment expects {g['expected_mw']:,.0f} MW of new gas and adds "
             f"{s['added_mw']:,.0f} MW of storage; the lists hold {g['queue_mw']:,.0f} MW and "
             f"{s['queue_mw']:,.0f} MW")
    _frame(fig, title,
           f"Its stated secure-case deficit, around {n['deficit_start_mw']:,.0f} MW to over "
           f"{n['deficit_end_mw']:,.0f} MW in {n['deficit_end_year']}, is {n['deficit_share_low']:.0%} to "
           f"{n['deficit_share_high']:.0%} of what the queue counts for. The assessment's deliveries come "
           "from the same projects the lists hold, so the two are not additive.",
           f"Source: {q['source']['name']}, read {q['source']['checked_on']}; {LISTS_CREDIT} · {_as_of(rep)}")
    return fig


CHARTS = {
    "technology": technology, "history": history, "flows": flows, "burndown": burndown,
    "map": grid_map, "counties": counties, "freshness": freshness, "left": left,
    "pace-dso": pace_dso, "pace-tso": pace_tso, "slippage": slippage, "funnel": funnel,
    "external": external, "firm": firm, "plan": plan,
}


def build_all(report: Path, out_dir: Path = OUT) -> list[Path]:
    rep = json.loads(report.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, draw in CHARTS.items():
        fig = draw(rep)
        path = out_dir / f"{name}.png"
        fig.savefig(path, facecolor="white")
        plt.close(fig)
        written.append(path)
    return written


def main(argv: list[str]) -> None:
    report = Path(argv[1]) if len(argv) > 1 else newest_report()
    out_dir = Path(argv[2]) if len(argv) > 2 else OUT
    for path in build_all(report, out_dir):
        print(f"wrote {path.relative_to(store.ROOT) if path.is_relative_to(store.ROOT) else path}")


if __name__ == "__main__":
    main(sys.argv)
