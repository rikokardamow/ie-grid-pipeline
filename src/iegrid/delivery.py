"""Layer: delivery pace. How fast does contracted capacity actually energise, and what is
the queue in years of that pace? (docs/layers/02-delivery-pace/README.md)

A queue's size says little until it is set against delivery speed. "Years of cover" is the
normalisation the energy-analyst skill recommends for stocks (days of cover, not absolute
levels): contracted MW divided by the average annual MW energised over a stated window of
complete years. It is a ratio of two published quantities, not a forecast of when the queue
clears: most contracted MW never energises, and the pace changes.

Two series, each from the list that dates the events:

    distribution   ESB's energised lists give a date per project (1996 onward): MW by
                   year of energisation, summed across the renewable and non-renewable
                   lists of each edition
    transmission   EirGrid's connected list prints a year-by-year table of wind MW added.
                   Wind only: the non-wind lists print no dates per project, so
                   transmission non-wind has NO pace here, which is blank, not zero

Checks, each of which has found something:

    stability    the same year's total differs between ESB editions (a project struck
                 off the list, a date corrected): compared across every edition
    restatement  EirGrid restated its own history once: +100 MW on every cumulative wind
                 figure from 2015 on, between its Aug and Dec 2018 editions (2017: 1,491.5
                 MW before, 1,591.5 after). The list gives no reason (it mentions
                 Knockacummer moving from TSO to DSO, which would lower, not raise, TSO
                 wind), so the step is reported as observed. The table is read from one
                 edition and its vintage is named
    tie          every year's printed wind addition equals the change in the printed
                 cumulative figure, or the table is refused
    back-test    would a trailing average have predicted next year's pace better than
                 last year's? (it is the only forecast claim, and it is tested)
"""

from __future__ import annotations

import io
import re
import statistics
from collections import defaultdict
from datetime import date
from decimal import Decimal

import pdfplumber

from iegrid import parse

DSO_SOURCES = ("esb.dso_energised_renewable", "esb.dso_energised_nonrenewable")
WINDOWS = (3, 5)
TIE_MW = Decimal("0.5")
ROW = re.compile(r"^(\d{4})(?: YTD)? ([\d.,]+) ([\d.,]+) ([\d.,]+) (-|[\d.,]+) (-|[\d.,]+) (-|[\d.,]+)")


def _num(s: str) -> Decimal:
    return Decimal(0) if s == "-" else Decimal(s.replace(",", ""))


# --- distribution ----------------------------------------------------------------------

def dso_by_edition(con) -> dict[date, dict[int, tuple[float, int]]]:
    """{edition as-of: {year: (MW, projects)}} over the dated rows of both energised lists.
    An undated row ('pre 2005') is in no year."""
    rows = con.execute(f"""
        select p.as_of, year(r.energised_on), sum(r.mec_mw), count(*)
        from project_row r join publication p using (publication_id)
        where p.source_id in ({", ".join(repr(s) for s in DSO_SOURCES)})
          and r.parser_version = {int(parse.PARSER_VERSION)} and r.energised_on is not null
        group by 1, 2 order by 1, 2
    """).fetchall()
    out: dict[date, dict[int, tuple[float, int]]] = defaultdict(dict)
    for as_of, year, mw, n in rows:
        out[as_of][int(year)] = (float(mw), int(n))
    return dict(out)


def legacy_by_edition(con) -> dict[date, dict[int, tuple[float, int]]]:
    """The same series from ESB's 2017-2023 energised lists (esb_legacy.py), for editions where
    both the wind and the non-wind file exist: a year's total from one file alone would look
    like a collapse, not a revision. {} until the legacy lists are loaded."""
    try:
        both = {r[0] for r in con.execute("""
            select as_of from publication where source_id like 'esb.dso_energised_%wind'
            group by as_of having count(distinct source_id) = 2""").fetchall()}
        rows = con.execute("""
            select p.as_of, year(l.date_on), sum(l.mec_mw), count(*)
            from esb_legacy_row l join publication p using (publication_id)
            where p.source_id like 'esb.dso_energised_%wind' and l.date_on is not null
              and l.mec_mw is not null
            group by 1, 2""").fetchall()
    except Exception:  # noqa: BLE001 - a store from before the legacy layer
        return {}
    out: dict[date, dict[int, tuple[float, int]]] = defaultdict(dict)
    for as_of, year, mw, n in rows:
        if as_of in both:
            out[as_of][int(year)] = (float(mw), int(n))
    return dict(out)


def dso_queue_mw(con) -> float:
    """Contracted DSO MW in the newest contracted editions."""
    from iegrid import metrics

    ids = metrics._latest(con, ("esb.dso_contracted_renewable", "esb.dso_contracted_nonrenewable"))
    return float(con.execute(f"""
        select sum(mec_mw) from project_row
        where publication_id in ({", ".join(str(i) for i in ids)})
          and parser_version = {int(parse.PARSER_VERSION)}""").fetchone()[0])


