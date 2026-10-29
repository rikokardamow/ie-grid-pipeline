"""g8: the weekly run. Checks both pages for new files, stores and parses them,
rebuilds the county placements, writes the report, and logs one run_log row.

    uv run python -m iegrid.weekly                 # data/iegrid.duckdb -> data/reports/
    uv run python -m iegrid.weekly --db x.duckdb --out x/

A list lands quarterly (ESB) or irregularly (EirGrid), so most weeks store nothing and
the report says "no new publication": that run is still logged. Status:

    ok          every expected list found, every new file stored and parsed
    attention   the run finished but something needs a look: an edition the load
                refused or couldn't read (retried next run), a list whose newest
                edition isn't parsed, a PDF link of a kind no source covers (a new
                list on the page), or the ECP batch results couldn't be fetched
    failed      an expected list is missing from its page, a page or a list's file
                couldn't be fetched, or a step raised; exit code 1

The ECP batch results (counties.read_ecp_files) come from the web archive and change
once a batch, so they are read only when due: a publication has come in since the
last run that read them without a failure (the first run reads them). A failed read
stays due, so next week tries again. New stations still missing from the map are
looked up as cited sites or townlands (grid.fetch_places, cached: only names not yet
asked go to Nominatim). The OSM grid itself (`python -m iegrid.grid`) and the archive
backfill (iegrid.backfill) stay separate commands.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from iegrid import connected, counties, esb_legacy, grid, ingest, load, parse, report, store


@dataclass
class Run:
    started_at: datetime
    status: str = "ok"
    stored: list[str] = field(default_factory=list)
    parsed: int = 0
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    ecp_read: bool = False
    report_path: str | None = None
    error: str | None = None

    def flag(self, items: list[str], prefix: str, status: str) -> None:
        for item in items:
            self.problems.append(f"{prefix}: {item}")
        if items and (status == "failed" or self.status == "ok"):
            self.status = status


def code_version() -> str:
    try:
        sha = subprocess.run(["git", "-C", str(store.ROOT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        sha = "unknown"
    return f"{sha} parser {parse.PARSER_VERSION}"


def ecp_due(con) -> bool:
    """A publication came in after the last run that read the ECP results cleanly."""
    last = con.execute("select max(started_at) from run_log where ecp_read").fetchone()[0]
    if last is None:
        return True
    return con.execute("select count(*) from publication where ingested_at >= ?",
                       [last]).fetchone()[0] > 0


def steps(con, run: Run, out: Path, raw: Path, now: datetime, **ingest_kw) -> None:
    got = ingest.run(con, raw, now=now, **ingest_kw)
    run.stored = got.stored
    run.flag(got.missing_sources, "missing from its page", "failed")
    run.flag(got.errors, "fetch", "failed")
    run.flag(got.unknown_links, "unknown link", "attention")

    loaded = load.run(con, now)
    run.parsed = len(loaded.parsed)
    run.flag(loaded.errors, "load", "attention")

    # the archived connected lists (no longer posted, so this adds nothing once read): the
    # report's outcome, pace, slippage, funnel and errata sections need them
    _, connected_problems = connected.load(con, now)
    run.flag(connected_problems, "connected lists", "attention")
    _, legacy_problems, _ = esb_legacy.load(con, now)  # ESB's archived 2017-2023 lists, likewise
    run.flag(legacy_problems, "ESB legacy lists", "attention")

    if ecp_due(con):
        notes = counties.read_ecp_files(con, now)
        failed = [n for n in notes if n.startswith(("index ", "download "))]
        run.flag(failed, "ECP results", "attention")
        run.notes += [f"ECP results: {n}" for n in notes if n not in failed]
        run.ecp_read = not failed
    run.notes.append(f"counties: {counties.build(con, now)}")
    if grid.CACHE.exists():  # new stations on the map: Nominatim is asked only new names
        run.flag(grid.fetch_places(grid.queries_for(con)), "places", "attention")
    run.report_path = ingest.stored_path(report.write(con, out, now))


def log(con, run: Run, finished_at: datetime) -> int:
    return con.execute("""
        insert into run_log (started_at, finished_at, status, new_files, stored, parsed,
                             problems, notes, ecp_read, report_path, code_version, error)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) returning run_id
    """, [run.started_at, finished_at, run.status, len(run.stored), "\n".join(run.stored),
          run.parsed, "\n".join(run.problems), "\n".join(run.notes), run.ecp_read,
          run.report_path, code_version(), run.error]).fetchone()[0]


def run_weekly(con, out: Path = report.REPORTS, raw: Path = ingest.DEFAULT_RAW,
               now: datetime | None = None, **ingest_kw) -> tuple[int, Run]:
    run = Run(started_at=now or datetime.now(UTC))
    try:
        steps(con, run, out, raw, run.started_at, **ingest_kw)
    except Exception as exc:  # noqa: BLE001 - a crash is logged as a failed run, then shown
        run.status = "failed"
        run.error = "".join(traceback.format_exception_only(exc)).strip()[:2000]
    return log(con, run, datetime.now(UTC)), run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(store.DEFAULT_DB))
    parser.add_argument("--out", default=str(report.REPORTS))
    parser.add_argument("--raw", default=str(ingest.DEFAULT_RAW))
    args = parser.parse_args(argv)
    con = store.connect(args.db)
    try:
        run_id, run = run_weekly(con, Path(args.out), Path(args.raw))
    finally:
        con.close()
    print(f"snapshot: {store.snapshot(args.db).name}")
    print(f"run {run_id}: {run.status}, {len(run.stored)} new files, {run.parsed} parsed")
    for item in run.stored:
        print(f"  stored {item}")
    for item in run.problems + run.notes:
        print(f"  {item}")
    if run.report_path:
        print(f"report: {run.report_path}")
    if run.error:
        print(f"error: {run.error}")
    return 1 if run.status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
