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
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from iegrid import asof, fetch, store
from iegrid.sources import PAGES, SOURCES, classify

DEFAULT_RAW = Path("data/raw")


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
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(dl.content)
    if dl.last_modified is not None:
        published_at, basis, quality = dl.last_modified, "last-modified", "exact"
    else:
        published_at, basis, quality = now, "ingested", "estimated"
    pub = store.Publication(
        source_id=source_id, url=dl.url, sha256=sha, size_bytes=len(dl.content), as_of=as_of,
        published_at=published_at, published_at_basis=basis, vintage_quality=quality,
        raw_path=str(path), ingested_at=now,
    )
    if store.insert(con, pub) is None:
        return "unchanged", f"{source_id} {sha[:12]}"
    return "stored", f"{source_id} as of {as_of} {sha[:12]}"


def run(con, raw_dir: Path = DEFAULT_RAW,
        page_links: Callable[[str], list[str]] = fetch.page_links,
        download: Callable[[str], fetch.Download] = fetch.download,
        now: datetime | None = None) -> Summary:
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
    for label in ("stored", "unchanged", "unknown_links", "missing_sources", "errors"):
        items = getattr(summary, label)
        print(f"{label}: {len(items)}")
        for item in items:
            print(f"  {item}")
    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
