"""g4 job: read the ECP results files, load OpenStreetMap substations, build counties.

    uv run python -m iegrid.counties          # new ECP files, then a build if anything changed
    uv run python -m iegrid.counties --osm    # also look up unplaced nodes in OpenStreetMap

ECP files come from the Internet Archive (same index and cache as g3) and from
EirGrid's live page. --osm looks up, in OpenStreetMap's Nominatim, only the
connection nodes still unplaced (a few dozen), at one request a second. A build is stored once per (contracted editions, rules):
re-running with nothing new adds nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from iegrid import backfill, ecp, fetch, parse, region, store
from iegrid.sources import ARCHIVE_PREFIXES, normalised_name

# ECP results publications: joint system-operator results, Categories B and C, GSS.
ECP_NAME = re.compile(r"(ecp|gss).*result|result.*(ecp|gss)")
NOT_RESULTS = re.compile(r"webinar|constraint|slides|presentation|questions|draft-results")
LIVE_ECP = (
    ("https://cms.eirgrid.ie/sites/default/files/publications/"
     "2023-Batch-ECP-2.4-Results-Joint-SO-Publication-Sept-25-Status-Update.pdf"),
)
OSM_CACHE = store.ROOT / "data" / "osm"


def is_ecp_results(url: str) -> bool:
    name = normalised_name(url)
    return bool(name.endswith(".pdf") and ECP_NAME.search(name) and not NOT_RESULTS.search(name))


def ecp_candidates(rows: list[list[str]]) -> list[backfill.Candidate]:
    first: dict[str, backfill.Candidate] = {}
    for ts, original, digest, _mime in rows:
        if is_ecp_results(original) and (digest not in first or ts < first[digest].capture_ts):
            first[digest] = backfill.Candidate(None, original, ts, digest)
    return sorted(first.values(), key=lambda c: c.capture_ts)


def store_ecp(con, digest: str, url: str, capture_ts: str, content: bytes, now) -> int | None:
    """Read one results file into ecp_row. None if it was read before."""
    v = ecp.READER_VERSION
    if con.execute("select 1 from ecp_file where archive_digest = ? and reader_version = ?",
                   [digest, v]).fetchone():
        return None
    rows = ecp.parse_ecp(content)
    con.execute("begin transaction")
    try:
        con.execute("insert into ecp_file values (?, ?, ?, ?, ?, ?, ?)",
                    [digest, v, url, capture_ts, normalised_name(url), len(rows), now])
        con.executemany("insert into ecp_row values (?, ?, ?, ?, ?, ?, ?, ?)",
                        [[digest, v, i, r.page, r.name, r.county, r.mec_mw, r.node]
                         for i, r in enumerate(rows, start=1)])
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise
    return len(rows)


def read_ecp_files(con, now, rows_for=backfill.cdx_rows, get_capture=backfill.capture,
                   live=LIVE_ECP, download=fetch.download) -> list[str]:
    notes = []
    rows: list[list[str]] = []
    for prefix in ARCHIVE_PREFIXES:
        try:
            rows.extend(rows_for(prefix))
        except Exception as exc:  # noqa: BLE001 - reported; the others still count
            notes.append(f"index {prefix}: {exc}")
    for c in ecp_candidates(rows):
        try:
            content = get_capture(c).content
        except Exception as exc:  # noqa: BLE001
            notes.append(f"download {c.original_url}: {exc}")
            continue
        if (n := store_ecp(con, c.digest, c.original_url, c.capture_ts, content, now)) is not None:
            notes.append(f"read {n} rows from {normalised_name(c.original_url)}")
    for url in live:
        try:
            dl = download(url)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"download {url}: {exc}")
            continue
        digest = "sha256:" + hashlib.sha256(dl.content).hexdigest()
        if (n := store_ecp(con, digest, url, f"live:{now:%Y%m%d}", dl.content, now)) is not None:
            notes.append(f"read {n} rows from {normalised_name(url)} (live)")
    return notes


NOMINATIM = "https://nominatim.openstreetmap.org/search"
NOMINATIM_PAUSE_S = 1.1  # the usage policy allows one request a second


def _nominatim(query: str) -> list[dict]:
    url = NOMINATIM + "?" + urllib.parse.urlencode(
        {"q": query, "countrycodes": "ie", "format": "jsonv2", "addressdetails": 1, "limit": 10})
    req = urllib.request.Request(url, headers={"User-Agent": fetch.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _county_of(r: dict) -> str | None:
    address = r.get("address", {})
    return region.osm_county(address.get("county", "") or address.get("city", ""))


def substation_county(node: str, results: list[dict]) -> tuple[str, dict] | None:
    """The county of the substation for this node, if the results settle it.

    A result counts when it is a substation (by type, or by "substation" in its name)
    and the node is its own name or a place in its description: search also matches
    addresses, so "Knockraha substation" finds the Gogganstown substation in Knockraha,
    which is the right one; a substation that merely mentions the word elsewhere is not."""
    want = region.norm_node(node)
    found: dict[str, dict] = {}
    for r in results:
        name = r.get("name") or r["display_name"].split(",")[0]
        is_substation = r.get("type") == "substation" or "substation" in name.lower()
        parts = [p.strip() for p in r["display_name"].split(",")[1:]]
        named_for = region.norm_substation(name) == want or any(
            region.norm_node(p) == want for p in parts)
        if is_substation and named_for and (county := _county_of(r)):
            found.setdefault(county, r)
    if len(found) != 1:
        return None
    return next(iter(found.items()))


def lookup_nodes(con, nodes: list[str], now, cache: Path = OSM_CACHE,
                 search=_nominatim) -> list[str]:
    """Look up nodes not yet looked up. Answers are cached on disk (data/osm/), so a
    re-run doesn't ask again; a node with no settled answer is cached as such."""
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "nominatim.json"
    answers = json.loads(path.read_text()) if path.exists() else {}
    notes = []
    for node in sorted({region.norm_node(n) for n in nodes if n}):
        for kind, query in (("substation", f"{node} substation"),):
            k = f"{kind}:{node}"
            if k in answers:
                continue
            time.sleep(NOMINATIM_PAUSE_S)
            try:
                answers[k] = search(query)
            except Exception as exc:  # noqa: BLE001 - reported, asked again next run
                notes.append(f"nominatim {query!r}: {exc}")
            path.write_text(json.dumps(answers))
    for node in sorted({k.split(":", 1)[1] for k in answers}):
        # Only a substation found by name counts. A place of the same name (the g4 review
        # found Barnakyle townland in Limerick for a Barnakyle 110 kV node in Dublin)
        # says nothing about where the node is.
        got = substation_county(node, answers.get(f"substation:{node}", []))
        label = "substation"
        if got is None:
            continue
        county, r = got
        con.execute("insert into osm_node values (?, ?, ?, ?, ?) on conflict do nothing",
                    [node, county, f"{r['osm_type']}/{r['osm_id']}",
                     f"{label}: {r['display_name']}", now])
    return notes


