"""Layer: the connection funnel. Of the projects an ECP batch offered a connection, how many
ever reach a contracted list, and what has become of those? (docs/layers/04-funnel/README.md)

The batch results publications (ECP-1 in 2018 to ECP-2.5) list who was offered. The lists
tag each contracted project with its batch ("ECP-2.3" in the processing column). The
parked g5 question was the denominator: joined to the lists, offers give the top of the
funnel, and layers 1-3 give the bottom.

    offered      distinct rows across a batch's results files (not the Categories B/C or
                 non-batch lists), a project counted once however many status updates
                 list it: same distinctive name and an MEC within region.mec_close
    found        an offer with a list row (contracted or energised, any edition) of the
                 same name key and a close MEC: STRICT matching, so the share found is
                 a lower bound on what the lists hold
    tagged       list refs whose own processing column names the batch: a second,
                 independent count of the same thing

The two are triangulated, and the match is validated against the tags, which are ground
truth the matcher never saw:

    precision    of matched list rows that carry a batch tag, the share whose tag is this
                 batch (a row matched to a project of another batch is a false match, or a
                 project re-offered)
    recall       of list refs tagged with this batch, the share matched to one of its offers

What the lists can't show is stated per batch, not hidden: ESB's contracted lists in the
store begin in 2024, so a distribution project that signed and withdrew before then leaves
no trace, and the early batches' DSO side is undercounted. Batches the lists cover from
signing to now (ECP-2.3, 2.4) are the cleaner reading.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from iegrid import ecp, metrics, parse, region

# The batches the funnel reads. The GSS rounds (Sep 2025, Mar 2026) are left out: no list row
# carries their tag yet, and the one "match" GSS-2 had was a name collision.
BATCHES = ("ECP-1", "ECP-2.1", "ECP-2.2", "ECP-2.3", "ECP-2.4", "ECP-2.5")
TSO_PREFIX = "eirgrid."


@dataclass(frozen=True)
class Offer:
    batch: str
    key: tuple[str, ...]
    name: str
    mw: Decimal


@dataclass(frozen=True)
class Listed:
    ref: str
    key: tuple[str, ...]
    name: str
    mw: Decimal
    source_id: str      # the list it was last seen on
    tag: str | None     # the batch its processing column names, if it ever did


def close(a: Decimal, b: Decimal) -> bool:
    return region.mec_close(a, b) or region.mec_close(b, a)


def distinct_offers(rows: list[tuple[str, Decimal]], batch: str) -> list[Offer]:
    """One Offer per project: rows (name, MW) in publication order; a row whose key and MEC
    match an earlier one is the same offer in a later status update. A name that has no
    distinctive words can't be matched and is dropped (counted by the caller)."""
    out: list[Offer] = []
    for name, mw in rows:
        k = region.key(name)
        if not k or mw is None:
            continue
        if not any(o.key == k and close(o.mw, mw) for o in out):
            out.append(Offer(batch, k, name, mw))
    return out


def match(offers: list[Offer], listed: list[Listed]) -> dict[Offer, list[Listed]]:
    """Each offer with the list refs of the same name key and a close MEC (possibly none)."""
    by_key: dict[tuple[str, ...], list[Listed]] = collections.defaultdict(list)
    for item in listed:
        by_key[item.key].append(item)
    return {o: [x for x in by_key.get(o.key, []) if close(x.mw, o.mw)] for o in offers}


def validate(matches: dict[Offer, list[Listed]], listed: list[Listed], batch: str) -> dict:
    """Precision and recall of the match against the lists' own batch tags."""
    tagged_pairs = [(x.tag == batch) for hits in matches.values() for x in hits if x.tag]
    matched_refs = {x.ref for hits in matches.values() for x in hits}
    tagged = {x.ref for x in listed if x.tag == batch}
    return {
        "tagged_matches": len(tagged_pairs),
        "precision": round(sum(tagged_pairs) / len(tagged_pairs), 3) if tagged_pairs else None,
        "tagged_refs": len(tagged),
        "recall": round(len(tagged & matched_refs) / len(tagged), 3) if tagged else None,
    }


def offers_by_batch(con) -> dict[str, list[Offer]]:
    files = con.execute(f"""
        select archive_digest, file_name, original_url from ecp_file
        where reader_version = {int(ecp.READER_VERSION)} order by capture_ts""").fetchall()
    rows: dict[str, list[tuple[str, Decimal]]] = collections.defaultdict(list)
    for digest, file_name, url in files:
        b = metrics.batch_of(file_name) or metrics.batch_of(url)
        if b not in BATCHES or "categor" in file_name.lower():
            continue
        rows[b] += con.execute("""select name, mec_mw from ecp_row
                                  where archive_digest = ? and reader_version = ?
                                  order by row_order""", [digest, ecp.READER_VERSION]).fetchall()
    return {b: distinct_offers(r, b) for b, r in rows.items()}


