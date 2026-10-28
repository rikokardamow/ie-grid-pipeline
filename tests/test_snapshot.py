from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from iegrid import store


def test_snapshot_is_complete_and_readable(tmp_path):
    db = tmp_path / "s.duckdb"
    con = store.connect(db)
    con.execute("create table t as select 42 as x")
    con.close()
    snap = store.snapshot(db)
    assert snap.parent == tmp_path / "snapshots"
    assert not list(snap.parent.glob("*.part"))
    ro = store.connect_read_only(snap)
    assert ro.execute("select x from t").fetchone() == (42,)
    with pytest.raises(duckdb.Error):  # read only
        ro.execute("insert into t values (1)")


def test_same_second_runs_do_not_overwrite_and_latest_wins(tmp_path):
    db = tmp_path / "s.duckdb"
    store.connect(db).close()
    t = datetime(2026, 10, 28, 9, 0, 0, tzinfo=UTC)
    a = store.snapshot(db, now=t)
    b = store.snapshot(db, now=t + timedelta(microseconds=1))
    assert a != b and a.exists()
    assert store.latest_snapshot(tmp_path / "snapshots") == b


def test_old_snapshots_pruned(tmp_path):
    db = tmp_path / "s.duckdb"
    store.connect(db).close()
    t = datetime(2026, 10, 28, tzinfo=UTC)
    made = [store.snapshot(db, now=t + timedelta(minutes=i)) for i in range(store.KEEP_SNAPSHOTS + 3)]
    assert sorted((tmp_path / "snapshots").glob("*.duckdb")) == made[-store.KEEP_SNAPSHOTS:]


def test_no_snapshot_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        store.latest_snapshot(tmp_path)
