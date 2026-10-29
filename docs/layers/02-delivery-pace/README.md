# Layer 2: delivery pace and years of cover

**What it adds.** The contracted queue set against the pace at which capacity actually
energises: *years of cover* = contracted MW ÷ the mean annual MW energised over a window of
complete years. It answers the question every reader of a queue number asks next: "so how long
is that?"

**Why it's worth having.** The queue's size says little by itself. 1.96 GW contracted on the
distribution grid is 19.2 years at the 2023-25 pace (102 MW a year), and still 7.6 years at the
fastest three years on record (2017-19, 259 MW a year). It's the normalisation the
energy-analyst skill recommends for stocks (days of cover, not absolute levels).

## Result

| grid | queue | pace, last 3 complete years | years of cover | fastest 3 years |
|---|---|---|---|---|
| distribution (ESB) | 1,964 MW | 102 MW/yr (2023-25) | 19.2 | 7.6 (2017-19) |
| transmission wind (EirGrid) | 2,054 MW | 100 MW/yr (2019-21) | 20.6 | 9.9 (2016-18) |
| transmission non-wind | 12.6 GW | **no series** | blank | blank |

The transmission pace ends in 2021 because the connected lists end in Oct 2022: it is older
than the queue it is set against, and the page says so. Non-wind has no dated series at all,
so it is blank, not zero.

## It is not a forecast, and the one forecast claim it makes is tested

Years of cover is a ratio of two published numbers. It does not say when the queue clears:
most contracted MW never energises. The only predictive claim is the choice of window, and
that is back-tested (rolling origin, each year forecast from earlier years only, benchmark =
last year's value):

- **distribution, 2008-2025 (18 years):** the 3-year mean beat last year's value in 14 of 18
  years, mean error 60 MW against 82 MW. So the headline window is 3 years.
- **transmission wind, 2016-2021 (6 years):** last year's value won (54 MW against 65 MW for
  the 3-year mean), so **no averaging claim is made** there; the page says this.

With 18 and 6 points, and autocorrelated, this is evidence about the window, not a significance
test.

## Checks

- **Stability** (distribution), two figures because one flatters. Inside the pace window (2023-25)
  a year's total differs by at most 10 MW across the 8 editions that list it. Over every year back to
  Sep 2017 it differs by up to 147 MW (2013). (This README first said "at most 10 MW", measured on
  only the four 2024-26 editions; layer 6 read the 2017-2023 editions and showed that was too
  reassuring.) The 147 MW is one project, TG24 Knockacummer, 100 MW, which left ESB's lists and joined
  EirGrid's (layer 5).
- **Vintage check** of the back-test: the same test on the series as first printed in the Sep 2017
  edition (the one a forecaster then had), years 2008-2016. The trailing means still beat last year's
  value (the 3-year mean in 7 of 9 years). Which of the 3- or 5-year mean is best flips between the
  two vintages, 3 MW apart, so the claim is only that averaging beats last year, not which window.
- **Tie** (transmission wind): each year's printed wind addition must equal the change in the
  printed cumulative column, or the table is refused (a unit test breaks it on purpose).
- **Restatement**: EirGrid restated its own history once, by exactly **+100 MW** on every
  cumulative wind figure from 2015, between its Aug and Dec 2018 editions. That is TG24 Knockacummer
  (100 MW), which moved between ESB's lists and EirGrid's in the same period (layers 5 and 6); EirGrid's
  own note says "TSO to DSO", the opposite of the order the lists show. The newest edition's table is
  used throughout.

## What it doesn't prove

- That the queue will energise at any pace, or that the future resembles 2023-25.
- Anything about solar and batteries under the current rules: the long history is wind.
- That ESB's energised list is complete (it lists what is on the list now, not what ever was).
- "Rice" in ESB's technology column is a reciprocating engine (RICE, a 115 MW gas plant at
  Grange Castle with a TG ref), not a parse error. It is in 2025's 200 MW.

## To bring it into the project

New: `src/iegrid/delivery.py`, `tests/test_delivery.py` (7 tests). Changed: `report.py`
(`delivery_pace`, a warning if the wind table fails its tie), the site's `Dashboard.tsx`,
`report.ts`, a fixture and test variants. Needs layer 1's `connected.py` only for the wind
table's raw file (it reads the stored PDF), not for any outcome.
