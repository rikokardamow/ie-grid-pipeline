"""g4: a county for every project in the newest contracted lists.

Two ways, tried in order, and the way is kept with the answer:

    name   the project is in an ECP results publication under the same name
           (normalised) and a MEC within MEC_TOLERANCE: the county is the one
           that publication prints. Several matching rows must agree.
    node   no name match, but the project's connection point (TSO node, or the
           DSO's designed 110 kV station) has NODE_MIN_PROJECTS or more projects
           with a known county, and NODE_MIN_SHARE of them are in one county.
           The county is then where that node's projects mostly are, which is an
           inference about the project, labelled as one.
    osm-node  still nothing, but OpenStreetMap has a substation of that name in
           exactly one county. The county of the substation, not of the project:
           an offshore wind farm gets the county where it lands.

A project with none of these stays without a county and is listed by name.

The job that feeds this is iegrid.counties.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal

from iegrid.ecp import COUNTIES, EcpRow

MEC_TOLERANCE = Decimal("0.10")  # 10%, or 1 MW, whichever is larger
NODE_MIN_PROJECTS = 2
NODE_MIN_SHARE = 0.75

# Words that differ between a list and a batch publication for the same project.
FILLER = {
    "wind", "farm", "farms", "windfarm", "wf", "solar", "park", "pv", "energy", "storage",
    "battery", "bess", "facility", "project", "limited", "ltd", "the", "and", "plus", "of",
    "power", "plant", "station", "renewable", "renewables", "hybrid", "system", "systems",
    "phase", "ph", "extension", "ext", "repowering", "development", "array",
}


@dataclass(frozen=True)
class Project:
    project_ref: str
    source_id: str
    name: str
    mec_mw: Decimal
    node: str          # TSO node; DSO designed 110 kV station


@dataclass(frozen=True)
class County:
    project_ref: str
    source_id: str
    county: str | None
    basis: str         # 'name', 'node', 'osm-node' or 'none'
    evidence: str


def key(name: str) -> tuple[str, ...]:
    """'Ballyroe Solar Extension (prev. X)' -> ('ballyroe', 'x'): the distinctive words,
    numbers kept ('Ballymoneen Phase 2' and 'Ballymoneen' stay apart)."""
    s = name.lower().replace("&", " and ")
    s = re.sub(r"\([^)]*\)", " ", s)  # "(prev. X)", "(ECP2.4+2.5)", "(Split)"
    s = re.sub(r"\b(prev|previously|formerly|fka)\b\.?", " ", s)
    words = re.findall(r"[a-z]+|\d+", s)
    return tuple(sorted({w for w in words if w not in FILLER}))


def norm_node(node: str) -> str:
    return re.sub(r"\s*\d+\s*kv\b|\s+t\d+$|[^a-z ]", "", node.lower()).strip()


def mec_close(a: Decimal | None, b: Decimal) -> bool:
    if a is None:
        return False
    return abs(a - b) <= max(Decimal(1), MEC_TOLERANCE * b)


def _hits(p: Project, index: dict[tuple[str, ...], list[EcpRow]]) -> list[EcpRow]:
    """Rows with the same distinctive words, else rows whose words contain the
    project's (or the other way round), always with a close MEC."""
    k = key(p.name)
    if not k:
        return []
    same = [r for r in index.get(k, []) if mec_close(r.mec_mw, p.mec_mw)]
    if same:
        return same
    ks = set(k)
    return [r for other, rows in index.items()
            if (ks <= set(other) or set(other) <= ks) and len(min(ks, set(other), key=len)) >= 1
            for r in rows if mec_close(r.mec_mw, p.mec_mw)]


