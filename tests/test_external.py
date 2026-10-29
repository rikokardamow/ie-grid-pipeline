"""The outside check: sourced figures, a scope-and-date-matched total, and the arithmetic."""

from datetime import UTC, date, datetime

from iegrid import external, store

NOW = datetime(2026, 10, 29, tzinfo=UTC)


def pub(con, source, sha, as_of):
    return store.insert(con, store.Publication(
        source, f"u-{sha}", sha, 1, date.fromisoformat(as_of), NOW, "last-modified", "estimated",
        f"raw/{sha}.pdf", NOW))


def test_every_published_figure_names_its_source_and_the_words_it_says():
    for row in external.published().values():
        assert row["source_url"].startswith("https://") and row["source_says"]
        assert float(row["value"]) > 0 and row["unit"] and row["scope"] and row["checked_on"]


def test_the_difference_is_ours_minus_theirs_in_mw_and_as_a_share_of_theirs():
    assert external.compare(4409.9, 4536.0) == {
        "ours_mw": 4409.9, "theirs_mw": 4536.0, "diff_mw": -126.1, "diff_pct": -0.0278}


def test_the_total_takes_the_connected_list_before_the_day_and_the_esb_list_after_it():
    con = store.connect(":memory:")
    old = pub(con, "eirgrid.tso_connected_renewable", "a", "2022-03-01")
    new = pub(con, "eirgrid.tso_connected_renewable", "b", "2022-10-01")
    esb = pub(con, "esb.dso_energised_wind", "c", "2023-04-20")
    for pid, mw in ((old, 2074.05), (new, 2117.25)):
        con.execute("insert into connected_row values (?, 1, 'TG1', 'x', 1, ?, null, true, 'Wind', "
                    "'', now())", [pid, mw])
    for i, (mw, on) in enumerate(((10.0, date(2020, 1, 1)), (5.0, None), (7.0, date(2023, 2, 1))), 1):
        con.execute("insert into esb_legacy_row values (?, ?, 'DG1', 'n', 'Wind', ?, '', '', '', "
                    "'Energised', '', ?, '', '', now())", [esb, i, mw, on])
    got = external.wind_at(con, date(2022, 12, 31))
    assert got["tso_mw"] == 2117.25 and got["tso_edition"] == "2022-10-01"   # the newer, not 2022-03
    # dated by the day or undated counts; one energised in Feb 2023 does not
    assert got["dso_mw"] == 15.0 and got["dso_rows"] == 2 and got["dso_undated_mw"] == 5.0


def test_no_total_is_given_when_either_publishers_list_is_missing():
    con = store.connect(":memory:")
    pub(con, "eirgrid.tso_connected_renewable", "a", "2022-10-01")
    assert external.wind_at(con, date(2022, 12, 31)) is None
    assert external.build(con) is None
