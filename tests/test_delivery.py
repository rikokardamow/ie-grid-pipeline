"""Delivery pace: years of cover, its back-test, and the wind table's gate."""

from datetime import date

import pytest

from iegrid import delivery
from tests.conftest import make_pdf

TABLE = ["2014 212.18 1,046.55 1,258.73 - 201.35 201.35",
         "2015 212.18 1,152.55 1,364.73 - 106 106",
         "2016 212.18 1,371.25 1,583.43 - 218.7 218.7",
         "2018 YTD 212.18 1,774.45 1,986.63 - 182.95 182.95"]


def test_years_of_cover_is_queue_over_the_mean_pace_of_the_complete_years_in_the_window():
    annual = {2021: 20.0, 2022: 130.0, 2023: 40.0, 2024: 70.0, 2025: 200.0}
    c = delivery.cover(2000.0, annual, 2025, 3)
    assert (c["from"], c["to"], c["pace_mw"], c["years"]) == (2023, 2025, 103.3, 19.4)
    assert delivery.cover(2000.0, annual, 2025, 5)["years"] == 21.7
    assert delivery.cover(2000.0, annual, 2025, 6) is None  # a year missing: no figure
    assert delivery.cover(2000.0, {2024: 0.0, 2025: 0.0}, 2025, 2)["years"] is None  # no pace


def test_the_fastest_window_shows_how_far_the_answer_moves_with_the_window_chosen():
    annual = {2017: 250.0, 2018: 180.0, 2019: 340.0, 2020: 90.0, 2021: 20.0}
    best = delivery.best_window(1000.0, annual, 2021, 3)
    assert (best["from"], best["to"], best["pace_mw"]) == (2017, 2019, 256.7)


def test_the_backtest_forecasts_each_year_from_earlier_years_only():
    # a flat series: every method is exact; a noisy one (100, 200, 100, ...): last year is
    # always 100 out, the mean of 3 is 66.7 out. (One spike alone ties them: both miss 600 in
    # total, last year in two years, the mean in four.)
    flat = {y: 100.0 for y in range(2000, 2012)}
    r = delivery.backtest(flat, 2005, 2011)
    assert r["years"] == 7 and all(m["mae_mw"] == 0 for m in r["methods"])
    noisy = {y: 100.0 if y % 2 == 0 else 200.0 for y in range(2000, 2012)}
    by = {m["method"]: m for m in delivery.backtest(noisy, 2005, 2011)["methods"]}
    assert (by["last year"]["mae_mw"], by["mean of 3"]["mae_mw"]) == (100.0, 66.7)
    assert by["mean of 3"]["beats_last_year"] == 7 and by["last year"]["beats_last_year"] == 0
    # a year with fewer than five years behind it is not tested
    assert delivery.backtest({2000: 1.0, 2001: 2.0}, 2000, 2001)["years"] == 0
    # the reported span is the years actually tested, not the range asked for
    r = delivery.backtest({y: 100.0 for y in range(2000, 2012)}, 2001, 2011)
    assert (r["first"], r["through"], r["years"]) == (2005, 2011, 7)


def test_the_wind_table_is_read_with_each_addition_tied_to_its_cumulative_change():
    add = delivery.tso_wind_additions(make_pdf(["TSO Connected Renewables", *TABLE]))
    # 2014 has no 2013 row to tie to; 2018 follows a gap; year-to-date rows read like any
    assert add == {2015: 106.0, 2016: 218.7}


def test_a_wind_table_whose_addition_does_not_tie_is_refused():
    bad = TABLE[:2] + ["2016 212.18 1,371.25 1,583.43 - 250 250"]
    with pytest.raises(delivery.DeliveryParseError, match="2016"):
        delivery.tso_wind_additions(make_pdf(bad))
    with pytest.raises(delivery.DeliveryParseError, match="no year"):
        delivery.tso_wind_additions(make_pdf(["nothing here"]))


def test_a_restated_history_is_measured_on_the_years_already_complete():
    old = make_pdf(["2014 212.18 946.55 1,158.73 - 100 100", "2015 212.18 1,052.55 1,264.73 - 106 106",
                    "2016 YTD 212.18 1,100 1,312 - 47.45 47.45"])
    new = make_pdf(TABLE[:3])
    r = delivery.restatement(old, new, complete_before=2016)
    # 2014 and 2015 were restated by +100; 2016 was year-to-date in the older, so not compared
    assert (r["years_compared"], r["largest_mw"]) == (2, 100.0)


def test_summarise_gives_the_series_the_cover_and_the_test():
    annual = {y: 100.0 + y - 2000 for y in range(2000, 2026)}
    s = delivery.summarise(3000.0, annual, 2025, 2010)
    assert s["annual"][0]["year"] == 2010 and s["annual"][-1]["year"] == 2025
    assert [c["window"] for c in s["cover"]] == [3, 5]
    assert s["backtest"]["first"] == 2010 and date  # the test starts where the series is shown


def test_stability_reports_the_pace_window_and_the_whole_history_separately():
    # one project listed as energised in 2013 in the early editions and gone from the later ones
    eds = {date(2017, 9, 7): {2013: (256.0, 21), 2016: (185.0, 9)},
           date(2018, 5, 30): {2013: (156.0, 20), 2016: (185.0, 9)},
           date(2023, 4, 20): {2013: (156.0, 20), 2016: (205.0, 12), 2022: (99.0, 8)},
           date(2026, 7, 1): {2013: (156.0, 20), 2016: (205.0, 12), 2022: (132.0, 17),
                              2025: (200.0, 20)}}
    s = delivery.stability(eds, 2025, window=1)
    assert s["largest_change_mw"] == 100.0 and s["year"] == 2013       # the whole history
    assert s["window_change_mw"] == 0.0 and s["window_years"] == [2025, 2025]  # the pace window
    assert s["editions_compared"] == 4 and s["first_edition"] == "2017-09-07"
    # over the recent editions alone the same series looks steady: the reason for two figures
    assert delivery.stability({a: e for a, e in eds.items() if a.year > 2022}, 2025)[
        "largest_change_mw"] == 33.0


def test_the_vintage_check_asks_whether_averaging_still_wins_on_the_series_as_first_printed():
    noisy = {y: 100.0 if y % 2 == 0 else 200.0 for y in range(2000, 2012)}
    eds = {date(2012, 6, 1): noisy, date(2020, 6, 1): noisy}
    eds = {a: {y: (mw, 1) for y, mw in s.items()} for a, s in eds.items()}
    got = delivery.vintage_check(eds, date(2020, 6, 1), first=2005)
    assert got["averaging_beats_last_year"] is True and got["edition"] == "2012-06-01"
    assert got["through"] == 2011 and got["years"] == 7
    assert delivery.vintage_check({date(2012, 6, 1): eds[date(2012, 6, 1)]}, date(2012, 6, 1)) is None
