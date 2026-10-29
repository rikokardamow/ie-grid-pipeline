"""The queue against the plan: figures read from the adequacy assessment, and what is set against them."""

import csv
from pathlib import Path

import pytest

from iegrid import adequacy, store
from tests.test_derating import add, pub

ROWS = adequacy.load()


def ids(i):
    return {r["year"]: r["value"] for r in ROWS if r["id"] == i}


def test_every_row_names_its_source_page_and_the_date_it_was_read():
    with open(adequacy.DATA, newline="") as f:
        for r in csv.DictReader(f):
            assert r["source_url"].startswith("https://www.eirgrid.ie/") and r["source_name"]
            assert int(r["page"]) > 0 and r["checked_on"] and r["unit"] and r["label"]


def test_the_tables_are_the_assessments_printed_values():
    assert ids("new_conventional_awarded")[2026] == 900 and ids("new_conventional_awarded")[2030] == 2450
    assert ids("new_conventional_expected")[2030] == 1900
    assert ids("storage_total")[2026] == 1140 and ids("storage_total")[2029] == 1800
    assert ids("lole_base")[2026] == 71.6 and ids("lole_secure")[2033] == 4.1
    assert ids("standard")[None] == 3.0


def test_the_storage_rows_add_to_their_total_and_expected_never_exceeds_awarded():
    adequacy.check(ROWS)                          # raises if either fails
    broken = [{**r, "value": r["value"] + 500} if r["id"] == "storage_total" and r["year"] == 2030 else r
              for r in ROWS]
    with pytest.raises(adequacy.AdequacyParseError):
        adequacy.check(broken)


def test_the_data_matches_the_document_it_was_read_from_when_it_is_here():
    pdf = Path(__file__).parents[1] / "data" / "sources" / "AIRAA-2026-2035_Ireland.pdf"
    if not pdf.exists():
        pytest.skip("the assessment is not in data/sources")
    got = {(r["id"], r["year"] or None): r["value"] for r in adequacy.extract(pdf)}
    assert got == {(r["id"], r["year"]): r["value"] for r in ROWS}


def test_the_comparison_is_the_lists_against_the_assessments_figures():
    con = store.connect(":memory:")
    wind = pub(con, "eirgrid.tso_contracted_wind", "w")
    other = pub(con, "eirgrid.tso_contracted_nonwind", "n")
    add(con, wind, 1, "Wind", 100.0)
    add(con, other, 1, "OCGT", 950.0)
    add(con, other, 2, "Battery", 330.0)
    got = adequacy.build(con, ROWS)
    assert got["gas"]["queue_mw"] == 950.0 and got["gas"]["expected_mw"] == 1900.0
    assert got["gas"]["awarded_mw"] == 2450.0 and got["gas"]["not_expected_mw"] == 550.0
    assert got["gas"]["queue_share_of_expected"] == 0.5
    # 1,800 in 2029 less 1,140 in 2026, of which pumped storage (unchanged) is not part of the growth
    assert got["storage"]["added_mw"] == 660.0 and got["storage"]["implied_share"] == 2.0
    need = got["need"]
    assert need["base_outside"] == [2026, 2027, 2028]
    assert need["secure_outside"] == [2026, 2027, 2028, 2029, 2030, 2033, 2034, 2035]   # 2031 and 2032 are within 3 hours
    assert need["deficit_share_low"] < need["deficit_share_high"]
    assert need["deficit_start_mw"] == 200.0 and need["deficit_end_mw"] == 400.0


def test_nothing_is_built_without_a_contracted_list():
    assert adequacy.build(store.connect(":memory:"), ROWS) is None
