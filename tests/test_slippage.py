"""Target slippage: both bounds, the refusal to give a median on a handful, and the unmatched."""

from datetime import date
from decimal import Decimal

from iegrid import connected, slippage


def hist(ref, first, month, full=True):
    row = connected.ConnectedRow(ref, "n", Decimal(1), Decimal(1), date.fromisoformat(month), full,
                                 "Wind", "")
    return connected.History(ref, frozenset({"n"}), date.fromisoformat(first), row)


def test_a_project_is_measured_to_its_first_listing_and_to_its_completion():
    # Seecon-style: target Jan 2017, first listed (partial) May 2017, completed Aug 2017
    slips, unmatched = slippage.compute(
        {"TG58": ("Seecon (1)", 105.0, date(2017, 1, 1))},
        {"TG58": hist("TG58", "2017-05-01", "2017-08-01")})
    s = slips[0]
    assert (s.months_to_first, s.months_to_completion) == (4, 7) and unmatched == []


def test_a_target_with_no_connected_record_is_unmatched_not_late():
    slips, unmatched = slippage.compute(
        {"TG1": ("A", 10.0, date(2017, 1, 1)), "TG2": ("B", 10.0, date(2017, 1, 1))},
        {"TG2": hist("TG2", "2017-02-01", "2017-02-01")})
    assert [s.ref for s in slips] == ["TG2"] and unmatched == ["TG1"]


def test_an_early_project_is_negative_and_the_list_is_sorted_latest_first():
    targets = {r: (r, 10.0, date(2017, 6, 1)) for r in ("A", "B", "C")}
    h = {"A": hist("A", "2017-04-01", "2017-04-01"), "B": hist("B", "2019-06-01", "2019-06-01"),
         "C": hist("C", "2017-07-01", "2018-01-01")}
    slips, _ = slippage.compute(targets, h)
    assert [(s.ref, s.months_to_completion) for s in slips] == [("B", 24), ("C", 7), ("A", -2)]


def test_no_median_is_given_on_a_handful_of_projects():
    targets = {f"T{i}": (f"n{i}", 10.0, date(2017, 1, 1)) for i in range(slippage.MIN_N - 1)}
    h = {r: hist(r, "2017-06-01", "2017-09-01") for r in targets}
    slips, un = slippage.compute(targets, h)
    s = slippage.summarise(slips, un, len(targets))
    assert (s["enough"], s["median_to_completion"]) == (False, None)
    assert s["late_to_completion"] == slippage.MIN_N - 1  # the counts are still given

    targets = {f"T{i}": (f"n{i}", 10.0, date(2017, 1, 1)) for i in range(slippage.MIN_N)}
    h = {r: hist(r, "2017-06-01", "2017-09-01") for r in targets}
    s = slippage.summarise(*slippage.compute(targets, h), len(targets))
    assert (s["enough"], s["median_to_completion"], s["median_to_first"]) == (True, 8, 5)
