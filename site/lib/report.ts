import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

// The weekly report written by `uv run python -m iegrid.report` (src/iegrid/report.py).
// The site only reads it: every number on the page comes from here.

export type Project = { ref: string; name: string; mw: number };

export type Grid = {
  osm_fetched_at: string;
  backbone_kv: number[];
  far_km: number;
  placed_share: number | null;
  placed_gw: number;
  far_gw: number;
  far_nodes: number;
  bands: { label: string; gw: number; nodes: number }[];
  nodes: {
    node: string;
    kv: number;
    lon: number;
    lat: number;
    mw: number;
    projects: number;
    tso_mw: number;
    match: string;
    km_backbone: number | null;
  }[];
  // list node vs ECP-results node (km apart), or a project whose station's other projects are in another county
  conflicts?: {
    ref: string;
    name: string;
    mw: number;
    list_node: string;
    results_node?: string;
    km?: number;
    list_node_county?: string;
    county?: string;
  }[];
  unplaced: { node: string; mw: number }[];
  lines: { kv: number; path: number[][] }[];
  outline: number[][][];
};

export type Point = { as_of: string; gw: number };

export type Cover = { window: number; from: number; to: number; pace_mw: number; years: number | null };

export type Pace = {
  queue_mw: number;
  through: number;
  as_of: string;
  annual: { year: number; mw: number }[];
  cover: Cover[];
  fastest: Cover[];
  backtest: {
    years: number;
    first?: number;
    through?: number;
    methods: { method: string; mae_mw: number; beats_last_year: number }[];
  };
};

export type Report = {
  report_date: string;
  generated_at?: string;
  editions: Record<string, string>;
  new: { first_report: boolean; since?: string; lists: { list: string; as_of: string }[] };
  warnings: string[];
  queue: {
    transmission_gw: number;
    transmission_projects: number;
    interconnector_gw: number;
    distribution_gw: number;
    distribution_projects: number;
    by_technology: {
      transmission_as_of: string | null;
      distribution_as_of: string | null;
      total_gw: number;
      top_share: number | null;
      groups: { group: string; transmission_gw: number; distribution_gw: number }[];
    };
    history: { nonwind: Point[]; wind: Point[]; batches: { batch: string; results: string; label: string }[] };
  };
  moved: {
    transmission: {
      editions: string[];
      joined_count: number;
      joined_gw: number;
      left_count: number;
      left_gw: number;
      all_confirmed: boolean;
      joined: Project[];
      left: Project[];
    };
    distribution: {
      editions: string[];
      count: number;
      mw: number;
      projects: (Project & { list: string; energised_on: string | null; note: string | null })[];
      newly_listed_count: number;
    };
    by_year: { year: number; joined_gw: number; left_gw: number }[];
  };
  stuck: {
    as_of: string;
    large_mw: number;
    at_years: number;
    longest_waiting: (Project & {
      route: string;
      months: number;
      years_part: number;
      months_part: number;
      first_signed: string;
    })[];
    burndown: {
      batch: string;
      results: string;
      age_months: number;
      share_now: number;
      share_at: number | null;
      projects: number;
    }[];
    burndown_first: string | null;
    burndown_first_at: number | null;
    burndown_later_max_at: number | null;
  };
  where: { generation_placed_share: number | null; counties: { county: string; gw: number }[] };
  grid: Grid | null;
  freshness: { list: string; as_of: string; published: string; days: number }[];
  // the queue against the pace at which capacity actually energises (null until the connected lists are in)
  delivery_pace?: {
    distribution: Pace & {
      stability: {
        editions_compared: number;
        first_edition: string | null;
        window_years: number[];
        window_change_mw: number;
        largest_change_mw: number;
        year: number | null;
      };
      vintage_check: { edition: string; through: number; years: number; averaging_beats_last_year: boolean } | null;
    };
    transmission_wind: Pace & {
      restatement: { editions_compared: number; largest_mw: number; last_edition_before: string | null; first_edition_matching: string | null };
    };
  } | null;
  // published target connection months vs when the projects connected (wind, 2015-16 targets)
  target_slippage?: {
    with_target: number;
    matched: number;
    unmatched: number;
    enough: boolean;
    late_to_completion: number;
    over_a_year_to_completion: number;
    late_to_first: number;
    median_to_completion: number | null;
    median_to_first: number | null;
    rows: { ref: string; name: string; mw: number; target: string; first_listed: string; completed: string; to_first: number; to_completion: number }[];
  } | null;
  // the record against a figure published elsewhere
  external?: {
    checks: {
      id: string; label: string; as_of: string; scope: string; source: string; url: string; says: string;
      checked_on: string; notes: string; ours_mw: number; theirs_mw: number; diff_mw: number; diff_pct: number;
      tso_mw: number; tso_edition: string; dso_mw: number; dso_edition: string; dso_rows: number;
      dso_undated_mw: number; ruled_out: string[];
      decomposition: {
        year: number; ours_before_mw: number; theirs_before_mw: number; gap_before_mw: number;
        gap_before_pct: number; ours_added_mw: number; theirs_net_added_mw: number;
        added_shortfall_mw: number; added_source_says: string;
      } | null;
    }[];
  } | null;
  // where a publisher's list disagrees with itself or another publication (regenerated each report)
  errata?: {
    total: number;
    entries: {
      kind: string; ref: string; project: string; says: string; against: string; settles: string;
      answer?: { status: string; verdict: string; detail: string; source: string; url: string; says: string; checked_on: string } | null;
    }[];
    kinds: { kind: string; count: number }[];
  } | null;
  // of the projects each ECP batch offered, how many reach a contracted list, and where they are now
  funnel?: {
    batches: {
      batch: string;
      results: string | null;
      age_months: number | null;
      offered: number;
      offered_mw: number;
      offered_by_name: number;
      found: number;
      found_mw: number;
      found_tso: number;
      tagged: number;
      share_found: number | null;
      share_found_mw: number | null;
      share_tagged: number | null;
      status: Record<string, number>;
      validation: { tagged_matches: number; precision: number | null; tagged_refs: number; recall: number | null };
    }[];
  } | null;
  // what became of the projects that left the contracted lists (null until the connected lists are read)
  left_outcomes?: {
    cover_end: string;
    total: number;
    total_gw: number;
    by_outcome: { outcome: string; count: number; gw: number }[];
    why_unknown: { why: string; count: number }[];
    not_listed: { ref: string; name: string; mw: number; left: string }[];
    energised_at_leave: { refs: number; within_a_year: number };
  } | null;
  runs: {
    count: number;
    with_new_files: number;
    failed: number;
    first: string | null;
    latest: { run: number; started: string; status: string; new_files: number; stored: string[]; parsed: number }[];
  };
  caveats: string[];
};

