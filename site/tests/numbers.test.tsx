import { readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import RootLayout, { metadata } from "@/app/layout";
import { Dashboard } from "@/components/Dashboard";
import type { Report } from "@/lib/report";

// The g6 check, for the dashboard: render the page from the report and from two copies
// with every number moved far (checks._perturb); a number on all three pages was
// written by the page, not read from the report. "On the page" is the text, the
// attributes a reader or screen reader gets (title, aria-label, alt, content), and the
// page's metadata; style widths are geometry, not text.

const fixture = (): Report =>
  JSON.parse(readFileSync(join(import.meta.dirname, "fixtures", "report.json"), "utf8"));

function perturb(x: unknown, k: number): unknown {
  if (typeof x === "boolean" || x === null) return x;
  if (typeof x === "number") {
    return Number.isInteger(x) ? x + 1000 * k : x * (1.37 + 0.11 * k) + 111.1 * k;
  }
  if (typeof x === "string") return x.replace(/\d+/g, (d) => String(Number(d) + 1000 * k));
  if (Array.isArray(x)) return x.map((v) => perturb(v, k));
  if (typeof x === "object") {
    return Object.fromEntries(Object.entries(x).map(([key, v]) => [key, perturb(v, k)]));
  }
  return x;
}

const READ_ATTRS = /\b(?:title|aria-label|alt|content)="([^"]*)"/g;

export function pageText(html: string): string {
  const attrs = [...html.matchAll(READ_ATTRS)].map((m) => m[1]);
  // a chart's axis zero is layout, marked data-layout (checks.LAYOUT_NUMBERS does the same)
  const body = html
    .replace(/<style[\s\S]*?<\/style>/g, "")
    .replace(/<text[^>]*data-layout[^>]*>[^<]*<\/text>/g, " ")
    .replace(/<[^>]+>/g, " ");
  return [body, ...attrs, String(metadata.title), String(metadata.description)]
    .join(" ")
    .replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, " ");
}

const page = (report: Report, extra?: React.ReactNode) =>
  renderToStaticMarkup(
    <RootLayout>
      <Dashboard report={report} />
      {extra}
    </RootLayout>,
  );

const numbers = (report: Report, extra?: React.ReactNode) =>
  pageText(page(report, extra)).match(/\d+(?:\.\d+)?/g) ?? [];

function numbersNotFromReport(report: Report, extra?: React.ReactNode): string[] {
  const base = numbers(report, extra);
  const moved = [1, 2].map((k) => new Set(numbers(perturb(report, k) as Report, extra)));
  return [...new Set(base.filter((n) => moved.every((m) => m.has(n))))];
}

// The branches the fixture doesn't take
function variants(): [string, Report][] {
  const later = fixture();
  later.new = { first_report: false, since: "2026-10-21", lists: [{ list: "ESB energised renewable", as_of: "2026-10-01" }] };
  later.warnings = ["esb.dso_contracted_renewable 2026-10-01: MW 1520.4 against a printed 1530.1"];
  const quiet = fixture();
  quiet.new = { first_report: false, since: "2026-10-21", lists: [] };
  const empty = fixture();
  empty.moved.transmission = { ...empty.moved.transmission, editions: [], joined: [], left: [], joined_count: 0, left_count: 0, joined_gw: 0, left_gw: 0 };
  empty.moved.distribution = { ...empty.moved.distribution, editions: [], projects: [], count: 0, mw: 0, newly_listed_count: 0 };
  empty.stuck = { ...empty.stuck, burndown_first: null, burndown_first_at: null, burndown_later_max_at: null, longest_waiting: [] };
  empty.where = { generation_placed_share: null, counties: [] };
  const bare = fixture();
  bare.grid = null;
  bare.freshness = [];
  bare.queue.history = { nonwind: [], wind: [], batches: [] };
  bare.queue.by_technology = { ...bare.queue.by_technology, groups: [], top_share: null };
  bare.moved.by_year = [];
  bare.runs = { count: 0, with_new_files: 0, failed: 0, first: null, latest: [] };
  bare.left_outcomes = null;
  bare.delivery_pace = null;
  bare.target_slippage = null;
  bare.funnel = null;
  bare.errata = null;
  bare.external = null;
  later.runs = { ...later.runs, count: 1, failed: 1, latest: later.runs.latest.slice(0, 1) };
  const fewSlips = fixture();
  if (fewSlips.target_slippage) {
    fewSlips.target_slippage = { ...fewSlips.target_slippage, enough: false, median_to_completion: null, median_to_first: null, rows: fewSlips.target_slippage.rows.slice(0, 3), matched: 3 };
  }
  const noTags = fixture();
  if (noTags.funnel) {
    noTags.funnel.batches = noTags.funnel.batches.map((b) => ({ ...b, share_tagged: null, share_found: null, validation: { ...b.validation, precision: null, recall: null }, status: {} }));
  }
  const noErrata = fixture();
  noErrata.errata = { total: 0, entries: [], kinds: [] };
  const over = fixture();
  if (over.external) {
    over.external.checks[0] = { ...over.external.checks[0], diff_mw: 12.5, diff_pct: 0.003, ours_mw: 4548.5 };
  }
  const noPace = fixture();
  if (noPace.delivery_pace) {
    noPace.delivery_pace.distribution = { ...noPace.delivery_pace.distribution, annual: [], cover: [], fastest: [], backtest: { years: 0, methods: [] } };
    noPace.delivery_pace.transmission_wind.cover = [{ window: 3, from: 2019, to: 2021, pace_mw: 0, years: null }];
  }
  const onePoint = fixture();
  onePoint.queue.history = { ...onePoint.queue.history, nonwind: onePoint.queue.history.nonwind.slice(-1), wind: [] };
  return [
    ["first report", fixture()], ["new lists and a warning", later], ["no new list", quiet],
    ["empty", empty], ["no grid and no series", bare], ["one-point history", onePoint],
    ["no recent pace", noPace],
    ["no tags", noTags],
    ["no errata", noErrata],
    ["total over the published one", over],
    ["few matched targets", fewSlips],
  ];
}

describe("every number on the page comes from the report", () => {
  for (const [name, report] of variants()) {
    it(`finds none written by the page: ${name}`, () => {
      expect(numbersNotFromReport(report)).toEqual([]);
    });
  }

  it("catches a number the page writes in its text", () => {
    expect(numbersNotFromReport(fixture(), <p>13.69 GW</p>)).toContain("13.69");
  });

  it("catches a zero the page writes outside a chart axis", () => {
    expect(numbersNotFromReport(fixture(), <p>0 projects</p>)).toContain("0");
  });

  it("catches a number the page writes in an attribute", () => {
    expect(numbersNotFromReport(fixture(), <span title="42 projects" aria-label="7 GW" />)).toEqual(
      expect.arrayContaining(["42", "7"]),
    );
  });
});

describe("the page says true things when lists are empty", () => {
  const empty = variants().find(([n]) => n === "empty")![1];
  const text = pageText(page(empty));

  it("doesn't claim every one of no projects is confirmed", () => {
    expect(text).toContain("No project joined or left the transmission lists.");
    expect(text).not.toContain("Every one is confirmed");
  });

  it("prints no placed share when there is none, and no dangling comma", () => {
    expect(text).not.toMatch(/\b0% of generation MW placed/);
    expect(text).not.toMatch(/Transmission,\s+(Projects|No|\d+ projects)/);
    expect(text).toContain("No project placed in a county yet");
  });
});
