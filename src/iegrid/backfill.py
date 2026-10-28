"""g3: every archived edition of the lists, stored like a live one and marked.

    uv run python -m iegrid.backfill            # search the archive, store what's new
    uv run python -m iegrid.backfill --retry    # also retry editions that failed before

The Wayback Machine's index (CDX) is searched under each publisher prefix. One
edition = one distinct file (the archive's content digest), taken from its
earliest capture. Every edition found gets a backfill_found row saying what
became of it, so "found but not stored" always has a written reason.

Publication time for an archived file: the original server's Last-Modified,
which the archive keeps (x-archive-orig-last-modified). EirGrid re-uploaded its
library around 2015, so on older files that date can be years after the as-of;
the first capture time is kept beside it as a second upper bound.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from iegrid import asof, fetch, ingest, store
from iegrid.sources import ARCHIVE_PREFIXES, classify_archived, normalised_name

CDX = "https://web.archive.org/cdx/search/cdx"
CACHE = store.ROOT / "data" / "archive-cache"
PAUSE_S = 1.5          # between archive requests
RETRIES = 4
LISTISH = ("contracted", "connected", "energised", "summary-report", "live-connection")

# Outcomes that are final: a re-run skips these digests unless --retry.
FINAL = ("stored", "duplicate", "not-a-list")


@dataclass(frozen=True)
class Candidate:
    source_id: str | None
    original_url: str
    capture_ts: str
    digest: str


@dataclass(frozen=True)
class Capture:
    content: bytes
    orig_last_modified: datetime | None
    captured_at: datetime


@dataclass
class Summary:
    outcomes: dict[str, list[str]] = field(default_factory=dict)

    def add(self, outcome: str, msg: str) -> None:
        self.outcomes.setdefault(outcome, []).append(msg)

    @property
    def ok(self) -> bool:
        return "download-failed" not in self.outcomes


def _get(url: str) -> tuple[bytes, dict[str, str]]:
    """GET with backoff: the archive answers 429 and 5xx under load."""
    for attempt in range(RETRIES):
        try:
            return fetch._get(url)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == RETRIES - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == RETRIES - 1:
                raise
        time.sleep(PAUSE_S * 4 ** (attempt + 1))
    raise AssertionError("unreachable")


def cdx_rows(prefix: str) -> list[list[str]]:
    query = (f"{CDX}?url={prefix}&output=json&fl=timestamp,original,digest,mimetype"
             f"&filter=statuscode:200&limit=200000")
    body, _ = _get(query)
    if not body.lstrip().startswith(b"["):
        raise OSError(f"archive index unavailable for {prefix}: {body[:80]!r}")
    rows = json.loads(body or b"[]")
    return rows[1:] if rows else []


def candidates(rows: list[list[str]]) -> list[Candidate]:
    """One per distinct file, from its earliest capture. Only list-like PDF names."""
    first: dict[str, Candidate] = {}
    for ts, original, digest, _mime in rows:
        if not original.split("?", 1)[0].lower().endswith(".pdf"):
            continue
        if not any(k in normalised_name(original) for k in LISTISH):
            continue
        if digest not in first or ts < first[digest].capture_ts:
            first[digest] = Candidate(classify_archived(original), original, ts, digest)
    return sorted(first.values(), key=lambda c: (str(c.source_id), c.capture_ts))


def capture(c: Candidate, cache: Path = CACHE) -> Capture:
    """The file as first captured, from the cache when it's been fetched before."""
    body_path, meta_path = cache / f"{c.digest}.pdf", cache / f"{c.digest}.json"
    if body_path.exists() and meta_path.exists():
        content, meta = body_path.read_bytes(), json.loads(meta_path.read_text())
    else:
        time.sleep(PAUSE_S)
        content, headers = _get(f"https://web.archive.org/web/{c.capture_ts}id_/{c.original_url}")
        meta = {k: headers.get(k) for k in ("x-archive-orig-last-modified", "memento-datetime")}
        cache.mkdir(parents=True, exist_ok=True)
        ingest.write_raw(body_path, content, hashlib.sha256(content).hexdigest())
        meta_path.write_text(json.dumps(meta))
    captured = (fetch.parse_last_modified(meta.get("memento-datetime"))
                or datetime.strptime(c.capture_ts, "%Y%m%d%H%M%S").replace(tzinfo=UTC))
    return Capture(content, fetch.parse_last_modified(meta.get("x-archive-orig-last-modified")),
                   captured)


