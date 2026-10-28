import { copyFileSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadReport, newestReportFile } from "@/lib/report";

const fixture = join(import.meta.dirname, "fixtures", "report.json");

describe("loadReport", () => {
  it("reads the newest <date>[T<HHMM>].json", () => {
    const dir = mkdtempSync(join(tmpdir(), "reports-"));
    for (const n of ["2026-10-21.json", "2026-10-28.json", "2026-10-28T1946.json"]) {
      copyFileSync(fixture, join(dir, n));
    }
    writeFileSync(join(dir, "notes.json"), "{}");
    writeFileSync(join(dir, "2026-10-29-draft.json"), "{}");
    expect(newestReportFile(dir)).toBe(join(dir, "2026-10-28T1946.json"));
    expect(loadReport(dir).queue.transmission_projects).toBeGreaterThan(0);
  });

  it("skips a newest file that is cut off, for the one before it", () => {
    const dir = mkdtempSync(join(tmpdir(), "reports-"));
    copyFileSync(fixture, join(dir, "2026-10-21.json"));
    writeFileSync(join(dir, "2026-10-28T1200.json"), '{"report_date": "2026-10-');
    expect(loadReport(dir).report_date).toBe(JSON.parse(readFileSync(fixture, "utf8")).report_date);
  });

  it("refuses an older report rather than drawing a page with gaps", () => {
    const dir = mkdtempSync(join(tmpdir(), "reports-"));
    writeFileSync(join(dir, "2026-10-28.json"), JSON.stringify({ report_date: "2026-10-28", new: [] }));
    expect(() => loadReport(dir)).toThrow(/older report.*iegrid\.report/);
  });

  it("says how to make one when there is none", () => {
    const dir = mkdtempSync(join(tmpdir(), "reports-"));
    expect(() => loadReport(dir)).toThrow(/No report/);
  });
});
