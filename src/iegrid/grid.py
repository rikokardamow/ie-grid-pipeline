"""g7b: where the queue sits on the grid.

The lists name the substation each project connects at (the node), not the project's
site, so the map places MW at nodes. OpenStreetMap gives the grid: every line of
110 kV and over and every named substation, fetched from Overpass once and cached in
data/osm/grid.json (ODbL, (c) OpenStreetMap contributors). A node is placed when its
name matches one substation:

    exact     norm_node(list node) == norm_substation(OSM name)
    prefix    one is the other's prefix, both at least PREFIX_MIN letters, one candidate
              ("Lanesboro" / "Lanesborough")

with two checks the g7b review showed prefix names need (Raheenmeel is not Raheen,
244 km away): a transmission project only matches a substation tagged TSO_MIN_KV or
over, and a distribution project's feeding station must be within PARENT_KM of its
110 kV station when that station is on the map. A distribution project whose feeding
station isn't found is drawn at its 110 kV station ('parent'). A name OSM gives to
several substations far apart is not placed (ambiguous).

The ECP batch results give a node too, for the projects they list (matched by name and
MEC, as in region.by_name). It is often the existing station a new one ties into
(Castlebanny: list node Kilvinoge, results node Waterford), so it is used two ways:
a transmission project whose own node isn't on the map is drawn at the results' node
('ecp'), and one whose two nodes are both on the map but more than CONFLICT_KM apart
is not drawn at all (Kilmorna Energy Storage: Kinnegad on the list, Knockanure in
Kerry in the results) and is listed as a conflict.

A station still not found is a new one OSM doesn't have. Two more ways place it, both
approximate and labelled so on the map:

    cited     data/cited_stations.csv gives the site, with the source that says so
              (Southbank: the Poolbeg power station)
    townland  EirGrid names a new station after its townland, so it is drawn at the
              one townland of that name in the project's county (g4's latest build,
              from the ECP results, a cited source or other projects at the node).
              Two townlands of the name in the county (Bellewstown, Meath) place
              nothing: the g4 review showed a same-named place elsewhere is no evidence

The places are looked up in Nominatim by `python -m iegrid.grid --places` (and by the
weekly run, for names not yet asked) and cached in data/osm/places.json.
Distance is from the substation to the nearest line of BACKBONE_KV, all-island (the
north's backbone is 275 kV): how far the queued MW sits from the transmission
backbone. It is not the length of the project's own cable.
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from iegrid import parse, region, store

CACHE = Path(__file__).resolve().parents[2] / "data" / "osm" / "grid.json"
PLACES = CACHE.parent / "places.json"
CITED_STATIONS = Path(__file__).parent / "data" / "cited_stations.csv"
BBOX = (51.3, -10.8, 55.5, -5.9)  # the island: the grid is all-island
ENDPOINTS = ("https://overpass-api.de/api/interpreter",
             "https://maps.mail.ru/osm/tools/overpass/api/interpreter")
QUERIES = {
    "lines": 'way["power"="line"]["voltage"~"(110|220|275|400)000"];out tags geom;',
    "substations": ('(way["power"="substation"];node["power"="substation"];'
                    'relation["power"="substation"];);out tags center;'),
}
BACKBONE_KV = (220, 275, 400)
MIN_SUBSTATION_KV = 38
TSO_MIN_KV = 110
PARENT_KM = 40          # a feeding station hangs off a 110 kV station nearby
# list node and ECP-results node this far apart: one is wrong. Real long connections
# reach 39 km (Lyrenacarriga: Knockraha on the list, Woodhouse in the results); the one
# wrong node found is 185 km out (Kilmorna), so the line sits well clear of both
CONFLICT_KM = 80
PREFIX_MIN = 6
SAME_PLACE_KM = 2.0     # two OSM objects of one name this close are one substation
FAR_KM = 20             # "far from the backbone", printed with the number it gives
BANDS_KM = (2, 10, FAR_KM)  # distance bands for the chart: on it, near, further, far
SIMPLIFY_DEG = 0.004    # about 300 m: line paths drawn on a page-wide map

KM_PER_DEG_LAT = 111.32


@dataclass(frozen=True)
class Substation:
    name: str
    kv: int
    lon: float
    lat: float


@dataclass(frozen=True)
class Line:
    kv: int
    path: tuple[tuple[float, float], ...]  # (lon, lat)


# --- fetch and cache ---------------------------------------------------------------

def _overpass(query: str) -> dict:
    s, w, n, e = BBOX
    body = urllib.parse.urlencode(
        {"data": f"[out:json][timeout:240][bbox:{s},{w},{n},{e}];{query}"}).encode()
    last: Exception | None = None
    for url in ENDPOINTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, data=body, headers={
                    "User-Agent": "ie-grid-pipeline/0.1 (local research)"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.loads(r.read())
            except (OSError, ValueError) as exc:  # busy (429/504) or a cut-off answer
                last = exc
                time.sleep(15 * 2 ** attempt)
    raise RuntimeError(f"Overpass did not answer: {last}")


def fetch(cache: Path = CACHE) -> Path:
    data = {name: _overpass(q)["elements"] for name, q in QUERIES.items()}
    data["fetched_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data))
    return cache


def _kv(tags: dict) -> int:
    vs = [int(v) for v in re.findall(r"\d+", tags.get("voltage", ""))]
    return max(vs) // 1000 if vs else 0


def load(cache: Path = CACHE) -> tuple[list[Line], list[Substation], str]:
    raw = json.loads(cache.read_text())
    lines = [Line(_kv(e["tags"]), tuple((p["lon"], p["lat"]) for p in e["geometry"]))
             for e in raw["lines"] if e.get("geometry")]
    subs = []
    for e in raw["substations"]:
        t, c = e.get("tags", {}), e.get("center") or e
        if "name" in t and "lat" in c and (_kv(t) >= MIN_SUBSTATION_KV or not t.get("voltage")):
            subs.append(Substation(t["name"], _kv(t), c["lon"], c["lat"]))
    return lines, subs, raw["fetched_at"]


# --- geometry ---------------------------------------------------------------------

def _xy(lon: float, lat: float, lat0: float = 53.4) -> tuple[float, float]:
    return (lon * KM_PER_DEG_LAT * math.cos(math.radians(lat0)), lat * KM_PER_DEG_LAT)


def km_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    (x1, y1), (x2, y2) = _xy(*a), _xy(*b)
    return math.hypot(x2 - x1, y2 - y1)


def _km_to_segment(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = _xy(*p), _xy(*a), _xy(*b)
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy)
                                               / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def km_to_lines(p: tuple[float, float], lines: list[Line]) -> float | None:
    best = None
    for ln in lines:
        for a, b in pairwise(ln.path):
            d = _km_to_segment(p, a, b)
            best = d if best is None or d < best else best
    return best


def simplify(path: tuple[tuple[float, float], ...], tol: float = SIMPLIFY_DEG):
    """Douglas-Peucker in degrees: enough for drawing, never used for distance."""
    if len(path) < 3:
        return list(path)
    if path[0] == path[-1]:  # a closed ring: no chord to measure from, so halve it first
        mid = len(path) // 2
        return simplify(path[: mid + 1], tol)[:-1] + simplify(path[mid:], tol)
    (x1, y1), (x2, y2) = path[0], path[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-12
    far, idx = 0.0, 0
    for i, (x, y) in enumerate(path[1:-1], start=1):
        d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
        if d > far:
            far, idx = d, i
    if far <= tol:
        return [path[0], path[-1]]
    return simplify(path[: idx + 1], tol)[:-1] + simplify(path[idx:], tol)


# --- matching ---------------------------------------------------------------------

def _index(subs: list[Substation]) -> dict[str, list[Substation]]:
    idx: dict[str, list[Substation]] = defaultdict(list)
    for s in subs:
        if (k := region.norm_substation(s.name)):
            idx[k].append(s)
    return idx


def _one_place(cands: list[Substation]) -> Substation | None:
    """The highest-voltage candidate, if every candidate is in one place."""
    top = max(cands, key=lambda s: s.kv)
    if all(km_between((s.lon, s.lat), (top.lon, top.lat)) <= SAME_PLACE_KM for s in cands):
        return top
    return None


def match(node: str, idx: dict[str, list[Substation]], min_kv: int = 0,
          near: Substation | None = None) -> tuple[Substation | None, str]:
    """The one substation this list node names, of min_kv or over and, if near is
    given, within PARENT_KM of it."""
    k = region.norm_node(node)
    if not k:
        return None, "none"

    def ok(s: Substation) -> bool:
        return (s.kv >= min_kv and
                (near is None or km_between((s.lon, s.lat), (near.lon, near.lat)) <= PARENT_KM))

    def pick(name: str, how: str) -> tuple[Substation | None, str]:
        cands = [s for s in idx[name] if ok(s)]
        if not cands:
            return None, "none"
        s = _one_place(cands)
        return (s, how) if s else (None, "ambiguous")

    if k in idx and (got := pick(k, "exact"))[1] != "none":
        return got
    if len(k) >= PREFIX_MIN:
        hits = [n for n in idx if n != k and len(n) >= PREFIX_MIN
                and (n.startswith(k) or k.startswith(n)) and any(ok(s) for s in idx[n])]
        if len(hits) == 1:
            return pick(hits[0], "prefix")
    return None, "none"


def place(tso: bool, node: str, station: str,
          idx: dict[str, list[Substation]]) -> tuple[Substation | None, str]:
    """Where a list row is drawn. Transmission: its node, at TSO_MIN_KV or over.
    Distribution: its feeding station near its 110 kV station, else that station."""
    if tso:
        return match(node, idx, TSO_MIN_KV)
    parent, _ = match(station, idx, TSO_MIN_KV) if station else (None, "none")
    s, how = match(node, idx, near=parent) if node else (None, "none")
    if s is None and parent is not None:
        return parent, "parent"
    return s, how


def ecp_nodes(con) -> dict[tuple[str, ...], list[tuple[str, Decimal]]]:
    """{name key: [(node, MEC)]} from the ECP batch results, rows that name a node
    (some give a grid reference instead, which isn't a node)."""
    from iegrid import ecp

    out: dict[tuple[str, ...], list[tuple[str, Decimal]]] = defaultdict(list)
    for name, node, mw in con.execute(
            "select name, node, mec_mw from ecp_row where reader_version = ? and node <> ''",
            [ecp.READER_VERSION]).fetchall():
        if re.search(r"[a-z]", node, re.IGNORECASE) and (k := region.key(name)):
            out[k].append((node, mw))
    return out


def results_node(name: str, mw, ecp: dict) -> str | None:
    """The one node the ECP results give this project (same name key, close MEC)."""
    found = {region.norm_node(n) for n, m in ecp.get(region.key(name), [])
             if region.mec_close(m, Decimal(str(mw)))}
    # two readings of one node ("mount" / "mount lucas"): the shorter, if it starts the rest
    if found and (short := min(found, key=len)) and all(
            f == short or f.startswith(short + " ") for f in found):
        return short
    return None


# --- what the report shows ----------------------------------------------------------

@dataclass(frozen=True)
class Placement:
    ref: str
    name: str
    tso: bool
    mw: float
    label: str                  # the node as the list gives it, for the unplaced table
    at: Substation | None
    how: str                    # exact, prefix, parent, ecp; or none, ambiguous, conflict
    conflict: dict | None = None


def placements(con, idx: dict[str, list[Substation]], ecp: dict) -> list[Placement]:
    """Where each contracted row (interconnectors left out) is drawn, if anywhere."""
    rows = con.execute(f"""
        select p.source_id like 'eirgrid%', r.node, r.station_110kv, r.mec_mw, r.project_ref,
               r.name
        from project_row r join ({store.LATEST_LIVE}) l using (publication_id)
        join publication p using (publication_id)
        where p.source_id like '%contracted%' and r.parser_version = {int(parse.PARSER_VERSION)}
          and coalesce(r.technology, '') <> 'Interconnector'
    """).fetchall()
    out = []
    for tso, node, station, mw, ref, name in rows:
        label = (node or station or "").strip() or "(no node)"
        s, how = place(tso, node or "", station or "", idx)
        conflict = None
        if tso and (rn := results_node(name or "", mw, ecp)):
            e, _ = match(rn, idx, TSO_MIN_KV)
            if s is None and e is not None:
                s, how = e, "ecp"
            elif s is not None and e is not None and (
                    km := km_between((s.lon, s.lat), (e.lon, e.lat))) > CONFLICT_KM:
                conflict = {"ref": ref, "name": name, "mw": round(float(mw), 1),
                            "list_node": s.name, "results_node": e.name, "km": round(km)}
                label = f"{(node or '').strip()} (list) or {rn.title()} (ECP results)"
                s, how = None, "conflict"
        out.append(Placement(ref, name or "", bool(tso), float(mw), label, s, how, conflict))
    return out


# --- new stations: cited sites and townlands -------------------------------------------

def cited_stations(path: Path = CITED_STATIONS) -> dict[str, dict[str, str]]:
    import csv

    with path.open(newline="") as f:
        return {region.norm_node(r["node"]): r for r in csv.DictReader(f)}


def counties_of(con) -> dict[str, str]:
    """{project_ref: county} from g4's latest build, placed rows only; a ref on two lists
    takes its newest publication's row."""
    try:
        return dict(con.execute("""
            select project_ref, county from project_county
            where build_id = (select max(build_id) from region_build) and county is not null
            order by publication_id, row_order
        """).fetchall())
    except Exception:  # noqa: BLE001 - a store without g4's tables places no townlands
        return {}


def node_counties(pls: list[Placement], county_of: dict[str, str]
                  ) -> tuple[dict[str, str], dict[str, str]]:
    """The county of each station still not found, from all its projects (g7b review:
    per project, a station was drawn for some and unplaced for the rest). Where its
    projects disagree, the county with most of the MW is the station's, and each project
    in another county is returned as a conflict: {ref: its own county}."""
    mw: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for p in pls:
        if p.at is None and p.how != "conflict" and (c := county_of.get(p.ref)):
            mw[region.norm_node(p.label)][c] += p.mw
    node_county = {n: max(cs, key=lambda c: (cs[c], c)) for n, cs in mw.items()}
    odd = {p.ref: county_of[p.ref] for p in pls
           if p.at is None and p.how != "conflict" and p.ref in county_of
           and node_county.get(region.norm_node(p.label)) not in (None, county_of[p.ref])}
    return node_county, odd


def place_queries(pls: list[Placement], node_county: dict[str, str],
                  cited: dict[str, dict[str, str]]) -> dict[str, tuple[str, str, str]]:
    """{query: (kind, node, county)} for the stations still not found."""
    out = {}
    for p in pls:
        if p.at is not None or p.how == "conflict":
            continue
        node = region.norm_node(p.label)
        if node in cited:
            r = cited[node]
            out[r["place_query"]] = ("cited", node, r["county"])
        elif node and (county := node_county.get(node)):
            out[f"{node}, County {county}"] = ("townland", node, county)
    return out


def fetch_places(queries, cache: Path = PLACES, search=None) -> list[str]:
    """Ask Nominatim for the queries not yet cached (one a second, its usage policy)."""
    from iegrid import counties

    search = search or counties._nominatim
    answers = json.loads(cache.read_text()) if cache.exists() else {}
    notes = []
    for q in sorted(set(queries) - set(answers)):
        time.sleep(counties.NOMINATIM_PAUSE_S)
        try:
            answers[q] = search(q)
        except Exception as exc:  # noqa: BLE001 - reported, asked again next run
            notes.append(f"nominatim {q!r}: {exc}")
            continue
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(answers))
    return notes


