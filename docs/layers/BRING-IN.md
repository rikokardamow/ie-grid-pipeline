# Bringing the layers into the project

Everything described under `docs/layers/` was built in `~/Projects/ie-grid-pipeline-connected`,
a git worktree (branch `layer-connected`) with its own copy of `data/`, then committed on that branch
and fast-forwarded into main (it was at `b94a77c`). A later fix and layer 8 are on the branch
`fix-declared-renames`, now merged into main: see "Layer 8 and the flows fix" at the end. The main checkout's store, `data/reports` and
notebooks were not touched by the build: **the new sections appear only once you run the steps below
against your own store.**

## What changes

| | files |
|---|---|
| new modules | `src/iegrid/connected.py` `delivery.py` `slippage.py` `funnel.py` `errata.py` `esb_legacy.py` `external.py`, and `src/iegrid/data/external_checks.csv` |
| new tests | `tests/test_connected.py` `test_delivery.py` `test_slippage.py` `test_funnel.py` `test_errata.py` `test_esb_legacy.py` `test_external.py` |
| changed | `src/iegrid/store.py` (two new insert-only tables, `connected_row` and `esb_legacy_row`), `report.py` (six optional sections), `weekly.py` (loads both), `tests/test_weekly.py` |
| site | `components/Dashboard.tsx`, `components/SplitBars.tsx` (optional `scaleMax`), `lib/report.ts` (optional fields), `tests/numbers.test.tsx`, `tests/fixtures/report.json` |
| docs | `docs/layers/` (this folder: decisions, seven READMEs), `docs/layer-connected-risk.md` |

Not to bring: anything under the worktree's `data/` (a copy; the main store has its own).

## Why it is safe

- **No existing number moves.** The contracted parse, `flows.py`, `PARSER_VERSION`, the g4/g5
  metrics and every earlier report field are unchanged; the layers read them.
- **The store change is additive**: `create table if not exists` for two tables, no migration.
  ESB's older lists go in their own table, not `project_row`, because dozens of queries select
  `like '%contracted%'` and would have been moved by them.
- **Old reports still render.** The five new report fields are optional on the site: a report
  written before the layers builds the page without those sections (checked: an older report
  builds). The site's own "older report" refusal is unchanged.
- **A failing check hides a section instead of drawing unchecked numbers**: the wind table's
  tie failing puts a warning on the page and drops the pace section; a refused connected
  edition marks the weekly run "attention".

## Steps

1. Read `docs/layers/00-decisions.md`, then the five READMEs (one page each).
2. (Done: committed and merged into main.)
3. In the main checkout:
   ```
   uv run python -m iegrid.connected        # once; the weekly run does this too
   uv run python -m iegrid.esb_legacy       # once; likewise (23 ESB lists from 2017-2023)
   uv run python -m iegrid.grid --places    # only if the map's new-station lookups are stale
   uv run python -m iegrid.report           # writes the report with the new sections
   cd site && pnpm build && pnpm serve
   ```
   (`ops/weekly.sh` does the first, third and fourth steps, plus ingest.)
4. Check against what this build produced:

| check | expected on the store of 29 Oct 2026 |
|---|---|
| `uv run pytest -q` | 334 passed (333 here plus the ECP-2.5 test the worktree's data copy lacked) |
| `pnpm test` in `site/` | 23 passed |
| left the contracted lists | 87 projects, 4.59 GW: 21 connected, 1 on the distribution grid, 8 as phases, 10 wind on no connected list, 47 unknown |
| delivery pace | distribution 1,964 MW = 19.2 years at the 2023-25 pace, 7.6 at 2017-19; transmission wind 2,054 MW = 20.6 years at 2019-21 |
| promise against delivery | 15 of 16 followable wind projects connected after their target; median 8 months to first listing, 9.5 to completion |
| funnel | 29% to 62% of each batch's offers have appeared on a list |
| pace stability | inside the pace window at most 10 MW between editions; up to 147 MW in 2013 |
| where the lists disagree | 6 rows: 2 node, 1 gap, 1 reused ref, 1 moved (TG24), 1 restated |
| against a published total | wind 4,410 MW against 4,536 MW published: 126 MW (2.8%) short |

5. Remove the worktree when done: `git worktree remove ../ie-grid-pipeline-connected`.

## What to decide, or check by hand

- **Licence**: the new sections show list-derived numbers and project names, as the page
  already does. Nothing here changes the position that the page stays private until ESB
  Networks answers (`PARKING.md`).
- **Still open after layer 8**: TG22a (one project or two), TG24's two dates, Dooray and
  Cronacarkfree (nothing found), the 70 MW level difference at end-2021, and the voltage for TG485.
  TG44, TG594, TG485 and the restatement are answered; so are five of the ten unmatched wind projects.

## Layer 8 and the flows fix (branch `fix-declared-renames`, merged into main)

| | files |
|---|---|
| new | `src/iegrid/resolutions.py`, `src/iegrid/data/resolutions.csv`, `tests/test_resolutions.py`, `docs/layers/08-resolutions/README.md` |
| changed | `src/iegrid/flows.py` (declared renames) and `tests/test_flows.py`, `connected.py` (two sourced outcomes), `errata.py` (answers), `external.py` and `external_checks.csv` (year split), `report.py`, the site's `Dashboard.tsx` `report.ts` and tests |

**It moves already-merged numbers** (g3b by year, layer 1's counts): see `00-decisions.md`, fourth
session. No new step is needed beyond the ones above. On this branch's build:

| check | expected |
|---|---|
| `uv run pytest -q` | 341 passed, 1 skipped (the worktree's data copy) |
| `pnpm test` in `site/` | 23 passed |
| left the contracted lists | 86 projects, 4.53 GW: 20 connected, 1 distribution, 8 phases, 2 reorganised, 3 refused, 5 wind unmatched, 47 unknown |
| where the lists disagree | 5 rows: 2 node (settled), 1 reused ref (open), 1 moved (partly), 1 restated (settled) |
| against a published total | -126.1 MW = -69.8 (end-2021) + -56.3 (during 2022) |

## Layer 9: firm capacity (on main)

New: `src/iegrid/derating.py`, `src/iegrid/data/derating.csv`, `tests/test_derating.py`, `docs/layers/09-firm-capacity/README.md`,
the page's firm-capacity section, `docs/img/firm.png`. Changed: `report.py` (one optional field), `site/lib/report.ts`,
`Dashboard.tsx`, `site/tests/numbers.test.tsx` (a third perturbed copy), the fixture. Expected on the 29 Oct store:
`uv run pytest -q` 355 passed; `pnpm test` 24 passed; 11,990 MW of 16,658 MW has a factor; 2.04 to 2.15 GW counts in 2030/31.
The saved packs live in `data/sources/` (not in git); the CSV is what the report reads, so the weekly run needs no download.

## Layer 10: queue vs plan (branch `layer-queue-vs-plan`, PR)

New: `src/iegrid/adequacy.py`, `src/iegrid/data/adequacy.csv`, `tests/test_adequacy.py`, `docs/layers/10-queue-vs-plan/README.md`,
`docs/img/plan.png`, the page section. Changed: `report.py` (one optional field), `site/lib/report.ts`, `Dashboard.tsx`,
`numbers.test.tsx`, the fixture. On the 29 Oct store: gas 1,944 MW against 1,900 MW expected; storage +660 MW (37% of
1,789 MW); stated deficit 9% to 20% of the de-rated queue. The chart is drawn by `readme_charts.py` and shown in the main README.

## Not done, on purpose

Queue vs need (needs the primary EirGrid document), dwell-time survival (leaving a list isn't
connecting), a forecast of energisation dates (the outcome data is wind only). The reasons are
in `00-decisions.md`.
