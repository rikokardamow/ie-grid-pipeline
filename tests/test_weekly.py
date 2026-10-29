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
    )

    def ecp(con, now):
        calls["ecp"] += 1
        return ["read 40 rows from ECP-2.5 results", "download https://x/ECP.pdf: timed out"]

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
    return got, calls, tmp_path


def rows(con):
    return con.execute("select status, new_files, stored, parsed, problems, report_path, "
                       "error from run_log order by run_id").fetchall()


def test_a_quiet_week_is_logged_ok_and_the_archive_is_not_read(con, steps):
    _, calls, tmp = steps
    _, run = weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW)
    assert run.status == "ok" and calls["ecp"] == 0
    status, new, stored, parsed, problems, path, error = rows(con)[0]
    assert (status, new, stored, parsed, error) == ("ok", 0, "", 0, None)
    assert problems == "counties: build: unchanged"
    assert path.endswith("r.json")


def test_a_week_with_a_new_file_reads_the_batch_results_and_flags_a_failed_download(con, steps):
    got, calls, tmp = steps
    got.ingest.stored = ["esb.dso_contracted_renewable as of 2026-10-01 0123456789ab"]
    got.load.parsed = ["esb.dso_contracted_renewable #160: 120 rows"]
    _, run = weekly.run_weekly(con, tmp / "out", tmp / "raw", NOW)
    assert calls["ecp"] == 1
    assert run.status == "attention"  # the ECP download failed; the list itself is in
    status, new, _, parsed, problems, _, _ = rows(con)[0]
    assert (status, new, parsed) == ("attention", 1, 1)
    assert "ECP results: download https://x/ECP.pdf: timed out" in problems
    assert "ECP results: read 40 rows from ECP-2.5 results" in problems


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


def test_a_store_from_before_g8_has_no_runs_to_show():
    class Old:
        def execute(self, sql):
            raise RuntimeError("Catalog Error: Table with name run_log does not exist")

    assert report._runs(Old())["latest"] == []
