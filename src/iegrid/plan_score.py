"""Layer: scoring the plan. How did what each adequacy assessment expected compare with what came?
(docs/layers/11-plan-score/README.md)

Each edition of EirGrid and SONI's capacity statement prints the new conventional plant it expects
by year (its "risk adjusted view") and, from 2023, what was awarded in capacity auctions. Those are
forecasts with dates on them. The printed tables are data, src/iegrid/data/plan_editions.csv, each
row with its page, and a test re-reads the PDFs when they are here. They are scored like any forecast:

    target       new conventional plant, Ireland, rated MW, cumulative from the start of 2024
    out of sample  an edition is scored only on years after its data freeze
    benchmark    everything awarded arrives in the year it was awarded for (the naive reading of the
                 same table)
    observed     units a later edition says are operating, plus gas on ESB's energised list by its
                 energised date. EirGrid's lists can't date a transmission connection, and a unit can
                 connect before it leaves a list, so observed is a floor

A year is scored once the newest lists are past its end; until then it is shown as open, with what
each edition still needs, so the next one scores itself when the lists arrive. Two scored years
over three editions is a record, not a test of skill: no significance is claimed.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from iegrid import metrics, parse

DATA = Path(__file__).parent / "data" / "plan_editions.csv"
START = 2024
GAS = ("Rice", "RICE", "Nat. Gas", "Gas", "OCGT", "CCGT")   # ESB's words for conventional plant
TSO_LIST = "eirgrid.tso_contracted_nonwind"
DSO_LIST = "esb.dso_energised_nonrenewable"


def load(path: Path = DATA) -> list[dict]:
    with open(path, newline="") as f:
        return [{**r, "year": int(r["year"]), "mw": float(r["mw"]), "page": int(r["page"])}
                for r in csv.DictReader(f)]


def cumulative(rows: list[dict], edition: str, series: str, year: int, operational: float = 0.0) -> float | None:
    """The edition's cumulative MW from START to the end of `year`, or None past its table. A table
    printed as cumulative leaves out plant already operating, so that is added back."""
    mine = sorted((r for r in rows if r["edition"] == edition and r["series"] == series), key=lambda r: r["year"])
    if not mine or year > mine[-1]["year"]:
        return None
    if mine[0]["basis"] == "cumulative":
        at = [r for r in mine if r["year"] == year]
        return at[0]["mw"] + operational if at else None
    return sum(r["mw"] for r in mine if START <= r["year"] <= year)


def editions_for(rows: list[dict], year: int) -> list[tuple[str, str]]:
    """Editions whose freeze comes before the year starts: only those are out of sample."""
    seen: dict[str, str] = {}
    for r in rows:
        if r["series"] == "expected" and r["freeze"][:4] < str(year):
            seen[r["edition"]] = r["freeze"]
    return sorted(seen.items(), key=lambda kv: kv[1])


def score(rows: list[dict], dso: list[dict], newest: date) -> dict:
    sourced = [r for r in rows if r["series"] == "operational"]
    operational = sum(r["mw"] for r in sourced)

    def observed(year: int) -> float:
        return sum(r["mw"] for r in sourced if r["year"] <= year) + sum(
            d["mw"] for d in dso if d["energised_on"].year <= year)

    years = []
    last = newest.year
    for year in range(START, last + 1):
        obs = observed(year)
        entries = []
        for ed, freeze in editions_for(rows, year):
            exp = cumulative(rows, ed, "expected", year, operational)
            if exp is None:
                continue
            naive = cumulative(rows, ed, "awarded", year, operational)
            entries.append({"edition": ed, "freeze": freeze, "expected_mw": round(exp, 1),
                            "error_mw": round(exp - obs, 1), "still_needs_mw": round(max(exp - obs, 0), 1),
                            "naive_mw": None if naive is None else round(naive, 1),
                            "naive_error_mw": None if naive is None else round(naive - obs, 1)})
        years.append({"year": year, "scored": newest > date(year, 12, 31), "observed_mw": round(obs, 1),
                      "editions": entries})
    return {"years": years}


def build(con, rows: list[dict] | None = None) -> dict | None:
    """The report section; None until the lists it reads are in the store."""
    rows = load() if rows is None else rows
    ids = metrics._latest(con, (DSO_LIST,))
    newest = con.execute("select max(as_of) from publication where source_id in (?, ?)",
                         [TSO_LIST, DSO_LIST]).fetchone()[0]
    if not ids or newest is None:
        return None
    marks = ", ".join("?" for _ in GAS)
    dso = [{"ref": r[0], "name": r[1], "mw": float(r[2]), "energised_on": r[3]} for r in con.execute(f"""
        select project_ref, name, mec_mw, energised_on from project_row
        where publication_id = ? and parser_version = {int(parse.PARSER_VERSION)}
          and technology in ({marks}) and energised_on >= ?
        order by energised_on""", [ids[0], *GAS, date(START, 1, 1)]).fetchall()]
    got = score(rows, dso, newest)
    src = {}
    for r in rows:
        src.setdefault(r["source_name"], {"name": r["source_name"], "url": r["source_url"],
                                          "checked_on": r["checked_on"]})
    tso_as_of = con.execute("select max(as_of) from publication where source_id = ?", [TSO_LIST]).fetchone()[0]
    return {**got, "start_year": START, "as_of": str(newest), "tso_as_of": str(tso_as_of),
            "sourced_mw": sum(r["mw"] for r in rows if r["series"] == "operational"),
            "dso_units": [{**d, "energised_on": str(d["energised_on"])} for d in dso],
            "sources": list(src.values())}
