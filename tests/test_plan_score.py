"""Scoring the plan: the printed tables, what an edition may be scored on, and the arithmetic."""

import csv
from datetime import date
from pathlib import Path

import pytest

from iegrid import connected, derating, plan_score, resolutions, store
from tests.test_derating import add_named, pub

ROWS = plan_score.load()
DSO = [{"ref": "TG175", "name": "Ballymakaily RICE", "mw": 115.2, "energised_on": date(2025, 3, 31)}]
SOURCES = Path(__file__).parents[1] / "data" / "sources"


def by(got, year):
    return next(y for y in got["years"] if y["year"] == year)


def edition(year_row, name):
    return next(e for e in year_row["editions"] if e["edition"] == name)


def test_every_row_names_its_source_and_page():
    with open(plan_score.DATA, newline="") as f:
        for r in csv.DictReader(f):
            assert r["source_url"].startswith("https://www.eirgrid.ie/") and int(r["page"]) > 0
            assert r["source_name"] and r["checked_on"] and r["freeze"]


@pytest.mark.parametrize("pdf,page,lines", [
    ("editions/EirGrid_SONI_Ireland_Capacity_Outlook_2022-2031.pdf", 47,
     ["Ireland 2023 2024 2025 2026 2027", "Gas Turbine 0 120 190 790"]),
    ("editions/19035-EirGrid-Generation-Capacity-Statement-Combined-2023-V5-Jan-2024.pdf", 81,
     ["Ireland 2024 2025 2026 2027 2028", "Gas turbine GCS2023 risk 330 200 290 0 570", "Total successful in 230 1,280 120 1,270"]),
    ("editions/AIRAA-2025-2034.pdf", 81,
     ["2025 2026 2027 2028 Total", "Total Successful in Capacity Auctions 980 120 1270 60 2430",
      "Core Scenario Risk Adjusted View of New 530 290 760 60 1640"]),
    ("AIRAA-2026-2035_Ireland.pdf", 88,
     ["Total Successful in 900 2,060 2,110 2,450", "AIRAA 2025 Expected 610 910 1,500 1,900"]),
    ("AIRAA-2026-2035_Ireland.pdf", 87, ["FlexGen Ringsend 64 Newly operational as of Q4 2024."]),
])
def test_the_data_is_what_the_documents_print_when_they_are_here(pdf, page, lines):
    path = SOURCES / pdf
    if not path.exists():
        pytest.skip("the document is not in data/sources")
    import pdfplumber

    with pdfplumber.open(path) as doc:
        text = doc.pages[page - 1].extract_text()
    for line in lines:
        assert line in text


def test_a_per_year_table_adds_up_from_the_start_year_and_a_cumulative_one_adds_back_what_operates():
    assert plan_score.cumulative(ROWS, "GCS 2022", "expected", 2024) == 120     # 2023's zero is before the start
    assert plan_score.cumulative(ROWS, "GCS 2023", "expected", 2026) == 820
    assert plan_score.cumulative(ROWS, "AIRAA 2026", "expected", 2026, 192) == 802
    assert plan_score.cumulative(ROWS, "GCS 2022", "expected", 2030) is None    # past its table


def test_an_edition_is_only_scored_on_years_after_its_freeze():
    assert [e for e, _ in plan_score.editions_for(ROWS, 2024)] == ["GCS 2022", "GCS 2023"]
    assert "AIRAA 2026" not in [e for e, _ in plan_score.editions_for(ROWS, 2025)]


def test_the_score_is_expected_less_observed_and_the_open_year_says_what_is_still_needed():
    got = plan_score.score(ROWS, DSO, date(2026, 8, 5))
    y24, y25, y26 = by(got, 2024), by(got, 2025), by(got, 2026)
    assert (y24["observed_mw"], y25["observed_mw"]) == (192.0, 307.2)
    assert edition(y24, "GCS 2022")["error_mw"] == -72.0
    assert edition(y24, "GCS 2023")["naive_error_mw"] == 38.0
    assert edition(y25, "GCS 2023")["error_mw"] == 222.8 and edition(y25, "GCS 2023")["naive_mw"] == 1510.0
    assert edition(y25, "GCS 2022")["naive_mw"] is None                         # that edition prints no awards
    assert y25["scored"] and not y26["scored"]
    assert edition(y26, "AIRAA 2026")["still_needs_mw"] == 494.8


def test_a_year_scores_itself_once_the_lists_pass_its_end():
    assert by(plan_score.score(ROWS, DSO, date(2027, 1, 5)), 2026)["scored"]


def test_nothing_is_built_without_the_lists():
    assert plan_score.build(store.connect(":memory:"), ROWS) is None


def test_emergency_generation_has_no_capacity_value_whatever_its_technology():
    con = store.connect(":memory:")
    other = pub(con, "eirgrid.tso_contracted_nonwind", "n")
    add_named(con, other, 1, "OCGT", 160.0, "Tarbert TEG2")
    add_named(con, other, 2, "Gas", 260.0, "Shannonbridge TEG2 TEG2")
    add_named(con, other, 3, "OCGT", 100.0, "Integrated Power")
    got = derating.build(con)
    assert got["applied_mw"] == 100.0
    assert got["left_alone"] == [{"technology": derating.TEG_LABEL, "mw": 420.0}]
    assert got["contracted_mw"] == 520.0


def test_a_sourced_connection_is_an_outcome_and_a_connected_ref_still_wins():
    answers = resolutions.for_leavers()
    assert answers["TG383"]["verdict"] == "connected" and answers["TG385"]["verdict"] == "reorganised"
    assert connected.CONNECTED_SOURCED == "connected (sourced)"
