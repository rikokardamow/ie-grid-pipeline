"""The firm-capacity layer: factors read from the packs, how a factor is looked up, and the sums."""

from datetime import UTC, date, datetime
from itertools import pairwise
from pathlib import Path

import pytest

from iegrid import derating, parse, store

NOW = datetime(2026, 10, 29, tzinfo=UTC)
ROWS = derating.load()
YEARS = ("2029/30", "2030/31")


def test_both_packs_are_in_the_data_each_row_with_its_source():
    assert {r["capacity_year"] for r in ROWS} == set(YEARS)
    with open(derating.DATA, newline="") as f:
        import csv
        for r in csv.DictReader(f):
            assert r["source_url"].startswith("https://www.sem-o.com/") and r["source_name"]
            assert r["checked_on"] and int(r["page"]) >= 5


def test_wind_and_solar_are_the_packs_printed_table_5_values():
    f = lambda y, c: derating.factor(ROWS, y, c, 100.0)
    assert (f("2029/30", "Wind"), f("2029/30", "Solar")) == (0.063, 0.049)
    assert (f("2030/31", "Wind"), f("2030/31", "Solar")) == (0.059, 0.041)


@pytest.mark.parametrize("year", YEARS)
@pytest.mark.parametrize("cls,hours", [("Gas Turbine", None), ("Other Storage", 2.0), ("Other Storage", 4.0)])
def test_each_curve_runs_from_zero_without_a_gap_and_never_rises_with_size(year, cls, hours):
    curve = sorted((r for r in ROWS if (r["capacity_year"], r["class"], r["hours"]) == (year, cls, hours)),
                   key=lambda r: r["ic_over"])
    assert curve[0]["ic_over"] == 0 and curve[-1]["ic_upto"] is None
    for a, b in pairwise(curve):
        assert a["ic_upto"] == b["ic_over"]
        assert b["factor"] <= a["factor"] + 1e-9
    assert all(0 < r["factor"] < 1 for r in curve)


def test_a_size_takes_the_band_it_falls_in_a_band_includes_its_upper_edge():
    f = lambda mw: derating.factor(ROWS, "2030/31", "Gas Turbine", mw)
    assert f(0.0) == f(10.0) == 0.868          # the first band, 0 to 10
    assert f(10.5) == 0.857                    # the next band, 10 to 20
    assert f(20.0) == 0.857 and f(20.01) == 0.848
    assert f(5000.0) == 0.627                  # the open band, over 690
    with pytest.raises(KeyError):
        derating.factor(ROWS, "2030/31", "Hydro", 10.0)


def test_a_longer_battery_counts_for_more_and_a_later_auction_for_less():
    two = derating.factor(ROWS, "2030/31", "Other Storage", 100.0, 2.0)
    four = derating.factor(ROWS, "2030/31", "Other Storage", 100.0, 4.0)
    assert four > two
    assert derating.factor(ROWS, "2029/30", "Other Storage", 100.0, 4.0) > four


def test_the_data_matches_the_pack_it_was_read_from_when_the_pack_is_here():
    pack = Path(__file__).parents[1] / "data" / "sources" / "IAIP3031T-4.pdf"
    if not pack.exists():
        pytest.skip("the pack is not in data/sources")
    rows, ident = derating.extract(pack)
    assert ident["capacity_year"] == "2030/31"
    mine = {(r["table"], r["class"], r["hours"], float(r["ic_over"])): r["factor"] for r in rows}
    theirs = {(int(r["table"]), r["class"], r["hours"], r["ic_over"]): r["factor"]
              for r in ROWS if r["capacity_year"] == "2030/31"}
    assert {(t, c, h or "", lo): v for (t, c, h, lo), v in mine.items()} == {
        (t, c, h or "", lo): v for (t, c, h, lo), v in theirs.items()}


def pub(con, source, sha):
    pid = store.insert(con, store.Publication(
        source, f"u-{sha}", sha, 1, date(2026, 8, 5), NOW, "last-modified", "estimated",
        f"raw/{sha}.pdf", NOW))
    con.execute("insert into parse_result values (?, ?, 1, 1, 1, 1, now())", [pid, parse.PARSER_VERSION])
    return pid


