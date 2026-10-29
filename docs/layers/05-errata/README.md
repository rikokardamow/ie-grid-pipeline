# Layer 5: where the lists disagree

**What it adds.** A ledger of the places where a publisher's list disagrees with itself or
with another publication, each with what disagrees and what would settle it. Today it has five
rows, each with the answer found where one could be (layer 8). (It had six: the "gap" row for TG44
was a bug in our own flows code, not a publisher discrepancy, and is gone.) It is a
different kind of output from the other layers: not a finding about the queue but
a record of where the sources can't be trusted yet, for the reader and for the publishers.

**Why it's worth having.** Every one of these was found by the other layers' checks and was
previously buried in a parking file or a table footnote. A reader building on the lists should
know that EirGrid's own node for Kilmorna Energy Storage (Kinnegad) contradicts its own ECP
results (Knockanure, 185 km away), and that a 100 MW wind farm, TG24 Knockacummer, moved between ESB's lists and EirGrid's with
the two publishers disagreeing on its connection date by 20 months (which is also why EirGrid's
published wind history changed by +100 MW in 2018). It is also the cheapest way for the publishers to see what a
careful reader trips over.

## Today's ledger

| kind | project | what disagrees |
|---|---|---|
| node | TG485 Kilmorna Energy Storage | list: Kinnegad 110 kV; ECP-2.4 results: Knockanure 220 kV, 185 km away. **Settled**: a 170 MW battery project at Knockanure, Co. Kerry, got consent in Oct 2025 (Irish Examiner, read 29 Oct 2026); the article doesn't use the name Kilmorna, so the article doesn't name Kilmorna, so the match is by size, place and technology, and its 110 kV against the results' 220 kV is not resolved |
| node | TG594 Fieldstown Extension 2 | list: Timoney (Tipperary); the ECP-2.4 results and its two sibling projects say Finglas. **Settled**: Timoney belongs to an unrelated project (TG433) and looks like a slip |
| reused ref | TG22a Athea (1)a | on a connected list from Aug 2015, first on a contracted list Jun 2020. **Open**: a connected project listed in error, or a re-contracting; nothing found separates them |
| moved | TG24 Knockacummer (1) | ESB's lists carry it Sep 2017 - May 2018, energised 9 Nov 2013; EirGrid's from Dec 2018, connected Jul 2015; EirGrid's note says TSO to DSO, the opposite of the order the lists show. **Partly settled**: ESB's own name for it is "(Temp)" and a 110 kV cable for its permanent connection was built from 2016, so a temporary ESB connection then a permanent one fits; the two dates both precede the cable and still disagree |
| restated | EirGrid's wind history | the Dec 2018 edition and every later one print the same years up to +100 MW different from the Aug 2018 edition. **Settled**: the size of TG24 |

## Rules, so it doesn't cry wolf

- A **gap** needs more than a year on neither list. A project that left the contracted list
  *long after* it first appeared connected is not an entry: that is a partial connection, the
  contracted list keeping the unconnected remainder until the last phase. (The first version of
  this check flagged five projects; four were this, and were removed. The fifth, TG44, was a bug in
  our own flows code, a rename counted as a leave and a join: fixed, and the row disappeared. The
  gap rule stays, but no project triggers it today.)
- Nothing is called an error. Each row says what would settle it (a grid-connection offer, a
  planning file, the publisher saying what changed).
- The ledger is rebuilt with every report, so a row disappears when a publisher fixes its list.
  It holds no manual entries; every row is reproducible from the store.

## What it doesn't prove

- That any of these is wrong: only that two sources disagree. TG594 may really connect at
  Timoney with a Dublin site, and TG22a may be a legitimate renaming.
- That the ledger is complete. It reports what the other layers' checks can see; a disagreement
  on a project outside the matched samples (non-wind outcomes, the 2008-11 lists) is invisible.

## To bring it into the project

New: `src/iegrid/errata.py`, `tests/test_errata.py` (9 tests), and layer 8's `resolutions.py`. Changed: `report.py` (`errata`
built from the grid, connected and pace sections), the site's `Dashboard.tsx` and `report.ts`,
a fixture and a variant. Needs layers 1, 2 and the map's conflicts, and layer 6 for the "moved" row; it adds
no detection of its own except the gap rule and the cross-publisher match, which reads EirGrid's
"switched from a TSO to a DSO" note out of its own editions rather than having it typed in.