def listed_refs(con) -> list[Listed]:
    """Every ref ever on a contracted or ESB energised list (its latest row), and the batch
    its processing column has ever named."""
    out: dict[str, Listed] = {}
    for sid, ref, name, mw, pt in con.execute(f"""
            select p.source_id, r.project_ref, r.name, r.mec_mw, r.processing_type
            from project_row r join publication p using (publication_id)
            where r.parser_version = {int(parse.PARSER_VERSION)}
              and (p.source_id like '%contracted%' or p.source_id like 'esb.dso_energised%')
            order by p.as_of, p.published_at, r.row_order""").fetchall():
        k = region.key(name)
        if not k:
            continue
        tag = metrics.batch_of(pt or "") or (out[ref].tag if ref in out else None)
        out[ref] = Listed(ref, k, name, mw, sid, tag)
    return list(out.values())


def legacy_refs(con) -> list[Listed]:
    """The refs ESB's 2017-2023 lists add (esb_legacy.py): distribution projects that signed
    and later withdrew, or connected, before the current lists begin. Empty until loaded."""
    try:
        rows = con.execute("""
            select l.project_ref, l.name, l.mec_mw, l.offer_type, p.source_id
            from esb_legacy_row l join publication p using (publication_id)
            where l.mec_mw is not null order by p.as_of, p.published_at, l.row_order""").fetchall()
    except Exception:  # noqa: BLE001 - a store from before the legacy layer
        return []
    out: dict[tuple[str, str], Listed] = {}
    for ref, name, mw, offer, sid in rows:
        k = region.key(name)
        if k:
            prev = out.get((ref, name))
            out[(ref, name)] = Listed(ref, k, name, mw, sid,
                                      metrics.batch_of(offer or "") or (prev.tag if prev else None))
    return list(out.values())


def status_of(refs: set[str], con, outcomes: dict[str, str],
              legacy: set[str] | None = None) -> dict[str, int]:
    """Where matched refs are now: on a newest contracted list (waiting), on ESB's energised
    list (energised), a TSO leaver (its layer-1 outcome), or gone from the lists held."""
    newest_contracted = {r[0] for r in con.execute(f"""
        select project_ref from project_row where parser_version = {int(parse.PARSER_VERSION)}
          and publication_id in ({", ".join(str(i) for i in metrics._latest(con, (
              "eirgrid.tso_contracted_wind", "eirgrid.tso_contracted_nonwind",
              "esb.dso_contracted_renewable", "esb.dso_contracted_nonrenewable")))})""").fetchall()}
    energised = {r[0] for r in con.execute(f"""
        select project_ref from project_row r join publication p using (publication_id)
        where r.parser_version = {int(parse.PARSER_VERSION)}
          and p.source_id like 'esb.dso_energised%' and r.energised_on is not null""").fetchall()}
    out: dict[str, int] = collections.Counter()
    for ref in refs:
        if ref in newest_contracted:
            out["still contracted"] += 1
        elif ref in energised:
            out["energised (ESB list)"] += 1
        elif ref in outcomes:
            out[f"left: {outcomes[ref]}"] += 1
        elif legacy and ref in legacy:
            out["on ESB's earlier lists only"] += 1
        else:
            out["gone from the lists held"] += 1
    return dict(out)


def build(con, today: date | None = None) -> dict | None:
    """The report section: None until the ECP results are in the store."""
    from iegrid import connected

    offers = offers_by_batch(con)
    if not offers:
        return None
    current = listed_refs(con)
    have = {x.ref for x in current}
    legacy = [x for x in legacy_refs(con) if x.ref not in have]
    listed = current + legacy
    try:
        outcomes = {o.ref: o.outcome for o in connected.outcomes(con)}
    except Exception:  # noqa: BLE001 - a store without the connected layer: no outcomes
        outcomes = {}
    dates = metrics.batch_dates(con)
    latest = max(r[0] for r in con.execute("select as_of from publication where source_id like '%contracted%'").fetchall())
    out = []
    for b in BATCHES:
        if b not in offers:
            continue
        of = offers[b]
        hits = match(of, listed)
        found = [o for o, h in hits.items() if h]
        refs = {x.ref for h in hits.values() for x in h}
        total_mw = sum((o.mw for o in of), Decimal(0))
        found_mw = sum((o.mw for o in found), Decimal(0))
        tagged = {x.ref for x in listed if x.tag == b}
        by_key = len({o.key for o in of})
        d = dates.get(b)
        out.append({
            "batch": b,
            "results": d.label() if d else None,
            "age_months": metrics._months(d.when, latest) if d else None,
            "offered": len(of), "offered_mw": float(total_mw),
            "offered_by_name": by_key,
            "found": len(found), "found_mw": float(found_mw),
            "found_tso": len({r for r in refs if any(x.ref == r and x.source_id.startswith(TSO_PREFIX)
                                                     for h in hits.values() for x in h)}),
            "tagged": len(tagged),
            "share_found": round(len(found) / len(of), 3) if of else None,
            "share_found_mw": round(float(found_mw / total_mw), 3) if total_mw else None,
            # the same count from the lists' own tags, over the offers counted by name only
            "share_tagged": round(len(tagged) / by_key, 3) if by_key else None,
            "status": status_of(refs, con, outcomes, {x.ref for x in legacy}),
            "validation": validate(hits, listed, b),
        })
    return {"batches": out}