def seen_digests(con, final_only: bool) -> set[str]:
    sql = "select archive_digest from backfill_found"
    if final_only:
        sql += f" where outcome in ({', '.join(repr(o) for o in FINAL)})"
    return {r[0] for r in con.execute(sql).fetchall()}


def record(con, c: Candidate, outcome: str, note: str, now: datetime,
           publication_id: int | None = None) -> None:
    con.execute(
        "insert into backfill_found (source_id, original_url, capture_ts, archive_digest, "
        "outcome, publication_id, note, found_at) values (?, ?, ?, ?, ?, ?, ?, ?)",
        [c.source_id, c.original_url, c.capture_ts, c.digest, outcome, publication_id, note, now],
    )


def backfill_one(con, c: Candidate, raw_dir: Path, now: datetime,
                 get_capture=capture) -> tuple[str, str, int | None]:
    """Returns (outcome, note, publication_id)."""
    if c.source_id is None:
        return "not-a-list", "name matches none of the lists", None
    try:
        cap = get_capture(c)
    except Exception as exc:  # noqa: BLE001 - recorded, retried with --retry
        return "download-failed", str(exc)[:200], None
    if not cap.content.startswith(b"%PDF"):
        return "download-failed", f"not a PDF ({cap.content[:20]!r})", None
    sha = hashlib.sha256(cap.content).hexdigest()
    existing = con.execute("select publication_id from publication where source_id = ? and "
                           "sha256 = ?", [c.source_id, sha]).fetchone()
    if existing:
        return "duplicate", f"same bytes as publication {existing[0]}", existing[0]
    try:
        as_of = asof.as_of_from_pdf(cap.content)
    except ValueError as exc:  # two different as-of dates in one file
        return "no-as-of", str(exc), None
    except Exception as exc:  # noqa: BLE001 - a PDF pdfplumber can't open
        return "no-as-of", f"unreadable PDF: {str(exc)[:150]}", None
    if as_of is None:
        return "no-as-of", "no as-of phrase found in the first pages", None
    if cap.orig_last_modified is None:
        return "no-publish-time", "the archive kept no Last-Modified for this capture", None
    path = ingest.raw_path_for(raw_dir, c.source_id, as_of, sha)
    ingest.write_raw(path, cap.content, sha)
    pid = store.insert(con, store.Publication(
        source_id=c.source_id, url=c.original_url, sha256=sha, size_bytes=len(cap.content),
        as_of=as_of, published_at=cap.orig_last_modified, published_at_basis="last-modified",
        vintage_quality="estimated", raw_path=ingest.stored_path(path), ingested_at=now,
        fetched_from=f"https://web.archive.org/web/{c.capture_ts}id_/{c.original_url}",
        first_captured_at=cap.captured_at,
    ))
    return "stored", f"as of {as_of}", pid


def run(con, raw_dir: Path = ingest.DEFAULT_RAW, retry: bool = False,
        rows_for=cdx_rows, get_capture=capture, now: datetime | None = None) -> Summary:
    now = now or datetime.now(UTC)
    summary = Summary()
    rows: list[list[str]] = []
    for prefix in ARCHIVE_PREFIXES:
        try:
            rows.extend(rows_for(prefix))
        except Exception as exc:  # noqa: BLE001 - one prefix down doesn't stop the rest
            summary.add("download-failed", f"index {prefix}: {exc}")
    skip = seen_digests(con, final_only=retry)
    for c in candidates(rows):
        if c.digest in skip:
            continue
        outcome, note, pid = backfill_one(con, c, raw_dir, now, get_capture)
        record(con, c, outcome, note, now, pid)
        summary.add(outcome, f"{c.source_id} {normalised_name(c.original_url)}: {note}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(store.DEFAULT_DB))
    parser.add_argument("--raw", default=str(ingest.DEFAULT_RAW))
    parser.add_argument("--retry", action="store_true",
                        help="retry editions whose outcome wasn't final")
    args = parser.parse_args(argv)
    con = store.connect(args.db)
    try:
        summary = run(con, Path(args.raw), retry=args.retry)
    finally:
        con.close()
        print(f"snapshot: {store.snapshot(args.db).name}")
    for outcome, items in sorted(summary.outcomes.items()):
        print(f"{outcome}: {len(items)}")
        for item in items if outcome != "stored" else items[:5]:
            print(f"  {item}")
    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
