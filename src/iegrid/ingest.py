"""g1: find every current list, keep the raw file, store one publication row each.

    uv run python -m iegrid.ingest            # data/iegrid.duckdb, data/raw/
    uv run python -m iegrid.ingest --db x.duckdb --raw x/

Re-running with nothing new published adds 0 rows. Exit code 1 if an expected
list is missing from its page or a file has no as-of date, so a scheduled run
fails loudly when a publisher changes its page.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from iegrid import asof, fetch, store
from iegrid.sources import PAGES, SOURCES, classify

DEFAULT_RAW = store.ROOT / "data" / "raw"


@dataclass
class Summary:
    stored: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    unknown_links: list[str] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing_sources or self.errors)


def raw_path_for(raw_dir: Path, source_id: str, as_of, sha256: str) -> Path:
    return raw_dir / source_id / f"{as_of.isoformat()}-{sha256[:12]}.pdf"


def stored_path(path: Path) -> str:
    """raw_path as stored: relative to the repo root when it is inside it."""
    try:
        return str(path.resolve().relative_to(store.ROOT))
    except ValueError:
        return str(path.resolve())


def write_raw(path: Path, content: bytes, sha256: str) -> None:
    """Write via a temp file and rename, so a killed run never leaves a half file.
    A file already there with the wrong hash (a half write from before) is replaced."""
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == sha256:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(content)
    os.replace(tmp, path)


def ingest_file(con, raw_dir: Path, source_id: str, dl: fetch.Download,
                now: datetime) -> tuple[str, str]:
    """Returns ('stored' | 'unchanged' | 'error', message)."""
    sha = hashlib.sha256(dl.content).hexdigest()
    if store.known(con, source_id, sha):
        return "unchanged", f"{source_id} {sha[:12]}"
    as_of = asof.as_of_from_pdf(dl.content)
    if as_of is None:
        return "error", f"{source_id}: no as-of date found in {dl.url}"
    path = raw_path_for(raw_dir, source_id, as_of, sha)
    write_raw(path, dl.content, sha)
    if dl.last_modified is not None:
        published_at, basis = dl.last_modified, "last-modified"
    else:
        published_at, basis = now, "ingested"
    pub = store.Publication(
        source_id=source_id, url=dl.url, sha256=sha, size_bytes=len(dl.content), as_of=as_of,
        published_at=published_at, published_at_basis=basis, vintage_quality="estimated",
        raw_path=stored_path(path), ingested_at=now,
    )
    if store.insert(con, pub) is None:
        return "unchanged", f"{source_id} {sha[:12]}"
    return "stored", f"{source_id} as of {as_of} {sha[:12]}"


def run(con, raw_dir: Path = DEFAULT_RAW,
        page_links: Callable[[str], list[str]] | None = None,
        download: Callable[[str], fetch.Download] | None = None,
        now: datetime | None = None) -> Summary:
    page_links = page_links or fetch.page_links
    download = download or fetch.download
    now = now or datetime.now(UTC)
    summary = Summary()
    found: set[str] = set()
    for page in PAGES:
        try:
            links = page_links(page)
        except Exception as exc:  # noqa: BLE001 - a page being down is reported, not fatal to the other page
            summary.errors.append(f"page {page}: {exc}")
            continue
        for url in links:
            source = classify(url)
            if source is None:
                summary.unknown_links.append(url)
                continue
            found.add(source.source_id)
            try:
                status, msg = ingest_file(con, raw_dir, source.source_id, download(url), now)
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the rest
                status, msg = "error", f"{source.source_id}: {exc}"
            {"stored": summary.stored, "unchanged": summary.unchanged,
             "error": summary.errors}[status].append(msg)
    summary.missing_sources = [s.source_id for s in SOURCES if s.source_id not in found]
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(store.DEFAULT_DB))
    parser.add_argument("--raw", default=str(DEFAULT_RAW))
    args = parser.parse_args(argv)
    con = store.connect(args.db)
    summary = run(con, Path(args.raw))
    con.close()
    print(f"snapshot: {store.snapshot(args.db).name}")
    for label in ("stored", "unchanged", "unknown_links", "missing_sources", "errors"):
        items = getattr(summary, label)
        print(f"{label}: {len(items)}")
        for item in items:
            print(f"  {item}")
    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
