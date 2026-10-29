# Reading guide

The working documents use short names and stage codes. This page says what each one is for and how the pieces fit. The README is the summary; this is the map.

## How the pieces fit

```
EirGrid and ESB Networks PDFs  ->  ingest (hash, dates)  ->  load (parse, tie to the printed total)
    -> place (county, substation)  ->  report: data/reports/<date>.json and .pdf
    -> the dashboard (site/, static page built from the JSON)
    -> the README charts (docs/img/, drawn from the same JSON)
```

Every number in the report comes from a query in a module, every number on the page from the report, and every chart from the report. The weekly run (`ops/weekly.sh`) does all of it and writes one row to the run log.

## The documents

| File | What it is |
|---|---|
| `README.md` | What the project is, the results, how to run it |
| `docs/spec.md` | The build specification: what each stage does and the test that says it is done |
| `PARKING.md` | Decisions and ideas not in the spec yet, dated, with what would settle each |
| `NOTICE` | Data credits and permissions |
| `docs/layers/00-decisions.md` | Which analysis layers were built, which were tested and not built, and why |
| `docs/layers/BRING-IN.md` | The expected numbers for each layer, to check a rebuild against |
| `docs/layers/01-…/` to `09-…/` | One folder per layer: a README with the finding, the method and the caveats |
| `docs/layer-connected-risk.md` | What can go wrong when reading EirGrid's connected lists |
| `docs/licence-request-draft.md` | The permission requests as drafted; both publishers have since agreed |

## The stage codes

The spec and PARKING.md number the build stages g1 to g8. In plain words:

| Code | Stage |
|---|---|
| g1 | Fetch and store every current list with its dates |
| g2 | Parse the lists into rows, tied to the printed total |
| g3, g3b | Backfill older editions from the Internet Archive, including the older page layouts |
| g4 | Place projects in counties |
| g5 | Metrics: what moved, how old the queue is, batch burn-down |
| g6 | The weekly report, PDF and JSON |
| g7, g7b | The dashboard, the map and the README charts |
| g8 | The weekly schedule and the run log |

"Stone" in older notes means the same thing as a stage.

## The analysis layers

| Layer | Question |
|---|---|
| 1, connected outcomes | What became of the projects that left the contracted lists? |
| 2, delivery pace | How many MW are energised a year, and how many years of the queue is that? |
| 3, target slippage | Did projects connect by the target month EirGrid first printed? |
| 4, funnel | How much of what each batch offered ever reached a contracted list? |
| 5, errata | Where do the lists disagree with themselves or each other? |
| 6, ESB legacy | What do ESB's 2017 to 2023 lists add? |
| 7, external check | Do the lists add up to a total published elsewhere? |
| 8, resolutions | Sourced answers to open questions from the other layers |
| 9, firm capacity | How much of the queue counts under the capacity auction's de-rating factors? |

Each candidate layer was screened with the same six questions (can it be built from the data held, does it forecast, can it be validated, what would it propose, what does it give the reader, does it add anything checkable) and built only if it did. The screen is recorded in `docs/layers/00-decisions.md`.

## The two kinds of chart

- `docs/img/*.png`, in the README, are drawn with matplotlib by `src/iegrid/readme_charts.py` from the newest report.
- The dashboard draws its own charts in the browser from the same report. `pnpm exhibit` screenshots the served page into `data/exhibits/site/`.

## Data that is not in git

`data/` holds the raw PDFs, the DuckDB store, the OpenStreetMap extract and the reports. It is rebuilt by the pipeline. The lists are used with their publishers' permission and are not redistributed here.