def site(kind: str, node: str, county: str, results: list[dict],
         query_place: str = "") -> Substation | None:
    """Where a cited site or a townland is, if the answers settle it. For a cited site,
    query_place is the place the query names (its part before a comma)."""
    from iegrid import counties

    def at(r):
        return float(r["lon"]), float(r["lat"])

    in_county = [r for r in results if counties._county_of(r) == county]
    if kind == "cited":
        # the answer must be the place the source names, not anything in the county
        named = set(region.key(query_place))
        hits = [r for r in in_county if named and named <= set(region.key(r.get("name", "")))
                ][:1]
    else:
        hits = [r for r in in_county if r.get("category") == "boundary"
                and r.get("type") == "administrative"
                and region.norm_node(r.get("name", "")) == node]
        if any(km_between(at(r), at(hits[0])) > SAME_PLACE_KM for r in hits):
            return None  # two townlands of the name in the county
    if not hits:
        return None
    lon, lat = at(hits[0])
    label = "cited site" if kind == "cited" else f"townland, {county}"
    return Substation(f"{node.title()} ({label})", 0, lon, lat)


def nodes(con, cache: Path = CACHE, ecp: dict | None = None,
          places: Path = PLACES) -> dict:
    lines, subs, fetched_at = load(cache)
    idx = _index(subs)
    backbone = [ln for ln in lines if ln.kv in BACKBONE_KV]
    ecp = ecp_nodes(con) if ecp is None else ecp
    pls = placements(con, idx, ecp)
    answers = json.loads(places.read_text()) if places.exists() else {}
    county_of, cited = counties_of(con), cited_stations()
    node_county, odd = node_counties(pls, county_of)
    for i, p in enumerate(pls):
        if p.ref in odd:  # its station's other projects are in another county
            c = node_county[region.norm_node(p.label)]
            pls[i] = Placement(p.ref, p.name, p.tso, p.mw,
                               f"{p.label} (list, {c}) or {odd[p.ref]} (county)", None,
                               "conflict", {"ref": p.ref, "name": p.name,
                                            "mw": round(p.mw, 1), "list_node": p.label,
                                            "list_node_county": c, "county": odd[p.ref]})
            continue
        for q, (kind, node, county) in place_queries([p], node_county, cited).items():
            where = q.split(",")[0] if kind == "cited" else ""
            if (s := site(kind, node, county, answers.get(q, []), where)) is not None:
                pls[i] = Placement(p.ref, p.name, p.tso, p.mw, p.label, s, kind)
    at: dict[str, dict] = {}
    unplaced: dict[str, float] = defaultdict(float)
    conflicts: list[dict] = []
    total = 0.0
    for pl in pls:
        total += pl.mw
        if pl.conflict:
            conflicts.append(pl.conflict)
        s = pl.at
        if s is None:
            unplaced[pl.label] += pl.mw
            continue
        n = at.setdefault(s.name, {"node": s.name, "kv": s.kv, "lon": round(s.lon, 4),
                                   "lat": round(s.lat, 4), "mw": 0.0, "projects": 0,
                                   "tso_mw": 0.0, "match": pl.how})
        n["mw"] += pl.mw
        n["projects"] += 1
        n["tso_mw"] += pl.mw if pl.tso else 0.0
    for n in at.values():
        d = km_to_lines((n["lon"], n["lat"]), backbone)
        n["km_backbone"] = round(d, 1) if d is not None else None
        n["mw"], n["tso_mw"] = round(n["mw"], 1), round(n["tso_mw"], 1)
    placed = sum(n["mw"] for n in at.values())
    edges = (0, *BANDS_KM)
    bands = [{"label": f"{lo}-{hi} km" if lo else f"under {hi} km", "gw": 0.0, "nodes": 0}
             for lo, hi in pairwise(edges)]
    bands.append({"label": f"{FAR_KM} km and over", "gw": 0.0, "nodes": 0})
    # a node with no distance (no backbone line loaded) is in no band and not "far"
    for n in at.values():
        if n["km_backbone"] is None:
            continue
        b = bands[sum(n["km_backbone"] >= e for e in BANDS_KM)]
        b["gw"] += n["mw"] / 1000
        b["nodes"] += 1
    for b in bands:
        b["gw"] = round(b["gw"], 3)
    return {
        "osm_fetched_at": fetched_at,
        "bands": bands,
        "backbone_kv": list(BACKBONE_KV),
        "far_km": FAR_KM,
        "placed_share": round(placed / total, 3) if total else None,
        "placed_gw": round(placed / 1000, 3),
        "far_gw": bands[-1]["gw"],      # the last band: FAR_KM and over
        "far_nodes": bands[-1]["nodes"],
        "nodes": sorted(at.values(), key=lambda n: -n["mw"]),
        "conflicts": conflicts,
        "unplaced": [{"node": k, "mw": round(v, 1)}
                     for k, v in sorted(unplaced.items(), key=lambda kv: -kv[1])],
        "lines": [{"kv": ln.kv, "path": [[round(x, 3), round(y, 3)] for x, y in simplify(ln.path)]}
                  for ln in lines],
    }


def queries_for(con) -> list[str]:
    """The Nominatim queries the map needs for stations still not found."""
    _, subs, _ = load()
    pls = placements(con, _index(subs), ecp_nodes(con))
    node_county, _ = node_counties(pls, counties_of(con))
    return list(place_queries(pls, node_county, cited_stations()))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--places", action="store_true",
                        help="look up new stations' cited sites and townlands (not the grid)")
    args = parser.parse_args(argv)
    if args.places:
        notes = fetch_places(queries_for(store.connect_read_only()))
        print(f"places: {PLACES}" + "".join(f"\n  {n}" for n in notes))
        return 1 if notes else 0
    path = fetch()
    lines, subs, at = load(path)
    print(f"grid: {len(lines)} lines, {len(subs)} named substations, fetched {at} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
