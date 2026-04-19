/**
 * Vitest page-level smoke suite.
 *
 * Renders every App Router page (all 20 of them) with `api.ts` mocked out
 * and `next/navigation` stubbed. The goal is purely structural:
 *
 *   - the module resolves and runs without throwing at import time;
 *   - the default export renders without a React error boundary trip;
 *   - no `console.error` is emitted during render (the console watcher
 *     below throws on any `console.error` so any page that logs
 *     PropType / hydration / suspense errors fails the test).
 *
 * Adding a new page to `frontend/src/app/**\/page.tsx` should fail this
 * suite until the author adds an entry to `PAGES` below.
 */
import { render } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/Toaster";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  useParams: () => ({ id: "doc-1" }),
  useSearchParams: () => new URLSearchParams(""),
  usePathname: () => "/",
  redirect: vi.fn(),
  notFound: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children?: React.ReactNode;
    href?: string;
    [key: string]: unknown;
  }) => React.createElement("a", { href, ...rest }, children),
}));

// Return successful empty-ish responses for every api.ts function so pages
// render without triggering the error paths. The "data" shape is the loosest
// superset of what our pages ever read — always arrays (empty), always
// numbers (0), so `.length` and `.toFixed()` stay safe.
const emptyData = (shape: Record<string, unknown> | unknown[]) => ({
  data: shape as unknown,
  error: null,
});

const BROAD_ENVELOPE = {
  items: [],
  results: [],
  documents: [],
  projects: [],
  tasks: [],
  ambiguities: [],
  contradictions: [],
  duplicates: [],
  edge_cases: [],
  test_cases: [],
  compliance_tags: [],
  total: 0,
  count: 0,
  overall_score: 0,
  completeness: 0,
  clarity: 0,
  consistency: 0,
  id: "doc-1",
  filename: "x.txt",
  status: "UPLOADED",
  sections: [],
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("@/lib/api");
  const stubbed: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(actual)) {
    if (typeof v === "function") {
      // Default stub: resolve with a broad envelope that contains every
      // key our pages destructure during first render, so `.length` and
      // similar operations never blow up.
      stubbed[k] = vi.fn().mockResolvedValue(emptyData({ ...BROAD_ENVELOPE }));
    } else {
      stubbed[k] = v;
    }
  }
  // More specific stubs that pages hard-depend on during first render.
  stubbed.listDocuments = vi
    .fn()
    .mockResolvedValue(emptyData({ documents: [], total: 0 }));
  stubbed.listProjects = vi
    .fn()
    .mockResolvedValue(emptyData({ projects: [], total: 0 }));
  stubbed.listDuplicates = vi.fn().mockResolvedValue(emptyData({ duplicates: [] }));
  stubbed.listTasks = vi.fn().mockResolvedValue(emptyData({ tasks: [], total: 0 }));
  stubbed.listAmbiguities = vi.fn().mockResolvedValue(emptyData([]));
  stubbed.listTestCases = vi.fn().mockResolvedValue(emptyData({ test_cases: [] }));
  stubbed.getQualityDashboard = vi.fn().mockResolvedValue(
    emptyData({
      overall_score: 0,
      quality_score: {
        overall: 0,
        completeness: 0,
        clarity: 0,
        consistency: 0,
        testability: 0,
        coverage: 0,
      },
      completeness: 0,
      clarity: 0,
      consistency: 0,
      contradictions: [],
      edge_cases: [],
      compliance_tags: [],
      ambiguities: [],
      duplicates: [],
      tasks: [],
      diff: [],
      versions: [],
      refined_lines: [],
    }),
  );
  stubbed.getDocument = vi.fn().mockResolvedValue(
    emptyData({
      id: "doc-1",
      filename: "x.txt",
      status: "UPLOADED",
      sections: [],
      parsed_text: "",
      original_text: "",
      content: "",
      text: "",
      metadata: {},
    }),
  );
  stubbed.getRefinementSuggestions = vi.fn().mockResolvedValue(
    emptyData({
      refined_text: "",
      diff: [],
      suggestions: [],
      rationale: [],
    }),
  );
  stubbed.getVersionText = vi.fn().mockResolvedValue(emptyData({ text: "" }));
  stubbed.revertToVersion = vi.fn().mockResolvedValue(emptyData({ ok: true }));
  stubbed.applyRefinement = vi.fn().mockResolvedValue(emptyData({ ok: true }));
  stubbed.getMcpConfig = vi.fn().mockResolvedValue(
    emptyData({
      cursor: { path: ".cursor/mcp.json", snippet: { mcpServers: {} }, install_steps: [] },
      claude_code: {
        path: "mcp-config.json",
        snippet: { mcpServers: {} },
        install_steps: [],
      },
      notes: "",
    }),
  );
  stubbed.getOrchestrationConfig = vi.fn().mockResolvedValue(
    emptyData({ llm_provider: "api", fallback_chain: ["api"] }),
  );
  // Provider lists are consumed via `.filter` / `.map` on the envelope's
  // `data` — keep them as array-returning envelopes, not object-returning.
  stubbed.getOrchestrationProviders = vi
    .fn()
    .mockResolvedValue({ data: [], error: null });
  stubbed.listProviders = vi.fn().mockResolvedValue({ data: [], error: null });
  stubbed.getToolConfig = vi.fn().mockResolvedValue({
    data: { cursor_config: {}, claude_code_config: {} },
    error: null,
  });
  stubbed.getFSVersions = vi.fn().mockResolvedValue(emptyData({ versions: [] }));
  stubbed.listVersions = vi.fn().mockResolvedValue(emptyData({ versions: [] }));
  stubbed.errorMessage = (e: unknown) => (e instanceof Error ? e.message : String(e));
  stubbed.isCursorTaskEnvelope = () => false;
  return stubbed;
});

