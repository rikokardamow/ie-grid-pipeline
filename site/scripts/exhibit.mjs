// g7's exhibit: the served page, full length, light and dark, written to data/exhibits.
// Run against the served export: pnpm build && pnpm serve, then pnpm exhibit.
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const base = process.env.IEGRID_SITE_URL ?? "http://127.0.0.1:3100";
const out = join(import.meta.dirname, "..", "..", "data", "exhibits");
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
for (const colorScheme of ["light", "dark"]) {
  const ctx = await browser.newContext({ colorScheme, viewport: { width: 1200, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(base + "/", { waitUntil: "networkidle" });
  const file = join(out, `g7_dashboard_${colorScheme}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(file);
  await ctx.close();
}
await browser.close();
