# Layer 6: ESB's 2017-2023 lists, read

**What it adds.** The 23 archived ESB editions from before the current lists (contracted and
energised, wind and non-wind, Sep 2017 to Apr 2023), unread since g3b, now read: 3,068 rows,
each edition gated. It is infrastructure, but it earned its place by testing three of the
project's own claims.

**What it found.**

1. **The funnel's biggest caveat is small.** Layer 4 warned that the early batches' distribution
   side was undercounted, because ESB's current lists begin in 2024 and a project that signed and
   withdrew earlier leaves no trace. With the legacy rows in, ECP-1 goes from 43 to 47 found offers
   (31% to 34%) and ECP-2.1 to 2.5 barely move. The "29% to 62%" range stands.
2. **The pace series is revised more than I first said.** Layer 2 reported that a year's energised
   total moves by at most 10 MW between editions. That was measured on the four 2024-26 editions
   only. Across the eight editions that list both ESB energised files, the pace window's own years
   (2023-25) still move by at most 10 MW, but an earlier year moves by up to **147 MW** (2013).
   Layer 2 now reports both figures, and a back-test on the series *as first printed* (Sep 2017) still
   finds averaging beats last year's value.
3. **That 147 MW is one project, and it explains a puzzle.** TG24 Knockacummer (1), 100 MW,
   is on ESB's lists from Sep 2017 to May 2018 (energised 9 Nov 2013; undated from Dec 2017) and on
   EirGrid's from Dec 2018 (connected Jul 2015). It is the +100 MW that layer 2 had found added to
   EirGrid's wind history "with no reason given". EirGrid's own note says it "switched from a TSO to a
   DSO grid connection": the opposite of the order the lists show, and the two publishers disagree
   by 20 months on when it connected. It is now a row in layer 5.

## How it is read

`src/iegrid/esb_legacy.py`. `uv run python -m iegrid.esb_legacy` loads each edition into
`esb_legacy_row` (re-runs add nothing; the weekly run does the same step). Three layouts, each a
table under a header row, so columns are found by header name. Each edition passes a gate: every
ref at the start of a text line is a row read, and every row read is one. The lists print no total
to tie MW to, so that is all there is to check.

What the gate and the checks around it caught, each with a test:

- **`ZG` refs are real**, not typos for `DG`: `ZG937` "Anarget Wind Farm (1)" sits beside `DG937`
  "(2)", and 202 current-list rows carry `ZG` too. (I first assumed a typo; the data said no.)
- **A ref on two rows is legitimate** (`DG249` "Coomleagh Wind Farm" and its "(extension)", with
  different MEC and gate). The same row twice is accepted only if the page text prints it twice
  (`DG943a` in the Dec 2017 energised non-wind list), then counted once and noted.
- **Cell borders cut through words on some rows** (`DG1814 Temp` | `lederry Windfarm`; `Battery
  Storag` | `e 30.000`). The text line is intact, so those rows are rebuilt from it, accepted only if
  the cells joined without whitespace are exactly the start of the line.
- **A status can be overprinted**: `TG175`'s prints as `DSCOontracted`, "DSO" over "Contracted".
  Read as Contracted only because exactly one known status fits, and noted.

## Why its rows sit in their own table

Dozens of queries select `like '%contracted%'`; legacy editions in `project_row` would have moved
every existing number. The funnel, layer 2's stability check and layer 5 read the table explicitly,
and nothing else sees it.

## What it doesn't prove

- That the legacy lists are complete: it reads what each edition prints.
- Why Knockacummer moved, or which publisher is right about its date: only that they disagree.
- It resolves no new leavers (the only match, DG217, was already resolved).

## To bring it into the project

New: `src/iegrid/esb_legacy.py`, `tests/test_esb_legacy.py` (8 tests). Changed: `store.py` (one new
insert-only table), `weekly.py` (loads it), and layers 2, 4 and 5 read it. A refused edition marks the
weekly run "attention".
