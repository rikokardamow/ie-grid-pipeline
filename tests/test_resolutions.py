"""Sourced answers: the data's own rules, and what they change in outcomes, the ledger and the
wind check."""

from datetime import date
from decimal import Decimal

from iegrid import connected, errata, external, flows, resolutions


def test_every_answer_has_a_known_status_and_a_source_to_check_it_against():
    rows = resolutions.load()
    assert rows and {r["kind"] for r in rows} <= {"leaver", "errata"}
    for r in rows:
        assert r["status"] in resolutions.STATUSES and r["ref"] and r["detail"]
        assert r["checked_on"] and r["source_name"]
        if r["status"] in ("settled", "partly") and not r["source_name"].startswith("this record"):
            # an answer from outside the record shows where, and the words it rests on
            assert r["source_url"].startswith("https://") and r["source_says"], r["ref"]
        if r["status"] == "unresolved":
            assert not r["verdict"] and not r["source_url"], r["ref"]  # nothing claimed


def test_only_settled_rows_with_a_verdict_decide_a_leavers_outcome():
    got = resolutions.for_leavers(resolutions.load())
    assert set(got) >= {"P230", "TG261", "TG301", "TG319", "TG22b"}
    assert {r["verdict"] for r in got.values()} <= {"refused", "reorganised", "connected"}
    assert "TG93" not in got and "TG103" not in got  # searched, nothing found: stay unresolved


def leaver(ref, name, mw=50):
    return flows.Flow("eirgrid.tso_contracted_wind", date(2021, 3, 16), "left", ref, name,
                      Decimal(mw))


def test_a_sourced_refusal_makes_the_outcome_not_connected_with_its_source_named():
    res = {"P230": {"verdict": "refused", "source_name": "Irish Legal News"},
           "TG319": {"verdict": "reorganised", "source_name": "this record"}}
    got = {o.ref: o for o in connected.classify(
        [leaver("P230", "Castletownmoor", 120), leaver("TG319", "Tobertooreen", 34),
         leaver("TG93", "Dooray")], {}, resolutions=res)}
    assert got["P230"].outcome == connected.REFUSED and "Irish Legal News" in got["P230"].why
    assert got["TG319"].outcome == connected.REORGANISED
    assert got["TG93"].outcome == connected.NOT_LISTED  # no answer: not claimed either way


def test_a_ref_on_a_connected_list_beats_a_sourced_answer():
    row = connected.ConnectedRow("P230", "n", Decimal(1), Decimal(1), date(2018, 1, 1), True,
                                 "Wind", "")
    h = {"P230": connected.History("P230", frozenset({"n"}), date(2017, 9, 1), row)}
    got = connected.classify([leaver("P230", "Castletownmoor")], h,
                             resolutions={"P230": {"verdict": "refused", "source_name": "x"}})
    assert got[0].outcome == connected.CONNECTED  # the data outranks a reading of the news


def test_the_ledger_attaches_the_answer_found_to_the_row_of_the_same_ref_only():
    conflicts = [{"ref": "TG485", "name": "Kilmorna", "list_node": "Kinnegad 110kV",
                  "results_node": "Knockanure", "km": 185}]
    answers = {"TG485": {"status": "settled", "verdict": "ECP results right", "detail": "d",
                         "source_name": "Irish Examiner", "source_url": "https://x",
                         "source_says": "170MW at Knockanure", "checked_on": "2026-10-29"}}
    restated = {"largest_mw": 100.0, "last_edition_before": "2018-08-01",
                "first_edition_matching": "2018-12-01"}
    got = errata.from_parts(conflicts, [], restated, [], answers)
    by_kind = {e["kind"]: e for e in got}
    assert by_kind["node"]["answer"]["status"] == "settled"
    assert by_kind["node"]["answer"]["source"] == "Irish Examiner"
    assert by_kind["restated"]["answer"] is None  # no project ref, no moved project of its size
    move = {"ref": "TG24", "name": "K", "mw": 100.0, "esb_first": date(2017, 9, 7),
            "esb_last": date(2018, 5, 30), "esb_energised": None,
            "eir_first": date(2018, 12, 1), "eir_connected": None}
    explained = {e["kind"]: e for e in errata.from_parts([], [], restated, [move], {})}
    assert explained["restated"]["answer"]["status"] == "settled"   # it is TG24's 100 MW
    assert "TG24" in explained["restated"]["answer"]["verdict"]
    assert errata.from_parts(conflicts, [], None, [], {})[0]["answer"] is None


def test_the_wind_gap_splits_into_what_was_there_a_year_earlier_and_what_the_year_added(monkeypatch):
    # the real figures: 4,410 ours against 4,536 published (126 short); 134 MW net added in 2022
    monkeypatch.setattr(external, "published", lambda: {
        "wind_net_added_2022": {"value": "134", "source_says": "net 134"}})
    monkeypatch.setattr(external, "wind_by_year",
                        lambda con, year: {"year": year, "tso_mw": 2074.05, "dso_mw": 2258.14})
    got = external._decompose(None, {}, {"as_of": "2022-12-31", "value": "4536"},
                              {"ours_mw": 4409.9})
    assert got["gap_before_mw"] == -69.8 and got["added_shortfall_mw"] == -56.3
    assert got["ours_added_mw"] == 77.7 and got["theirs_before_mw"] == 4402.0
    # the two parts add to the whole gap: -69.8 + -56.3 = 4,409.9 - 4,536.0 within rounding
    assert abs(got["gap_before_mw"] + got["added_shortfall_mw"] - (4409.9 - 4536.0)) < 0.2
