# Layer: the EirGrid connected lists (risk analysis, 29 Oct 2026)

Written before any code, for the owner to read on return. Nothing here is committed.

## Why this layer

The page's biggest caveat is its own: "'Left' a list means connected, withdrawn or
moved: the contracted lists don't say which." Since 2015, 114 projects (6.4 GW) have left the
EirGrid contracted lists, and the page can't say whether any of them connected. The
store already holds 42 EirGrid connected-list editions from the archive (g3), none of
them read:

| source | editions | as of |
|---|---|---|
| eirgrid.tso_dso_connected_wind | 14 | 2008-12 to 2011-12 |
| eirgrid.tso_connected_wind / nonwind | 6 + 8 | 2015-08 to 2017-05 |
| eirgrid.tso_connected_renewable / nonrenewable | 13 + 1 | 2017-09 to 2022-10 |

Reading them gives three things the project doesn't have:

1. **Left = connected or not.** A project that leaves the contracted list and turns up on
   a connected list connected; one that never turns up within the lists' cover didn't.
2. **Transmission connection dates.** The connected lists print a connection month per
   project, so the transmission side of g5's burn-down (parked: "transmission waits for
   the connected lists") can start.
3. **A check on the contracted lists.** A project on both lists in one edition, or
   connected before it was contracted, is a fault in one of them.

Other candidates, set aside: ESB's 2017-2023 lists (extends distribution history; useful
but doesn't remove a caveat); a forecast of connection dates (spec: not in v1); alerts
or a publishing layer (blocked by the licence).

## What it would build

- `src/iegrid/connected.py`: reads every 2015-2022 connected edition into
  `connected_row` (ref, name, MEC, connection month, edition), each edition gated like
  the contracted lists: the refs read equal the refs in the page text, and MW within
  TIE_MW of a printed total where the list prints one.
- `flows.py`: each 'left' flow gets an outcome: `connected` (with month), `not connected`
  (left at least two connected editions before the last one, never listed), or
  `unknown` (left after the connected lists stop, Oct 2022).
- The report and page: the g3b chart splits 'left' into connected / not connected /
  unknown; a caveat changes; a transmission burn-down if enough batches are covered.
- Tests for each layout, the gate, and the outcomes.

## Risks, and what each one costs

