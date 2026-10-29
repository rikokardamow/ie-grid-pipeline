"""Layer: promise vs delivery. When EirGrid printed a target connection month for a wind
project, when did it actually connect? (docs/layers/03-target-slippage/README.md)

Only the 2015-16 contracted lists print a target month (project_row.target_month, g3b), and
only wind projects can be followed to a connection (the connected layer). So the sample is
small and one cohort; the layer states its n beside every figure and extrapolates nothing.

A project's connection has two dates, which bound the slip:

    first listed   the first connected edition that has it (first energisation, to the
                   edition's date: editions are 3-12 months apart)
    completed      the month its newest connected row gives; for a project that is Full,
                   when it reached full export capacity

A slip measured to 'first listed' is the lower bound, to 'completed' the upper bound; the
lists don't say which of the two the target meant, so both are shown.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date

MIN_N = 10   # fewer matched projects than this and no median is given


@dataclass(frozen=True)
class Slip:
    ref: str
    name: str
    mw: float
    target: date
    first_listed: date
    completed: date
    months_to_first: int
    months_to_completion: int
    full: bool | None


def months(a: date, b: date) -> int:
    return (a.year - b.year) * 12 + a.month - b.month


def compute(targets: dict[str, tuple[str, float, date]], history) -> tuple[list[Slip], list[str]]:
    """targets: {ref: (name, MW, first target month printed)}; history: connected.History by
    ref. Returns the matched projects (sorted by completion slip, latest first) and the
    refs with a target but no connected record (still waiting, on the distribution grid, or
    spelled differently: the lists can't say)."""
    slips, unmatched = [], []
    for ref, (name, mw, target) in targets.items():
        h = history.get(ref)
        if h is None or h.row.connected is None:
            unmatched.append(ref)
            continue
        slips.append(Slip(ref, name, mw, target, h.first_listed, h.row.connected,
                          months(h.first_listed, target), months(h.row.connected, target),
                          h.row.full))
    return sorted(slips, key=lambda s: -s.months_to_completion), sorted(unmatched)


def summarise(slips: list[Slip], unmatched: list[str], with_target: int) -> dict:
    n = len(slips)
    done = [s.months_to_completion for s in slips]
    first = [s.months_to_first for s in slips]
    return {
        "with_target": with_target,
        "matched": n,
        "unmatched": len(unmatched),
        "enough": n >= MIN_N,
        "late_to_completion": sum(1 for m in done if m > 0),
        "over_a_year_to_completion": sum(1 for m in done if m > 12),
        "late_to_first": sum(1 for m in first if m > 0),
        "median_to_completion": statistics.median(done) if n >= MIN_N else None,
        "median_to_first": statistics.median(first) if n >= MIN_N else None,
        "rows": [{"ref": s.ref, "name": s.name, "mw": round(s.mw, 1), "target": str(s.target)[:7],
                  "first_listed": str(s.first_listed)[:7], "completed": str(s.completed)[:7],
                  "to_first": s.months_to_first, "to_completion": s.months_to_completion}
                 for s in slips],
    }


def build(con) -> dict | None:
    """The report section; None until the connected lists are read (connected.load)."""
    from iegrid import connected, parse

    try:
        if con.execute("select count(*) from connected_row").fetchone()[0] == 0:
            return None
    except Exception:  # noqa: BLE001 - a store from before the connected layer
        return None
    rows = con.execute(f"""
        select r.project_ref, r.name, r.mec_mw, r.target_month
        from project_row r join publication p using (publication_id)
        where r.parser_version = {int(parse.PARSER_VERSION)} and r.target_month is not null
        order by p.as_of, r.row_order""").fetchall()
    targets: dict[str, tuple[str, float, date]] = {}
    for ref, name, mw, target in rows:
        targets.setdefault(ref, (name, float(mw), target))  # the first target printed
    slips, unmatched = compute(targets, connected.connected_history(con))
    return summarise(slips, unmatched, len(targets))
