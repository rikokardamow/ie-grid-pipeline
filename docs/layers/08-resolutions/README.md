# Layer 8: resolutions

**In plain English.** Other layers ended with questions the lists couldn't answer. This layer records the answers found elsewhere, each with its source and the date it was read, so they can be checked.

**What it adds.** Layers 1, 5 and 7 each ended with a list of things the data couldn't explain. This
layer answers them where an answer exists, and keeps each answer as data with its source, the source's
own words and the date it was read, so the page can show "answer found" next to the question and a
reader can check it.

**Why data and not prose.** An answer in a README can't reach the page, can't be tested and goes stale
without anyone noticing. `src/iegrid/data/resolutions.csv` has 11 rows (kind, ref, status, verdict,
detail, source name and URL, what the source says, date read). `resolutions.py` loads them. Only a
**settled** answer changes anything: a leaver with a settled verdict of "refused" or "reorganised" gets
that outcome in layer 1, and an errata row gets its answer. A project whose ref is on a connected list
keeps that outcome whatever a resolution says (tested).

## What it answered

| question | status | answer |
|---|---|---|
| TG44 Barnadivane: 26 months on neither list | **our bug** | a rename on the same ref was counted as a leave and a join; fixed in `flows.py`, test added |
| TG594 Fieldstown Extension 2: Timoney or Finglas | settled | Finglas. Its two sibling projects connect there, and Timoney is TG433's node |
| TG485 Kilmorna: Kinnegad or Knockanure | settled | Knockanure, Co. Kerry (a 170 MW battery project consented Oct 2025, Irish Examiner). Matched by size, place and technology; the article doesn't use the name; 110 against 220 kV unresolved |
| restated wind history (+100 MW) | settled | the size of TG24, which moved between publishers |
| TG24 Knockacummer: which publisher, which date | partly | ESB's "(Temp)" entry then a permanent 110 kV connection fits the order the lists show; the two dates still disagree |
| TG22a Athea: one project or two | open | no record separates a list error from a re-contracting |
| P230 Castletownmoor (120 MW), TG261 and TG301 Carrickaduff | settled: refused | An Bord Pleanála (2017, 2016); Castletownmoor also lost in the High Court |
| TG319, TG22b | settled: reorganised | one 34.15 MW project split and re-numbered; the parts add back exactly, 23.1 MW connected as DG141a |
| TG93 Dooray (55 MW), TG103 Cronacarkfree (105 MW) | unresolved | searched 29 Oct 2026; no record under either name |

The external 126 MW gap isn't in the CSV: it is arithmetic on two printed figures, in `external.py` (layer 7).

## What it changes on the page

- Layer 1: 86 leavers, of which 2 are "reorganised" and 3 "refused" (sourced), 5 still unmatched.
- Layer 5: the ledger has 5 rows, each with an "Answer found" cell (status, verdict, source link, date
  read) or "Not looked into".
- Layer 7: the gap is shown as its two parts.

## The rules it keeps

- A figure is read at its source. Search summaries, a 403 and a 404 are not sources; three candidates
  (an Oireachtas answer, EirGrid's GCS page, a Donegal Live article) were dropped for that reason.
- "Unresolved" is a result. Two projects are recorded as searched-and-not-found rather than guessed.
- A resolution never overrides a list: it can only label an outcome the lists left as unknown.

## What it doesn't prove

- That a news article is right: the answers are as good as their sources. Each row says what the
  source says, so a reader can disagree with the match.
- That the unmatched remainder (42 unknown leavers, 2.71 GW) is explained. This layer reached the ones
  with a public record to find.

## Tests

`tests/test_resolutions.py`: CSV rules (columns, statuses, a source for every settled row), outcome
precedence, ledger answers, the restated row's explanation, the gap-decomposition arithmetic.
