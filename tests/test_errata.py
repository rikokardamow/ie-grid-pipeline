"""The errata ledger: each kind from its check, and the cases that are NOT discrepancies."""

from datetime import date
from decimal import Decimal

from iegrid import connected, errata


def outcome(ref, kind, left, first, why="by ref"):
    return connected.Outcome(ref, f"{ref} Wind", Decimal(50), "eirgrid.tso_contracted_wind",
                             date.fromisoformat(left), kind, why,
                             date.fromisoformat(first) if first else None)


def kinds(entries):
    return sorted((e["kind"], e["ref"]) for e in entries)


def test_a_project_on_neither_list_for_over_a_year_is_a_gap():
    # TG44: left the contracted list Dec 2018, first connected Feb 2021
    got = errata.from_parts([], [outcome("TG44", connected.CONNECTED, "2018-12-14", "2021-02-01")], None)
    assert kinds(got) == [("gap", "TG44")]
    assert "on neither list for 26 months" in got[0]["against"]


def test_leaving_long_after_first_connecting_is_a_partial_connection_not_an_erratum():
    # TG25: first connected Jul 2019, left the contracted list Feb 2022: the unconnected
    # remainder stayed contracted. And a short gap (under a year) is not a gap.
    got = errata.from_parts([], [
        outcome("TG25", connected.CONNECTED, "2022-02-11", "2019-07-01"),
        outcome("TG9", connected.CONNECTED, "2018-01-01", "2018-09-01")], None)
    assert got == []


def test_a_reused_ref_states_both_dates_the_outcome_gave():
    why = "ref reused: on a connected list before any contracted list has it (connected from 2015-08-31, first contracted 2020-06-16)"
    got = errata.from_parts([], [outcome("TG22a", connected.UNKNOWN, "2021-03-16", "2015-08-31", why)], None)
    assert kinds(got) == [("reused ref", "TG22a")]
    assert "first contracted 2020-06-16" in got[0]["against"]


def test_node_conflicts_of_both_kinds_are_entries():
    got = errata.from_parts([
        {"ref": "TG485", "name": "Kilmorna", "list_node": "Kinnegad 110kV",
         "results_node": "Knockanure 220kV", "km": 185},
        {"ref": "TG594", "name": "Fieldstown Ext 2", "list_node": "Timoney",
         "list_node_county": "Tipperary", "county": "Dublin"}], [], None)
    assert kinds(got) == [("node", "TG485"), ("node", "TG594")]
    assert "185 km away" in got[0]["against"] and "Dublin" in got[1]["against"]


def test_a_restated_history_is_an_entry_only_when_something_changed():
    r = {"largest_mw": 100.0, "last_edition_before": "2018-08-01", "first_edition_matching": "2018-12-01"}
    assert kinds(errata.from_parts([], [], r)) == [("restated", "")]
    assert errata.from_parts([], [], {**r, "largest_mw": 0.0}) == []
    assert errata.from_parts([], [], None) == []


def test_the_report_section_counts_its_own_entries(monkeypatch):
    class Con:
        def execute(self, sql):
            return self

        def fetchone(self):
            return (1,)

    monkeypatch.setattr(connected, "outcomes", lambda con: [
        outcome("TG44", connected.CONNECTED, "2018-12-14", "2021-02-01")])
    got = errata.build(Con(), [], None)
    assert got["total"] == 1 and got["kinds"] == [{"kind": "gap", "count": 1}]


def test_a_project_that_changed_publisher_is_an_entry_and_explains_a_restatement_of_its_size():
    # TG24 Knockacummer: on ESB's lists Sep 2017 - May 2018 (energised 9 Nov 2013), on
    # EirGrid's from Dec 2018 (connected Jul 2015); EirGrid's history gained exactly 100 MW
    move = {"ref": "TG24", "name": "Knockacummer (1) (Temp)", "mw": 100.0,
            "esb_first": date(2017, 9, 7), "esb_last": date(2018, 5, 30),
            "esb_energised": date(2013, 11, 9), "eir_first": date(2018, 12, 1),
            "eir_connected": date(2015, 7, 1)}
    restated = {"largest_mw": 100.0, "last_edition_before": "2018-08-01",
                "first_edition_matching": "2018-12-01"}
    got = errata.from_parts([], [], restated, [move])
    assert kinds(got) == [("moved", "TG24"), ("restated", "")]
    moved = next(e for e in got if e["kind"] == "moved")
    assert "energised 9 Nov 2013" in moved["says"] and "connected Jul 2015" in moved["against"]
    assert "the size of TG24" in next(e for e in got if e["kind"] == "restated")["against"]
    # a restatement no moved project accounts for keeps the plain wording
    other = errata.from_parts([], [], {**restated, "largest_mw": 87.0}, [move])
    assert "no note" in next(e for e in other if e["kind"] == "restated")["against"]


def test_the_switch_note_is_read_from_the_text_and_quoted_against_the_order_the_lists_show():
    m = errata.SWITCH.search("Note: Knockacummer windfarm has switched from a TSO to a DSO grid "
                             "connection. Both the TSO and DSO connected wind reports have "
                             "been updated accordingly.")
    assert (m.group(1), m.group(2), m.group(3)) == ("Knockacummer", "TSO", "DSO")
    move = {"ref": "TG24", "name": "Knockacummer (1)", "mw": 100.0,
            "esb_first": date(2017, 9, 7), "esb_last": date(2018, 5, 30),
            "esb_energised": date(2013, 11, 9), "eir_first": date(2018, 12, 1),
            "eir_connected": date(2015, 7, 1),
            "note": {"edition": "2018-12-01", "from": "TSO", "to": "DSO"}}
    against = errata.from_parts([], [], None, [move])[0]["against"]
    assert "switched from TSO to DSO" in against and "the opposite of the order" in against
    # the same note with the lists agreeing (ESB's after EirGrid's) is not called opposite
    agrees = {**move, "esb_first": date(2019, 1, 1), "esb_last": date(2019, 6, 1)}
    assert "opposite" not in errata.from_parts([], [], None, [agrees])[0]["against"]
