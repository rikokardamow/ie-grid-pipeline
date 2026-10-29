"""The connected-lists layer: three layouts read, each edition gated, leavers classified."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from iegrid import connected, flows, store
from tests.conftest import make_pdf

NOW = datetime(2026, 10, 29, tzinfo=UTC)
ROWS = ["1 Onshore Pre-Gate TG13 Ballywater 1 Full 31.5 31.5 May-2005",
        "2 Onshore 2 TG35 Ballywater 2 Full 10.5 11 Aug-2007"]


def test_the_2016_table_reads_mec_first_then_installed():
    r = connected.parse_line("3 Onshore 3 TG66 Mountlucas 1 Full 79.2 84 Nov-2014")
    assert (r.ref, r.name, r.mec_mw, r.installed_mw, r.connected, r.full, r.kind) == (
        "TG66", "Mountlucas", Decimal("79.2"), Decimal(84), date(2014, 11, 1), True, "Onshore")
    p = connected.parse_line("38 Onshore 2 TG51 Mulreavy 1 Partial 89.85 45 Nov-2016 "
                             "Croaghnameal 1 (4.25MW)[DG198] +")
    assert p.full is False and p.installed_mw == Decimal(45) and p.name == "Mulreavy"


def test_the_2017_renewables_table_has_a_type_and_a_category():
    r = connected.parse_line("29 Wind Onshore 2 TG55a Lisheen 2 Full 23 24 May-2013 Tipperary 12 Y")
    assert (r.ref, r.name, r.kind, r.connected) == ("TG55a", "Lisheen", "Wind", date(2013, 5, 1))


def test_the_2015_lines_give_installed_before_mec_and_may_leave_the_mec_out():
    r = connected.parse_line("Castledockrell (3) 3 DG189 2.300 3.300 Gate 2 Castledockrell "
                             "110 kV Jan 2011")
    assert (r.ref, r.name, r.installed_mw, r.mec_mw, r.full) == (
        "DG189", "Castledockrell", Decimal("2.300"), Decimal("3.300"), None)
    d = connected.parse_line("Boggeragh 2 (Killavoy (1)) 1 DG200 18.000 Gate 2 Boggeragh "
                             "110 kV Nov 2015")
    assert d.installed_mw == Decimal("18.000") and d.mec_mw is None


def test_a_note_or_a_heading_that_mentions_a_ref_is_not_a_row():
    assert connected.parse_line("Booltiagh 2 & 3 (TG38 & TG39)") is None
    assert connected.parse_line("Note: DG198 and DG65 are extensions") is None
    assert connected.parse_line("Year Hydro Wind Total RES") is None


def test_an_edition_whose_rows_tie_to_both_printed_totals_is_read_in_either_order():
    for total in ("Total MW 42 42.5", "Total MW 42.5 42"):
        rows, found = connected.read(make_pdf(["Transmission Connected Wind Farms", *ROWS, total]))
        assert [r.ref for r in rows] == ["TG13", "TG35"]
        assert found["wind_installed_mw"] == Decimal("42.5") and found["wind_mec_mw"] == Decimal("42.0")


def test_an_edition_is_refused_when_a_total_a_row_or_the_numbering_is_off():
    with pytest.raises(connected.ConnectedParseError, match="against printed"):
        connected.read(make_pdf([*ROWS, "Total MW 42 50"]))
    with pytest.raises(connected.ConnectedParseError, match="not read"):
        connected.read(make_pdf([*ROWS, "3 Onshore 2 TG99 Broken Full x y", "Total MW 42 42.5"]))
    with pytest.raises(connected.ConnectedParseError, match="numbering"):
        connected.read(make_pdf([ROWS[0], "3 Onshore 2 TG35 Ballywater 2 Full 10.5 11 Aug-2007",
                                 "Total MW 42 42.5"]))
    with pytest.raises(connected.ConnectedParseError, match="no rows"):
        connected.read(make_pdf(["Connected TSO (Non Wind) Generators", "Aghada 220kV Aghada (1) Gas 258.000 Pre 2000"]))


def hist(ref, names, first="2017-09-01", month="2018-03-01"):
    row = connected.ConnectedRow(ref, min(names), Decimal(10), Decimal(10),
                                 date.fromisoformat(month), True, "Wind", "")
    return connected.History(ref, frozenset(names), date.fromisoformat(first), row)


def leaver(ref, name, on, sid="eirgrid.tso_contracted_wind", mw=50):
    return flows.Flow(sid, date.fromisoformat(on), "left", ref, name, Decimal(mw))


def test_a_leaver_is_connected_when_its_ref_is_on_a_connected_list():
    got = connected.classify([leaver("TG1", "Foo Wind Farm", "2018-01-30")],
                             {"TG1": hist("TG1", {"Foo"})})[0]
    assert (got.outcome, got.why, got.first_listed) == (connected.CONNECTED, "by ref",
                                                        date(2017, 9, 1))


def test_a_phase_is_connected_with_its_sibling_by_name_across_every_name_the_ref_had():
    # g-layer finding: the 2017+ table calls TG23a "Garvagh", the 2015 lines "Garvagh - Glebe (1a)"
    h = {"TG23a": hist("TG23a", {"Garvagh", "Garvagh - Glebe (1a)"})}
    got = connected.classify([leaver("TG23b", "Garvagh - Glebe (1b)", "2015-12-31")], h)[0]
    assert (got.outcome, got.connected_ref) == (connected.SIBLING, "TG23a")
    # two connected projects with the name: which one isn't known
    h["TG24"] = hist("TG24", {"Garvagh - Glebe (2a)"})
    got = connected.classify([leaver("TG23b", "Garvagh", "2015-12-31")],
                             {**h, "TG25": hist("TG25", {"Garvagh"})})[0]
    assert got.outcome == connected.NOT_LISTED


def test_only_wind_can_be_not_listed_and_a_late_leaver_is_unknown():
    out = {o.ref: o for o in connected.classify([
        leaver("TG2", "Bar Solar", "2018-01-30", "eirgrid.tso_contracted_nonwind"),
        leaver("TG3", "Baz Wind Farm", "2022-08-01"),
        leaver("TG4", "Qux Wind Farm", "2019-01-01")], {})}
    assert out["TG2"].outcome == connected.UNKNOWN and "no refs" in out["TG2"].why
    assert out["TG3"].outcome == connected.UNKNOWN and "too near" in out["TG3"].why
    assert out["TG4"].outcome == connected.NOT_LISTED


def test_a_ref_connected_before_it_was_ever_contracted_was_reused():
    # TG22a: Athea, connected 2013, back on a contracted list from 2020 as another project
    h = {"TG22a": hist("TG22a", {"Athea"}, first="2015-08-31")}
    got = connected.classify([leaver("TG22a", "Beenanaspock", "2021-03-16")], h,
                             first_contracted={"TG22a": date(2020, 6, 16)})[0]
    assert got.outcome == connected.UNKNOWN and "reused" in got.why


def test_only_a_refs_final_leave_counts_and_a_ref_that_came_back_is_no_leaver(monkeypatch):
    evs = [leaver("TG34", "Wind A", "2016-05-31"), leaver("TG34", "Wind A", "2021-03-16"),
           leaver("TG9", "Wind B", "2018-06-15"), leaver("TG7", "Wind C", "2019-01-01")]
    monkeypatch.setattr(flows, "flows", lambda con: evs)
    monkeypatch.setattr(flows, "editions", lambda con: {
        "eirgrid.tso_contracted_wind": [(date(2026, 8, 5), {"TG9": ("Wind B", Decimal(50))})]})
    got = connected.final_leavers(None)
    assert [(f.ref, str(f.as_of)) for f in got] == [("TG7", "2019-01-01"), ("TG34", "2021-03-16")]


def test_loading_reads_each_edition_once_and_reports_a_refused_one(tmp_path):
    con = store.connect(":memory:")
    good, bad = tmp_path / "good.pdf", tmp_path / "bad.pdf"
    good.write_bytes(make_pdf([*ROWS, "Total MW 42 42.5"]))
    bad.write_bytes(make_pdf([*ROWS, "Total MW 42 99"]))
    for i, (path, d) in enumerate(((good, "2017-05-01"), (bad, "2017-06-01")), 1):
        store.insert(con, store.Publication(
            "eirgrid.tso_connected_wind", f"u{i}", f"sha{i}", 1, date.fromisoformat(d), NOW,
            "last-modified", "estimated", str(path), NOW))
    loaded, problems = connected.load(con, NOW)
    assert loaded == 1 and len(problems) == 1 and "against printed" in problems[0]
    assert connected.load(con, NOW)[0] == 0  # nothing new; the refused one is asked again
    assert con.execute("select count(*) from connected_row").fetchone()[0] == 2
    h = connected.connected_history(con)
    assert h["TG13"].first_listed == date(2017, 5, 1) and h["TG35"].row.connected == date(2007, 8, 1)


def test_a_ref_on_an_esb_energised_list_connected_on_the_distribution_grid_not_as_a_sibling():
    # DG217 "Cloghboola (2) Ext" is ESB's "Glantaunyalkeen Windfarm", energised Sep 2018;
    # the name rule had called it a phase of Cloghboola (DG50)
    h = {"DG50": hist("DG50", {"Cloghboola"})}
    dso = {"DG217": ("Glantaunyalkeen Windfarm", date(2018, 9, 8))}
    got = connected.classify([leaver("DG217", "Cloghboola (2) Ext", "2016-05-31", mw=10)], h,
                             dso_energised=dso)[0]
    assert got.outcome == connected.DSO_CONNECTED and got.first_listed == date(2018, 9, 8)
    assert "Glantaunyalkeen" in got.why
    # without the ESB list the same project is only a phase by name
    assert connected.classify([leaver("DG217", "Cloghboola (2) Ext", "2016-05-31")],
                              h)[0].outcome == connected.SIBLING