def add(con, pid, order, tech, mw):
    con.execute("insert into project_row values (?, ?, ?, 1, ?, 'n', ?, ?, '', '', '', '', '', null, null, '', '', null)",
                [pid, parse.PARSER_VERSION, order, f"TG{order}", tech, mw])


def test_the_sum_counts_what_has_a_factor_and_lists_what_does_not():
    con = store.connect(":memory:")
    wind = pub(con, "eirgrid.tso_contracted_wind", "w")
    other = pub(con, "eirgrid.tso_contracted_nonwind", "n")
    add(con, wind, 1, "Wind", 100.0)
    add(con, other, 1, "Solar", 50.0)
    add(con, other, 2, "Battery", 100.0)
    add(con, other, 3, "OCGT", 100.0)
    add(con, other, 4, "Solar + Battery", 60.0)
    got = derating.build(con)
    assert got["contracted_mw"] == 410.0 and got["applied_mw"] == 350.0
    by = {c["class"]: c for c in got["classes"]}
    assert by["Wind"]["latest"]["low_mw"] == 5.9 and by["Wind"]["latest"]["low_share"] == 0.059
    assert by["Solar"]["latest"]["low_mw"] == pytest.approx(2.05, abs=0.06)
    # storage is a range over the two durations, low under high
    st = by["Other Storage"]["latest"]
    assert st["low_mw"] < st["high_mw"]
    assert by["Gas Turbine"]["latest"]["low_mw"] == 81.9
    assert got["left_alone"] == [{"technology": "Solar + Battery", "mw": 60.0}]
    assert got["left_alone_mw"] == 60.0 and got["left_alone_share"] == round(60 / 410, 3)
    # the totals add the classes, and gas's share of them is gas over the total
    tot = got["totals"]["latest"]
    # the total is summed before rounding, so it can differ from the rounded class values by a rounding step
    assert tot["low_mw"] == pytest.approx(sum(c["latest"]["low_mw"] for c in got["classes"]), abs=0.15)
    assert got["gas_share_low"] == pytest.approx(81.9 / tot["high_mw"], abs=0.002)


def add_named(con, pid, order, tech, mw, name):
    con.execute("insert into project_row values (?, ?, ?, 1, ?, ?, ?, ?, '', '', '', '', '', null, null, '', '', null)",
                [pid, parse.PARSER_VERSION, order, f"TG{order}", name, tech, mw])


def test_the_interconnector_to_great_britain_counts_by_the_printed_curve_and_the_one_to_france_does_not():
    con = store.connect(":memory:")
    other = pub(con, "eirgrid.tso_contracted_nonwind", "n")
    add_named(con, other, 1, "Interconnector", 504.0, "Greenlink Interconnector")
    add_named(con, other, 2, "Interconnector", 700.0, "Celtic Interconnector")
    got = derating.build(con)
    ic = next(c for c in got["classes"] if c["class"] == "Interconnector")
    assert ic["nameplate_mw"] == 504.0
    assert ic["latest"]["low_mw"] == round(504.0 * derating.factor(ROWS, "2030/31", "Interconnector", 504.0), 1)
    assert ic["latest"]["low_share"] == 0.587      # the 500 to 510 MW band of the 2030/31 pack
    # Celtic is left alone, by name, and its MW is still in the total
    assert got["left_alone"] == [{"technology": "Celtic Interconnector", "mw": 700.0}]
    assert got["contracted_mw"] == 1204.0 and got["applied_mw"] == 504.0


def test_the_interconnector_curve_never_rises_and_is_adjusted_down_by_the_external_market_factor():
    for year, top in (("2029/30", 0.572), ("2030/31", 0.625)):
        assert derating.factor(ROWS, year, "Interconnector", 5.0) == top
        assert derating.factor(ROWS, year, "Interconnector", 5000.0) < top


def test_nothing_is_built_without_a_contracted_list():
    assert derating.build(store.connect(":memory:")) is None
