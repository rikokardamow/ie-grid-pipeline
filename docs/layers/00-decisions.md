# Layers: what to build, and why (29 Oct 2026)

Written while the owner was away, before the layers it decides. Rule 1 from the owner:
**a layer must add value to the project.** Rule 2: no interference with other sessions
(everything here is in `../ie-grid-pipeline-connected`, a separate git worktree with its own
copy of `data/`; the main checkout, its store and `data/reports` are untouched; nothing is
committed). Rule 3: each layer has its own README.

The project is a point-in-time record of Ireland's grid connection queue (EirGrid and ESB
Networks lists, 2015-2026). Its core questions are: how much is waiting, what moved, what is
stuck, where. A layer has to sharpen one of those, or answer the question a reader asks next.

## The frame: what a queue is

A queue is a set of **claims** on scarce grid capacity, made cheaply and held at no cost. A
published queue figure adds claims of very different credibility, and the reader's real
question is not "how big" but "how many of these become electrons, how fast, and where do they
drop out". Five numbers answer it, and each is a layer:

1. **size** (the page): how much is claimed;
2. **funnel** (layer 4): how much of what was *offered* ever becomes a claim on a list;
3. **outcome** (layer 1): what became of the claims that left;
4. **pace** (layer 2): how fast capacity actually energises, so the size can be read in years;
5. **promise** (layer 3): how well the published targets held.

Layer 5 is the sixth thing a careful reader needs: where the sources contradict each other.
The project's discipline throughout is the same: a number is only shown with the check that
makes it trustworthy, and where the data can't say, the page says "unknown" instead of
filling the gap.

## The six questions, asked of every idea

The energy-analyst skill (described in the main README) is the checklist for these questions.

1. **Build**: what exactly, from which data?
2. **Forecast**: does it say anything about the future, and is that claim earned?
3. **Validate**: how do we know it's right (a tie, a back-test, a cross-check)?
4. **Propose**: what is the claim we'd put our name to?
5. **Give**: what does the community or energy space get that it doesn't have?
6. **Alpha**: does it generate a trading or investment edge?

The energy-analyst skill sets the bar for 2 and 3 (section 18): a forecast must beat a named
naive benchmark, out of sample, with the benchmark shown and intervals, not a path; MAPE on
levels flatters; and "a queue is not demand" (the skill's note on Europe's data-centre queue).
Its note on vintages ("track vintages, not levels") is what the point-in-time record already
does.

## Honest answer on alpha

**No.** Nothing here predicts a price or has a trading signal. The project can't be read as
alpha, and none of these layers should be sold as it. What it can be is **decision support
with a verified base rate**: for a developer deciding whether a queue position means
anything, a lender or investor judging a contracted-MW claim, a regulator or journalist
asking whether the queue is real. The edge, to the extent there is one, is that the numbers
are checked (every list ties to its own printed total; every number on the page comes from
one report) and nobody else publishes them point-in-time.

## Candidates and verdicts

