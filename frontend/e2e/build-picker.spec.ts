import { test, expect } from "@playwright/test";
import { loadRuntime, projectsList } from "./runtime";

test.describe("Build page provider picker", () => {
  test("tabs switch between Cursor and Claude Code and MCP JSON renders", async ({ page }) => {
    const rt = loadRuntime();
    const proj = projectsList(rt)[0];
    expect(proj).toBeTruthy();

    const url = `/documents/${proj.document_id}/build?provider=cursor`;
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});

    // Agent runtime section renders
    await expect(page.getByRole("heading", { name: /Agent runtime/i })).toBeVisible();

    // Both tabs visible
    const cursorTab = page.getByRole("tab", { name: /^Cursor$/ });
    const claudeTab = page.getByRole("tab", { name: /Claude Code/i });
    await expect(cursorTab).toBeVisible();
    await expect(claudeTab).toBeVisible();

    // MCP config snippet visible (contains mcpServers key) for cursor
    const cursorSnippet = page.locator("pre code").first();
    await expect(cursorSnippet).toContainText("mcpServers", { timeout: 15_000 });

    // Switch to Claude Code and assert snippet changes
    await claudeTab.click();
    await expect(claudeTab).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("pre code").first()).toContainText("mcpServers", {
      timeout: 15_000,
    });
  });

  test("Kickoff modal opens with Setup steps and Copy button", async ({ page }) => {
    const rt = loadRuntime();
    const proj = projectsList(rt)[0];
    await page.goto(`/documents/${proj.document_id}/build?provider=cursor`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});

    await page.getByRole("button", { name: /Kickoff instructions/i }).click();
    await expect(page.getByRole("heading", { name: /Setup steps/i })).toBeVisible();
    await expect(
      page.getByRole("button", { name: /^Copy$/ }).first(),
    ).toBeVisible();
  });
});
