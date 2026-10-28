import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

// The weekly report written by `uv run python -m iegrid.report` (src/iegrid/report.py).
// The site only reads it: every number on the page comes from here.

export type Project = { ref: string; name: string; mw: number };

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
  where: { generation_placed_share: number; counties: { county: string; gw: number }[] };
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
];

export function newestReportFile(dir: string = REPORTS): string {
  const names = readdirSync(dir).filter((n) => REPORT_NAME.test(n)).sort();
  if (names.length === 0) {
    throw new Error(`No report in ${dir}. Run: uv run python -m iegrid.report`);
  }
  return join(dir, names[names.length - 1]);
}

export function loadReport(dir: string = REPORTS): Report {
  const file = newestReportFile(dir);
  const report = JSON.parse(readFileSync(file, "utf8")) as Report;
  const missing = REQUIRED.filter(([, get]) => get(report) === undefined).map(([k]) => k);
  if (missing.length > 0) {
    throw new Error(
      `${file} is an older report (no ${missing.join(", ")}). Run: uv run python -m iegrid.report`,
    );
  }
  return report;
}
