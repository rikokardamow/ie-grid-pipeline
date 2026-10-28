import { readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Dashboard } from "@/components/Dashboard";
import type { Report } from "@/lib/report";

// The g6 check, for the dashboard: render the page from the report and from two copies
// with every number moved far (checks._perturb); a number on all three pages was
// written by the page, not read from the report.

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

const text = (html: string) =>
  html.replace(/<style[\s\S]*?<\/style>/g, "").replace(/<[^>]+>/g, " ").replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, " ");

const numbers = (report: Report) => text(renderToStaticMarkup(<Dashboard report={report} />)).match(/\d+(?:\.\d+)?/g) ?? [];

function numbersNotFromReport(report: Report): string[] {
  const base = numbers(report);
  const moved = [1, 2].map((k) => new Set(numbers(perturb(report, k) as Report)));
  return [...new Set(base.filter((n) => moved.every((m) => m.has(n))))];
}

describe("every number on the page comes from the report", () => {
  it("finds none written by the page", () => {
    expect(numbersNotFromReport(fixture())).toEqual([]);
  });

  it("catches a number the page writes itself", () => {
    const report = fixture();
    const html = (r: Report) =>
      renderToStaticMarkup(
        <>
          <Dashboard report={r} />
          <p>13.69 GW</p>
        </>,
      );
    const base = text(html(report)).match(/\d+(?:\.\d+)?/g) ?? [];
    const moved = [1, 2].map(
      (k) => new Set(text(html(perturb(report, k) as Report)).match(/\d+(?:\.\d+)?/g) ?? []),
    );
    expect(base.filter((n) => moved.every((m) => m.has(n)))).toContain("13.69");
  });
});
