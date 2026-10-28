from datetime import UTC, datetime

import pytest

from iegrid import load, parse, store
from tests.test_store import PUB

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)


@pytest.fixture
def fake_parser(monkeypatch):
    calls = []

    def fake(content):
        calls.append(content)
        if content == b"broken":
            raise parse.ParseError("bad row")
        orders = (1, 1) if content == b"dup" else (1, 2)  # a duplicate key fails mid-insert
        total = parse.Decimal("99") if content == b"off" else parse.Decimal("21")
        rows = [parse.ProjectRow(
            row_order=o, page=1, project_ref=f"TG{i}", name="x", technology="Wind",
            mec_mw=parse.Decimal("10.5"), node="N", station_110kv="", voltage="110 kV",
            processing_type="ECP-2.1", status="Contracted", signed_month=None,
            energised_on=None, energised_note="", raw="[]") for i, o in enumerate(orders, 1)]
        return parse.Parsed(rows, total)

    monkeypatch.setitem(parse.PARSERS, PUB.source_id, fake)
    monkeypatch.setattr(parse, "printed_total", lambda content: None)
    monkeypatch.setattr(parse, "refs_in_text", lambda content: {1: 2})
    return calls


def add_pub(con, tmp_path, content, sha):
    raw = tmp_path / f"{sha}.pdf"
    raw.write_bytes(content)
    return store.insert(con, store.Publication(**{**PUB.__dict__, "sha256": sha,
                                                   "raw_path": str(raw)}))


def test_parses_once(con, tmp_path, fake_parser):
    add_pub(con, tmp_path, b"ok", "a" * 64)
    s = load.run(con, NOW)
    assert s.ok and len(s.parsed) == 1
    assert con.execute("select count(*) from project_row").fetchone()[0] == 2
    assert con.execute("select row_count, text_ref_count, parsed_total_mw, printed_total_mw "
                       "from parse_result").fetchone() == (2, 2, 21, 21)
    assert not load.run(con, NOW).parsed
    assert len(fake_parser) == 1


def test_failed_parse_stores_nothing(con, tmp_path, fake_parser):
    add_pub(con, tmp_path, b"broken", "b" * 64)
    s = load.run(con, NOW)
    assert not s.ok and "bad row" in s.errors[0]
    assert con.execute("select count(*) from project_row").fetchone()[0] == 0
    assert con.execute("select count(*) from parse_result").fetchone()[0] == 0


def test_new_parser_version_adds_rows_keeps_old(con, tmp_path, fake_parser, monkeypatch):
    add_pub(con, tmp_path, b"ok", "a" * 64)
    load.run(con, NOW)
    monkeypatch.setattr(parse, "PARSER_VERSION", 2)
    assert len(load.run(con, NOW).parsed) == 1
    got = con.execute("select parser_version, count(*) from project_row group by 1 order by 1")
    assert got.fetchall() == [(1, 2), (2, 2)]


def test_sources_without_a_parser_are_left_alone(con, tmp_path, fake_parser):
    raw = tmp_path / "s.pdf"
    raw.write_bytes(b"x")
    store.insert(con, store.Publication(**{**PUB.__dict__, "source_id": "esb.renewable_summary",
                                           "raw_path": str(raw)}))
    assert not load.run(con, NOW).parsed


def test_exit_code(tmp_path, fake_parser):
    db = tmp_path / "s.duckdb"
    con = store.connect(db)
    add_pub(con, tmp_path, b"broken", "b" * 64)
    con.close()
    assert load.main(["--db", str(db)]) == 1
    assert list((tmp_path / "snapshots").glob("*.duckdb"))


def counts(con):
    return [con.execute(f"select count(*) from {t}").fetchone()[0]
            for t in ("project_row", "parse_result")]


def test_failure_mid_insert_rolls_back(con, tmp_path, fake_parser):
    add_pub(con, tmp_path, b"dup", "c" * 64)
    s = load.run(con, NOW)
    assert not s.ok and counts(con) == [0, 0]


def test_total_that_does_not_tie_stores_nothing(con, tmp_path, fake_parser):
    add_pub(con, tmp_path, b"off", "d" * 64)
    s = load.run(con, NOW)
    assert not s.ok and "prints 99" in s.errors[0] and counts(con) == [0, 0]
    assert con.execute("select count(*) from parse_failure").fetchone()[0] == 1  # the reason is kept


def test_skipped_page_stores_nothing(con, tmp_path, fake_parser, monkeypatch):
    monkeypatch.setattr(parse, "refs_in_text", lambda content: {1: 2, 2: 16})
    add_pub(con, tmp_path, b"ok", "e" * 64)
    s = load.run(con, NOW)
    assert not s.ok and "18 refs" in s.errors[0] and counts(con) == [0, 0]


def test_unexpected_error_is_reported_and_others_still_load(con, tmp_path, fake_parser,
                                                            monkeypatch):
    add_pub(con, tmp_path, b"ok", "f" * 64)
    add_pub(con, tmp_path, b"ok", "g" * 64)
    real = parse.refs_in_text
    seen = []

    def flaky(content):
        seen.append(1)
        if len(seen) == 1:
            raise RuntimeError("boom")
        return real(content)

    monkeypatch.setattr(parse, "refs_in_text", flaky)
    s = load.run(con, NOW)
    assert len(s.errors) == 1 and "boom" in s.errors[0] and len(s.parsed) == 1


def test_failed_parse_is_recorded_and_not_retried_until_version_bump(con, tmp_path, fake_parser,
                                                                      monkeypatch):
    add_pub(con, tmp_path, b"broken", "h" * 64)
    assert not load.run(con, NOW).ok
    assert con.execute("select parser_version, error from parse_failure").fetchall() == [
        (1, "bad row")]
    assert load.run(con, NOW).ok  # not retried at the same version
    monkeypatch.setattr(parse, "PARSER_VERSION", 2)
    assert not load.run(con, NOW).ok  # tried again under a new parser


def test_printed_totals_read_even_when_rows_fail(con, tmp_path, fake_parser, monkeypatch):
    monkeypatch.setattr(parse, "printed_total",
                        lambda content: (parse.Decimal("1714.23"), "Total TSO Contracted Wind"))
    add_pub(con, tmp_path, b"broken", "i" * 64)
    load.run(con, NOW)
    assert con.execute("select printed_mw, phrase from edition_total").fetchall() == [
        (parse.Decimal("1714.23"), "Total TSO Contracted Wind")]
    load.run(con, NOW)  # read once
    assert con.execute("select count(*) from edition_total").fetchone()[0] == 1
