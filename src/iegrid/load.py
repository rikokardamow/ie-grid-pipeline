"""g2: parse every stored publication that has no rows yet at this parser version.

    uv run python -m iegrid.load

Reads the raw PDF kept by g1, never the network. A publication whose parse
fails stores nothing (all rows or none), gets a parse_failure row and the run
exits 1. It is not retried until PARSER_VERSION goes up, so an old layout the
parser can't read fails once, not every week.
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
          and not exists (select 1 from parse_failure f
                          where f.publication_id = p.publication_id and f.parser_version = ?)
        order by p.publication_id
        """,
        [*sources, version, version],
    ).fetchall()


def load_one(con, publication_id: int, source_id: str, content: bytes, now: datetime) -> str:
    try:
        result = parse.PARSERS[source_id](content)
    except parse.ParseError:
        raise
    except Exception as exc:  # the parser choking on a layout is a parse failure too
        raise parse.ParseError(f"{type(exc).__name__}: {exc}") from exc
    total = sum((r.mec_mw for r in result.rows), start=parse.Decimal(0))
    # The tie gates the store: a parse that skipped a page or misread a MEC stores nothing.
    if result.ref_check == "set":
        text = parse.text_ref_set(content)
        parsed = {r.project_ref for r in result.rows}
        text_refs = len(text)
        if parsed != text:
            raise parse.ParseError(f"refs differ from the text: parsed only {sorted(parsed - text)[:5]}, "
                                   f"text only {sorted(text - parsed)[:5]}")
    else:
        text_refs = sum(parse.refs_in_text(content).values())
        if len(result.rows) != text_refs:
            raise parse.ParseError(f"{len(result.rows)} rows parsed but {text_refs} refs in the text")
    printed = result.printed_total_mw
    if printed is not None and abs(total - printed) > parse.TIE_MW:
        raise parse.ParseError(f"parsed {total} MW, the list prints {printed}")
    con.execute("begin transaction")
    try:
        con.executemany(
            "insert into project_row (publication_id, parser_version, row_order, page, "
            "project_ref, name, technology, mec_mw, node, station_110kv, voltage, "
            "processing_type, status, signed_month, energised_on, energised_note, raw, "
            "target_month) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [[publication_id, parse.PARSER_VERSION, r.row_order, r.page, r.project_ref, r.name,
              r.technology, r.mec_mw, r.node, r.station_110kv, r.voltage, r.processing_type,
              r.status, r.signed_month, r.energised_on, r.energised_note, r.raw, r.target_month]
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


def read_totals(con, now: datetime) -> list[str]:
    """The printed total of every EirGrid contracted edition that has none stored yet,
    whether or not its rows parse. Returns problems with the files themselves (a raw
    file that can't be read), not editions that print no total or two different ones:
    those are reported by notebook 15, so they don't fail every weekly run."""
    problems = []
    todo = con.execute(
        f"""select p.publication_id, p.raw_path from publication p
        where p.source_id in ({", ".join("?" * len(parse.TOTAL_SOURCES))})
          and not exists (select 1 from edition_total t where t.publication_id = p.publication_id)
        """, list(parse.TOTAL_SOURCES)).fetchall()
    for publication_id, raw_path in todo:
        try:
            content = (store.ROOT / raw_path).read_bytes()
        except OSError as exc:
            problems.append(f"total #{publication_id}: {exc}")
            continue
        try:
            got = parse.printed_total(content)
        except parse.ParseError:
            continue  # two different totals in one file: left out, shown in notebook 15
        if got is not None:
            con.execute("insert into edition_total values (?, ?, ?, ?)",
                        [publication_id, got[0], got[1], now])
    return problems


def run(con, now: datetime | None = None) -> Summary:
    now = now or datetime.now(UTC)
    summary = Summary()
    summary.errors.extend(read_totals(con, now))
    for publication_id, source_id, raw_path in pending(con):
        try:
            content = (store.ROOT / raw_path).read_bytes()
            summary.parsed.append(load_one(con, publication_id, source_id, content, now))
        except parse.ParseError as exc:
            # The content can't be read by this parser: record it, so it isn't retried
            # every run, only when PARSER_VERSION goes up.
            summary.errors.append(f"{source_id} #{publication_id}: {exc}")
            con.execute("insert into parse_failure values (?, ?, ?, ?) on conflict do nothing",
                        [publication_id, parse.PARSER_VERSION, str(exc)[:500], now])
        except Exception as exc:  # noqa: BLE001 - one bad publication must not stop the rest
            # A missing raw file, a database hiccup: not the content's fault. Retried next run.
            summary.errors.append(f"{source_id} #{publication_id} (will retry): {exc}")
    summary.errors.extend(newest_unparsed(con))
    return summary


def newest_unparsed(con) -> list[str]:
    """A current list whose newest live edition failed to parse: reported on every run,
    so a publisher's layout change can't fail once and then go quiet."""
    sources = list(parse.PARSERS)
    rows = con.execute(
        f"""
        with newest as (
            select source_id, max(as_of) as as_of from publication
            where fetched_from is null and source_id in ({", ".join("?" * len(sources))})
            group by 1)
        select p.source_id, p.as_of, f.error from publication p
        join newest n on n.source_id = p.source_id and n.as_of = p.as_of
        join parse_failure f on f.publication_id = p.publication_id and f.parser_version = ?
        where not exists (select 1 from parse_result r where r.publication_id = p.publication_id
                          and r.parser_version = ?)
        """,
        [*sources, parse.PARSER_VERSION, parse.PARSER_VERSION],
    ).fetchall()
    return [f"{sid}: newest edition ({as_of}) does not parse: {err}" for sid, as_of, err in rows]


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