| # | idea | verdict | why |
|---|---|---|---|
| 1 | **Connected outcomes**: read EirGrid's archived connected lists; say which leavers connected | **built** | removes the page's biggest caveat ("left = connected, withdrawn or moved"). `01-connected-outcomes/` |
| 2 | **Queue bridge**: reconcile each edition-to-edition change into joins, leaves and MEC revisions | **no-go** | tested first: MEC revisions of projects that stay total 0.7 GW over 11 years against 18.7 GW of joins and 5.9 GW of leaves. The bridge would repeat g3b's chart and add a sliver. The finding itself ("the headline is stable; change is churn, not revision") is one sentence on the `02-delivery-pace` README |
| 3 | **Delivery pace and years of cover**: contracted MW divided by what actually energises per year | **build** | the normalisation the skill recommends (days of cover, not absolute levels); a queue's size says little until set against delivery speed. The DSO has 30 years of dated energisations. `02-delivery-pace/` |
| 4 | **Target slippage**: published target connection month vs actual | **build, small** | the only published-promise evidence in the data. Sample is 16 wind projects from 2015-16, so descriptive, bounded, never extrapolated. `03-target-slippage/` |
| 5 | **Queue vs need**: contracted MW against EirGrid's Generation Capacity Statement | **defer** | the primary 2025-34 document wasn't reachable (the eirgrid.ie page 404s, the search returned only secondhand figures); comparing MEC with de-rated capacity without EirGrid's de-rating factors would produce a misleading headline; a queue is not demand. Needs the PDF read properly before it is a layer |
| 6 | **Wind capacity factor and curtailment** from the Smart Grid Dashboard | **out of scope** | a different question (operation, not connection). EirGrid's Open Data Licence would allow it, but it doesn't sharpen any of the project's four questions |
| 7 | **A forecast of energisation dates for the current queue** | **no** | (a) the spec rules it out of v1; (b) the only outcome data is wind 2013-2022, which would be extrapolated onto 12.6 GW of non-wind (solar, batteries, gas) under a different regime: "regional behaviour is not transferable" (skill, section 12); (c) not enough events to beat a benchmark. What layers 2 and 3 give instead are rates and base rates, stated as history |
| 8 | **Dwell-time survival**: how long a signed project stays on a list, for all technologies | **deferred** | leaving the list is not connecting, so the curve would be easy to misread; the burn-down (g5) and the funnel (layer 4) already show the part of it that is about delivery. Worth building only with left-truncation handled (projects already listed when the record began) and a clear label that it is list tenure |

## What we are proposing, and giving

- **Proposition**: the queue's size is not its delivery. Put the contracted MW next to the pace
  at which projects actually energise, and next to what happened to the projects that left.
- **Given to the space**: (1) a connection-outcome table for transmission wind since 2015
  and the cases where it can't say; (2) a years-of-cover figure per grid with the definition
  and the sensitivity to the window; (3) a documented base rate that published connection
  targets slip, with the sample size beside it; (4) all of it reproducible from public PDFs,
  gates stated.
- **Not given**: a forecast, a ranking of projects, an energisation date.

## Order of work and stop rules

1. `01-connected-outcomes` (done; refreshed with an ESB cross-check).
2. `02-delivery-pace`.
3. `03-target-slippage`.
4. Stop. The next candidate (5) needs the primary document, not more code.

A layer is only kept if its README can say in two sentences what it proves and what it
doesn't. If a test of a layer's value fails the way candidate 2 (the queue bridge) did, it's logged
here as a no-go and nothing is built.

## What happened (built 29 Oct 2026, nothing committed)

| layer | state | what it found |
|---|---|---|
| 1 connected outcomes | built, refreshed with an ESB cross-check; counts revised in the fourth session | 86 final leavers (4.53 GW): 20 connected by ref, 1 on the distribution grid, 8 as phases, 2 reorganised, 3 refused, 5 wind on no connected list, 47 unknown. Leaving the contracted list marks first energisation |
| 2 delivery pace | built | distribution queue 1.96 GW = 19.2 years at the 2023-25 pace, 7.6 at the fastest (2017-19). The 3-year window beats last year in 14 of 18 back-test years on the distribution series; on transmission wind it does not, and no averaging claim is made. EirGrid restated its wind history once, +100 MW, Aug-Dec 2018 |
| 3 target slippage | built, small | 15 of 16 followable wind projects connected after their published target (median 8-9.5 months, worst 45) |
| queue bridge | no-go (tested) | revisions are 3% of gross movement |
| queue vs need | deferred | primary document not reachable |