// Same names as report.REPORT_NAME: <date>[T<HHMM>[SS]].json
export const REPORT_NAME = /^\d{4}-\d{2}-\d{2}(T\d{4}(\d{2})?)?\.json$/;

export const REPORTS = process.env.REPORT_DIR ?? join(process.cwd(), "..", "data", "reports");

// The fields an older report (before g6's review) doesn't have.
const REQUIRED: [string, (r: Report) => unknown][] = [
  ["warnings", (r) => r.warnings],
  ["new.first_report", (r) => r.new?.first_report],
  ["queue.interconnector_gw", (r) => r.queue?.interconnector_gw],
  ["stuck.at_years", (r) => r.stuck?.at_years],
  ["where.generation_placed_share", (r) => r.where?.generation_placed_share],
  ["queue.history", (r) => r.queue?.history],
  ["queue.by_technology", (r) => r.queue?.by_technology],
  ["moved.by_year", (r) => r.moved?.by_year],
  ["grid", (r) => r.grid],
  ["freshness", (r) => r.freshness],
  ["runs.latest", (r) => r.runs?.latest],
];

function reportFiles(dir: string): string[] {
  const names = readdirSync(dir).filter((n) => REPORT_NAME.test(n)).sort();
  if (names.length === 0) {
    throw new Error(`No report in ${dir}. Run: uv run python -m iegrid.report`);
  }
  return names;
}

export function newestReportFile(dir: string = REPORTS): string {
  const names = reportFiles(dir);
  return join(dir, names[names.length - 1]);
}

// Like report.last_report: the newest file that reads as JSON; one cut off mid-write
// is skipped for the one before it.
export function loadReport(dir: string = REPORTS): Report {
  const names = reportFiles(dir);
  let file = "";
  let report: Report | undefined;
  for (const name of names.reverse()) {
    try {
      report = JSON.parse(readFileSync(join(dir, name), "utf8")) as Report;
      file = join(dir, name);
      break;
    } catch {
      continue;
    }
  }
  if (report === undefined) {
    throw new Error(`No readable report in ${dir}. Run: uv run python -m iegrid.report`);
  }
  const missing = REQUIRED.filter(([, get]) => get(report) === undefined).map(([k]) => k);
  if (missing.length > 0) {
    throw new Error(
      `${file} is an older report (no ${missing.join(", ")}). Run: uv run python -m iegrid.report`,
    );
  }
  return report;
}
