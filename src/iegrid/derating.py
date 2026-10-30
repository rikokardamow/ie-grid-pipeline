"""Layer: the queue counted the way the capacity market counts it. How much of the contracted
nameplate would count as capacity? (docs/layers/09-firm-capacity/README.md)

A contracted MW is nameplate. The Irish capacity auction counts a unit by its de-rated capacity:
its size times a de-rating factor the system operators publish in each T-4 auction's Initial
Auction Information Pack (tables of marginal de-rating factors by technology class and size). A
wind or solar MW counts for about 5%; a 4-hour battery about 15%; an open-cycle gas unit about
75-80%. So 16.7 GW of contracted nameplate is a very different number of capacity.

The factors are data, read from the packs themselves (python -m iegrid.derating <pack.pdf>), each
row with its source, page and the date it was read, in src/iegrid/data/derating.csv. Two auctions
are read (2029/30 and 2030/31) so the result shows how much the answer moves between them.

What it applies, and what it leaves alone, is stated on the page and in the README:

    wind, solar        Table 5, one factor each
    gas turbine class  Table 1's Gas Turbine curve at the unit's size (OCGT, CCGT, gas)
    interconnector     Table 1's Interconnector curve at the unit's size, for an interconnector to Great
                       Britain (Greenlink). The pack says that curve is already adjusted by its external-market
                       factor, so it is applied as printed. The pack treats an interconnector to another EU
                       state (Celtic, to France) as non-participating capacity in the auction: no factor
    battery            Table 3 (other storage) at the unit's size, for 2 and 4 hours of storage:
                       the lists do not say how long a battery lasts, so both are shown
    everything else    no factor applied, listed with its MW: hybrids (a solar-plus-battery
                       project is one MEC, and the pack gives no hybrid class), the EU interconnector,
                       temporary emergency generation (out of market, named TEG on the lists),
                       biomass, hydro, CHP, reciprocating engines, wave, synchronous condensers

The factor is the pack's marginal factor for the unit's size, which is how the pack tells an
applicant to use it. It is a statement about the auction's rules, not a forecast that a
project will connect, and not a measure of what a MW delivers in a given hour.
"""

from __future__ import annotations

import csv
import re
import sys
from itertools import pairwise
from pathlib import Path

DATA = Path(__file__).parent / "data" / "derating.csv"
FIELDS = ["capacity_year", "table", "class", "hours", "ic_over", "ic_upto", "factor",
          "source_name", "source_url", "page", "checked_on"]

BAND = re.compile(r"^(?:(\d+)\s*(?:<|≤)\s*IC\s*≤\s*(\d+)|IC\s*>\s*(\d+))\s+(.*)$")
# Table 3 columns, in the order the pack prints them
STORAGE_HOURS = [0.5, 1, 1.5, 2, 3, 4, 6, 8, 12]
# Table 1 columns, in the order the pack prints them (2029/30 and 2030/31 agree)
TABLE1_CLASSES = ["DSU", "Gas Turbine", "Hydro", "Steam Turbine", "Interconnector", "System Wide"]
LOW_HOURS, HIGH_HOURS = 2, 4   # the lists do not say how long a battery lasts: both are shown
KEEP_HOURS = (LOW_HOURS, HIGH_HOURS)


class DeratingParseError(ValueError):
    pass


def _bands(text: str, ncols: int) -> list[tuple[float, float | None, list[float]]]:
    out = []
    for line in text.splitlines():
        m = BAND.match(line.strip())
        if not m:
            continue
        nums = re.findall(r"\d*\.\d+|\d+", m.group(4))
        if len(nums) != ncols:
            continue
        lo = float(m.group(1)) if m.group(1) is not None else float(m.group(3))
        hi = float(m.group(2)) if m.group(2) is not None else None
        out.append((lo, hi, [float(n) for n in nums]))
    return out


def _check_curve(rows, label: str) -> None:
    """Bands must run from 0 with no gap, end open, and no factor outside (0, 1)."""
    if not rows or rows[0][0] != 0 or rows[-1][1] is not None:
        raise DeratingParseError(f"{label}: bands do not run from 0 to open-ended")
    for (_, hi, _), (lo, _, _) in pairwise(rows):
        if hi != lo:
            raise DeratingParseError(f"{label}: gap between bands at {hi} and {lo}")


