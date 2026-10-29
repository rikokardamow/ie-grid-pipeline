"""Layer: an errata ledger. Where a publisher's list disagrees with itself or with another
publication, with the evidence that reproduces it. (docs/layers/05-errata/README.md)

A discrepancy is not necessarily an error: a connection can be longer than the distance
allowed, a ref can be legitimately reused. Each entry says what disagrees and what would
settle it, and nothing is called wrong that the data can't show to be. The ledger is
regenerated with every report, so an entry disappears when a publisher fixes the list.

Four kinds, each from a check another layer already makes:

    node       EirGrid's contracted list names a connection station that the ECP batch
               results contradict (80+ km apart), or that disagrees with the county every
               other project at that station is in
    reused ref a ref on a connected list before any contracted list has it: the same label
               for two projects
    gap        a project that left the contracted list more than a year BEFORE it first
               appears on a connected list, so it was on neither list in between. (One
               that left long AFTER first appearing connected is not listed: that is a
               partial connection, the contracted list keeping the unconnected remainder
               until the last phase)
    restated   EirGrid changed its own published history between two editions
    moved      a project on one publisher's lists that later turns up on the other's, with
               the two disagreeing on when it connected (TG24 Knockacummer: ESB says
               energised Nov 2013, EirGrid says connected Jul 2015). When its size matches
               a restatement, the restatement row says so: EirGrid's +100 MW is this project
"""

from __future__ import annotations

import re

GAP_DAYS = 365


def moves(con) -> list[dict]:
    """Refs on ESB's 2017-2023 lists that later appear on an EirGrid connected list: the
    project changed publisher. One entry per ref, with each side's dates."""
    try:
        rows = con.execute("""
            with esb as (
                select l.project_ref, min(p.as_of) first_seen, max(p.as_of) last_seen,
                       any_value(l.name) name,
                       coalesce(max(l.mec_mw) filter (where p.source_id like '%energised%'),
                                max(l.mec_mw)) mec,
                       min(l.date_on) filter (where p.source_id like '%energised%') energised_on
                from esb_legacy_row l join publication p using (publication_id)
                where l.project_ref like 'TG%' group by 1),
            eir as (
                select c.project_ref, min(p.as_of) first_listed,
                       any_value(c.connected_month) connected
                from connected_row c join publication p using (publication_id) group by 1)
            select e.project_ref, e.name, e.mec, e.first_seen, e.last_seen, e.energised_on,
                   t.first_listed, t.connected
            from esb e join eir t using (project_ref) order by e.project_ref""").fetchall()
    except Exception:  # noqa: BLE001 - a store without the legacy or connected layers
        return []
    out = [{"ref": r[0], "name": r[1], "mw": float(r[2] or 0), "esb_first": r[3],
            "esb_last": r[4], "esb_energised": r[5], "eir_first": r[6], "eir_connected": r[7]}
           for r in rows]
    if out:
        notes = _switch_notes(con)
        for m in out:
            m["note"] = next((n for w, n in notes if w.lower() in m["name"].lower()), None)
    return out


SWITCH = re.compile(r"(\w[\w-]*) (?:windfarm |wind farm )?has switched from an? (TSO|DSO) to an? "
                    r"(TSO|DSO)", re.IGNORECASE)


def _switch_notes(con) -> list[tuple[str, dict]]:
    """Notes in EirGrid's connected editions of the form "<project> has switched from a TSO to
    a DSO ...": [(first word of the project, {edition, from, to})], earliest edition first."""
    from iegrid import asof, connected, store

    found: dict[str, dict] = {}
    for _, _, as_of, raw in connected.editions(con):
        for m in SWITCH.finditer(asof.pdf_text((store.ROOT / raw).read_bytes())):
            found.setdefault(m.group(1), {"edition": str(as_of), "from": m.group(2).upper(),
                                          "to": m.group(3).upper()})
    return list(found.items())


