"""Layer: an outside check. Does the record reproduce a published national total?
(docs/layers/07-external-check/README.md)

Every other check compares the lists with themselves or with each other. This one compares the
record with a figure published elsewhere, so a list that was missing, double-counted or misread
would show. The published figures are data (src/iegrid/data/external_checks.csv, each with its
source, the words it says, and the date it was checked), like g4's cited counties.

What it can and can't say is stated on the page and in the README:

    * it checks our reading of the lists, not the lists: the national figure is SEAI's, which draws
      on EirGrid and ESB data, so agreement was expected, and disagreement would have meant we
      lost or double-counted something;
    * scope and date are matched, not hoped for (total wind, onshore and offshore, at end-2022),
      and the gap that remains is reported with the causes ruled out, not explained away.

One check so far: total installed wind at end-2022, the date the last EirGrid connected list
(Oct 2022) and the first ESB list after it (Apr 2023, dated entries only) can both be taken to.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

CHECKS = Path(__file__).parent / "data" / "external_checks.csv"


def published(path: Path = CHECKS) -> dict[str, dict[str, str]]:
    with path.open(newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def wind_at(con, day: date) -> dict | None:
    """Total wind in the two publishers' lists at `day`: EirGrid's newest connected edition on or
    before it (installed MW), plus ESB's first energised-wind edition after it, counting entries
    dated on or before it and those with no date (MEC). None if either list is missing."""
    tso = con.execute("""
        select p.publication_id, p.as_of from publication p
        where p.source_id = 'eirgrid.tso_connected_renewable' and p.as_of <= ?
          and exists (select 1 from connected_row c where c.publication_id = p.publication_id)
        order by p.as_of desc limit 1""", [day]).fetchone()
    dso = con.execute("""
        select p.publication_id, p.as_of from publication p
        where p.source_id = 'esb.dso_energised_wind' and p.as_of > ?
          and exists (select 1 from esb_legacy_row l where l.publication_id = p.publication_id)
        order by p.as_of limit 1""", [day]).fetchone()
    if tso is None or dso is None:
        return None
    tso_mw = con.execute("""select sum(installed_mw) from connected_row
                            where publication_id = ?""", [tso[0]]).fetchone()[0] or Decimal(0)
    dso_mw, dso_rows, undated = con.execute("""
        select sum(mec_mw), count(*), sum(mec_mw) filter (where date_on is null)
        from esb_legacy_row
        where publication_id = ? and mec_mw is not null
          and (date_on is null or date_on <= ?)""", [dso[0], day]).fetchone()
    return {"tso_mw": float(tso_mw), "tso_edition": str(tso[1]),
            "dso_mw": float(dso_mw or 0), "dso_edition": str(dso[1]), "dso_rows": dso_rows,
            "dso_undated_mw": float(undated or 0)}


def compare(ours: float, theirs: float) -> dict:
    return {"ours_mw": round(ours, 1), "theirs_mw": round(theirs, 1),
            "diff_mw": round(ours - theirs, 1), "diff_pct": round((ours - theirs) / theirs, 4)}


def build(con) -> dict | None:
    """The report section; None until the connected and ESB legacy lists are loaded."""
    try:
        got = published()["wind_end_2022"]
        parts = wind_at(con, date.fromisoformat(got["as_of"]))
    except Exception:  # noqa: BLE001 - a store without the layers' tables
        return None
    if parts is None:
        return None
    out = compare(parts["tso_mw"] + parts["dso_mw"], float(got["value"]))
    return {"checks": [{
        "id": got["id"], "label": got["label"], "as_of": got["as_of"], "scope": got["scope"],
        "source": got["source_name"], "url": got["source_url"], "says": got["source_says"],
        "checked_on": got["checked_on"], "notes": got["notes"], **out, **parts,
        # causes tested and ruled out, so a reader doesn't have to guess
        "ruled_out": [
            "Arklow Bank (25.2 MW offshore) is on ESB's list, so it is in our total",
            ("EirGrid's connected list prints installed and MEC totals 0.3% apart, "
             "far short of the gap"),
        ],
    }]}