def extract(pack: Path) -> tuple[list[dict], dict]:
    """Rows for the classes this layer uses, read from a pack PDF, and the pack's identity."""
    import pdfplumber

    pages: dict[int, str] = {}
    with pdfplumber.open(pack) as pdf:
        for i, page in enumerate(pdf.pages[:10]):
            pages[i + 1] = page.extract_text() or ""
        head = pdf.pages[0].extract_text() or ""
    m = re.search(r"(\d{4})/(\d{4})\s+T-4", head.replace("\n", " "))
    if not m:
        raise DeratingParseError("cannot read the capacity year from the pack's first page")
    year = f"{m.group(1)}/{m.group(2)[2:]}"
    rows: list[dict] = []

    def add(table, cls, hours, lo, hi, factor, page):
        rows.append({"capacity_year": year, "table": table, "class": cls, "hours": hours,
                     "ic_over": lo, "ic_upto": hi if hi is not None else "", "factor": factor, "page": page})

    t1 = [(p, b) for p, t in pages.items() if "Table 1" in t or p in (5, 6) for b in [_bands(t, 6)] if b]
    t1_rows = [r for _, b in t1 for r in b]
    _check_curve(t1_rows, "Table 1")
    for page, bands in t1:
        for lo, hi, vals in bands:
            add(1, "Gas Turbine", "", lo, hi, vals[1], page)
            add(1, "Interconnector", "", lo, hi, vals[4], page)
    t3_all = []
    for p, t in pages.items():
        if p in (7, 8):
            for lo, hi, vals in _bands(t, len(STORAGE_HOURS)):
                t3_all.append((p, lo, hi, vals))
    _check_curve([(lo, hi, v) for _, lo, hi, v in t3_all], "Table 3")
    for page, lo, hi, vals in t3_all:
        for h, v in zip(STORAGE_HOURS, vals):
            if h in KEEP_HOURS:
                add(3, "Other Storage", h, lo, hi, v, page)
    page5 = next((p for p, t in pages.items() if "Table 5 -" in t), None)
    if page5 is None:
        raise DeratingParseError("Table 5 not found")
    t = pages[page5]
    k = t.index("Table 5 -")
    m5 = re.search(r"Wind Solar\s+(\d*\.\d+)\s+(\d*\.\d+)", t[k:])
    if not m5:
        raise DeratingParseError("Table 5 values not readable")
    add(5, "Wind", "", 0, None, float(m5.group(1)), page5)
    add(5, "Solar", "", 0, None, float(m5.group(2)), page5)
    for r in rows:
        if not 0 < r["factor"] < 1:
            raise DeratingParseError(f"factor out of range: {r}")
    return rows, {"capacity_year": year, "name": head.strip().splitlines()[-1] if head else ""}


def write(rows: list[dict], source_name: str, source_url: str, checked_on: str,
          path: Path = DATA) -> None:
    """Replace the capacity year's rows in the CSV, keeping every other year's."""
    keep = []
    if path.exists():
        with open(path, newline="") as f:
            keep = [r for r in csv.DictReader(f) if r["capacity_year"] != rows[0]["capacity_year"]]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(keep)
        for r in rows:
            w.writerow({**r, "source_name": source_name, "source_url": source_url,
                        "checked_on": checked_on})


def load(path: Path = DATA) -> list[dict]:
    with open(path, newline="") as f:
        return [{**r, "factor": float(r["factor"]), "ic_over": float(r["ic_over"]),
                 "ic_upto": float(r["ic_upto"]) if r["ic_upto"] else None,
                 "hours": float(r["hours"]) if r["hours"] else None} for r in csv.DictReader(f)]


def factor(rows: list[dict], year: str, cls: str, mw: float, hours: float | None = None) -> float:
    """The pack's factor for a unit of `mw` rated MW: the band where over < mw <= upto (the first
    band includes 0)."""
    for r in rows:
        if r["capacity_year"] != year or r["class"] != cls or r["hours"] != hours:
            continue
        if (mw > r["ic_over"] or mw == r["ic_over"] == 0) and (r["ic_upto"] is None or mw <= r["ic_upto"]):
            return r["factor"]
    raise KeyError(f"no {cls} factor for {mw} MW in {year}")


# which of the lists' technology words fall in which class (everything not here is left alone)
CLASS_OF = {
    "Wind": "Wind", "Solar": "Solar",
    "Battery": "Other Storage", "Battery Storage": "Other Storage",
    "OCGT": "Gas Turbine", "CCGT": "Gas Turbine", "Gas": "Gas Turbine", "Nat. Gas": "Gas Turbine",
}
# Greenlink joins Wales to Ireland (Great Britain); Celtic joins Cork to France (an EU state)
GB_INTERCONNECTORS = ("Greenlink",)
# Temporary Emergency Generation: "an out of market measure of last resort" (AIRAA 2025-2034, p.20),
# so a TEG unit has no capacity-auction value. The lists name them (Tarbert TEG2, Shannonbridge TEG2)
TEG = re.compile(r"\bTEG\d*\b")
TEG_LABEL = "Temporary emergency generation (out of market)"
SOURCES = ("eirgrid.tso_contracted_wind", "eirgrid.tso_contracted_nonwind",
           "esb.dso_contracted_renewable", "esb.dso_contracted_nonrenewable")


