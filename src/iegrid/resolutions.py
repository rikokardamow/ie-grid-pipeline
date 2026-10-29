"""Answers to open questions, as data. (docs/layers/08-resolutions/README.md)

The ledger of disagreements (errata.py) and the leavers no list resolves (connected.py) leave
questions the lists can't answer. Each answer found elsewhere is a row in
src/iegrid/data/resolutions.csv with its source, the words the source says, and the date it was
read; an answer that could not be sourced is a row too, marked unresolved or open, so the same
search isn't repeated and nothing looks settled that isn't.

    status    settled     the sources settle it (their limits are in `detail`)
              partly      the sources fit one reading but leave something unexplained
              open        two readings, nothing to separate them
              unresolved  searched, nothing found

A source quoted here was read at its own page, not from a search summary (the Oireachtas
answer that returned 403 and the capacity statement page that 404'd are not used).
"""

from __future__ import annotations

import csv
from pathlib import Path

RESOLUTIONS = Path(__file__).parent / "data" / "resolutions.csv"
STATUSES = ("settled", "partly", "open", "unresolved")


def load(path: Path = RESOLUTIONS) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def for_leavers(rows: list[dict[str, str]] | None = None) -> dict[str, dict[str, str]]:
    """{ref: row} for the leaver rows that settle an outcome (refused, reorganised)."""
    rows = load() if rows is None else rows
    return {r["ref"]: r for r in rows
            if r["kind"] == "leaver" and r["status"] == "settled"
            and r["verdict"] in ("refused", "reorganised")}


def for_errata(rows: list[dict[str, str]] | None = None) -> dict[str, dict[str, str]]:
    """{ref: row} for the answers to ledger rows."""
    rows = load() if rows is None else rows
    return {r["ref"]: r for r in rows if r["kind"] == "errata"}
