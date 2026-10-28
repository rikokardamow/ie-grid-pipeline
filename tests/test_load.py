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
        rows = [parse.ProjectRow(
            row_order=i, page=1, project_ref=f"TG{i}", name="x", technology="Wind",
            mec_mw=parse.Decimal("10.5"), node="N", station_110kv="", voltage="110 kV",
            processing_type="ECP-2.1", status="Contracted", signed_month=None,
            energised_on=None, energised_note="", raw="[]") for i in (1, 2)]
        return parse.Parsed(rows, parse.Decimal("21"))

    monkeypatch.setitem(parse.PARSERS, PUB.source_id, fake)
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
