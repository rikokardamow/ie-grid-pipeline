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
    cited  the project is in data/cited_counties.csv, a short table of projects
           no ECP publication names, each row with the source it was read from
           (planning case, developer or EirGrid). Keyed on ref and checked against
           the name, so a reused ref doesn't carry a county to another project.
    osm-node  still nothing, but OpenStreetMap has a substation of that name in
           exactly one county. The county of the substation, not of the project:
           an offshore wind farm gets the county where it lands.

A project with none of these stays without a county and is listed by name.

The job that feeds this is iegrid.counties.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from iegrid.ecp import COUNTIES, EcpRow

MEC_TOLERANCE = Decimal("0.10")  # 10%, or MEC_FLOOR, whichever is larger
MEC_FLOOR = Decimal("0.5")
NODE_MIN_PROJECTS = 2            # distinct ECP projects at the node, each voting once
NODE_MIN_SHARE = 0.75

# Words that differ between a list and a batch publication for the same project.
FILLER = {
    "wind", "farm", "farms", "windfarm", "wf", "solar", "park", "pv", "energy", "storage",
    "battery", "bess", "facility", "project", "limited", "ltd", "the", "and", "plus", "of",
    "power", "plant", "station", "renewable", "renewables", "hybrid", "system", "systems",
    "phase", "ph", "extension", "ext", "repowering", "development", "array",
    # generic words that alone would match unrelated projects (g4 review)
    "north", "south", "east", "west", "upper", "lower", "esb", "turbine", "turbines",
    "community", "single", "co", "ireland", "irish",
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
    basis: str         # 'name', 'cited', 'node', 'osm-node' or 'none'
    evidence: str


def key(name: str) -> tuple[str, ...]:
    """'Ballyroe Solar Extension (prev. X)' -> ('ballyroe', 'x'): the distinctive words,
    numbers kept ('Ballymoneen Phase 2' and 'Ballymoneen' stay apart)."""
    s = name.lower().replace("&", " and ")
    s = re.sub(r"\([^)]*\)", " ", s)  # "(prev. X)", "(ECP2.4+2.5)", "(Split)"
    s = re.sub(r"\b(prev|previously|formerly|fka)\b\.?", " ", s)
    words = re.findall(r"[a-z]+|\d+", s)
    # single letters ("P" of "P2") carry nothing; numbers stay, so phases stay apart
    return tuple(sorted({w for w in words if w not in FILLER and (len(w) > 1 or w.isdigit())}))


def norm_node(node: str) -> str:
    return re.sub(r"\s*\d+\s*kv\b|\s+t\d+$|[^a-z ]", "", node.lower()).strip()


def mec_close(a: Decimal | None, b: Decimal) -> bool:
    if a is None:
        return False
    return abs(a - b) <= max(MEC_FLOOR, MEC_TOLERANCE * b)


def _subset_ok(a: set[str], b: set[str]) -> bool:
    """One name's words inside the other's: only when the smaller has two or more
    distinctive words and the extra words carry no number (a phase stays apart)."""
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return len(small) >= 2 and small <= big and not any(w.isdigit() for w in big - small)


def _hits(p: Project, index: dict[tuple[str, ...], list[EcpRow]]) -> list[EcpRow]:
    """Rows with the same distinctive words, else rows whose words contain the
    project's (or the other way round, see _subset_ok), always with a close MEC."""
    k = key(p.name)
    if not k:
        return []
    same = [r for r in index.get(k, []) if mec_close(r.mec_mw, p.mec_mw)]
    if same:
        return same
    ks = set(k)
    return [r for other, rows in index.items() if _subset_ok(ks, set(other))
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
    """Counties for the rest, from where the other projects at the same node are.
    Each distinct ECP project naming the node votes once (the same project in five
    editions is one vote; a project also placed by name doesn't vote again), and the
    cited projects vote for their sourced county."""
    votes: dict[str, Counter] = defaultdict(Counter)
    seen = set()
    for r in ecp:
        k = (key(r.name), norm_node(r.node))
        if r.node and k[0] and k not in seen:
            seen.add(k)
            votes[norm_node(r.node)][r.county] += 1
    for p in projects:
        c = known.get(p.project_ref)
        if c is not None and c.basis == "cited" and p.node:
            votes[norm_node(p.node)][c.county] += 1
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
           substations: list[tuple[str, ...]]) -> dict[str, County]:
    """substations: (node or substation name, county[, what was found]) from OpenStreetMap."""
    where: dict[str, set[str]] = defaultdict(set)
    found: dict[str, str] = {}
    for name, county, *what in substations:
        if (n := norm_substation(name)):
            where[n].add(county)
            if what:
                found[n] = what[0]
    out = {}
    for p in projects:
        if p.project_ref in placed or not p.node:
            continue
        counties = where.get(norm_node(p.node), set())
        if len(counties) == 1:
            county = next(iter(counties))
            what = found.get(norm_node(p.node), f"{p.node} substation")
            out[p.project_ref] = County(p.project_ref, p.source_id, county, "osm-node",
                                        f"OpenStreetMap, {what}")
    return out


CITED = Path(__file__).parent / "data" / "cited_counties.csv"


def cited_table(path: Path = CITED) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def by_cited(projects: list[Project], table: list[dict[str, str]]) -> dict[str, County]:
    rows = {r["project_ref"]: r for r in table}
    out = {}
    for p in projects:
        r = rows.get(p.project_ref)
        if r and key(r["name_in_list"]) == key(p.name):
            out[p.project_ref] = County(p.project_ref, p.source_id, r["county"], "cited",
                                        f"{r['source_says']} <{r['source_url']}>")
    return out


def assign(projects: list[Project], ecp: list[EcpRow],
           substations: list[tuple[str, str]] = (),
           cited: list[dict[str, str]] | None = None) -> list[County]:
    named = by_name(projects, ecp)
    sourced = by_cited(projects, cited_table() if cited is None else cited)
    known = {**named, **{k: v for k, v in sourced.items() if k not in named}}
    noded = by_node(projects, known, ecp)
    osm = by_osm(projects, set(known) | set(noded), substations)
    out = []
    for p in projects:
        got = (named.get(p.project_ref) or sourced.get(p.project_ref)
               or noded.get(p.project_ref) or osm.get(p.project_ref))
        out.append(got or County(p.project_ref, p.source_id, None, "none",
                                 "no ECP name match, no settled node, no OSM substation"))
    return out


def rules() -> str:
    """What a build depends on, beyond its inputs: the matching code, the reader code
    and the cited table, by content hash. Editing a rule, a filler word, the reader or
    a cited county makes a new build rather than leaving an old one in place."""
    import hashlib

    from iegrid import ecp as reader

    h = hashlib.sha256()
    for path in (Path(__file__), Path(reader.__file__), CITED):
        h.update(path.read_bytes())
    return f"reader={reader.READER_VERSION};code+table={h.hexdigest()[:16]}"
