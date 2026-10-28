# PARKING.md: decisions and ideas not in the spec yet

Format: `date | item | what would settle it | stone`

- 2026-10-28 | Licence: EirGrid and ESB Networks site terms not checked; republishing parsed project lists may need attribution or permission | read both sites' terms of use; set licence_class like the record | before g7 goes public
- 2026-10-28 | "Late" threshold: no published scheduled energisation dates, so late = age since signed date over LATE_AGE_MONTHS (placeholder 36) until there are enough energised rows to use the batch median | >= 50 energised projects with a signed date | g5
- 2026-10-28 | Region grain: county (from ECP batch PDFs) vs node group (from the lists themselves) | how much contracted MW the batch PDFs cover | g4
- 2026-10-28 | TSO connected (energised) list: not linked from the current EirGrid page; without it, TSO contracted -> energised is only inferred from a project dropping off the list | find a current TSO connected list or ask info@eirgrid.com | g2/g5
- 2026-10-28 | published_at for files without a Last-Modified header: use the first Wayback capture, else ingested_at with vintage_quality = estimated | check headers on the 7 current files | g1
- 2026-10-28 | Data centre / large energy user connections: only aggregate MVA in policy papers (CRU LEU decision, EirGrid data centre process, June 2026) | a per-project or per-quarter published series | after v1
- 2026-10-28 | Northern Ireland (SONI) lists for an all-island view | v1 done and read by someone | after v1
- 2026-10-28 | Repo name and visibility (public on GitHub as rikokardamow/ie-grid-pipeline?) | owner's call | before g7
