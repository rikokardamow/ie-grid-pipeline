// g7's exhibit: the served page, full length, light and dark, into data/exhibits; and
// each chart on its own, light, into docs/img for the README.
// Run against the served export: pnpm build && pnpm serve, then pnpm exhibit.
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const base = process.env.IEGRID_SITE_URL ?? "http://127.0.0.1:3100";
const root = join(import.meta.dirname, "..", "..");
const out = join(root, "data", "exhibits");
const img = join(root, "docs", "img");
mkdirSync(out, { recursive: true });
mkdirSync(img, { recursive: true });

const browser = await chromium.launch();
for (const colorScheme of ["light", "dark"]) {
  const ctx = await browser.newContext({
    colorScheme, viewport: { width: 1000, height: 900 }, deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  await page.goto(base + "/", { waitUntil: "networkidle" });
  const file = join(out, `g7_dashboard_${colorScheme}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(file);
  if (colorScheme === "light") {
    for (const fig of await page.locator("figure[id^=fig-]").all()) {
      const name = (await fig.getAttribute("id")).replace(/^fig-/, "");
      const f = join(img, `${name}.png`);
      await fig.screenshot({ path: f });
      console.log(f);
    }
  }
  await ctx.close();
}
await browser.close();