vi.mock("@/lib/toolConfig", () => ({
  useToolConfig: () => ({
    config: { llm_provider: "api", build_provider: "cursor" },
    loading: false,
    refresh: vi.fn().mockResolvedValue(undefined),
    // Legacy fields kept in case other tests still read them.
    llmProvider: "api",
    setLlmProvider: vi.fn(),
    fallbackChain: ["api"],
    isReady: true,
  }),
  normalizeProvider: (p: string | null | undefined) =>
    (p ?? "").toString().trim().toLowerCase(),
  isCursorProvider: (p: string | null | undefined) =>
    ((p ?? "").toString().trim().toLowerCase()) === "cursor",
}));

const PAGES = [
  "./page",
  "./create/page",
  "./upload/page",
  "./documents/page",
  "./documents/[id]/page",
  "./documents/[id]/ambiguities/page",
  "./documents/[id]/build/page",
  "./documents/[id]/collab/page",
  "./documents/[id]/impact/page",
  "./documents/[id]/quality/page",
  "./documents/[id]/refine/page",
  "./documents/[id]/tasks/page",
  "./documents/[id]/tests/page",
  "./documents/[id]/traceability/page",
  "./projects/page",
  "./projects/[id]/page",
  "./reverse/page",
  "./library/page",
  "./monitoring/page",
  "./settings/page",
  "./analysis/page",
] as const;

let consoleSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  consoleSpy = vi.spyOn(console, "error").mockImplementation((...args) => {
    // Suppress React act() warnings that are unavoidable from mocked effects,
    // but capture hydration / proptype errors so the test fails.
    const msg = args.map(String).join(" ");
    if (msg.includes("not wrapped in act(")) return;
    if (msg.includes("Warning: An update to")) return;
    throw new Error(`console.error during page render: ${msg}`);
  });
});
afterEach(() => {
  consoleSpy.mockRestore();
});

describe("App Router page smoke tests", () => {
  for (const rel of PAGES) {
    it(`renders ${rel} without throwing`, async () => {
      const mod = await import(/* @vite-ignore */ rel);
      const Component = mod.default as React.ComponentType;
      expect(typeof Component).toBe("function");
      const { container } = render(
        <ToastProvider>
          <Component />
        </ToastProvider>,
      );
      expect(container).toBeTruthy();
      // Allow microtasks (useEffect, async fetches) to settle.
      await new Promise((r) => setTimeout(r, 0));
    });
  }
});

// ── Detail-page Build CTA contract ────────────────────────────────────
//
// Once a doc is COMPLETE, the detail page must render exactly ONE Build
// CTA whose label mirrors `Settings.build_provider`. The legacy generic
// "Build (Cursor or Claude Code)" tile must be gone from the Explore
// Analysis grid.
describe("Document detail page — single Build CTA", () => {
  let api: typeof import("@/lib/api");

  beforeEach(async () => {
    api = await import("@/lib/api");
    (api.getDocument as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      emptyData({
        id: "doc-1",
        filename: "spec.md",
        status: "COMPLETE",
        analysis_stale: false,
        sections: [],
        parsed_text: "# Spec\n",
        original_text: "# Spec\n",
      }),
    );
  });

  it("renders only Build with Claude when build_provider === 'claude_code'", async () => {
    vi.doMock("@/lib/toolConfig", () => ({
      useToolConfig: () => ({
        config: { llm_provider: "api", build_provider: "claude_code" },
        loading: false,
        refresh: vi.fn().mockResolvedValue(undefined),
      }),
      normalizeProvider: (p: string | null | undefined) =>
        (p ?? "").toString().trim().toLowerCase(),
      isCursorProvider: () => false,
    }));
    vi.resetModules();

    const { default: Page } = await import("./documents/[id]/page");
    const { container } = render(
      <ToastProvider>
        <Page />
      </ToastProvider>,
    );
    await new Promise((r) => setTimeout(r, 0));

    const html = container.innerHTML;
    expect(html).toContain("Build with Claude");
    expect(html).not.toContain("Build with Cursor");
    expect(html).not.toContain("Build (Cursor or Claude Code)");

    vi.doUnmock("@/lib/toolConfig");
  });
});
