import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// g7 done-when, "same look as the record": the colour tokens and base styles are the
// record's files, byte for byte, and this site's own CSS defines no colour of its own.

const here = (f: string) => join(import.meta.dirname, "..", "styles", f);
const record = process.env.RECORD_SITE ?? join(process.env.HOME ?? "", "energy-forecasting", "site");

describe("same look as the record", () => {
  for (const f of ["tokens.css", "base.css"]) {
    it.skipIf(!existsSync(join(record, "styles", f)))(`${f} is the record's`, () => {
      expect(readFileSync(here(f), "utf8")).toBe(readFileSync(join(record, "styles", f), "utf8"));
    });
  }

  it("ie.css uses only tokens for colour", () => {
    const css = readFileSync(here("ie.css"), "utf8");
    expect(css.match(/#[0-9a-f]{3,8}\b|rgb\(|hsl\(/gi) ?? []).toEqual([]);
  });
});
