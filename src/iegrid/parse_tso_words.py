"""g3b: EirGrid contracted lists the table finder can't read, parsed line by line.

Most editions before 2026 can't be read by pdfplumber's table finder: those
before Aug 2022 draw no lines between rows, and many after split the header or
draw "Signed Date*" as a separate table. parse.parse_tso tries both readers and
keeps the one that ties and reads more of each row. Every row is one line of text holding the project's ref, in
one of two shapes:

    node first   Cahernagh 110kV TG166 Cahernagh Mid Merit OCGT 101.0 Oct 2013
                 Aghada 220 kV TG377 Aghada BESS 01 post Gate 1 Battery 19.0 Aug 2020
                 Knockranny 110 kV TG443 Ardderroo Wind Farm Extension ECP-2.1 Wind 18.0 Jul 2023
    wind lists   Athea (2) 3 TG77 20.00 Gate 2 Athea 110kV May 2008
                 Barnadivane (1) TG44 60.00 Gate 3 Barnadivine 110kV Aug 2014 Apr 2017

The MEC is the last number before the signed month (node first), or the first
number after the ref (wind lists), so a number in a name ("BESS 01", "Gate 1")
is never read as the MEC. A name wrapped onto the next line, which then has no
ref and no number, is joined to the row above. The 2015-2016 lists give a
target connection month after the signed month, kept as target_month.

The caller gates every edition: its set of refs equals the set in the page text,
and its MW is within parse.TIE_MW of the total the list prints. Names, processing
and technology aren't gated; a wrapped cell or footer sentence is kept in raw.
"""

from __future__ import annotations

import io
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

import pdfplumber

# TG/DG refs, the older P-series (P230, P283A) and the demand-side D40d
REF = re.compile(r"^(?:TG|DG|P|D)\d+(?:-\d+)?[A-Za-z]?\.?$")
# A ref the list printed as a bare number after the voltage
BARE_REF = re.compile(r"\d+\s?kV\s+(\d{1,3})\s+(?=[A-Z])", re.IGNORECASE)
# Cramped type can run a ref into the next word ("TG286Gorman", "P283GAorman"): the
# ref is taken from the start of the token, the rest goes back into the line.
GLUED = re.compile(r"^((?:TG|DG|P|D)\d+(?:-\d+)?[A-Za-z]?)(?=[A-Z][a-z])(.+)$")
NUM = re.compile(r"^\d+(?:\.\d+)?$")
KV = re.compile(r"^(\d+)\s*kV$|^kV$", re.IGNORECASE)
MONTH = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*$")
YEAR = re.compile(r"^(19|20)\d{2}\*?$")
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
# How the lists write the processing route, longest first
PROCESSING = re.compile(
    r"(ECP-[\d.]+(?:\s+(?:Non-Batch|Fold In))?|post Gate \d|Pre-Gate \d|Pre-Gate|Gate \d|"
    r"Non GPA|T-\d\s+\d{4}/\d{2,4}|LCIS \d{4}|PCI|Demand|Zero Mec|Non-Batch|DS3|"
    r"Autoproducer)\s*$")
TECHNOLOGIES = (
    "Battery + Synchronous Condenser", "Gas Fired Reciprocating Engines", "Synchronous Condenser",
    "Battery & Inverter System", "Battery & Inverter", "Hybrid",
    "Rotating Stabiliser", "Solar + Battery", "Wind + Battery", "Wind + Solar", "Pumped Storage",
    "Interconnector", "Autoproducer", "Battery", "Solar", "Wind", "OCGT", "CCGT", "Gas", "CHP",
    "Hydro", "Biomass", "Diesel", "Distillate", "Peat", "Coal", "Waste", "Oil", "DSU",
)
# A name that runs on to the next line: ends in a joining word or an open bracket
OPEN_NAME = re.compile(r"(\b(and|&|of|the|formerly|prev\.?|previously|-)|\([^)]*)$", re.IGNORECASE)
SKIP = re.compile(r"^(Total|Note|Page \d|Disclaimer|\*|Correct as of|Contracted|TSO )", re.IGNORECASE)


def _month_at(tokens: list[str], i: int) -> date | None:
    if i + 1 < len(tokens) and MONTH.match(tokens[i]) and YEAR.match(tokens[i + 1]):
        return date(int(tokens[i + 1].rstrip("*")), MONTHS[tokens[i][:3].lower()], 1)
    return None


def _months(tokens: list[str]) -> tuple[int | None, list[date]]:
    """Index of the first month token, and every month-year in order."""
    first, found = None, []
    for i in range(len(tokens)):
        if (d := _month_at(tokens, i)) is not None:
            first = i if first is None else first
            found.append(d)
    return first, found


def _split_middle(text: str) -> tuple[str, str, str]:
    """'Aghada BESS 01 post Gate 1 Battery' -> name, processing, technology."""
    technology = ""
    for t in TECHNOLOGIES:
        if text.endswith(" " + t) or text == t:
            technology, text = t, text[: -len(t)].rstrip()
            break
    processing = ""
    if (m := PROCESSING.search(text)) is not None:
        processing, text = m.group(1), text[: m.start()].rstrip()
    return text.strip(), processing, technology


