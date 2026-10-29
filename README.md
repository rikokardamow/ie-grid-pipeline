# ie-grid-pipeline

Point-in-time record of Ireland's grid connection queue, read from the PDF lists EirGrid and ESB Networks publish: what is waiting, what moved, what is stuck, where, and what became of projects that left the lists.

## Question

How much generation is waiting to connect to Ireland's grid, what moved this week, what is stuck, and where?

## Method

EirGrid (transmission) and ESB Networks (distribution) publish their contracted and energised project lists as PDFs. Each edition is kept as published, with its as-of date, publication time and ingest time. Archived editions back to 2015 come from the Wayback Machine. Each edition is parsed and loaded only if it ties to the list itself: the same refs as the page text and MW within 1 MW of the printed total. Projects are placed in counties from the ECP batch results, a cited table and OpenStreetMap substations. A weekly report (PDF and JSON) is built from the store, and a static page is built from the JSON. Every number on both is checked to come from the report. Details are in `docs/spec.md` and the open questions in `PARKING.md`.

## Result

From the report of 28 Oct 2026, with lists as of 5 Aug 2026 (transmission) and 1 Jul 2026 (distribution):
- 14.69 GW is contracted on transmission (158 projects) and 1.96 GW on distribution (177), not yet energised.
- Three years after its results, ECP-1 had 10% of its distribution MW energised; no later batch passed 1%.
- Offaly holds the most contracted generation (1.68 GW); 95% of generation MW is placed in a county.
- 1.36 GW waits at 39 substations 20 km or more from the all-island 220/275/400 kV network; 7.07 GW is under 2 km from it.

The charts below are from the dashboard (`site/`), each with its finding as the title.

**What is waiting.** Solar is a third of the 16.66 GW signed to connect, and non-wind on transmission grew from 0.40 GW in 2015 to 12.64 GW.

![Contracted GW by technology](docs/img/technology.png)
![Non-wind and wind contracted on transmission, every edition since 2015](docs/img/history.png)

**What moved.** 2025 was the biggest year for joining: 4.28 GW joined the transmission lists and 0.33 GW left.

![GW joining and leaving the transmission lists each year](docs/img/flows.png)

**What's stuck.** At equal age, the older batch connected faster: three years after its results ECP-1 had 10% of its distribution MW energised, and no later batch passed 1%.

![Share of each ECP batch energised three years after its results](docs/img/burndown.png)

**Where.** Each circle is a connection substation, sized by the MW waiting there, on OpenStreetMap's 110 kV and higher lines. 96% of contracted MW is on the map: at a substation OpenStreetMap names, or for a new station, at the existing station its ECP results name, a site a cited source gives (`src/iegrid/data/cited_stations.csv`), or the townland it is named after. The rest is listed under the map.

![Contracted MW by substation on the grid, with distance to the 220/275/400 kV network](docs/img/map.png)
![Contracted GW by county](docs/img/counties.png)

**How fresh.** EirGrid posts its lists about 5 days after their as-of date and ESB about 29, so the distribution side runs a month behind.

