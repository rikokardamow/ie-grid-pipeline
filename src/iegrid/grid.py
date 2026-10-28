"""g7b: where the queue sits on the grid.

The lists name the substation each project connects at (the node), not the project's
site, so the map places MW at nodes. OpenStreetMap gives the grid: every line of
110 kV and over and every named substation, fetched from Overpass once and cached in
data/osm/grid.json (ODbL, (c) OpenStreetMap contributors). A node is placed when its
name matches one substation of 38 kV or over:

    exact     norm_node(list node) == norm_substation(OSM name)
    prefix    one is the other's prefix, both at least PREFIX_MIN letters, one candidate
              ("Lanesboro" / "Lanesborough")

and a name OSM gives to several substations far apart is not placed (ambiguous).
Distance is from the substation to the nearest line of BACKBONE_KV: how far the queued
MW sits from the 220/400 kV network. It is not the length of the project's own cable.
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
from itertools import pairwise
from pathlib import Path

from iegrid import parse, region, store

CACHE = Path(__file__).resolve().parents[2] / "data" / "osm" / "grid.json"
BBOX = (51.3, -10.8, 55.5, -5.9)  # the island; Northern Ireland's lines draw the whole grid
ENDPOINTS = ("https://overpass-api.de/api/interpreter",
             "https://maps.mail.ru/osm/tools/overpass/api/interpreter")
QUERIES = {
    "lines": 'way["power"="line"]["voltage"~"(110|220|400)000"];out tags geom;',
    "substations": ('(way["power"="substation"];node["power"="substation"];'
                    'relation["power"="substation"];);out tags center;'),
}
BACKBONE_KV = (220, 400)
MIN_SUBSTATION_KV = 38
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


def match(node: str, idx: dict[str, list[Substation]]) -> tuple[Substation | None, str]:
    k = region.norm_node(node)
    if not k:
        return None, "none"
    if k in idx:
        s = _one_place(idx[k])
        return (s, "exact") if s else (None, "ambiguous")
    if len(k) >= PREFIX_MIN:
        hits = [n for n in idx if len(n) >= PREFIX_MIN and (n.startswith(k) or k.startswith(n))]
        if len(hits) == 1:
            s = _one_place(idx[hits[0]])
            return (s, "prefix") if s else (None, "ambiguous")
    return None, "none"


# --- what the report shows ----------------------------------------------------------

def nodes(con, cache: Path = CACHE) -> dict:
    lines, subs, fetched_at = load(cache)
    idx = _index(subs)
    backbone = [ln for ln in lines if ln.kv in BACKBONE_KV]
    rows = con.execute(f"""
        select p.source_id like 'eirgrid%', coalesce(nullif(r.node, ''), r.station_110kv), r.mec_mw
        from project_row r join ({store.LATEST_LIVE}) l using (publication_id)
        join publication p using (publication_id)
        where p.source_id like '%contracted%' and r.parser_version = {int(parse.PARSER_VERSION)}
          and coalesce(r.technology, '') <> 'Interconnector'
    """).fetchall()
    at: dict[str, dict] = {}
    unplaced: dict[str, float] = defaultdict(float)
    total = 0.0
    for tso, node, mw in rows:
        total += float(mw)
        s, how = match(node or "", idx)
        if s is None:
            unplaced[(node or "").strip() or "(no node)"] += float(mw)
            continue
        n = at.setdefault(s.name, {"node": s.name, "kv": s.kv, "lon": round(s.lon, 4),
                                   "lat": round(s.lat, 4), "mw": 0.0, "projects": 0,
                                   "tso_mw": 0.0, "match": how})
        n["mw"] += float(mw)
        n["projects"] += 1
        n["tso_mw"] += float(mw) if tso else 0.0
    for n in at.values():
        d = km_to_lines((n["lon"], n["lat"]), backbone)
        n["km_backbone"] = round(d, 1) if d is not None else None
        n["mw"], n["tso_mw"] = round(n["mw"], 1), round(n["tso_mw"], 1)
    placed = sum(n["mw"] for n in at.values())
    far = [n for n in at.values() if (n["km_backbone"] or 0) > FAR_KM]
    edges = (0, *BANDS_KM)
    bands = [{"label": f"{lo}-{hi} km" if lo else f"under {hi} km", "gw": 0.0, "nodes": 0}
             for lo, hi in pairwise(edges)]
    bands.append({"label": f"over {FAR_KM} km", "gw": 0.0, "nodes": 0})
    for n in at.values():
        d = n["km_backbone"] if n["km_backbone"] is not None else float("inf")
        b = bands[sum(d >= e for e in BANDS_KM)]
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
        "far_gw": round(sum(n["mw"] for n in far) / 1000, 3),
        "far_nodes": len(far),
        "nodes": sorted(at.values(), key=lambda n: -n["mw"]),
        "unplaced": [{"node": k, "mw": round(v, 1)}
                     for k, v in sorted(unplaced.items(), key=lambda kv: -kv[1])],
        "lines": [{"kv": ln.kv, "path": [[round(x, 3), round(y, 3)] for x, y in simplify(ln.path)]}
                  for ln in lines],
    }


def main(argv: list[str] | None = None) -> int:
    path = fetch()
    lines, subs, at = load(path)
    print(f"grid: {len(lines)} lines, {len(subs)} named substations, fetched {at} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