def parse_line(line: str) -> dict | None:
    tokens = []
    for t in line.split():
        if (m := GLUED.match(t)) is not None and not REF.match(t):
            tokens += [m.group(1), m.group(2)]
        else:
            tokens.append(t)
    refs = [i for i, t in enumerate(tokens) if REF.match(t)]
    if not refs:
        # a ref printed as a bare number right after the voltage ("Wexford 110 kV 19
        # Wexford Synchronous Condenser ...", Sep 2025): the g5 review found it dropped
        m = BARE_REF.search(line)
        if m is None:
            return None
        bare = m.group(1)
        refs = [i for i, t in enumerate(tokens)
                if t == bare and i > 0 and tokens[i - 1].lower().endswith("kv")][:1]
        if not refs:
            return None
    r = refs[0]
    ref = tokens[r].rstrip(".")
    before, after = tokens[:r], tokens[r + 1:]
    if after and re.fullmatch(r"ph\d", after[0]):  # "TG69 ph2 22.50": a phase suffix
        after = after[1:]
    m_first, months = _months(after)
    # Wind lists give the MEC straight after the ref; node-first lists give a name.
    # (The node text can be garbled, "Kinn1e1g0ad k- V", so it can't be relied on.)
    node_first = not (after and NUM.match(after[0]))
    if node_first:
        node_text = " ".join(before)
        head = after[:m_first] if m_first is not None else after
        nums = [i for i, t in enumerate(head) if NUM.match(t)]
        if not nums:
            return {"ref": ref, "error": f"no MEC in {line!r}"}
        mec = head[nums[-1]]
        name, processing, technology = _split_middle(" ".join(head[:nums[-1]]))
    else:  # wind lists: name [phase] REF MEC Gate N node NNNkV month [month]
        if not after or not NUM.match(after[0]):
            return {"ref": ref, "error": f"no MEC after ref in {line!r}"}
        mec = after[0]
        rest = after[1:m_first] if m_first is not None else after[1:]
        rest_text = " ".join(rest)
        pm = re.match(r"((?:post |Pre-)?Gate \d|Pre-Gate|Non GPA|ECP-[\d.]+)\s*(.*)$", rest_text)
        processing, node_text = (pm.group(1), pm.group(2)) if pm else ("", rest_text)
        if before and re.fullmatch(r"\d+[a-z]?", before[-1]):
            before = before[:-1]  # the phase: "3", "1b"
        name, technology = " ".join(before), "Wind"
    vm = re.search(r"(\d+)\s*kV", node_text, re.IGNORECASE)
    node = re.sub(r"\s*\d*\s*kV\b", "", node_text, flags=re.IGNORECASE).strip(" -")
    try:
        mec_mw = Decimal(mec)
    except InvalidOperation:
        return {"ref": ref, "error": f"MEC {mec!r} in {line!r}"}
    return {"ref": ref, "name": name, "technology": technology, "mec_mw": mec_mw, "node": node,
            "voltage": f"{vm.group(1)} kV" if vm else "", "processing": processing,
            "signed": months[0] if months else None,
            "target": months[1] if len(months) > 1 else None, "line": line}


def read(content: bytes) -> list[dict]:
    rows: list[dict] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for line in (page.extract_text() or "").splitlines():
                line = line.strip()
                if not line or SKIP.match(line):
                    continue
                got = parse_line(line)
                if got is not None:
                    got["page"] = page_no
                    rows.append(got)
                elif rows and rows[-1]["page"] == page_no and "error" not in rows[-1]:
                    # A line with no ref continues the row above, but it is only the
                    # name's if the name is visibly unfinished ("Beenanaspock and",
                    # "Carrigdangan (formerly"). Otherwise it is a wrapped node or type
                    # cell, or a footer sentence: kept in raw, never put in the name.
                    if OPEN_NAME.search(rows[-1]["name"]) and len(line) < 60:
                        rows[-1]["name"] = f"{rows[-1]['name']} {line}".strip()
                    rows[-1]["line"] = f"{rows[-1]['line']} / {line}"
    return rows


def to_project_rows(rows: list[dict]):
    from iegrid import parse

    out = []
    for i, r in enumerate(rows, start=1):
        if "error" in r:
            raise parse.ParseError(f"page {r.get('page')}: {r['ref']}: {r['error']}")
        out.append(parse.ProjectRow(
            row_order=i, page=r["page"], project_ref=r["ref"], name=r["name"],
            technology=r["technology"], mec_mw=r["mec_mw"], node=r["node"], station_110kv="",
            voltage=r["voltage"], processing_type=r["processing"], status="Contracted",
            signed_month=r["signed"], energised_on=None, energised_note="",
            raw=json.dumps(r["line"]), target_month=r["target"],
        ))
    return out