def stability(editions: dict[date, dict[int, tuple[float, int]]], through: int,
              window: int = 3) -> dict:
    """How much a complete year's total moves between the editions that list it complete.
    Two figures, because one flatters: over the pace window's own years, and over every
    year back to the first edition. (Over the four 2024-26 editions alone the series moves
    by at most 10 MW; with the 2017-2023 editions a single year moves by 147 MW, so the
    first version of this check, on the recent editions only, reassured too much.)"""
    asofs = sorted(editions)

    def spread(y: int) -> tuple[float, int]:
        vals = [editions[a].get(y, (0.0, 0))[0] for a in asofs if y < a.year]
        return (max(vals) - min(vals), len(vals)) if len(vals) > 1 else (0.0, len(vals))

    years = sorted({y for ys in editions.values() for y in ys if y < through + 1})
    spreads = {y: spread(y) for y in years}
    in_window = [spreads[y][0] for y in range(through - window + 1, through + 1) if y in spreads]
    worst = max(spreads, key=lambda y: spreads[y][0], default=None)
    return {
        "editions_compared": len(asofs),
        "first_edition": str(asofs[0]) if asofs else None,
        "window_years": [through - window + 1, through],
        "window_change_mw": round(max(in_window, default=0.0), 1),
        "largest_change_mw": round(spreads[worst][0], 1) if worst else 0.0,
        "year": worst,
    }


def vintage_check(editions: dict[date, dict[int, tuple[float, int]]], latest: date,
                  first: int = 2008) -> dict | None:
    """The back-test again on the earliest edition's own series (what was known then), over
    the years that edition lists complete, beside the same years from the latest edition. If
    the best method is the same on both, the conclusion doesn't depend on the revisions."""
    if len(editions) < 2:
        return None
    oldest = min(editions)
    through = oldest.year - 1
    old = {y: mw for y, (mw, _) in editions[oldest].items() if y <= through}
    new = {y: mw for y, (mw, _) in editions[latest].items() if y <= through}
    a, b = backtest(old, first, through), backtest(new, first, through)
    if not a["methods"] or not b["methods"]:
        return None

    def averaging_beats(t: dict) -> bool:
        base = next(m for m in t["methods"] if m["method"] == "last year")["mae_mw"]
        return all(m["mae_mw"] < base for m in t["methods"] if m["method"] != "last year")

    # "the best method" can flip between a 3- and a 5-year mean a few MW apart: noise. What
    # the headline rests on is whether averaging beats last year's value on both vintages.
    return {"edition": str(oldest), "through": through, "years": a["years"],
            "earliest": a["methods"], "latest": b["methods"],
            "averaging_beats_last_year": averaging_beats(a) and averaging_beats(b)}


# --- transmission wind -----------------------------------------------------------------

class DeliveryParseError(Exception):
    pass


def _wind_table(content: bytes) -> tuple[dict[int, Decimal], dict[int, Decimal]]:
    """(cumulative wind MW, wind MW added) by year, from the rows that read."""
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = pdf.pages[0].extract_text() or ""
    cum: dict[int, Decimal] = {}
    add: dict[int, Decimal] = {}
    for line in text.splitlines():
        if (m := ROW.match(line)) is not None:
            y = int(m.group(1))
            cum[y], add[y] = _num(m.group(3)), _num(m.group(6))
    return cum, add


def restatement(old: bytes, new: bytes, complete_before: int) -> dict:
    """How far a newer edition's cumulative wind differs from an older one's for years that
    were already complete in the older (years before `complete_before`; the older edition's
    own year was year-to-date and was bound to grow)."""
    a, b = _wind_table(old)[0], _wind_table(new)[0]
    common = sorted(y for y in set(a) & set(b) if y < complete_before)
    diffs = {y: float(b[y] - a[y]) for y in common}
    worst = max(diffs, key=lambda y: abs(diffs[y]), default=None)
    return {"years_compared": len(common),
            "largest_mw": round(diffs[worst], 1) if worst else 0.0, "year": worst}


def tso_wind_additions(content: bytes) -> dict[int, float]:
    """Annual wind MW added, from the connected list's year table, tied to its cumulative
    column. A year that didn't read (chart text runs into its row) is absent, not zero;
    only years whose previous year also read are returned."""
    cum, add = _wind_table(content)
    out = {}
    for y in sorted(add):
        if y - 1 in cum:
            if abs((cum[y] - cum[y - 1]) - add[y]) > TIE_MW:
                raise DeliveryParseError(
                    f"{y}: wind added {add[y]} MW but the cumulative column moved "
                    f"{cum[y] - cum[y - 1]} MW")
            out[y] = float(add[y])
    if not out:
        raise DeliveryParseError("no year of the wind table read")
    return out


def tso_wind_queue_mw(con) -> float:
    from iegrid import metrics

    ids = metrics._latest(con, ("eirgrid.tso_contracted_wind",))
    return float(con.execute(f"""
        select sum(mec_mw) from project_row
        where publication_id in ({", ".join(str(i) for i in ids)})
          and parser_version = {int(parse.PARSER_VERSION)}""").fetchone()[0])


# --- the metric and its test -----------------------------------------------------------