def latest_contracted(con) -> list[tuple[int, int, region.Project]]:
    rows = con.execute(f"""
        select r.publication_id, r.row_order, r.project_ref, l.source_id, r.name, r.mec_mw,
               r.node, r.station_110kv
        from project_row r join ({store.LATEST_LIVE}) l using (publication_id)
        where l.source_id like '%contracted%' and r.parser_version = {int(parse.PARSER_VERSION)}
        order by r.publication_id, r.row_order
    """).fetchall()
    # TSO: the node. DSO: the feeding station, nearer the project than the designed
    # 110 kV station, which is used only when the feeding station is blank.
    return [(pid, order, region.Project(ref, sid, name, mec, node or st110))
            for pid, order, ref, sid, name, mec, node, st110 in rows]


def ecp_rows(con) -> list[ecp.EcpRow]:
    return [ecp.EcpRow(*r) for r in con.execute(
        "select page, name, county, mec_mw, node from ecp_row where reader_version = ?",
        [ecp.READER_VERSION]).fetchall()]


def unplaced_nodes(con) -> list[str]:
    """Connection nodes of projects the newest build couldn't place by name or node vote."""
    projects = latest_contracted(con)
    got = region.assign([p for _, _, p in projects], ecp_rows(con))
    return [p.node for (_, _, p), c in zip(projects, got, strict=True) if c.basis == "none"]


def build(con, now) -> str:
    projects = latest_contracted(con)
    pubs = ",".join(str(p) for p in sorted({pid for pid, _, _ in projects}))
    # the inputs count too: a new ECP file or new substations make a new build
    n_ecp = con.execute("select count(*) from ecp_file where reader_version = ?",
                        [ecp.READER_VERSION]).fetchone()[0]
    osm = con.execute("select node, county, osm_id from osm_node order by node").fetchall()
    osm_hash = hashlib.sha256(repr(osm).encode()).hexdigest()[:12]
    rules = f"{region.rules()};ecp_files={n_ecp};osm={osm_hash}"
    if con.execute("select 1 from region_build where publications = ? and rules = ?",
                   [pubs, rules]).fetchone():
        return "build: unchanged"
    subs = con.execute("select node, county, display_name from osm_node").fetchall()
    got = region.assign([p for _, _, p in projects], ecp_rows(con), subs)
    con.execute("begin transaction")
    try:
        build_id = con.execute("insert into region_build (publications, rules, built_at) "
                               "values (?, ?, ?) returning build_id",
                               [pubs, rules, now]).fetchone()[0]
        con.executemany("insert into project_county values (?, ?, ?, ?, ?, ?, ?, ?)",
                        [[build_id, pid, order, p.project_ref, p.mec_mw, c.county, c.basis,
                          c.evidence] for (pid, order, p), c in zip(projects, got, strict=True)])
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise
    return f"build {build_id}: {len(got)} projects"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(store.DEFAULT_DB))
    parser.add_argument("--osm", action="store_true",
                        help="look up unplaced connection nodes in OpenStreetMap")
    args = parser.parse_args(argv)
    now = datetime.now(UTC)
    con = store.connect(args.db)
    try:
        notes = read_ecp_files(con, now)
        if args.osm:
            notes += lookup_nodes(con, unplaced_nodes(con), now)
        notes.append(build(con, now))
    finally:
        con.close()
        print(f"snapshot: {store.snapshot(args.db).name}")
    for n in notes:
        print(n)
    return 1 if any(n.startswith(("index", "download", "nominatim")) for n in notes) else 0


if __name__ == "__main__":
    sys.exit(main())
