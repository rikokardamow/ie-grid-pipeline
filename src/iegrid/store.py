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

-- g2. One row per project per publication per parser version. A project that
-- changes shows up as a different row under a later publication.
create table if not exists project_row (
    publication_id   bigint not null references publication (publication_id),
    parser_version   integer not null,
    row_order        integer not null,
    page             integer not null,
    project_ref      text not null,
    name             text not null,
    technology       text not null,
    mec_mw           decimal(12, 5) not null,
    node             text not null,
    station_110kv    text not null,
    voltage          text not null,
    processing_type  text not null,
    status           text not null,
    signed_month     date,
    energised_on     date,
    energised_note   text not null,
    raw              text not null,
    primary key (publication_id, parser_version, row_order)
);

-- g3. Where a backfilled file came from: the archive capture it was read from,
-- and when the archive first captured it (an upper bound on publication).
alter table publication add column if not exists fetched_from text;
alter table publication add column if not exists first_captured_at timestamptz;

-- g3. Every archived edition found, and what became of it. Insert only: a later
-- run that changes the outcome adds a row.
create sequence if not exists backfill_seq;
create table if not exists backfill_found (
    found_id        bigint primary key default nextval('backfill_seq'),
    source_id       text,
    original_url    text not null,
    capture_ts      text not null,
    archive_digest  text not null,
    outcome         text not null check (outcome in ('stored', 'duplicate', 'no-as-of',
                        'download-failed', 'no-publish-time', 'not-a-list')),
    publication_id  bigint references publication (publication_id),
    note            text not null,
    found_at        timestamptz not null
);

-- g3. A parse that failed, so the load doesn't retry it every run. It is tried
-- again when PARSER_VERSION goes up.
create table if not exists parse_failure (
    publication_id  bigint not null references publication (publication_id),
    parser_version  integer not null,
    error           text not null,
    failed_at       timestamptz not null,
    primary key (publication_id, parser_version)
);

-- g3. The total MW a list prints for itself, read from its text even when its
-- rows can't be parsed yet (older layouts). One row per publication.
create table if not exists edition_total (
    publication_id  bigint primary key references publication (publication_id),
    printed_mw      decimal(14, 5) not null,
    phrase          text not null,
    read_at         timestamptz not null
);

-- g4. ECP batch results publications (no TG/DG refs; counties and nodes), the
-- rows read from them, named substations from OpenStreetMap, and the county
-- given to each project, with how it was found. All insert only.
create table if not exists ecp_file (
    archive_digest  text not null,
    reader_version  integer not null,
    original_url    text not null,
    capture_ts      text not null,
    file_name       text not null,
    row_count       integer not null,
    read_at         timestamptz not null,
    primary key (archive_digest, reader_version)
);
create table if not exists ecp_row (
    archive_digest  text not null,
    reader_version  integer not null,
    row_order       integer not null,
    page            integer not null,
    name            text not null,
    county          text not null,
    mec_mw          decimal(12, 5),
    node            text not null,
    primary key (archive_digest, reader_version, row_order)
);
-- A connection node looked up in OpenStreetMap (Nominatim): the substation found,
-- and its county. No row when the lookup found nothing, or found it in two counties.
create table if not exists osm_node (
    node            text primary key,       -- normalised node name, as region.norm_node
    county          text not null,
    osm_id          text not null,
    display_name    text not null,
    fetched_at      timestamptz not null
);
create sequence if not exists region_build_seq;
create table if not exists region_build (
    build_id        bigint primary key default nextval('region_build_seq'),
    publications    text not null,    -- the contracted editions it covers, by id
    rules           text not null,    -- region.rules() + inputs, so a change is a new build
    built_at        timestamptz not null
);
create table if not exists project_county (
    build_id        bigint not null references region_build (build_id),
    publication_id  bigint not null references publication (publication_id),
    row_order       integer not null,
    project_ref     text not null,
    mec_mw          decimal(12, 5) not null,
    county          text,
    basis           text not null check (basis in ('name', 'cited', 'node', 'osm-node', 'none')),
    evidence        text not null,
    primary key (build_id, publication_id, row_order)
);

-- What each parse found, with the totals it is checked against.
create table if not exists parse_result (
    publication_id    bigint not null references publication (publication_id),
    parser_version    integer not null,
    row_count         integer not null,
    text_ref_count    integer not null,
    parsed_total_mw   decimal(14, 5) not null,
    printed_total_mw  decimal(14, 5),
    parsed_at         timestamptz not null,
    primary key (publication_id, parser_version)
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
    fetched_from: str | None = None         # archive capture URL, for backfilled files
    first_captured_at: datetime | None = None


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
            published_at_basis, vintage_quality, raw_path, ingested_at, fetched_from,
            first_captured_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict (source_id, sha256) do nothing
        returning publication_id
        """,
        [pub.source_id, pub.url, pub.sha256, pub.size_bytes, pub.as_of, pub.published_at,
         pub.published_at_basis, pub.vintage_quality, pub.raw_path, pub.ingested_at,
         pub.fetched_from, pub.first_captured_at],
    ).fetchone()
    return row[0] if row else None


# The newest live edition of each list, one publication_id per source. Two editions
# can share an as-of (a re-issue), so this picks by as-of, then publication time.
LATEST_LIVE = """
    select source_id, arg_max(publication_id, (as_of, published_at)) as publication_id
    from publication where fetched_from is null group by source_id
"""

SNAPSHOTS = DEFAULT_DB.parent / "snapshots"
KEEP_SNAPSHOTS = 5


def snapshot(path: Path | str = DEFAULT_DB, out_dir: Path | None = None,
             now: datetime | None = None) -> Path:
    """Copy the store to snapshots/<UTC timestamp>.duckdb beside it, for notebooks.

    DuckDB lets no process write while another has the file open, even read-only,
    so a notebook left open on the live store would block the weekly job.
    Notebooks read a snapshot instead; jobs call this after they write."""
    import os
    import shutil
    from datetime import UTC

    now = now or datetime.now(UTC)
    out_dir = out_dir or Path(path).parent / "snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{now:%Y-%m-%dT%H%M%S.%fZ}.duckdb"  # microseconds: same-second runs differ
    con = duckdb.connect(str(path))
    try:
        con.execute("checkpoint")  # flush the WAL so the copy is complete on its own
    finally:
        con.close()
    part = out.with_name(out.name + ".part")  # not matched by *.duckdb until renamed
    shutil.copyfile(path, part)
    os.replace(part, out)
    # Snapshots are copies of the store, not the record, so old ones can go.
    for old in sorted(out_dir.glob("*.duckdb"))[:-KEEP_SNAPSHOTS]:
        old.unlink()
    return out


def latest_snapshot(out_dir: Path = SNAPSHOTS) -> Path:
    snaps = sorted(out_dir.glob("*.duckdb"))
    if not snaps:
        raise FileNotFoundError(f"no snapshot in {out_dir}; run a job first")
    return snaps[-1]


def connect_read_only(path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """For notebooks: the latest snapshot, read only. They read, never write."""
    con = duckdb.connect(str(path or latest_snapshot()), read_only=True)
    con.execute("set timezone = 'UTC'")
    return con
