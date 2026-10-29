# Layer 1: connected outcomes

**What it adds.** For each project that left the contracted lists for good, it says what the
connected lists show: connected, connected as a phase of another project, connected on the
distribution grid, on no connected list, or unknown, with the reason. It replaces the page's
oldest caveat ("'left' means connected, withdrawn or moved: the lists don't say which").

**Why it's worth having.** Until now a project leaving the queue was a dead end: 86 projects
(4.53 GW) have left the contracted lists for good since 2015 and the page couldn't say what became of
any. (It said 87 and 4.59 GW until a bug in `flows.py` was fixed: see "A bug this layer found" below.) The store already held 19 archived EirGrid connected lists that nothing read.

## Result (store of 29 Oct 2026)

| outcome | projects | GW |
|---|---|---|
| connected (its ref is on a TSO connected list) | 20 | 0.98 |
| connected on the distribution grid (its ref is on an ESB energised list) | 1 | 0.01 |
| connected as a phase of a connected project (same name, different ref) | 8 | 0.09 |
| reorganised into a project that connected (sourced: the parts add back exactly) | 2 | 0.05 |
| not connected: planning refused (sourced) | 3 | 0.19 |
| wind, on no connected list, nothing found | 5 | 0.18 |
| unknown | 47 | 3.04 |

The three refused are Castletownmoor (An Bord Pleanála, June 2017, upheld in the High Court) and the two
parts of Carrickaduff (An Bord Pleanála, March 2016). Both answers come from `src/iegrid/data/resolutions.csv`,
with the source, its words, and the date read (layer 8). Dooray (55 MW) and Cronacarkfree (105 MW) are
searched-and-unresolved: no public record was found under either name.

Unknown is 37 non-wind projects (the non-wind connected lists print no refs), 9 that left
within six months of the lists ending (Oct 2022), and 1 whose ref was reused. **Unknown is
never read as "not connected".**

Side finding: leaving the contracted list marks **first energisation**, not completion. The
projects that seemed to leave "before they connected" first appear on the connected list as
a *partial* connection in the same edition (Seecon (1): 5 MW of 105 MW listed May 2017,
complete Aug 2017). For 16 of the 20 matched by ref, leaving and first appearing connected
were within a year.

## How it works

`src/iegrid/connected.py`. `uv run python -m iegrid.connected` reads each archived edition into
the `connected_row` table (re-runs add nothing); the weekly run does the same step, so it needs
no manual run once the layer is in. The report then carries a
`left_outcomes` section and the page shows it under "What moved".

Two layouts carry a ref on every row and are read (2015-16 lines, 2016-22 table). The 2008-11
reports and the non-wind lists have no refs and are left out. Each edition passes a gate before
its rows count:

- every ref at a row's position in the page text is a row read, and every row read is one;
- table rows are numbered 1..N without a gap;
- the rows' installed wind MW and MEC MW match the two totals the list prints, in either order
  (the lists print them in different orders); 7 of the 19 editions print no total, and rest on
  the first two checks only.

All 19 pass. `tests/test_connected.py` (13 tests) covers each layout, each way a gate fails,
every classification rule, and idempotent loading.

## Things the data forced (each is a rule in the code, with a test)

- **A ref can leave more than once** (TG34, DG141a, TG25, TG22b drop off, come back, leave
  again). Only a ref's final leave counts, and one on a newest edition isn't a leaver.
- **Phases connect under a sibling's ref** (Athea 1b, 2, 3, 4 under TG22a). The name match uses
  every name a ref has had ("Garvagh" in the 2017+ table, "Garvagh - Glebe (1a)" in 2015).
- **A ref can be reused** (TG22a: on a connected list in 2013, back on a contracted list in
  2020 as another project): marked unknown.
- **A TSO ref can end up on the distribution grid.** DG217 "Cloghboola (2) Ext" is ESB's
  "Glantaunyalkeen Windfarm", energised Sept 2018. The name rule had called it a phase of
  Cloghboola; the ESB cross-check fixed it, and ranks above the name rule.

## A bug this layer found, in work already merged

TG44 "left" in Dec 2018 and "first appeared connected" 26 months later. Tracing it showed one
continuous project: "Barnadivane (1)" renamed "Carrigdangan (formerly Barnadivine)" on the same ref at
the same 60 MW, which stayed on the contracted list to May 2022 while its first phase (54.3 MW) connected
in Jan 2021. `flows.py` counted the rename as a leave and a join because the key function strips
parentheses, so the old and new names shared no words (and the old name's spelling differs from the
"formerly" anyway). Five projects were counted this way (TG44, TG49, DG1012, TG71, TG282), 405 MW of false
leaves. The rule now: a continuing ref whose new name declares "(formerly ...)" or "(previously ...)" is a
rename, whatever the spelling or MEC. It moves the already-published g3b figures: 2018 left 1.45 to 1.30 GW,
joined 1.68 to 1.53 GW; 2019 left 0.27 to 0.07 GW (TG71 alone was 199 MW), joined 0.32 to 0.27 GW; 2023 left
1.17 to 1.12 GW, joined 3.03 to 2.98 GW. 2025 is unchanged. `tests/test_flows.py` has the cases.

## What it doesn't prove

- It can't say the 5 "on no connected list" projects were withdrawn: they may be spelled
  differently, or connected somewhere the lists don't show. Three are small extensions (Cordal (3),
  two Mulreavy extensions, 19 MW together); two are Dooray and Cronacarkfree.
- Sibling matches rest on a name, not a ref or an MW check: lower confidence, a separate row.
- (TG44 Barnadivane looked like a project that left in Dec 2018 and was first connected in Feb 2021.
  It was a bug in `flows.py`, not a gap: see below.)
- Nothing about non-wind. That's 12.6 GW of the queue and 37 of the 47 unknowns.

## To bring it into the project

New files: `src/iegrid/connected.py`, `tests/test_connected.py`. Changed: `store.py` (the
`connected_row` table), `report.py` (`_left_outcomes`, one caveat), the site's `Dashboard.tsx`,
`report.ts`, a fixture and a test variant. No change to the contracted parse, `flows.py`, or
any existing number.
