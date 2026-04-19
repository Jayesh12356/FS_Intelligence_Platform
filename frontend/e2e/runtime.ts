import fs from "node:fs";
import path from "node:path";
import type { ConsoleMessage, Page } from "@playwright/test";

export interface ProjectEntry {
  provider: string;
  name: string;
  project_id: string;
  document_id: string;
  filename: string;
  quality_score: number | null;
  section_count: number | null;
  task_count: number | null;
  build_state_status: string | null;
  notes: string[];
}

export interface ReverseEntry {
  provider: string;
  document_id: string | null;
  section_count: number | null;
  flow_count: number | null;
  quality_score: number | null;
  notes: string[];
}

export interface RuntimeState {
  projects: Record<string, ProjectEntry>;
  reverses: Record<string, ReverseEntry>;
  code_upload_id: string | null;
  phase_status: Record<string, string>;
}

const RUNTIME_PATH = path.join(
  process.cwd(),
  "..",
  "backend",
  "scripts",
  ".e2e_runtime.json",
);

export function loadRuntime(): RuntimeState {
  const raw = fs.readFileSync(RUNTIME_PATH, "utf-8");
  return JSON.parse(raw);
}

export function projectsList(rt: RuntimeState): ProjectEntry[] {
  return Object.values(rt.projects ?? {}).filter(
    (p) => p && p.document_id && p.project_id,
  );
}

// ── Console guard ──────────────────────────────────────────
//
// The perfection loop's NUCLEAR gate requires **zero** browser-side
// errors across every e2e test. Attach this guard at the start of any
// Playwright test and call the returned `assertClean()` before the test
// completes. Any console.error, pageerror, or unhandledrejection between
// the attach and the assert raises a loud failure with the full list of
// offending messages.

export interface ConsoleIncident {
  kind: "console.error" | "pageerror" | "unhandledrejection";
  text: string;
  url: string;
}

const IGNORED_PATTERNS: RegExp[] = [
  /Failed to load resource.*favicon/i,
  /manifest\.json/i,
  // Next.js dev-mode chatter that does not indicate a real bug.
  /\[Fast Refresh\]/i,
  // Known harmless WebSocket reconnection chatter while backend restarts.
  /WebSocket.*closed before the connection is established/i,
];

function isIgnored(text: string): boolean {
  return IGNORED_PATTERNS.some((re) => re.test(text));
}

export function attachConsoleGuard(page: Page): () => ConsoleIncident[] {
  const incidents: ConsoleIncident[] = [];

  const onConsole = (msg: ConsoleMessage) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (isIgnored(text)) return;
    incidents.push({ kind: "console.error", text, url: page.url() });
  };

  const onPageError = (err: Error) => {
    const text = err.message || String(err);
    if (isIgnored(text)) return;
    incidents.push({ kind: "pageerror", text, url: page.url() });
  };

  // Playwright exposes unhandled promise rejections as 'pageerror' in most
  // cases; we also hook the raw `crash` event so a renderer crash becomes
  // an incident rather than an orphan failure.
  const onCrash = () => {
    incidents.push({
      kind: "pageerror",
      text: "page crashed",
      url: page.url(),
    });
  };

  page.on("console", onConsole);
  page.on("pageerror", onPageError);
  page.on("crash", onCrash);

  return () => {
    page.off("console", onConsole);
    page.off("pageerror", onPageError);
    page.off("crash", onCrash);
    return incidents.slice();
  };
}

export function assertCleanConsole(incidents: ConsoleIncident[]): void {
  if (incidents.length === 0) return;
  const rendered = incidents
    .map((i, idx) => `  ${idx + 1}. [${i.kind}] @${i.url}\n     ${i.text}`)
    .join("\n");
  throw new Error(
    `Browser console was not clean: ${incidents.length} incident(s) detected.\n${rendered}`,
  );
}
