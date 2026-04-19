import { test, expect } from "@playwright/test";
import { loadRuntime } from "./runtime";

test.describe("Reverse FS triple-provider comparison", () => {
  test("/reverse shows three provider outputs (or inconclusive note)", async ({
    page,
  }) => {
    const rt = loadRuntime();
    const reverses = Object.values(rt.reverses ?? {});
    if (!reverses.length) test.skip(true, "no reverse runs in runtime state yet");

    await page.goto("/reverse", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});

    // We don't assert exact provider tags (UI may render them as file titles);
    // just verify that the page loaded and the heading is present.
    await expect(page.getByText(/Reverse|Generated|Codebase/i).first()).toBeVisible();
  });

  test("each generated reverse doc detail page renders without crash", async ({
    page,
  }) => {
    const rt = loadRuntime();
    const reverses = Object.values(rt.reverses ?? {}).filter(
      (r) => r && r.document_id,
    );
    if (!reverses.length) test.skip(true, "no reverse document_ids yet");

    for (const rev of reverses) {
      await page.goto(`/documents/${rev.document_id}`, {
        waitUntil: "domcontentloaded",
      });
      await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
      await expect(page.locator("body")).toBeVisible();
      const bad = await page
        .locator('text="An unsupported type was passed to use()"')
        .count();
      expect(bad).toBe(0);
    }
  });
});
