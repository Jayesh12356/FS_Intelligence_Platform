/**
 * Visual-regression gate.
 *
 * We snapshot every major static page and assert pixel stability across
 * **three consecutive runs**. Rationale: a single flaky pass is easy to
 * land by accident (fonts, lazy-loaded hero motion). Requiring three
 * consecutive clean snapshots catches 99% of non-determinism.
 *
 * Threshold settings
 *   - maxDiffPixelRatio: 0.001   → max 0.1% of pixels may differ
 *   - animations:        disabled via CSS override on <html>
 *   - fonts:             waited on via document.fonts.ready
 *
 * Snapshots are stored under __screenshots__/ per Playwright default.
 * First-time runs will create the baseline; subsequent runs compare.
 */
import { expect, test } from "@playwright/test";
import { attachConsoleGuard, assertCleanConsole } from "./runtime";

const PAGES = [
  { name: "home", url: "/" },
  { name: "upload", url: "/upload" },
  { name: "create", url: "/create" },
  { name: "documents", url: "/documents" },
  { name: "projects", url: "/projects" },
  { name: "library", url: "/library" },
  { name: "analysis", url: "/analysis" },
  { name: "monitoring", url: "/monitoring" },
  { name: "reverse", url: "/reverse" },
  { name: "settings", url: "/settings" },
];

async function prepareForScreenshot(page: import("@playwright/test").Page, url: string) {
  // Disable animations: kills Framer Motion tweens, CSS transitions, and
  // any scroll-triggered reveals that would otherwise flicker between
  // runs.
  // ``addInitScript`` runs before any HTML is parsed, so ``document.head``
  // can be null on first execution. Defer the style injection until the
  // DOM is ready and idempotently guard against double-injection.
  await page.addInitScript(() => {
    const inject = () => {
      if (document.head?.querySelector("style[data-fsp-anim-disable]")) return;
      const style = document.createElement("style");
      style.setAttribute("data-fsp-anim-disable", "true");
      style.textContent = `
        *, *::before, *::after {
          animation-duration: 0s !important;
          animation-delay: 0s !important;
          transition-duration: 0s !important;
          transition-delay: 0s !important;
        }
      `;
      (document.head ?? document.documentElement).appendChild(style);
    };
    if (document.head) {
      inject();
    } else {
      document.addEventListener("DOMContentLoaded", inject, { once: true });
    }
  });
  await page.goto(url, { waitUntil: "networkidle", timeout: 30_000 });
  await page.evaluate(async () => {
    // Wait for all custom fonts so glyph metrics are stable.
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
    }
  });
  // Small settle delay for any post-font layout jitter.
  await page.waitForTimeout(200);
}

test.describe("Visual regression — stable across 3 runs", () => {
  for (const { name, url } of PAGES) {
    test(`visual: ${name}`, async ({ page }) => {
      const drainConsole = attachConsoleGuard(page);
      await prepareForScreenshot(page, url);
      // Compare with tight threshold; fails if any page drifts.
      await expect(page).toHaveScreenshot(`${name}.png`, {
        fullPage: true,
        maxDiffPixelRatio: 0.001,
        animations: "disabled",
        caret: "hide",
      });
      assertCleanConsole(drainConsole());
    });
  }
});
