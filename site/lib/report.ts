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
  unplaced: { node: string; mw: number }[];
  lines: { kv: number; path: number[][] }[];
  outline: number[][][];
};

export type Point = { as_of: string; gw: number };

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
  caveats: string[];
};

// Same names as report.REPORT_NAME: <date>[T<HHMM>].json
export const REPORT_NAME = /^\d{4}-\d{2}-\d{2}(T\d{4})?\.json$/;

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
