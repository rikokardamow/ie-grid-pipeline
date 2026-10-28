"""g2: parse every stored publication that has no rows yet at this parser version.

    uv run python -m iegrid.load

Reads the raw PDF kept by g1, never the network. A publication whose parse
fails stores nothing (all rows or none) and the run exits 1.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from iegrid import parse, store


@dataclass
class Summary:
    parsed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def pending(con, version: int | None = None) -> list[tuple[int, str, str]]:
    version = parse.PARSER_VERSION if version is None else version
    sources = list(parse.PARSERS)
    return con.execute(
        f"""
        select p.publication_id, p.source_id, p.raw_path from publication p
        where p.source_id in ({", ".join("?" * len(sources))})
          and not exists (select 1 from parse_result r
                          where r.publication_id = p.publication_id and r.parser_version = ?)
        order by p.publication_id
        """,
        [*sources, version],
    ).fetchall()


def load_one(con, publication_id: int, source_id: str, content: bytes, now: datetime) -> str:
    result = parse.PARSERS[source_id](content)
    text_refs = sum(parse.refs_in_text(content).values())
    total = sum((r.mec_mw for r in result.rows), start=parse.Decimal(0))
    # The tie gates the store: a parse that skipped a page or misread a MEC stores nothing.
    if len(result.rows) != text_refs:
        raise parse.ParseError(f"{len(result.rows)} rows parsed but {text_refs} refs in the text")
    printed = result.printed_total_mw
    if printed is not None and abs(total - printed) > parse.TIE_MW:
        raise parse.ParseError(f"parsed {total} MW, the list prints {printed}")
    con.execute("begin transaction")
    try:
        con.executemany(
            "insert into project_row values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [[publication_id, parse.PARSER_VERSION, r.row_order, r.page, r.project_ref, r.name,
              r.technology, r.mec_mw, r.node, r.station_110kv, r.voltage, r.processing_type,
              r.status, r.signed_month, r.energised_on, r.energised_note, r.raw]
             for r in result.rows],
        )
        con.execute(
            "insert into parse_result values (?, ?, ?, ?, ?, ?, ?)",
            [publication_id, parse.PARSER_VERSION, len(result.rows), text_refs, total,
             result.printed_total_mw, now],
        )
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise
    printed = "none printed" if result.printed_total_mw is None else f"printed {result.printed_total_mw}"
    return f"{source_id} #{publication_id}: {len(result.rows)} rows, {total} MW ({printed})"


def run(con, now: datetime | None = None) -> Summary:
    now = now or datetime.now(UTC)
    summary = Summary()
    for publication_id, source_id, raw_path in pending(con):
        try:
            content = (store.ROOT / raw_path).read_bytes()
            summary.parsed.append(load_one(con, publication_id, source_id, content, now))
        except Exception as exc:  # noqa: BLE001 - one bad publication must not stop the rest
            summary.errors.append(f"{source_id} #{publication_id}: {exc}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(store.DEFAULT_DB))
    args = parser.parse_args(argv)
    con = store.connect(args.db)
    try:
        summary = run(con)
    finally:
        con.close()
        print(f"snapshot: {store.snapshot(args.db).name}")
    for label in ("parsed", "errors"):
        items = getattr(summary, label)
        print(f"{label}: {len(items)}")
        for item in items:
            print(f"  {item}")
    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
