"""g8: the weekly run logs one row whatever happens, and says what needs a look."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from iegrid import counties, ingest, load, report, weekly

NOW = datetime(2026, 11, 4, 7, 0, tzinfo=UTC)


@pytest.fixture
def steps(monkeypatch, tmp_path):
    """Each step stubbed; a test changes what one of them returns."""
    calls = {"ecp": 0}
    got = SimpleNamespace(
        ingest=SimpleNamespace(stored=[], missing_sources=[], errors=[], unknown_links=[]),
        load=SimpleNamespace(parsed=[], errors=[]),
        report_error=None,
        ecp_notes=["read 40 rows from ECP-2.5 results", "download https://x/ECP.pdf: timed out"],
    )

    def ecp(con, now):
        calls["ecp"] += 1
        return got.ecp_notes

    def write(con, out, now):
        if got.report_error:
            raise got.report_error
        out.mkdir(parents=True, exist_ok=True)
        (out / "r.json").write_text("{}")
        return out / "r.json"

    monkeypatch.setattr(ingest, "run", lambda con, raw, now=None, **kw: got.ingest)
    monkeypatch.setattr(load, "run", lambda con, now=None: got.load)
    monkeypatch.setattr(counties, "read_ecp_files", ecp)
    monkeypatch.setattr(counties, "build", lambda con, now: "build: unchanged")
    monkeypatch.setattr(report, "write", write)
    monkeypatch.setattr(weekly, "code_version", lambda: "abc1234 parser 3")
    monkeypatch.setattr(weekly.connected, "load", lambda con, now: (0, []))
    monkeypatch.setattr(weekly.esb_legacy, "load", lambda con, now: (0, [], []))
    monkeypatch.setattr(weekly.grid, "queries_for", lambda con: [])
    monkeypatch.setattr(weekly.grid, "fetch_places", lambda q: [])
    return got, calls, tmp_path


def rows(con):
    return con.execute("select status, new_files, stored, parsed, problems, report_path, "
                       "error from run_log order by run_id").fetchall()


def test_a_quiet_week_is_logged_ok_and_the_archive_is_not_read_again(con, steps):
    got, calls, tmp = steps
    got.ecp_notes = ["read 40 rows from ECP-2.5 results"]
    weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW)  # the first run reads them
    _, run = weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW + timedelta(weeks=1))
    assert run.status == "ok" and calls["ecp"] == 1
    status, new, stored, parsed, problems, path, error = rows(con)[1]
    assert (status, new, stored, parsed, problems, error) == ("ok", 0, "", 0, "", None)
    assert path.endswith("r.json")
    assert run.notes == ["counties: build: unchanged"]


def test_a_failed_batch_results_read_is_tried_again_next_week(con, steps):
    # g8 review: it was only read in a week that stored a file
    got, calls, tmp = steps
    weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW)  # the download fails
    got.ecp_notes = ["read 40 rows from ECP-2.5 results"]
    _, run = weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW + timedelta(weeks=1))
    assert calls["ecp"] == 2 and run.status == "ok" and run.ecp_read
    _, run = weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW + timedelta(weeks=2))
    assert calls["ecp"] == 2  # read cleanly, and nothing new came in since


def test_a_week_with_a_new_file_reads_the_batch_results_and_flags_a_failed_download(con, steps):
    got, calls, tmp = steps
    con.execute("insert into run_log values (99, ?, ?, 'ok', 0, '', 0, '', '', true, null, "
                "'x', null)", [NOW - timedelta(weeks=1), NOW - timedelta(weeks=1)])
    con.execute("insert into publication values (1, 'esb.dso_contracted_renewable', 'u', "
                "'abc', 1, '2026-10-01', ?, 'last-modified', 'estimated', 'r', ?, null, null)",
                [NOW, NOW])
    got.ingest.stored = ["esb.dso_contracted_renewable as of 2026-10-01 0123456789ab"]
    got.load.parsed = ["esb.dso_contracted_renewable #160: 120 rows"]
    _, run = weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW)
    assert calls["ecp"] == 1
    assert run.status == "attention"  # the ECP download failed; the list itself is in
    status, new, _, parsed, problems, _, _ = rows(con)[0]
    assert (status, new, parsed) == ("attention", 1, 1)
    assert problems == "ECP results: download https://x/ECP.pdf: timed out"
    assert "ECP results: read 40 rows from ECP-2.5 results" in run.notes


def test_a_refused_edition_or_a_new_kind_of_link_needs_a_look_but_does_not_fail(con, steps):
    got, _, tmp = steps
    got.ingest.unknown_links = ["https://www.eirgrid.ie/TSO-Connected-Generators.pdf"]
    got.load.errors = ["eirgrid.tso_contracted_wind #170: MW 2050.0 against a printed 2061.0"]
    _, run = weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW)
    assert run.status == "attention"
    problems = rows(con)[0][4]
    assert "unknown link: https://www.eirgrid.ie/TSO-Connected-Generators.pdf" in problems
    assert "load: eirgrid.tso_contracted_wind #170" in problems


def test_a_missing_list_fails_the_run_but_the_report_is_still_written(con, steps):
    got, _, tmp = steps
    got.ingest.missing_sources = ["esb.dso_energised_renewable"]
    got.ingest.unknown_links = ["https://x/new.pdf"]  # attention can't hide a failure
    _, run = weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW)
    status, *_, path, _ = rows(con)[0]
    assert status == "failed" and run.report_path is not None and path is not None


def test_a_crash_is_logged_as_a_failed_run_with_its_error(con, steps):
    got, _, tmp = steps
    got.report_error = ValueError("the page runs over its footer")
    weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW)
    status, *_, path, error = rows(con)[0]
    assert status == "failed" and path is None
    assert error == "ValueError: the page runs over its footer"


def test_main_exits_1_only_for_a_failed_run(steps, monkeypatch, tmp_path, capsys):
    got, _, tmp = steps
    got.ecp_notes = []
    monkeypatch.setattr(weekly.store, "snapshot", lambda db: tmp / "snap.duckdb")
    db = str(tmp / "w.duckdb")
    assert weekly.main(["--db", db, "--out", str(tmp / "out"), "--raw", str(tmp / "raw")]) == 0
    got.ingest.missing_sources = ["esb.dso_energised_renewable"]
    assert weekly.main(["--db", db, "--out", str(tmp / "out"), "--raw", str(tmp / "raw")]) == 1
    out = capsys.readouterr().out
    assert "run 1: ok" in out and "run 2: failed" in out
    assert "missing from its page: esb.dso_energised_renewable" in out


def test_the_report_shows_earlier_runs_newest_first(con, steps):
    got, _, tmp = steps
    for week in range(4):
        got.ingest.stored = ["esb.dso_contracted_renewable as of 2026-10-01 x"] if week == 2 else []
        weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW + timedelta(weeks=week))
    got_runs = report._runs(con)
    assert (got_runs["count"], got_runs["with_new_files"], got_runs["failed"]) == (4, 1, 0)
    assert got_runs["first"] == "2026-11-04T07:00+00:00"
    runs = got_runs["latest"]
    assert [r["run"] for r in runs] == [4, 3, 2, 1]
    assert [r["new_files"] for r in runs] == [0, 1, 0, 0]
    assert runs[1]["stored"] == ["esb.dso_contracted_renewable as of 2026-10-01 x"]
    assert runs[-1]["started"] == "2026-11-04T07:00+00:00"




def test_two_runs_in_a_minute_keep_both_reports(con, tmp_path, monkeypatch):
    # g8 review: the second overwrote the first, losing a "new" it may have found
    monkeypatch.setattr(report, "build", lambda con, now, last: {"report_date": "x"})
    monkeypatch.setattr(report, "render", lambda rep, path: path.write_text("pdf"))
    a = report.write(con, tmp_path, NOW)
    b = report.write(con, tmp_path, NOW)
    assert (a.name, b.name) == ("2026-11-04T0700.json", "2026-11-04T070000.json")
    assert report.last_report(tmp_path) is not None
    assert max(p.name for p in tmp_path.glob("*.json")) == b.name


def test_a_page_that_cannot_be_drawn_leaves_no_json(con, tmp_path, monkeypatch):
    # g8 review: the JSON was written first and became next week's last_report
    monkeypatch.setattr(report, "build", lambda con, now, last: {"report_date": "x"})

    def broken(rep, path):
        raise ValueError("the page runs over its footer")

    monkeypatch.setattr(report, "render", broken)
    with pytest.raises(ValueError):
        report.write(con, tmp_path, NOW)
    assert list(tmp_path.glob("*.json")) == []


def test_a_real_store_without_run_log_shows_no_runs_but_other_errors_surface():
    import duckdb

    old = duckdb.connect(":memory:")
    assert report._runs(old)["latest"] == []

    class Broken:
        def execute(self, sql):
            raise duckdb.IOException("disk gone")

    with pytest.raises(duckdb.IOException):
        report._runs(Broken())


def test_a_failed_place_lookup_needs_a_look(con, steps, monkeypatch):
    got, _, tmp = steps
    got.ecp_notes = []
    monkeypatch.setattr(weekly.grid, "fetch_places",
                        lambda q: ["nominatim 'pollagh, County Kerry': timed out"])
    cache = tmp / "grid.json"
    cache.write_text("{}")
    monkeypatch.setattr(weekly.grid, "CACHE", cache)
    _, run = weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW)
    assert run.status == "attention"
    assert "places: nominatim 'pollagh, County Kerry': timed out" in run.problems


def test_a_refused_connected_edition_needs_a_look(con, steps, monkeypatch):
    got, _, tmp = steps
    got.ecp_notes = []
    monkeypatch.setattr(weekly.connected, "load", lambda con, now: (
        0, ["eirgrid.tso_connected_wind 2017-03-01: installed 1316.25 against printed 1286.555"]))
    _, run = weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW)
    assert run.status == "attention"
    assert any(p.startswith("connected lists: eirgrid.tso_connected_wind") for p in run.problems)


def test_a_refused_esb_legacy_edition_needs_a_look(con, steps, monkeypatch):
    got, _, tmp = steps
    got.ecp_notes = []
    monkeypatch.setattr(weekly.esb_legacy, "load", lambda con, now: (
        0, ["esb.dso_energised_wind 2019-06-04: refs on the page not read as rows: ['DG1']"], []))
    _, run = weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW)
    assert run.status == "attention"
    assert any(p.startswith("ESB legacy lists: esb.dso_energised_wind") for p in run.problems)
