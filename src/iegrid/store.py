"""The local DuckDB store. Insert only: nothing here updates or deletes.

publication: one row per distinct file we have seen for a source. The same bytes
seen again add nothing (unique source_id + sha256). A new edition of a list,
or a re-issue with changed bytes, is a new row.

Three times, as in the record:
    as_of         the "correct as of" date printed in the file
    published_at  when the publisher put it up. No publisher states this, so it
                  is always an estimate (vintage_quality = 'estimated'):
                  the HTTP Last-Modified header (the upload time, basis
                  'last-modified'), else the time we pulled it (basis 'ingested')
    ingested_at   when we pulled it
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb

# Anchored at the repo root, so running from notebooks/ or anywhere else finds the same store.
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "iegrid.duckdb"

SCHEMA = """
create sequence if not exists publication_seq;
create table if not exists publication (
    publication_id      bigint primary key default nextval('publication_seq'),
    source_id           text not null,
    url                 text not null,
    sha256              text not null,
    size_bytes          bigint not null,
    as_of               date not null,
    published_at        timestamptz not null,
    published_at_basis  text not null check (published_at_basis in ('last-modified', 'ingested')),
    vintage_quality     text not null check (vintage_quality in ('exact', 'estimated')),
    raw_path            text not null,
    ingested_at         timestamptz not null,
    unique (source_id, sha256)
);
"""


@dataclass(frozen=True)
class Publication:
    source_id: str
    url: str
    sha256: str
    size_bytes: int
    as_of: date
    published_at: datetime
    published_at_basis: str
    vintage_quality: str
    raw_path: str
    ingested_at: datetime


def connect(path: Path | str = DEFAULT_DB) -> duckdb.DuckDBPyConnection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("set timezone = 'UTC'")
    con.execute(SCHEMA)
    return con


def known(con: duckdb.DuckDBPyConnection, source_id: str, sha256: str) -> bool:
    row = con.execute(
        "select 1 from publication where source_id = ? and sha256 = ?", [source_id, sha256]
    ).fetchone()
    return row is not None


def insert(con: duckdb.DuckDBPyConnection, pub: Publication) -> int | None:
    """Store a publication. Returns its id, or None if these bytes are already stored."""
    row = con.execute(
        """
        insert into publication (source_id, url, sha256, size_bytes, as_of, published_at,
            published_at_basis, vintage_quality, raw_path, ingested_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict (source_id, sha256) do nothing
        returning publication_id
        """,
        [pub.source_id, pub.url, pub.sha256, pub.size_bytes, pub.as_of, pub.published_at,
         pub.published_at_basis, pub.vintage_quality, pub.raw_path, pub.ingested_at],
    ).fetchone()
    return row[0] if row else None


def connect_read_only(path: Path | str = DEFAULT_DB) -> duckdb.DuckDBPyConnection:
    """For notebooks: they read, never write."""
    con = duckdb.connect(str(path), read_only=True)
    con.execute("set timezone = 'UTC'")
    return con
