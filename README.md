# ie-grid-pipeline

A record of Ireland's grid connection queue, kept from the PDF lists that EirGrid and ESB Networks publish: how much generation is waiting to connect, what moved, what is stuck, and where.

The two grid companies each publish a list of projects that have signed a connection agreement but are not yet connected, EirGrid for the transmission grid and ESB Networks for the distribution grid. Each new edition replaces the last, so the history disappears unless somebody keeps it. This repository keeps it. Every edition is stored as published with the date it describes, the date it went up and the date it was fetched, and older editions back to 2015 are recovered from the Internet Archive. An edition is only accepted once it ties to itself: the same project references as the page text, and total MW within 1 MW of the printed total.

From that store it builds a weekly report (PDF, JSON and a static web page) and the charts below. It does not forecast anything. The one "years of delivery" figure is a ratio and is labelled as one.

## What the lists say

Report of 29 October 2026, with lists as of 5 August 2026 (transmission) and 1 July 2026 (distribution). Each chart is drawn from the report with `uv run python -m iegrid.readme_charts`.

16.66 GW has signed to connect and is not yet energised. Solar is a third of it.

![Generation contracted to connect, by technology](docs/img/technology.png)

![Contracted capacity on the transmission grid, every list since 2015](docs/img/history.png)

2025 was the biggest year for joining the transmission lists.

![Capacity joining and leaving the transmission lists, by year](docs/img/flows.png)

Compared at the same age, the oldest connection batch connected fastest, and no later batch has passed 1% three years after its results.

![Share of each connection batch energised three years after its results](docs/img/burndown.png)

Each circle below is a connection substation, sized by the MW waiting there, drawn on OpenStreetMap's lines. The blue ones are 20 km or more from the 220, 275 and 400 kV network.

![Contracted capacity by connection substation](docs/img/map.png)

![Contracted generation by county](docs/img/counties.png)

EirGrid posts its lists about five days after the date they describe, ESB Networks about a month, so the distribution side of any weekly report runs a month behind.

![Days from each list's as-of date to its publication](docs/img/freshness.png)

86 projects have left the contracted lists for good. Where a connected list exists it says what happened to them; where it does not, the outcome is left as unknown rather than read as "not connected".

![What became of the projects that left the contracted lists](docs/img/left.png)

Dividing the contracted MW by the MW energised each year gives a sense of scale, not a forecast, because most contracted MW never energises.

![MW energised each year, distribution](docs/img/pace-dso.png)

![MW energised each year, transmission wind](docs/img/pace-tso.png)

Of the wind projects whose target connection month EirGrid printed, 15 of 16 connected after it.

![Months from the target connection month to completion](docs/img/slippage.png)

Between a third and a half of what each connection batch offered has ever appeared on a contracted list, counted two independent ways.

![Share of each connection batch's offers that reached a contracted list](docs/img/funnel.png)

As a check, the two publishers' wind lists add up to within 3% of the national total published for the end of 2022.

![Wind capacity on the lists against the published national total](docs/img/external.png)

Under the capacity auction's de-rating factors, about 2.1 GW of the 12 GW with a published factor counts as firm capacity, and gas turbines make up about 70% of that.

![Share of contracted MW that counts as capacity](docs/img/firm.png)

Against the system operator's own plan: EirGrid and SONI's resource adequacy assessment expects 1,900 MW of new gas and adds 660 MW of storage by 2029, while the contracted lists hold 1,944 MW of gas turbines and 1,789 MW of batteries. Its stated deficit is a fifth or less of what the queue counts for, so how much of the queue gets built matters more than its size.

![The queue against the adequacy assessment's assumptions](docs/img/plan.png)

## Running it

    uv sync
    ops/weekly.sh          # the weekly run: new lists in, report out, page rebuilt

Or step by step:

    uv run python -m iegrid.ingest         # fetch every current list into data/
    uv run python -m iegrid.load           # parse what is new, tied to the printed total
    uv run python -m iegrid.counties       # place projects in counties
    uv run python -m iegrid.grid           # OpenStreetMap lines and substations
    uv run python -m iegrid.report         # data/reports/<date>T<HHMM>.json and .pdf
    uv run python -m iegrid.readme_charts  # the charts above, into docs/img/
    uv run pytest

The dashboard is a static Next.js page built from the report and served locally:

    cd site && pnpm install && pnpm test && pnpm build && pnpm serve

## Layout

`src/iegrid/` is the code: ingest, parse, load, place, report, the charts, and the analysis layers. Small cited tables (stations, external checks, resolutions) live in `src/iegrid/data/`. `tests/` ties every edition to its printed total. `site/` is the dashboard, with tests that check every number on the page against the report. `ops/` is the weekly run. `data/` holds the raw PDFs, the DuckDB store and the reports, and is not in git.

Ten further studies sit on top of the record in `docs/layers/`, each with its own README and tests: what became of the projects that left, delivery pace, target slippage, the offer-to-list funnel, where the lists disagree, ESB's older lists, the external check, sourced answers to open questions, firm capacity, and the queue against the adequacy assessment. `docs/layers/00-decisions.md` says which were built, which were tried and dropped, and why. `docs/README.md` explains the rest of the documents and the stage numbering used in them.

## Data and licence

The code is MIT. The lists belong to their publishers; ESB Networks and EirGrid have each confirmed permission to use them here, credit lines stay on every chart, and the full credits are in `NOTICE`. Grid lines and substations are © OpenStreetMap contributors (ODbL). The raw PDFs and the store are not redistributed.

A few terms, since the lists use them: *contracted* means a signed connection agreement but not yet connected; *energised* means connected and exporting; an *ECP batch* is a group of projects that applied together under the Enduring Connection Policy (ECP-1, ECP-2.1 and so on) and got their offers together; *MEC* is maximum export capacity, the MW a project may export, which is what the lists add up.
