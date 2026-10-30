# Layer 11: scoring the plan

**What it adds.** Layer 10 ended on the claim that how much of the queue gets built matters more than its
size. This layer tests the official view of that. Each edition of EirGrid and SONI's capacity statement prints
the new conventional plant it expects by year, which makes it a dated forecast, and nobody scores it here or, as
far as this record has found, anywhere else. So this layer does.

![New conventional plant expected and arrived](../../img/score.png)

**What it found** (Ireland, rated MW, cumulative from the start of 2024; lists to 5 Aug 2026):

| by the end of | arrived (a floor) | GCS 2022 | GCS 2023 | AIRAA 2025 | AIRAA 2026 | everything awarded, on time |
|---|---|---|---|---|---|---|
| 2024 | 192 | 120 | 330 | | | 230 (GCS 2023) |
| 2025 | 307 | 310 | 530 | 530 | | 1,510 (GCS 2023), 980 (AIRAA 2025) |
| 2026, open | 307 so far | 1,100 | 820 | 820 | 802 | 1,630, 1,100, 1,092 |

- **The operators' haircut earns its keep.** Reading the auctions at face value overstated 2025 by 673 to
  1,203 MW; the two risk-adjusted editions published nearest to it overstated by 223 MW. But 2024 went the other way
  for one of them: GCS 2023 (+138 MW) was further off than the naive reading (+38 MW).
- **The oldest edition was closest.** GCS 2022 was within 72 MW in 2024 and 3 MW in 2025. It then expected 790 MW in
  2026 alone, so that closeness is about to be tested hard.
- **Slippage shows in the revisions.** GCS 2023's 2024 expectation of 330 MW became part of AIRAA 2025's 2025 figure:
  330 + 200 = 530, the same total a year later, with nothing delivered between the two freezes.
- **The next test is live.** To meet their end-2026 figures the editions need 495 to 793 MW more, from a list where
  no gas project of auction size has left since the FlexGen units. This scores itself: the first report after
  the lists pass 31 Dec 2026 marks the year scored.

## The six questions

1. **Build**: four editions' printed tables (`src/iegrid/data/plan_editions.csv`, with pages) against units a later
   edition says are operating, plus gas on ESB's energised list by date.
2. **Forecast**: none of ours. It evaluates someone else's.
3. **Validate**: out of sample only (an edition is scored on years after its data freeze), against a named benchmark
   (everything awarded arrives on time, from the same tables), and a test re-reads each printed line from the PDFs.
4. **Propose**: that the risk-adjusted view is far better than the auctions' face value and has still run ahead of
   delivery in most comparisons.
5. **Give**: a public scorecard of an official adequacy input, updated by the weekly run.
6. **Alpha**: none directly. Late gas matters to anyone exposed to Irish capacity scarcity, but no price is tested here.

## What it doesn't prove

- **That any edition has skill.** Two scored years over three overlapping editions: no significance test is possible,
  and none is claimed. The energy-analyst rule (Diebold-Mariano on a loss series) needs far more years than exist.
- **Exactly what arrived.** Observed is a floor. EirGrid's lists can't date a transmission connection, and a unit can
  connect before it leaves a contracted list. Units are counted only when a later edition says they operate or ESB
  dates them. A unit commissioned in 2025 and not yet recorded would shrink the errors.
- **That the sets match.** Ballymakaily (115 MW, ESB's list) is counted as arrived without proof that any edition
  included it, which favours the editions. The tables' base also differs: AIRAA 2026 prints a cumulative that leaves
  out operating plant, so the 192 MW stated as operating is added back; if Ballymakaily is also left out of its
  base, that edition's 802 MW is really 917 MW.
- **Why plant was late.** Terminations, planning and supply chains all appear in the editions' text; none is attributed.

## Corrections this layer forced

Reading the editions showed Temporary Emergency Generation is "an out of market measure of last resort" (AIRAA 2025-2034,
p.20). Two projects on the lists are named TEG2 (420 MW), and layers 9 and 10 had counted them as gas. They now have
no factor, which removes the near-match of 1,944 MW on the lists against 1,900 MW expected: without them it is 1,524 MW,
0.80 of it. And AIRAA 2026's line "FlexGen ... newly operational as of Q4 2024" settled five leavers layer 1 had as unknown.

## Sources

EirGrid and SONI: *All-Island Generation Capacity Statement 2022-2031* p.47; *Generation Capacity Statement 2023-2032*
p.81; *All-Island Resource Adequacy Assessment 2025-2034* p.81; *2026-2035* pp.87-88. Saved copies are in `data/sources/` (not in git).

*Built with the energy-analyst skill (see the main README).*

## Files

`src/iegrid/plan_score.py`, `src/iegrid/data/plan_editions.csv`, `tests/test_plan_score.py`, the page's "Scoring the plan"
section, `docs/img/score.png`.
