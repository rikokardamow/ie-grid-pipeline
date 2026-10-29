# About the documents

The working documents use stage codes and short names, so here is what they mean.

`docs/spec.md` is the build specification. It numbers the stages g1 to g8: fetch and store the lists (g1), parse them into rows tied to the printed total (g2), backfill older editions from the Internet Archive including the older page layouts (g3, g3b), place projects in counties (g4), compute what moved and how old the queue is (g5), the weekly report (g6), the dashboard, the map and the README charts (g7, g7b), and the weekly schedule with its run log (g8). "Stone" in older notes means the same as a stage. Each stage has a test that says when it is done.

`PARKING.md` holds decisions and ideas not in the spec yet, dated, each with what would settle it. `NOTICE` has the data credits and permissions. `docs/licence-request-draft.md` is the permission request as drafted; both publishers have since agreed.

The analysis layers are in `docs/layers/`, one folder each, numbered 01 to 09, with a README that gives the finding, the method and the caveats. `00-decisions.md` records which layers were built and which were tried and dropped, and `BRING-IN.md` holds the expected numbers so a rebuild can be checked. Each candidate was put through the same questions before being built: can it be made from the data held, does it forecast, can it be validated, what does it give the reader, and does it add anything checkable.

Every number in the report comes from a query in a module, every number on the dashboard comes from the report, and every chart in the README is drawn from the report by `src/iegrid/readme_charts.py`. The dashboard draws its own charts in the browser from the same JSON; `pnpm exhibit` screenshots the served page into `data/exhibits/site/`. The weekly run, `ops/weekly.sh`, does all of it and writes one row to the run log.
