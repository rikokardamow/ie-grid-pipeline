# ie-grid-pipeline spec

28 oct 2026. p7 in energy-forecasting/docs/career.md. drafted from the sources as they stand today, before any code. same rules as the record: point-in-time, nothing overwritten, a stone ends in a notebook i open.

## the question

which irish grid connection projects are slipping, and where is the contracted capacity stuck? answered every time eirgrid or esb networks publish a new list, in the format a programme review reads: what moved, what didn't, what's late.

reader: programme / grid analyst (aws emea grid role). one page a week they could put in front of a steering group.

## what the sources actually are (checked 28 oct 2026)

all pdf. no xlsx, no api. tables parse cleanly with pdfplumber (checked on the 05/08/2026 tso lists and the q2 2026 dso list).

| source | file | id | columns | cadence | latest |
|---|---|---|---|---|---|
| eirgrid tso contracted wind | TSO-Contracted-Wind-Report-<dd-mm-yyyy>.pdf | TG### | node+kV, ref, name, processing type (ECP-1, ECP-2.x, Non GPA), type, MEC MW, signed date (month) | irregular (17-09-2025, 05-08-2026 in wayback) | 05/08/2026 |
| eirgrid tso contracted non-wind | TSO-Contracted-Non-Wind-Report-<date>.pdf | TG### | same; type incl. Battery, Solar, Solar + Battery, Synchronous Condenser | same | 05/08/2026 |
| esb dso contracted renewable / non-renewable | dso-contracted-*_q<n>_<yyyy>.pdf | DG#### | ref, project, type, MEC_MW, feeding station, designed 110kV station, offer type, status (Contracted / On Hold), conn voltage | quarterly | q2 2026 (correct 01/07/2026) |
| esb dso energised renewable / non-renewable | dso-energised-*.pdf | DG#### | as above, status energised | quarterly | q2 2026 |
| esb dso live connection assessments | dso-live-connection-assessments-*.pdf | - | community-led, capacity held 2 yrs for planning | quarterly | q2 2026 |
| esb renewable summary report | renewable-distribution-connected-generation_summary-report_<date>.pdf | - | totals | quarterly | 01jul26 |
| ecp batch results (joint so) | <yyyy>-Batch-ECP-2.x-Results-*.pdf | TG/DG | applicant, county, coordinates, type, MEC, node, planning ref | per batch, with status updates | ecp-2.4 sep 2025 update, ecp-2.5.1 may 2025 |

what's missing, said plainly:
- no per-project scheduled energisation date in any list. "slippage vs plan" can't be read off a date column. it has to come from status over time (see metrics).
- tso lists give node, not county. county comes from the ecp batch pdfs (have county + coords) or a node->county table i build once.
- no published per-project demand / data centre list. only aggregate MVA in policy papers. data centres stay out of v1 (parking).
- tso connected (energised) lists: not on the current page. older ones exist on cms.eirgrid.ie (e.g. "Connected (Other Types of Generators)"). check before g1.

history: wayback has 2 tso editions (17-09-2025, 05-08-2026) and dso q1-q3 2024. older tso lists under other names on cms (TSO-NonWind-Contracted-31.03.2022.pdf etc). backfill what exists, mark it, and start recording now. history can't be bought later.

## store

same shape as the record's observation table, one row per project per publication:

- `publication`: source, file url, file sha256, as_of (the "correct as of" date printed in the pdf), published_at (first seen: http last-modified or wayback timestamp, else ingested_at with vintage_quality = estimated), ingested_at.
- `project_row`: publication_id, project_ref (TG/DG), name, technology, mec_mw, node / feeding station, voltage, processing type, status, signed month. insert only. a change is a new row under a later publication.
- `project`: ref -> first seen, last seen, county (from batch pdfs or node map), batch.
- raw pdfs kept in data/raw/<source>/<as_of>.pdf, hash in publication. re-ingest of the same file = 0 rows.

duckdb file, no supabase. cheap, local, nothing to secure. the dashboard reads a json export.

licence: eirgrid / esb site terms not checked yet. gate before anything goes public (parking).

## metrics (all from status over time)

- **status transitions** per publication: new contracted, contracted -> energised, contracted -> on hold, dropped (in previous list, not in this one, not energised). count + MW.
- **age**: months since signed date for every still-contracted project. distribution by batch and technology. "late" = older than the batch median at energisation (set once we have enough energised rows; constant LATE_AGE_MONTHS until then).
- **batch burn-down**: per ecp batch, % of offered MW energised / contracted / dropped by months since batch result. this is the closest thing to a programme milestone chart the data supports.
- **capacity by region x year**: contracted and energised MW by county (or node group) and by signed year.
- **what changed since last publication**: the table a steering group reads first.

## stones

| # | stone | done when | nb |
|---|---|---|---|
| g1 | fetch + store: download every current pdf, hash, publication row, raw kept | re-run = 0 new rows; as_of printed in pdf == as_of stored for all 7 files | 00 |
| g2 | parse: pdfplumber -> project_row for tso wind, tso non-wind, dso contracted x2, dso energised x2 | row counts tie to the pdf (hand count 2 pages each); MW totals tie to the esb summary report within 1 MW | 10 |
| g3 | backfill: wayback + cms older editions, same parser, vintage_quality marked | every edition found has a publication row or a written reason it doesn't | - |
| g4 | region: county per project from ecp batch pdfs, node->county table for the rest | >= 95% of contracted MW has a county; the rest listed by name | 20 |
| g5 | metrics: transitions, age, batch burn-down, region x year | transitions between the 2 tso editions checked by hand on 10 projects | 30 |
| g6 | report: 1-page weekly status (what moved / what's stuck / batch burn-down / region) as pdf + json | page reads in 2 minutes; every number on it comes from a query in a module | 40 |
| g7 | dashboard: next.js, record's tokens (site/styles/tokens.css), static export from the json | builds and deploys; same look as the record | - |
| g8 | schedule: weekly job checks both pages for new files, ingests, regenerates report, run log row | 4 weekly runs logged, one with a new file | - |

g1 blocks all. g2 before g3. g4 ‖ g5 after g2. g6 after g5. g7 after g6. g8 last. "weekly" = the job checks weekly; a new list lands quarterly (dso) or irregularly (tso), so most weeks the report says "no new publication" and shows the age clock moving. that's honest, not a gap.

## notebook rules

same as the record's. first cell prints duckdb snapshot date + git sha. notebooks read, never write. logic lives in src/.

## readme (4 sections, for the hiring manager)

question / method / result with the number (e.g. "x GW contracted, y% of ecp-2.1 MW energised after z months") / how to run. if i can't say in one line what it proves, it isn't done.

## not in v1

data centre / demand connections, northern ireland (soni), planning-permission status, any forecast of energisation dates. all in parking.

## budget

2 weekends (career.md). nov-dec 2026, done before christmas. streak gate applies: a week with a missed freeze on the record = no stone that week.
