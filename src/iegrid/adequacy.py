"""Layer: the queue against the system's own plan. What does EirGrid's adequacy assessment assume
will be built, and how does the contracted queue compare? (docs/layers/10-queue-vs-plan/README.md)

EirGrid and SONI's All-Island Resource Adequacy Assessment (AIRAA, the successor to the Generation
Capacity Statement) says how much new gas plant and storage it assumes arrives each year, and how
far the system sits from the reliability standard. Those figures are data, read out of the document
(python -m iegrid.adequacy <pdf>), each row with its page and the date it was read, in
src/iegrid/data/adequacy.csv. Set beside the contracted lists:

    new gas       the lists' gas turbines (OCGT, CCGT, gas) against the plant the assessment counts as
                  successful in capacity auctions and not yet operating, and the part it expects to deliver
    storage       the lists' batteries against the storage the assessment adds between its first year and
                  the year it stops growing (pumped storage is unchanged and left out)
    need          the standard (Ireland, hours of expected loss of load), the years each case is outside
                  it, and the stated deficit, set against the layer-9 de-rated queue

What it can and can't say is on the page and in the README: the assessment's expected deliveries are
drawn from the same projects the lists hold, so the two are not additive and the comparison is a
reading of the plan, not a count of what is needed on top of it.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

DATA = Path(__file__).parent / "data" / "adequacy.csv"
FIELDS = ["id", "year", "value", "unit", "label", "qualifier", "source_name", "source_url", "page", "checked_on"]
YEARS = list(range(2026, 2036))
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


class AdequacyParseError(ValueError):
    pass


def _series(text: str, label: str, n: int = len(YEARS)) -> list[float]:
    """The n numbers that end the line starting with `label` (a wrapped label is fine: the numbers are
    taken from the line, never from the next one)."""
    for line in text.splitlines():
        if re.match(label, line.strip()):
            nums = [float(x.replace(",", "")) for x in NUM.findall(line[len(re.match(label, line.strip()).group(0)):])]
            if len(nums) == n:
                return nums
    raise AdequacyParseError(f"no row {label!r} with {n} numbers")


def extract(pdf_path: Path) -> list[dict]:
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        pages = {i + 1: (p.extract_text() or "") for i, p in enumerate(pdf.pages)}

    def page_of(marker: str, *near: int) -> int:
        for p in near:
            if marker in pages.get(p, ""):
                return p
        found = [p for p, t in pages.items() if marker in t]
        if not found:
            raise AdequacyParseError(f"{marker!r} not found")
        return found[0]

    rows: list[dict] = []

    def add(id_, label, unit, values, page, qualifier=""):
        for y, v in zip(YEARS, values):
            rows.append({"id": id_, "year": y, "value": v, "unit": unit, "label": label,
                         "qualifier": qualifier, "page": page})

    p = page_of("Table 5.2 Ireland assumptions", 88)
    add("new_conventional_awarded", "New conventional plant successful in capacity auctions, less operational plant",
        "MW rated, cumulative", _series(pages[p], r"Total Successful in"), p)
    add("new_conventional_expected", "New conventional plant the assessment expects to deliver",
        "MW rated, cumulative", _series(pages[p], r"AIRAA 2025 Expected"), p)
    p = page_of("Table 5.9 Ireland Energy Storage Capacity", 101)
    for id_, label, pat in (("storage_le1h", "Storage up to 1 hour", r"<= 1 Hour"),
                            ("storage_1_4h", "Storage 1 to 4 hours", r"1-4 Hours"),
                            ("storage_gt4h", "Storage over 4 hours", r"> 4 Hours"),
                            ("storage_pumped", "Pumped storage", r"Pump Storage"),
                            ("storage_total", "All storage", r"Total")):
        t = pages[p][pages[p].index("Table 5.9 Ireland Energy Storage Capacity"):]
        t = t[:t.index("Table 5.10")]
        add(id_, label, "MW", _series(t, pat), p)
    p = page_of("Table 6.2 LOLE and EENS Base results for Ireland", 122)
    add("lole_base", "Expected hours of lost load a year, base case", "hours", _series(pages[p], r"LOLE Base \(hours\)"), p)
    p = page_of("Table 6.5 LOLE and EENS Secure results for Ireland", 125)
    add("lole_secure", "Expected hours of lost load a year, secure case", "hours", _series(pages[p], r"LOLE Secure"), p)
    p = page_of("Table 6.1 LOLE Reliability Standards", 115)
    m = re.search(r"(?m)^Ireland (\d+(?:\.\d+)?)\b", pages[p][pages[p].index("Table 6.1"):])
    if not m:
        raise AdequacyParseError("Table 6.1 Ireland standard not found")
    rows.append({"id": "standard", "year": "", "value": float(m.group(1)), "unit": "hours",
                 "label": "LOLE reliability standard, Ireland", "qualifier": "", "page": p})
    p = page_of("deficit of around", 12)
    # the page is two columns, so the sentence's pieces sit on different lines: look for each piece
    if not all(piece in pages[p] for piece in ("a deficit of around 200 MW increasing to", "over 400 MW in 2034")):
        raise AdequacyParseError("the secure-case deficit sentence is not as expected")
    rows.append({"id": "secure_deficit_start", "year": "", "value": 200.0, "unit": "MW", "qualifier": "around",
                 "label": "Secure-case deficit from 2029, stated as 'around 200 MW'", "page": p})
    rows.append({"id": "secure_deficit_end", "year": 2034, "value": 400.0, "unit": "MW", "qualifier": "over",
                 "label": "Secure-case deficit in 2034, stated as 'over 400 MW'", "page": p})
    check(rows)
    return rows


def check(rows: list[dict]) -> None:
    """The tables must be internally consistent before they are written."""
    by: dict[str, dict[int, float]] = {}
    for r in rows:
        if r["year"] not in ("", None):
            by.setdefault(r["id"], {})[int(r["year"])] = float(r["value"])
    for y in YEARS:
        parts = sum(by[k][y] for k in ("storage_le1h", "storage_1_4h", "storage_gt4h", "storage_pumped"))
        if abs(parts - by["storage_total"][y]) > 15:   # the pack rounds each to 10 MW
            raise AdequacyParseError(f"storage rows do not add to the total in {y}")
        if by["new_conventional_expected"][y] > by["new_conventional_awarded"][y] + 1e-9:
            raise AdequacyParseError(f"expected delivery exceeds what was awarded in {y}")
    for k in ("lole_base", "lole_secure"):
        if len(by[k]) != len(YEARS) or min(by[k].values()) < 0:
            raise AdequacyParseError(f"{k}: a year is missing")


def write(rows: list[dict], source_name: str, source_url: str, checked_on: str, path: Path = DATA) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({**r, "source_name": source_name, "source_url": source_url, "checked_on": checked_on})


def load(path: Path = DATA) -> list[dict]:
    with open(path, newline="") as f:
        return [{**r, "value": float(r["value"]), "year": int(r["year"]) if r["year"] else None}
                for r in csv.DictReader(f)]


def _get(rows, id_, year=None) -> dict:
    return next(r for r in rows if r["id"] == id_ and r["year"] == year)


def build(con, rows: list[dict] | None = None) -> dict | None:
    """The report section; None until adequacy.csv and the layer-9 factors are both there."""
    from iegrid import derating

    try:
        rows = rows if rows is not None else load()
    except FileNotFoundError:
        return None
    firm = derating.build(con)
    if firm is None:
        return None
    cls = {c["class"]: c for c in firm["classes"]}
    gas, bat = cls.get("Gas Turbine"), cls.get("Other Storage")
    src = rows[0]
    first, last = 2026, 2029
    awarded, expected = _get(rows, "new_conventional_awarded", 2030)["value"], _get(rows, "new_conventional_expected", 2030)["value"]
    total = {y: _get(rows, "storage_total", y)["value"] for y in YEARS}
    pumped = _get(rows, "storage_pumped", first)["value"]
    added = total[last] - total[first]
    standard = _get(rows, "standard")["value"]

    def outside(id_):
        return [y for y in YEARS if _get(rows, id_, y)["value"] > standard]

    lo, hi = firm["totals"]["latest"]["low_mw"], firm["totals"]["latest"]["high_mw"]
    d0, d1 = _get(rows, "secure_deficit_start")["value"], _get(rows, "secure_deficit_end", 2034)["value"]
    return {
        "source": {"name": src["source_name"], "url": src["source_url"], "checked_on": src["checked_on"]},
        "gas": None if gas is None else {
            "queue_mw": gas["nameplate_mw"], "awarded_mw": awarded, "expected_mw": expected,
            "not_expected_mw": awarded - expected, "year": 2030,
            "queue_share_of_expected": round(gas["nameplate_mw"] / expected, 3)},
        "storage": None if bat is None else {
            "queue_mw": bat["nameplate_mw"], "from_year": first, "to_year": last,
            "from_mw": total[first], "to_mw": total[last], "added_mw": added, "pumped_mw": pumped,
            "implied_share": round(added / bat["nameplate_mw"], 3)},
        "need": {
            "standard_hours": standard,
            "base_outside": outside("lole_base"), "secure_outside": outside("lole_secure"),
            "deficit_start_mw": d0, "deficit_end_mw": d1, "deficit_end_year": 2034,
            "queue_derated_low_mw": lo, "queue_derated_high_mw": hi, "queue_year": firm["latest_year"],
            "deficit_share_low": round(d0 / hi, 3), "deficit_share_high": round(d1 / lo, 3)},
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    from datetime import date

    ap = argparse.ArgumentParser(description="Read the adequacy assessment's figures into adequacy.csv")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--url", required=True)
    a = ap.parse_args(argv)
    rows = extract(a.pdf)
    write(rows, a.name, a.url, date.today().isoformat())
    print(f"{len(rows)} rows into {DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
