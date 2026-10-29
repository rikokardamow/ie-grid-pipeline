# Layer 3: promise against delivery

**What it adds.** When EirGrid printed a target connection month for a wind project, when did
the project connect? One table and one chart; nothing extrapolated.

**Why it's worth having.** It is the only published promise in the data that can be checked
against an outcome. Of the 22 projects whose 2015-16 lists give a target month, 16 can be
followed to a connection: **15 of the 16 connected after their target**, 7 by more than a year,
the worst by 45 months (Barnadivane (1), target Apr 2017, completed Jan 2021). Only Mulreavy
Ext (Meenadreen South (2)) was early (2 months).

The lists don't say whether a target meant first energisation or full export, so both bounds
are shown:

| measured to | late | median |
|---|---|---|
| first connected listing (lower bound; the date is an edition's, so coarse) | 15 of 16 | 8 months |
| completion month (upper bound) | 15 of 16 | 9.5 months |

The conclusion doesn't depend on which one the target meant.

## What it doesn't prove

- **It is 16 wind projects from one cohort** (targets printed in 2015-16, connections 2016-21).
  It is a record of what happened to them, not a rate to apply to the 2026 queue, which is
  mostly solar, batteries and gas under different rules.
- 6 projects with a target can't be followed (still waiting, connected on the distribution
  grid, or spelled differently): the lists can't say, and they are counted, not assumed late.
- No median is given for fewer than 10 matched projects (a unit test checks the refusal).

## To bring it into the project

New: `src/iegrid/slippage.py`, `tests/test_slippage.py` (4 tests). Changed: `report.py`
(`target_slippage`), the site, a fixture. Depends on layer 1 (`connected_row` must be loaded:
`uv run python -m iegrid.connected`). The target months were already in the store from g3b.