def cover(queue_mw: float, annual: dict[int, float], through: int, window: int) -> dict | None:
    """Years of cover: queue MW over the mean annual MW of the `window` complete years ending
    at `through`. None if a year is missing or the pace is zero."""
    years = list(range(through - window + 1, through + 1))
    if any(y not in annual for y in years):
        return None
    pace = statistics.fmean(annual[y] for y in years)
    return {"window": window, "from": years[0], "to": through, "pace_mw": round(pace, 1),
            "years": round(queue_mw / pace, 1) if pace > 0 else None}


def best_window(queue_mw: float, annual: dict[int, float], through: int, window: int) -> dict | None:
    """The same measure over the fastest `window` consecutive complete years, so the
    reader sees how far the answer moves with the window chosen."""
    best = None
    for end in range(min(annual) + window - 1, through + 1):
        c = cover(queue_mw, annual, end, window)
        if c and (best is None or c["pace_mw"] > best["pace_mw"]):
            best = c
    return best


def backtest(annual: dict[int, float], first: int, through: int) -> dict:
    """Rolling-origin test of next-year pace: for each year t from `first` to `through`,
    forecast with only years before t. Benchmark is last year's value; the candidates are
    the mean of the last 3 and last 5 years. Reports mean absolute error and in how many
    years each beats the benchmark; with this few years it doesn't claim significance."""
    errs: dict[str, list[float]] = {"last year": [], "mean of 3": [], "mean of 5": []}
    tested: list[int] = []
    for t in range(first, through + 1):
        if any(y not in annual for y in range(t - 5, t)) or t not in annual:
            continue
        tested.append(t)
        past = [annual[y] for y in range(t - 5, t)]
        for name, f in (("last year", past[-1]), ("mean of 3", statistics.fmean(past[-3:])),
                        ("mean of 5", statistics.fmean(past))):
            errs[name].append(abs(f - annual[t]))
    n = len(errs["last year"])
    if n == 0:
        return {"years": 0, "methods": []}
    base = errs["last year"]
    return {"years": n, "first": tested[0], "through": tested[-1], "methods": [
        {"method": k, "mae_mw": round(statistics.fmean(v), 1),
         "beats_last_year": sum(1 for a, b in zip(v, base, strict=True) if a < b)}
        for k, v in errs.items()]}


def summarise(queue_mw: float, annual: dict[int, float], through: int, since: int) -> dict:
    return {
        "queue_mw": round(queue_mw, 1),
        "through": through,
        "annual": [{"year": y, "mw": round(annual[y], 1)} for y in sorted(annual)
                   if since <= y <= through],
        "cover": [c for w in WINDOWS if (c := cover(queue_mw, annual, through, w))],
        "fastest": [c for w in (3,) if (c := best_window(queue_mw, annual, through, w))],
        "backtest": backtest(annual, since, through),
    }


def restatement_history(con) -> dict:
    """Compare every older connected edition's complete years with the newest edition's."""
    from iegrid import store

    rows = con.execute("""select as_of, raw_path from publication
                          where source_id = 'eirgrid.tso_connected_renewable' order by as_of""").fetchall()
    new = (store.ROOT / rows[-1][1]).read_bytes()
    seen = []
    for as_of, raw in rows[:-1]:
        r = restatement((store.ROOT / raw).read_bytes(), new, as_of.year)
        if r["years_compared"]:
            seen.append((as_of, r))
    changed = [(a, r) for a, r in seen if r["largest_mw"] != 0]
    matching = [a for a, r in seen if r["largest_mw"] == 0]
    worst = max(changed, key=lambda t: abs(t[1]["largest_mw"]), default=None)
    return {"editions_compared": len(seen),
            "largest_mw": worst[1]["largest_mw"] if worst else 0.0,
            "last_edition_before": str(max(a for a, _ in changed)) if changed else None,
            "first_edition_matching": str(min(a for a in matching
                                              if not changed or a > max(c for c, _ in changed)))
            if matching else None}


def build(con) -> dict | None:
    """The report section: None until the connected lists are in the store."""
    from iegrid import store

    eds = dso_by_edition(con)
    conn = con.execute("""select as_of, raw_path from publication
                          where source_id = 'eirgrid.tso_connected_renewable'
                          order by as_of desc limit 1""").fetchone()
    if not eds or conn is None:
        return None
    newest = max(eds)
    d_through = newest.year - 1
    dso = summarise(dso_queue_mw(con), {y: mw for y, (mw, _) in eds[newest].items()},
                    d_through, 2008)
    dso["as_of"] = str(newest)
    every = {**legacy_by_edition(con), **eds}  # the 2017-2023 editions too, when loaded
    dso["stability"] = stability(every, d_through)
    dso["vintage_check"] = vintage_check(every, newest)
    t_through = conn[0].year - 1
    tso = summarise(tso_wind_queue_mw(con), tso_wind_additions((store.ROOT / conn[1]).read_bytes()),
                    t_through, 2013)
    tso["as_of"] = str(conn[0])
    tso["restatement"] = restatement_history(con)
    return {"distribution": dso, "transmission_wind": tso}