def build(con) -> dict | None:
    """The report section; None until derating.csv has rows for two capacity years."""
    from iegrid import metrics, parse

    try:
        rows = load()
    except FileNotFoundError:
        return None
    years = sorted({r["capacity_year"] for r in rows})
    if not years:
        return None
    ids = metrics._latest(con, SOURCES)
    if not ids:
        return None
    projects = con.execute(f"""
        select p.source_id, p.as_of, r.project_ref, r.name, r.technology, r.mec_mw
        from project_row r join publication p using (publication_id)
        where r.parser_version = {int(parse.PARSER_VERSION)}
          and r.publication_id in ({", ".join(str(i) for i in ids)})""").fetchall()
    total = sum(float(p[5] or 0) for p in projects)
    classes: dict[str, dict] = {}
    left: dict[str, float] = {}
    for _src, _asof, _ref, name, tech, mec in projects:
        mw = float(mec or 0)
        cls = CLASS_OF.get(tech)
        if tech == "Interconnector":
            cls = "Interconnector" if any(g in name for g in GB_INTERCONNECTORS) else None
            tech = tech if cls else name
        if TEG.search(name):   # out of market by direction of the regulator, whatever its technology
            cls, tech = None, TEG_LABEL
        if cls is None:
            left[tech] = left.get(tech, 0.0) + mw
            continue
        c = classes.setdefault(cls, {"class": cls, "projects": 0, "nameplate_mw": 0.0, "by_year": {}})
        c["projects"] += 1
        c["nameplate_mw"] += mw
        for y in years:
            if cls == "Other Storage":
                for h in (LOW_HOURS, HIGH_HOURS):
                    k = f"{y}|{h}"
                    c["by_year"][k] = c["by_year"].get(k, 0.0) + mw * factor(rows, y, cls, mw, float(h))
            else:
                c["by_year"][y] = c["by_year"].get(y, 0.0) + mw * factor(rows, y, cls, mw)
    labels = {"Wind": "Wind", "Solar": "Solar", "Other Storage": "Battery storage",
              "Gas Turbine": "Gas turbines (OCGT, CCGT, gas)",
              "Interconnector": "Interconnector to Great Britain"}

    def at(c: dict, y: str) -> tuple[float, float]:
        if c["class"] == "Other Storage":
            return c["by_year"][f"{y}|{LOW_HOURS}"], c["by_year"][f"{y}|{HIGH_HOURS}"]
        return c["by_year"][y], c["by_year"][y]

    prior, latest = years[-2] if len(years) > 1 else years[-1], years[-1]
    out_classes = []
    totals = {y: [0.0, 0.0] for y in years}
    for cls in ("Wind", "Solar", "Other Storage", "Gas Turbine", "Interconnector"):
        c = classes.get(cls)
        if not c:
            continue
        c["class"] = cls
        entry = {"class": cls, "label": labels[cls], "projects": c["projects"],
                 "nameplate_mw": round(c["nameplate_mw"], 1)}
        for key, y in (("prior", prior), ("latest", latest)):
            lo, hi = at(c, y)
            totals[y][0] += lo
            totals[y][1] += hi
            entry[key] = {"year": y, "low_mw": round(lo, 1), "high_mw": round(hi, 1),
                          "low_share": round(lo / c["nameplate_mw"], 3),
                          "high_share": round(hi / c["nameplate_mw"], 3)}
        out_classes.append(entry)
    applied = sum(c["nameplate_mw"] for c in classes.values())
    gas = next((c for c in out_classes if c["class"] == "Gas Turbine"), None)
    gas_mw = gas["latest"]["low_mw"] if gas else 0.0
    left_mw = sum(left.values())
    src = {y: next(r for r in rows if r["capacity_year"] == y) for y in years}
    return {
        "prior_year": prior, "latest_year": latest,
        "storage_hours": {"low": LOW_HOURS, "high": HIGH_HOURS},
        "contracted_mw": round(total, 1),
        "applied_mw": round(applied, 1),
        "applied_share": round(applied / total, 3) if total else None,
        "classes": out_classes,
        "totals": {k: {"year": y, "low_mw": round(totals[y][0], 1), "high_mw": round(totals[y][1], 1)}
                   for k, y in (("prior", prior), ("latest", latest))},
        # gas turbines' share of the de-rated total in the latest auction: a small total (storage at the
        # low duration) gives the high share
        "gas_share_low": round(gas_mw / totals[latest][1], 3) if totals[latest][1] else None,
        "gas_share_high": round(gas_mw / totals[latest][0], 3) if totals[latest][0] else None,
        "gas_nameplate_share": round(gas["nameplate_mw"] / applied, 3) if gas and applied else None,
        "left_alone": [{"technology": t, "mw": round(v, 1)}
                       for t, v in sorted(left.items(), key=lambda kv: -kv[1]) if v > 0],
        "left_alone_mw": round(left_mw, 1),
        "left_alone_share": round(left_mw / total, 3) if total else None,
        "sources": [{"capacity_year": y, "name": src[y]["source_name"], "url": src[y]["source_url"],
                     "checked_on": src[y]["checked_on"]} for y in years],
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    from datetime import date

    ap = argparse.ArgumentParser(description="Read a T-4 Initial Auction Information Pack into derating.csv")
    ap.add_argument("pack", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--url", required=True)
    a = ap.parse_args(argv)
    rows, ident = extract(a.pack)
    write(rows, a.name, a.url, date.today().isoformat())
    print(f"{ident['capacity_year']}: {len(rows)} rows into {DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