| # | risk | likelihood | effect | mitigation |
|---|---|---|---|---|
| 1 | **Three layouts** (2015-17 lines, 2017-22 numbered table, 2008-11 names only) | certain | a reader that fits one misreads another | read by ref + month on a line, not by column; gate every edition on refs vs page text; leave 2008-11 out (no refs: name matching across 15 years is the g4 lesson) |
| 2 | **Charts and summary tables on front pages** (the 2022 renewable file opens with a yearly MW table and a chart whose axis text interleaves digits) | certain | numbers read as rows | rows need a ref token; the gate counts refs, so stray numbers can't add rows |
| 3 | **Refs change between lists** (P38A on connected vs TG on contracted, relabels like Pollahoney D74 -> D40d, shared TG44) | likely | a connected project matched to nothing, called "not connected" | match by ref, then by flows' relabel chain, then by name+MEC (region.key, mec_close) only if unique; report the match basis; "not connected" only when none match |
| 4 | **Cover ends Oct 2022** | certain | most recent leavers can't be classed | 'unknown' is its own outcome, never folded into 'not connected'; the page says the cover |
| 5 | **Archived editions misdated** (g3's lesson: stale "as of" labels) | possible | a connection read in the wrong edition | as_of already settled in g3 with witnesses; the connection month is taken from the row, not the edition |
| 6 | **Partial connections** ("Full / Partial" column; phases) | likely | a phase connected, the rest still contracted | outcome per ref; a ref still on the contracted list after a connected listing is reported, not hidden |
| 7 | **TSO -> DSO switches** (Knockacummer note) | rare | "not connected" for a project that connected to the other grid | keep 'not connected' wording to "not on a TSO connected list"; check the 2024+ ESB energised lists by name for leavers (cheap, optional) |
| 8 | **Parser changes touch the contracted path** | low if separate | g2-g8 numbers move | new module and new table; no change to parse.PARSER_VERSION or project_row; the full test suite and the report's numbers compared before/after |
| 9 | **Interfering with the owner's runs or other sessions** | low | a broken store or a racing job | built in a separate git worktree (../ie-grid-pipeline-connected) on a copy of data/; main checkout, its store, data/reports and ops/weekly.sh untouched; no commits; the energy-forecasting repo and its f14 work not touched |
| 10 | **Licence** | as today | republishing connection dates is the same question as the lists | nothing published; same private page |
| 11 | **Time** | medium | half a layer | stop at a clean point: the reader + gate + outcomes are useful alone; the burn-down is the stretch |

## Go / no-go

Go, with these limits: 2015-2022 editions only, outcome per ref with its basis, 'unknown'
kept separate, no change to the contracted parse, nothing committed. If the gate refuses
most editions of a layout, stop there and report which, rather than loosen the gate.

## What happened (29 Oct 2026, built in ../ie-grid-pipeline-connected, nothing committed)

Built: `src/iegrid/connected.py` (reader, gate, loader, classification), the
`connected_row` table in `store.py`, `report._left_outcomes` and a new caveat, a section on
the page, `tests/test_connected.py` (12 tests). Python 292 passed + 1 skipped (the ECP-2.5
file isn't in the worktree's data copy), site 18 passed, a11y clean.

| risk | what actually happened |
|---|---|
| 1 three layouts | Two have refs and are read (2015-16 lines, 2016-22 table); 19 of 19 editions pass. The 2008-11 reports and the non-wind lists have no refs and are left out, as planned. Two editions needed the MEC/installed order sorted out (the lists print the two totals in different orders) |
| 2 front-page tables | Harmless: rows need a ref, and the gate compares the refs at row positions with the rows read |
| 3 refs change | **Happened twice.** Phases connect under a sibling's ref (Athea 1b/2/3/4 under TG22a): 9 projects, now their own outcome. TG22a itself is on a connected list in 2015 but first on a contracted list in 2020: marked unknown, not connected |
| 4 cover ends Oct 2022 | 9 leavers are unknown for that reason; 37 non-wind leavers are unknown because the non-wind connected lists print no refs |
| 5 misdated editions | No sign of it in this layer |
| 6 partial connections | **Happened, and turned out useful.** Every ref that seemed to leave before its connection month first appears on the connected list as a Partial connection in the same edition it leaves the contracted one. So leaving = first energisation, the connected month = completion (16 of 21 within a year) |
| 7 TSO to DSO | Not checked |
| 8 parser changes | None: new module and table; contracted parse, flows.py and the report's other numbers are unchanged |
| 9 interfering | Separate worktree and data copy; the main checkout, its store, data/reports and the f14 work untouched |

A risk the analysis missed: **a ref can leave more than once** (it drops off, comes back,
leaves again: TG34, DG141a, TG25, TG22b). flows.py reports each leave; only the final one
says anything about connecting, so `final_leavers` keeps the last and drops a ref that is
on a newest edition.

Result on today's store: 87 final leavers (4.59 GW): 21 connected by ref (1.03 GW), 9 as
phases of a connected project (0.10 GW), 10 wind projects on no connected list (0.42 GW),
47 unknown (3.04 GW). Open questions: the 10 (Castletownmoor 120 MW, Cronacarkfree 105 MW,
Dooray 55 MW...) may be withdrawn, connected under a name the lists spell differently
(Oweninney/Oweninny), or on the DSO side; TG44 Barnadivane leaves in Dec 2018 but is first
listed connected in Feb 2021. Seven of the 19 editions print no total to tie MW to, so
they rest on the ref gate alone.

Not done: the transmission ECP burn-down (the stretch goal), a weekly-run hook (the
connected lists are archived and no longer posted, so one `python -m iegrid.connected` is
enough), and merging into the main checkout's store.