Verification: 304 Python tests pass (1 skipped: an ECP-2.5 file the worktree's data copy lacks),
20 site tests pass, typecheck and lint clean, accessibility clean in both modes at desktop and
phone width, and the page's numbers check (every figure comes from the report) finds nothing the
page writes itself. It did catch the page writing a year into its own wording three times; each
was reworded.

Things that went wrong on the way and what they taught (kept because they are the evidence the
checks are worth having): a ref can leave more than once; a phase connects under a sibling's
ref; a TSO ref can end up on the distribution grid; two printed totals come in different
orders; a back-test premise I had wrong (one spike ties the methods); two miscounts of mine
(7 editions without a printed total, not 5) found by reading my own README against the data.

## Why I stopped building after layer 7 (29 Oct 2026)

Rule 1 is that a layer must add value. Each remaining candidate was put to the same test as the
ones above, and none passes today:

| candidate | verdict | why |
|---|---|---|
| Resolve the 37 non-wind leavers by matching the non-wind connected lists (2015-17, Aug 2022) on name, node and MEC | **not now** | the lists carry no refs, so the match would rest on names alone, the weakest evidence the project accepts (the g4 review's lesson). They stop in Aug 2022, before the solar and battery boom, so they can only describe gas and hydro. The expected gain is a handful of resolved rows in a table that already says "unknown" honestly. Worth doing only with a validation as strong as the wind layer's (leave date against connection date), which needs the rows' dates to the month |
| Transmission non-wind delivery pace | **not possible from the data** | no dated series exists after the connected lists end (Oct 2022). Showing the pre-2022 conventional-plant pace against a solar-and-battery queue would mislead, which is why the page says "blank, not zero" |
| Queue vs need (Generation Capacity Statement) | **needs the primary document** | the eirgrid.ie page 404s and the figures found were secondhand |
| A second external check (solar, batteries, gas) | **needs a source read at its origin** | two candidate figures could not be read at their source (an Oireachtas answer returned 403; a Wind Energy Ireland release was not found). A figure I can't verify doesn't go on the page as validation |
| A forecast of energisation dates | **no** | see row 7 above: wind-only outcome data, a different regime from the queue |

What would change this: a reachable primary document for the capacity statement or for a solar and
battery total; the owner's decisions on the licence and the repo; or four real weekly runs, which
would give layer 2 a vintage record of its own instead of the archive's.

## Next candidates, if more layers are wanted

- Read the primary Generation Capacity Statement / Resource Adequacy Assessment (the PDF
  itself), then decide on "queue vs need" with EirGrid's de-rating factors.
- Read the three older Knockacummer-style cases, if there are any: layer 6 found exactly one
  project on both publishers' lists, so this is closed unless a future edition adds more.
- The non-wind connected lists (2015-17, 2022) print a name, node and MEC but no ref: matching
  by name and MEC could resolve some of the 37 non-wind unknowns. Needs a stricter gate than
  names alone; the g4 review's lesson about same-named places applies.

## Second absence (29 Oct 2026): layers 4 and 5, and the weekly run

| layer | state | what it found |
|---|---|---|
| 4 funnel | built | 29% to 62% of what each ECP batch offered has ever appeared on a contracted list (two independent counts; the match validated against the lists' own batch tags: precision 75-100%, recall 64-93%); almost none of those has left a list: 40 of 40 of ECP-2.3 still contracted at 45 months |
| 5 errata | built | five disagreements between the lists, each reproducible; a first version flagged five "timing" cases of which four were partial connections, so the rule was narrowed to a gap on neither list |
| weekly run | wired | `ops/weekly.sh` now loads the connected lists (idempotent), so the report's new sections need no manual step; a refused edition marks the run "attention" |

## Third session (29 Oct 2026, "continue"): layer 6, and three corrections to my own claims

| layer | state | what it found |
|---|---|---|
| 6 ESB legacy | built | ESB's 23 archived 2017-2023 lists read (3,068 rows, each edition gated). They were the missing early life of the funnel, and reading them tested three claims: the funnel's caveat is small (ECP-1 31% to 34%); layer 2's "at most 10 MW" stability was measured on too few editions (inside the window it holds, but an earlier year moves 147 MW); and the +100 MW "unexplained restatement" is one project, TG24 Knockacummer, that moved between ESB's lists and EirGrid's, against EirGrid's own note on direction |

| 7 external check | built | the two publishers' wind lists add up to 4,410 MW at end-2022 against 4,536 MW published (IEA Wind TCP, from SEAI): 126 MW (2.8%) short, offshore and installed-versus-MEC ruled out, the rest not explained. The only check outside the lists; two other external figures were not used because they could not be read at their source |

Three things I got wrong and fixed, kept because they are the reason to check:
a stability figure measured on four editions that looked steady across eight; an assumption that
`ZG` refs were typos for `DG` (they are a real ESB series); and the date of EirGrid's Knockacummer note
(I had written Feb 2018; read from the editions, it is Dec 2018, the edition where the project first
appears). The last is why the errata layer reads that note out of the PDFs instead of quoting it.

## Fourth session (29 Oct 2026, "answer the open gaps yourself"): layer 8, and a bug in merged work

The open gaps were answered from data and from sources read at the source, and the answers are data
(`src/iegrid/data/resolutions.csv`, layer 8), not prose.

| gap | answer |
|---|---|
| TG44 Barnadivane, 26 months on neither list | **our bug, not the publishers'.** A rename "(formerly ...)" on the same ref was counted as a leave plus a join. `flows.py` now treats a declared rename as one project. Five projects, 405 MW of false leaves, gone |
| TG594, TG485 (which node) | settled: the ECP-2.4 results are right and the contracted list is wrong in both (Finglas; Knockanure, Co. Kerry, by size and place; 110 against 220 kV not resolved) |
| TG24 Knockacummer (which publisher, which date) | partly: a temporary ESB connection then a permanent one fits ESB's "(Temp)" name; the two dates still disagree and nothing says which event each records |
| TG22a (one project or two) | open: nothing found separates a list error from a re-contracting |
| the +100 MW restatement | settled: it is TG24's size |
| 10 wind leavers on no connected list | 5 sourced (3 refused by An Bord Pleanála, 2 reorganised into a connected project); Dooray (55 MW) and Cronacarkfree (105 MW) searched, nothing found; 3 small extensions unresolved |
| the 126 MW external gap | split, not explained: -69.8 MW already there at end-2021, -56.3 MW during 2022 |
| licence, repo name and visibility | no change: ESB's written permission is needed before anything is public. A draft request is for you to send; none was sent |

**The correction to merged work.** The flows fix changes figures already on main (g3b): 2018 left
1.45 to 1.30 GW and joined 1.68 to 1.53 GW; 2019 left 0.27 to 0.07 GW and joined 0.32 to 0.27 GW;
2023 left 1.17 to 1.12 GW and joined 3.03 to 2.98 GW; 2025 is unchanged. Layer 1 now has 86 leavers, not
87. This work was on the branch `fix-declared-renames` and is merged into main.

What the numbers check caught while building these: a hard-coded year in my wording (twice), a
count taken from an array's length instead of the report, and, most seriously, a fallback that
would have printed "100%" and "0%" where a batch had no count. Each is fixed and has a test.

## Fifth session (29 Oct 2026, "next session"): the 37 non-wind unknowns, tested, no build

The idea parked earlier: read the non-wind connected lists (nine editions held: eight from 2015-17, one
non-renewable list updated 1 Aug 2022), which print a name, node and MEC but no ref, and match the 37
non-wind unknown leavers by name and MEC. Prototyped before any code was kept: a leaver matched when its
distinctive name words all appear on a line and a number on that line is within 3% of its MEC.

**Result: 2 of 37 match; 18 cannot be tested and 17 did not match.** Lisdrumdoagh (TG320, 60 MW) is on the 2022 list as
"Lisdrumdoagh LH1 Battery", 60 MW, 30 Jan 2022, and Porterstown (TG336, 30 MW) as "Porterstown PN1 Battery",
27 Feb 2022. Of the other 35, 18 left the contracted list after the last connected non-wind list (Aug 2022),
so no list we hold can say whether they connected. The other 17 left before it and are not on it under a
name and MEC we match; that is weak evidence they never connected (a rename or a changed MEC would also hide
one), so it is not read as an outcome. EirGrid's connected non-renewable file is still the Aug 2022
one on its site (checked 29 Oct 2026 by search; the file page itself was not read), so the evidence does not exist in a
public list yet.

**Decision: no-go.** A parser for nine PDFs to move two projects (90 MW) from "unknown", with 17 more that
can only be read as "not found", would add a store table and a matching gate for little change to the picture. The two matches are recorded here; the outcomes are left
as they are. What would change this: a connected list published after Aug 2022. The weekly run already
checks the page for new files, so the first one is picked up without work, but the non-wind reader would
then be worth building. Parked in `PARKING.md`.

## Sixth session (29 Oct 2026, "a new layer through energy-analyst"): screened, none built

Three candidates were taken through the six questions and tested against the data and sources in hand.
The first rule is that a layer must add value, so a layer that cannot be checked is not built.

| candidate | build | what stopped it |
|---|---|---|
| **Firm capacity of the queue** (contracted MW de-rated by technology, set against EirGrid's Generation Capacity Statement) | would turn 16.7 GW of nameplate into a security-of-supply figure, the number a system planner uses (energy-analyst section 12: capacity is not energy, and storage and solar de-rate very differently) | the de-rating factors are not in the SEM Committee's 2030/31 parameters decision paper or the 2028/29 provisional auction report (both read in full; they say the factors are set by the system operators and sit in the Information Pack, which was not found), and EirGrid's publications index answers 403, so no GCS newer than the 2023-2032 one was listed. Nothing of the two can be read at its source |
| **Signed-to-energised lag, distribution** | an empirical "if I sign today" distribution | ESB's lists carry no signing date (signed month is empty on all 1,837 energised rows and the contracted rows), so one project can be timed |
| **Signed-to-connected lag, transmission wind** | the same, where signing dates exist | 22 projects can be followed (median 71.5 months, quartiles 30 and 93, range 18 to 145), the same wind cohort layer 3 already uses; 22 projects of one technology do not support a rate to quote |

**Decision: no layer this session.** A fourth candidate, a forecast of energisation dates, stays rejected: the
outcome data is wind only and the claim would not be earned (energy-analyst section 18: beat a named benchmark
out of sample).

**What would unlock the best one (firm capacity).** The SEM-O Initial Auction Information Pack for a T-4
auction (the de-rating curves by technology class) and a readable GCS newer than 2023-2032. Both are public; they need fetching by
hand from sem-o.com and eirgrid.ie, then the layer is a small join of the lists' technology column to the
factors with the source and date printed on every figure. Parked in `PARKING.md`.

## Seventh session (29 Oct 2026): firm capacity built (layer 9)

The firm-capacity layer parked in the sixth session was unblocked within the hour: the SEM-O Initial Auction
Information Packs for the 2029/30 and 2030/31 T-4 auctions are public PDFs and could be read at their source
(the search tool found their addresses; saved copies were read with a PDF reader). Their Tables 1, 3 and 5 carry
the factors. Built as `src/iegrid/derating.py`; the finding is in `docs/layers/09-firm-capacity/README.md`:
of 11.99 GW of the queue that has a factor, 2.04 to 2.15 GW counts in the 2030/31 auction, 70% to 74% of it gas.

Decisions made on the way: hybrids, interconnectors, CHP and the smaller technologies get no factor (4.67 GW,
listed, not guessed); battery duration is shown as a range because the lists do not give it; the two auctions are
both shown because the factors fall as more of a technology is contracted. The page's numbers check needed
two changes: a third perturbed copy of the report (with two, a pace value that landed on the same figure in both
copies, twice, passed for a number the page writes) and a rule that a missing share is left out of a sentence
instead of printed as 0%.

## Eighth session (29 Oct 2026): the need figure found, layer 10 built

"Queue vs need" was parked as source-blocked. The blocker was a name and a host: EirGrid's Generation Capacity
Statement is now the All-Island Resource Adequacy Assessment, and its PDFs are served from `www.eirgrid.ie`
(the `cms.eirgrid.ie` index page answers 403, the files redirect to `www`). The 2026-2035 Ireland chapter was
read in full (172 pages). Layer 10 (`docs/layers/10-queue-vs-plan/README.md`) sets the lists against its
assumed new gas and storage and its stated secure-case deficit.

Decisions: the comparison is of the lists with the plan's assumptions, never "need on top of the plan",
because the plan's expected deliveries come from the same projects; the deficit is kept as the document's
words (a chart carries the year-by-year values, and charts are not read); variable generation is left out for
the same reason. It was built in its own worktree and branch (`layer-queue-vs-plan`) and opened as a PR,
because the shared checkout was in use by the README-charts work.

## Ninth session (29 Oct 2026): the interconnector gets a factor

The pack's footnotes settled the open interconnector question. Footnote 2: the Great Britain interconnector
curve "has been adjusted by" an external-market factor (0.65 in 2030/31), so Table 1's printed column is applied
as it stands, to Greenlink (504 MW: 296 MW counts, 59%). Footnote 3: an interconnector to another EU state is
expected to be non-participating in the 2030/31 auction, so Celtic (700 MW, to France) keeps no factor and stays in
the listed remainder. Effect on layer 9: with a factor 11,990 to 12,494 MW; counts 2.04 to 2.15 GW becomes 2.33
to 2.45 GW; gas's share of it 70% to 74% becomes 62% to 65%. Layer 10's deficit share becomes 8% to 17% of the
de-rated queue (it was 9% to 20%). Earlier figures in this file are left as the record of what was said then.

## Tenth session (30 Oct 2026): the next path, screened with the energy-analyst skill

| # | candidate | build / forecast / validate / propose / give / alpha | verdict |
|---|---|---|---|
| 1 | **Score the system operator's own expected delivery** across editions of its adequacy assessment (this one, the 2025-2034 one, the 2023-2032 Generation Capacity Statement): what each edition expected to be built by year, against what was later commissioned (later editions' own "operational" status, the lists) and against a naive benchmark (everything auctioned is delivered in its award year) | builds from three public PDFs already named; evaluates a forecast rather than making one (skill section 18: a named benchmark, out of sample, stability); validates by reading each table at its source and stamping each edition's data-freeze date as a vintage (section 17); proposes whether the plan's delivery assumptions have been over-optimistic; gives the community the first scoring of an official forecast; no alpha | **next** if three comparable editions are readable. With fewer, or tables that changed definition, publish the vintages as a record and claim no skill |
| 2 | Conversion by technology: one table joining burn-down, funnel, pace and slippage into "share of signed MW energised within N years", by technology and publisher | the benchmark layer 1 needs (the plan's assumption is a conversion rate) | build with or just before 1 |
| 3 | Let the record accrue: four weekly runs (g8's done-when), ESB's next list (as of 1 Oct), and any EirGrid connected list after Aug 2022 (then the 37 non-wind unknowns can be read) | nothing to build; the weekly run picks them up | the owner's weekly run |
| 4 | Publish: pick a host and drop the page's noindex | permission is recorded, hosting is the owner's call | owner |
| - | Storage external check against the assessment's storage table | **rejected on the data**: the TSO connected non-renewable list is not held after Aug 2022 and ESB's energised batteries are 74 MW, so scope cannot be matched | rejected |
| - | Variable generation against the assessment | chart-only in the document | rejected (not read from charts) |
| - | Hybrid de-rating | the pack gives no hybrid class | rejected |
| - | A forecast of energisation dates | the outcome data is wind only; the claim would not be earned | rejected again |

