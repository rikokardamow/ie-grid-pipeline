# Layer 4: the connection funnel

**In plain English.** The lists only show projects that got far enough to sign. This layer looks one step earlier, at how many of the projects offered a connection ever reached a list, and where they are now.

**What it adds.** The top of the funnel. Layers 1-3 say what happens to projects once they are
on a list; this one says how many of the projects an ECP batch *offered* ever get there, and
where the ones that did are now. It answers the question the g5 review parked ("offer totals per
batch as the denominator"), and it is the one view that joins every other layer.

**Why it's worth having.** A published queue is a survivor set. Of the projects each batch
offered, **29% to 62% have ever appeared on a contracted list** (range over batches and over
the two counts below). And of those that did, almost none has left: all 40 of ECP-2.3's are
still contracted 45 months on, and of the 48 list rows matched to ECP-1's 47 found offers (one
offer matched two), 25 are still contracted 93 months on, 11 are energised on the distribution
grid, 4 are on ESB's earlier lists only, 5 left with an unknown outcome, 2 are gone from the lists
held and 1 connected.

| batch | results | offered | found by matching | counted from tags | match precision / recall |
|---|---|---|---|---|---|
| ECP-1 | Nov 2018 | 139 (2,470 MW) | 47 (34%) | 71 (53%) | 96% / 65% |
| ECP-2.1 | Nov 2020 | 180 (4,919 MW) | 60 (33%) | 59 (35%) | 77% / 78% |
| ECP-2.2 | Nov 2021 | 171 (4,805 MW) | 62 (36%) | 45 (29%) | 75% / 93% |
| ECP-2.3 | Nov 2022 | 98 (4,239 MW) | 41 (42%) | 51 (54%) | 100% / 78% |
| ECP-2.4 | Jan 2024 | 80 (6,067 MW) | 42 (53%) | 46 (62%) | 95% / 85% |
| ECP-2.5 | by Feb 2025 | 79 (5,913 MW) | 30 (38%) | 39 (51%) | 93% / 72% |

The two counts are independent and bracket the answer. ESB's current lists begin in 2024, so a
distribution project that signed and withdrew earlier would leave no trace; layer 6 read ESB's
2017-2023 lists to measure that. The effect is small: ECP-1 gains 4 found offers (31% to 34%) and the
other batches barely move, so the range doesn't depend on it.

## How it is validated

The lists tag each project with its batch ("ECP-2.3" in the processing column). That is ground
truth the matcher never saw, so it measures the matcher:

- **precision**: of matched list rows that carry a batch tag, the share whose tag is this batch.
  75-77% for ECP-2.1 and 2.2 means roughly a quarter of those matches are wrong or re-offers, so
  their "found" shares are, if anything, overstated; 93-100% for the rest.
- **recall**: of list refs tagged with a batch, the share matched to one of its offers: 64-93%.
  Matching is deliberately strict (same name key and an MEC within tolerance), so "found by
  matching" is a lower bound, and the tag count is the check on how low.

## What it doesn't prove

- That the offers not found were *declined*. Some are spelled differently, some are projects the
  lists never carried, and ECP-2.5 (18 months old) has not finished signing.
  It says how many appear on a list, not why the others don't.
- Anything about the GSS rounds (Sep 2025, Mar 2026): no list row carries their tag yet, and the
  single match GSS-2 produced was a name collision. They are left out.
- A rate to apply to a future batch. Three batches are still signing and the early two are
  incomplete.

## To bring it into the project

New: `src/iegrid/funnel.py`, `tests/test_funnel.py` (5 tests). Changed: `report.py` (`funnel`),
the site's `Dashboard.tsx` and `SplitBars.tsx` (an optional `scaleMax`), a fixture and a test
variant. The "where they are now" column uses layer 1's outcomes when the connected layer is
loaded, and shows only the lists' own state when it isn't.