def by_name(projects: list[Project], ecp: list[EcpRow]) -> dict[str, County]:
    index: dict[tuple[str, ...], list[EcpRow]] = defaultdict(list)
    for r in ecp:
        if (k := key(r.name)):
            index[k].append(r)
    out = {}
    for p in projects:
        hits = _hits(p, index)
        counties = {r.county for r in hits}
        if len(counties) == 1:
            county = counties.pop()
            out[p.project_ref] = County(p.project_ref, p.source_id, county, "name",
                                        f"{len(hits)} ECP rows: {hits[0].name!r}")
    return out


def by_node(projects: list[Project], known: dict[str, County],
            ecp: list[EcpRow] = ()) -> dict[str, County]:
    """Counties for the rest, from where the other projects at the same node are:
    every ECP row that names its node, and every project already placed by name."""
    votes: dict[str, Counter] = defaultdict(Counter)
    seen = set()
    for r in ecp:
        k = (key(r.name), r.county, norm_node(r.node))
        if r.node and k not in seen:  # a project repeated across editions votes once
            seen.add(k)
            votes[norm_node(r.node)][r.county] += 1
    for p in projects:
        if p.project_ref in known and p.node:
            votes[norm_node(p.node)][known[p.project_ref].county] += 1
    out = {}
    for p in projects:
        if p.project_ref in known or not p.node:
            continue
        tally = votes.get(norm_node(p.node))
        if not tally:
            continue
        county, n = tally.most_common(1)[0]
        total = sum(tally.values())
        if total >= NODE_MIN_PROJECTS and n / total >= NODE_MIN_SHARE:
            out[p.project_ref] = County(p.project_ref, p.source_id, county, "node",
                                        f"{n} of {total} projects at {p.node} are in {county}")
    return out


def osm_county(area: str) -> str | None:
    """'County Cork' -> 'Cork'; the Dublin and city councils -> their county."""
    a = area.replace("County ", "").replace("City and County", "").replace("City", "").strip()
    if a in ("Fingal", "South Dublin") or a.startswith(("Dún Laoghaire", "Dun Laoghaire")):
        return "Dublin"
    for c in COUNTIES:
        if a.startswith(c):
            return c
    return None


def norm_substation(name: str) -> str:
    """'Knockraha 220kV Substation' -> 'knockraha'."""
    s = re.sub(r"\b(sub)?station\b|\d+\s*-?\s*kv\b|\bkv\b|\bgis\b|\bswitchroom\b|\d+", " ",
               name.lower())
    return " ".join(re.findall(r"[a-z]+", s))


def by_osm(projects: list[Project], placed: set[str],
           substations: list[tuple[str, str]]) -> dict[str, County]:
    """substations: (node or substation name, county) from OpenStreetMap."""
    where: dict[str, set[str]] = defaultdict(set)
    for name, county in substations:
        if (n := norm_substation(name)):
            where[n].add(county)
    out = {}
    for p in projects:
        if p.project_ref in placed or not p.node:
            continue
        counties = where.get(norm_node(p.node), set())
        if len(counties) == 1:
            county = next(iter(counties))
            out[p.project_ref] = County(p.project_ref, p.source_id, county, "osm-node",
                                        f"OpenStreetMap: {p.node} substation is in {county}")
    return out


def assign(projects: list[Project], ecp: list[EcpRow],
           substations: list[tuple[str, str]] = ()) -> list[County]:
    named = by_name(projects, ecp)
    noded = by_node(projects, named, ecp)
    osm = by_osm(projects, set(named) | set(noded), substations)
    out = []
    for p in projects:
        got = named.get(p.project_ref) or noded.get(p.project_ref) or osm.get(p.project_ref)
        out.append(got or County(p.project_ref, p.source_id, None, "none",
                                 "no ECP name match, no settled node, no OSM substation"))
    return out


# Every constant the answer depends on. A build is keyed on it, so changing a rule
# makes a new build rather than relabelling an old one.
RULES = (f"mec_tolerance={MEC_TOLERANCE};node_min_projects={NODE_MIN_PROJECTS};"
         f"node_min_share={NODE_MIN_SHARE};filler={len(FILLER)}")
