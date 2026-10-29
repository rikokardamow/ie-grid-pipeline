# Layer 1: connected outcomes

**What it adds.** For each project that left the contracted lists for good, it says what the
connected lists show: connected, connected as a phase of another project, connected on the
distribution grid, on no connected list, or unknown, with the reason. It replaces the page's
oldest caveat ("'left' means connected, withdrawn or moved: the lists don't say which").

**Why it's worth having.** Until now a project leaving the queue was a dead end: 87 projects
(4.59 GW) have left the contracted lists since 2015 and the page couldn't say what became of
any. The store already held 19 archived EirGrid connected lists that nothing read.

## Result (store of 29 Oct 2026)

| outcome | projects | GW |
|---|---|---|
| connected (its ref is on a TSO connected list) | 21 | 1.04 |
| connected on the distribution grid (its ref is on an ESB energised list) | 1 | 0.01 |
| connected as a phase of a connected project (same name, different ref) | 8 | 0.09 |
| wind, on no connected list | 10 | 0.42 |
| unknown | 47 | 3.04 |

Unknown is 37 non-wind projects (the non-wind connected lists print no refs), 9 that left
within six months of the lists ending (Oct 2022), and 1 whose ref was reused. **Unknown is
never read as "not connected".**

Side finding: leaving the contracted list marks **first energisation**, not completion. The
projects that seemed to leave "before they connected" first appear on the connected list as
a *partial* connection in the same edition (Seecon (1): 5 MW of 105 MW listed May 2017,
complete Aug 2017). For 16 of the 21 matched by ref, leaving and first appearing connected
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

## What it doesn't prove

- It can't say the 10 "on no connected list" projects were withdrawn: they may be spelled
  differently (Oweninney / Oweninny), or connected somewhere the lists don't show.
- Sibling matches rest on a name, not a ref or an MW check: lower confidence, a separate row.
- TG44 Barnadivane left the contracted list in Dec 2018 and is first listed connected in Feb
  2021: unexplained.
- Nothing about non-wind. That's 12.6 GW of the queue and 37 of the 47 unknowns.

## To bring it into the project

New files: `src/iegrid/connected.py`, `tests/test_connected.py`. Changed: `store.py` (the
`connected_row` table), `report.py` (`_left_outcomes`, one caveat), the site's `Dashboard.tsx`,
`report.ts`, a fixture and a test variant. No change to the contracted parse, `flows.py`, or
any existing number.