![Days from each list's as-of date to its publication](docs/img/freshness.png)


## How to run

    ops/weekly.sh                      # the weekly run: new lists in, report out, page rebuilt, one run_log row

or step by step:

    uv sync
    uv run python -m iegrid.ingest     # fetch every current list into data/
    uv run python -m iegrid.load       # parse what's new, each edition tied to its printed total
    uv run python -m iegrid.counties   # place projects in counties
    uv run python -m iegrid.grid       # OpenStreetMap lines and substations into data/osm (once, or to refresh)
    uv run python -m iegrid.grid --places   # new stations' cited sites and townlands (the weekly run does this too)
    uv run python -m iegrid.report     # the weekly page: data/reports/<date>T<HHMM>.json and .pdf
    uv run pytest

    cd site && pnpm install
    pnpm test                          # every number on the page comes from the report
    pnpm build                         # static export of the newest report into site/out
    pnpm serve                         # http://127.0.0.1:3100, local only
    pnpm a11y                          # WCAG 2.2 AA, both modes, desktop and phone
    pnpm exhibit                       # screenshots into data/exhibits, charts into docs/img

ESB Networks and EirGrid have each confirmed permission to use their lists here. Credit lines stay on every exhibit; see `NOTICE`. The dashboard is served locally (127.0.0.1), not hosted.

## Analysis layers

Built on the record, each with its own README and tests (`docs/layers/`): connected outcomes, delivery pace, target slippage, the ECP funnel, an errata ledger of where the lists disagree, ESB's older lists, an external check against a published wind total, sourced resolutions of open questions, and how much of the queue counts as capacity under the capacity auction's de-rating factors. Start with `docs/layers/00-decisions.md`; `docs/layers/BRING-IN.md` lists the expected numbers.

**What became of the projects that left.** 86 projects (4.53 GW) left the contracted lists for good. 20 are on EirGrid's connected lists by ref and 8 more connected as phases of one; 5 were refused planning or reorganised into a project that did connect, each with its source; 47 stay unknown rather than being read as not connected.

![What became of the projects that left the contracted lists](docs/img/left.png)

**How long the queue would take at past paces.** At the 2023-25 pace the 1.96 GW distribution queue is 19.2 years of delivery, at the fastest three years (2017-19) 7.6; it is not a forecast, because most contracted MW never energises.

![MW energised each year, distribution](docs/img/pace-dso.png)
![MW energised each year, transmission wind](docs/img/pace-tso.png)

**Promises against delivery.** 15 of 16 followable wind projects connected after the target EirGrid first printed, by a median 8 months to first listing.

![Months from the target connection month to completion](docs/img/slippage.png)

**From offer to list.** 29% to 62% of what each ECP batch offered has ever appeared on a contracted list, counted two independent ways.

![Share of each ECP batch's offers found on the lists](docs/img/funnel.png)

**A check against a published total.** The two publishers' wind lists add to 4,410 MW at end-2022 against 4,536 MW published (IEA Wind TCP, from SEAI): 126 MW short, 70 MW of it already there a year earlier.

![Wind on the lists against the published national total](docs/img/external.png)

**How much of it counts as capacity.** Of 11.99 GW of the queue with a published de-rating factor, 2.04 to 2.15 GW counts in the 2030/31 capacity auction: wind about 6% and solar about 4% of their megawatts, batteries 8% to 14% by duration, gas turbines 78%, so gas is 70% to 74% of what counts.

![Share of contracted MW that counts as capacity](docs/img/firm.png)

## How the layers were chosen

Each candidate layer was put through six questions (build, forecast, validate, propose, give, alpha) using the energy-analyst skill, and built only if it added something checkable. Several were tested and not built; `docs/layers/00-decisions.md` records them. The energy-analyst skill is a reference file for Claude Code. It lives in the owner's own `.claude` folder, which is gitignored, so it is not part of this repository. It was written as a distillation, not a model: about 90 trading manuals,
textbooks and journal articles (89 PDFs, 85 unique) on oil, gas, LNG, power and risk were read and reduced to
the rules that cause real errors in energy data work (units, what a benchmark or spread is, how forecasts must
be scored, why macro figures need vintages), with each rule traceable to a source and disagreements between
sources recorded instead of settled. On 27 Oct 2026 it was extended with reference files from about 80 further
PDFs, checked against the project code and the EIA API. Dated market reports were deliberately left out: they are
data to ingest, not knowledge to encode. It is a checklist applied to each idea (the six questions below), not
a source of numbers: every figure on the page still comes from a list or from a source read at its source.

## Layout

    src/iegrid/     ingest, parse, load, report and the layer modules
    src/iegrid/data/ small cited tables (stations, external checks, resolutions)
    tests/          pytest; every edition is tied to its printed total
    site/           Next.js static dashboard; its tests check every number against the report
    ops/            the weekly run
    docs/           spec, layers, charts
    data/           raw PDFs, the store and reports (not in git)

## Licence and data

Code: MIT (`LICENSE`). The lists belong to their publishers and are used with their permission, not under this licence; the raw PDFs and the store are not in the repository. Credits and the OpenStreetMap (ODbL) attribution are in `NOTICE`.
