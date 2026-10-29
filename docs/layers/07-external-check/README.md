# Layer 7: against a published total

**What it adds.** The one check in the project that compares the record with something outside the
lists. Every other check compares a list with itself (rows against printed totals) or with another list
(offers against tags, EirGrid against ESB). This one adds up the two publishers' wind lists and sets the
sum against the national figure published elsewhere.

**Why it's worth having.** It could have failed. If a list were missing, double-counted or misread,
the sum would be far from the published total. It isn't:

| | MW |
|---|---|
| EirGrid connected wind, Oct 2022 list (installed) | 2,117 |
| ESB energised wind, Apr 2023 list, entries dated to end-2022 (MEC) | 2,293 |
| **our total** | **4,410** |
| published: total (net) installed wind, Republic of Ireland, end-2022 | 4,536 |
| difference | **-126 MW (-2.8%)** |

The published figure is from the IEA Wind TCP Annual Report 2022, Ireland chapter, written by the
national team (SEAI): "Total (net) installed wind power capacity 4.536 GW; Total offshore capacity
.0252 GW". The page (`docs/layers/00-decisions.md`) names the source, the words, and the date checked.
Scope and date are matched, not hoped for: total wind including the one offshore farm, at end-2022.

## What the 126 MW is not, and what we don't know

Tested and ruled out:

- **Offshore.** Arklow Bank (DG934, 25.2 MW) is on ESB's energised list, so it is in our total.
- **Installed against MEC.** EirGrid's list prints installed and MEC totals 0.3% apart (2,117 against
  2,111 MW), far short of 2.8%.

Not identified. Candidates, none of them tested: ESB's side is MEC where the published figure is
installed; wind the operators' lists don't carry; end-2022 against two list dates 6 months apart (small:
EirGrid's list added 43 MW in all of 2022). The README does not pick one.

## What it doesn't prove

- That the lists are right. The national figure is SEAI's, which draws on EirGrid and ESB data, so
  agreement was expected. What the check protects is our reading of the lists.
- Anything about solar, batteries or gas: no published total of comparable scope has been verified
  at its source. (Two others, an Oireachtas answer and a Wind Energy Ireland release, could not be read
  at their source, 403 and not found, and are not used.)
- That 2.8% is the typical error: it is one check on one technology at one date.

## How it is built

`src/iegrid/external.py` and `src/iegrid/data/external_checks.csv` (the published figures are data, each
with its source, the words it says and the date checked, like g4's cited counties). The report carries an
`external` section and the page shows it. `tests/test_external.py` (4 tests) checks the CSV, the
arithmetic, which editions are taken (the connected list before the day, ESB's after it) and that no total
is given when either list is missing. It needs layers 1 and 6 (the connected and ESB legacy tables).

To add a check: add a row to the CSV with a source you have read, and a function that computes our side
at the same scope and date. The page picks it up.
