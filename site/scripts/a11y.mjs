// WCAG 2.2 AA check of the page, both modes, desktop and phone width (the record's
// scripts/a11y.mjs, for one page). Run against the served export:
// pnpm build && pnpm serve, then pnpm a11y. First time: pnpm exec playwright install chromium
import { AxeBuilder } from "@axe-core/playwright";
import { chromium } from "playwright";

const base = process.env.IEGRID_SITE_URL ?? "http://127.0.0.1:3100";
const pages = ["/"];
const browser = await chromium.launch();
let problems = 0;

for (const colorScheme of ["light", "dark"]) {
  for (const width of [1200, 375]) {
    for (const path of pages) {
      const ctx = await browser.newContext({ colorScheme, viewport: { width, height: 900 } });
      const page = await ctx.newPage();
      await page.goto(base + path, { waitUntil: "networkidle" });
      // open the folded tables too, so their contrast and names are checked
      await page.evaluate(() => document.querySelectorAll("details").forEach((d) => (d.open = true)));
      const result = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      for (const v of result.violations) {
        problems++;
        console.log(`${colorScheme} ${width}px ${path}: ${v.id}: ${v.help}`);
      }
      if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) {
        problems++;
        console.log(`${colorScheme} ${width}px ${path}: page scrolls sideways`);
      }
      await ctx.close();
    }
  }
}
await browser.close();
console.log(problems === 0 ? "No accessibility problems found." : `${problems} problems found.`);
process.exit(problems === 0 ? 0 : 1);
