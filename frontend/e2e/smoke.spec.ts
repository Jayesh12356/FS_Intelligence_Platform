import { test, expect, ConsoleMessage, Page } from "@playwright/test";
import { loadRuntime, projectsList } from "./runtime";

const STATIC_PAGES = [
  "/",
  "/upload",
  "/create",
  "/documents",
  "/projects",
  "/library",
  "/analysis",
  "/monitoring",
  "/reverse",
  "/settings",
];

const DOC_PAGES = [
  "",
  "/ambiguities",
  "/quality",
  "/tasks",
  "/impact",
  "/collab",
  "/traceability",
  "/refine",
  "/tests",
  "/build",
];

interface PageProblem {
  url: string;
  kind: "console" | "response";
  detail: string;
}

async function gatherProblems(page: Page, url: string): Promise<PageProblem[]> {
  const problems: PageProblem[] = [];

  const onConsole = (msg: ConsoleMessage) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (/Failed to load resource/.test(text) && /\/favicon/.test(text)) return;
    if (/Manifest|manifest\.json/.test(text)) return;
    problems.push({ url, kind: "console", detail: text });
  };
  const onResponse = (resp: import("@playwright/test").Response) => {
    const status = resp.status();
    const ru = resp.url();
    if (status >= 500 && !ru.includes("_next/static") && !ru.includes("webpack")) {
      problems.push({ url, kind: "response", detail: `${status} ${ru}` });
    }
    // 4xx on backend API calls is usually a real problem (missing route /
    // wrong method). Two known exceptions: /build-state legitimately 404s
    // when the build hasn't been kicked off, and /ws/* may refuse.
    if (
      status >= 400 &&
      status < 500 &&
      ru.includes("/api/") &&
      !ru.includes("build-state") &&
      !ru.includes("generated-fs") &&
      !ru.includes("/ws/")
    ) {
      problems.push({ url, kind: "response", detail: `${status} ${ru}` });
    }
  };

  page.on("console", onConsole);
  page.on("response", onResponse);

  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
  } catch (err) {
    problems.push({ url, kind: "response", detail: `navigation failed: ${(err as Error).message}` });
  } finally {
    page.off("console", onConsole);
    page.off("response", onResponse);
  }
  return problems;
}

test.describe("Full platform smoke", () => {
  test("every static page renders with no 5xx / unexpected console errors", async ({ page }) => {
    const problems: PageProblem[] = [];
    for (const url of STATIC_PAGES) {
      problems.push(...(await gatherProblems(page, url)));
    }
    if (problems.length) {
      console.log("Static page problems:", JSON.stringify(problems, null, 2));
    }
    expect(problems, JSON.stringify(problems, null, 2)).toHaveLength(0);
  });

  test("every project document page renders for each provider", async ({ page }) => {
    test.setTimeout(300_000);
    const rt = loadRuntime();
    const projects = projectsList(rt);
    expect(projects.length).toBeGreaterThan(0);

    const problems: PageProblem[] = [];
    for (const proj of projects) {
      const base = `/documents/${proj.document_id}`;
      for (const suffix of DOC_PAGES) {
        const url = `${base}${suffix}`;
        problems.push(...(await gatherProblems(page, url)));
      }
      problems.push(...(await gatherProblems(page, `/projects/${proj.project_id}`)));
    }
    if (problems.length) {
      console.log("Document page problems:", JSON.stringify(problems, null, 2));
    }
    expect(problems, JSON.stringify(problems, null, 2)).toHaveLength(0);
  });
});