def from_parts(conflicts: list[dict], outcomes, restatement: dict | None,
               moved: list[dict] | None = None) -> list[dict]:
    """The ledger from the grid layer's conflicts, the connected layer's outcomes, the wind
    table's restatement check and the projects that changed publisher."""
    from iegrid import connected

    out: list[dict] = []
    for c in conflicts:
        if "results_node" in c:
            out.append({
                "kind": "node", "ref": c["ref"], "project": c["name"],
                "says": f"EirGrid's contracted list prints the connection station "
                        f"{c['list_node']}",
                "against": f"the ECP batch results print {c['results_node']}, {c['km']} km away",
                "settles": "the project's grid-connection offer or its planning file"})
        else:
            out.append({
                "kind": "node", "ref": c["ref"], "project": c["name"],
                "says": f"EirGrid's contracted list prints the connection station "
                        f"{c['list_node']} ({c['list_node_county']})",
                "against": f"the county placement from the ECP results and other sources "
                           f"is {c['county']}",
                "settles": "the project's grid-connection offer or its planning file"})
    for o in outcomes:
        if o.outcome == connected.UNKNOWN and o.why.startswith("ref reused"):
            out.append({
                "kind": "reused ref", "ref": o.ref, "project": o.name,
                "says": f"{o.ref} is on a connected list from {o.first_listed}",
                "against": o.why.removeprefix("ref reused: "),
                "settles": "whether the two projects are one (a renaming) or two"})
        elif (o.outcome == connected.CONNECTED and o.first_listed
              and (o.first_listed - o.left_on).days > GAP_DAYS):
            out.append({
                "kind": "gap", "ref": o.ref, "project": o.name,
                "says": f"left the contracted list in {o.left_on:%b %Y}",
                "against": f"first appears on a connected list in {o.first_listed:%b %Y}: "
                           f"on neither list for {(o.first_listed - o.left_on).days // 30} months",
                "settles": "the project's energisation record (a reused ref, or a list that "
                           "dropped it early)"})
    for m in moved or []:
        a = m["esb_energised"]
        b = m["eir_connected"]
        out.append({
            "kind": "moved", "ref": m["ref"], "project": m["name"],
            "says": f"ESB's lists carry it from {m['esb_first']:%b %Y} to {m['esb_last']:%b %Y}"
                    + (f", energised {a:%-d %b %Y}" if a else ", undated"),
            "against": f"EirGrid's lists carry it from {m['eir_first']:%b %Y}, connected "
                       f"{b:%b %Y}" if b else f"EirGrid's lists carry it from {m['eir_first']:%b %Y}",
            "settles": "which publisher the project is connected to, and when it was energised"})
        if m.get("note"):
            n = m["note"]
            out[-1]["against"] += (
                f". EirGrid's own note in its {n['edition']} edition says the project switched "
                f"from {n['from']} to {n['to']}"
                + (", the opposite of the order the lists show"
                   if n["from"] == "TSO" and m["esb_last"] < m["eir_first"] else ""))
    if restatement and restatement.get("largest_mw"):
        match = next((m for m in moved or [] if abs(m["mw"] - restatement["largest_mw"]) <= 1), None)
        out.append({
            "kind": "restated", "ref": "", "project": "EirGrid's wind capacity history",
            "says": f"cumulative wind MW by year, in the editions up to "
                    f"{restatement['last_edition_before']}",
            "against": f"the {restatement['first_edition_matching']} edition and every later one "
                       f"print the same years up to {restatement['largest_mw']:+.0f} MW "
                       + (f"different: the size of {match['ref']} {match['name']}, which moved "
                          "between ESB's lists and EirGrid's (see 'moved')"
                          if match else "different, with no note"),
            "settles": "EirGrid saying what the change was"})
    return out


def build(con, conflicts: list[dict], pace: dict | None) -> dict | None:
    """The report section; None until the connected layer is loaded."""
    from iegrid import connected

    try:
        if con.execute("select count(*) from connected_row").fetchone()[0] == 0:
            return None
    except Exception:  # noqa: BLE001 - a store from before the connected layer
        return None
    restatement = pace["transmission_wind"]["restatement"] if pace else None
    entries = from_parts(conflicts, connected.outcomes(con), restatement, moves(con))
    kinds: dict[str, int] = {}
    for e in entries:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    return {"total": len(entries), "entries": entries, "kinds": [{"kind": k, "count": n} for k, n in sorted(kinds.items())]}
