from dataclasses import replace
from datetime import UTC, date, datetime

from iegrid import store

PUB = store.Publication(
    source_id="eirgrid.tso_contracted_wind", url="https://x/a.pdf", sha256="ab" * 32,
    size_bytes=10, as_of=date(2026, 8, 5), published_at=datetime(2026, 8, 10, tzinfo=UTC),
    published_at_basis="last-modified", vintage_quality="estimated", raw_path="data/raw/a.pdf",
    ingested_at=datetime(2026, 10, 28, tzinfo=UTC),
)


def test_same_bytes_twice_keeps_the_first_row(con):
    assert store.insert(con, PUB) is not None
    before = con.execute("select * from publication").fetchall()
    again = replace(PUB, url="https://x/a.pdf?v=2", published_at=datetime(2026, 10, 1, tzinfo=UTC),
                    ingested_at=datetime(2026, 11, 4, tzinfo=UTC))
    assert store.insert(con, again) is None
    assert con.execute("select * from publication").fetchall() == before


def test_same_bytes_other_source_is_its_own_row(con):
    store.insert(con, PUB)
    assert store.insert(con, replace(PUB, source_id="eirgrid.tso_contracted_nonwind")) is not None
