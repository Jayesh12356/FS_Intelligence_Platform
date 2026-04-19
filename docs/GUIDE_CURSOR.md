# Cursor — Paste-Per-Action Document LLM + Build Agent

Cursor wears two hats in this platform:

1. **Document LLM** — Generate FS, Analyze, Refine, Reverse FS, and
   Impact all run inside your Cursor subscription via the
   **paste-per-action flow**: each click in the Web UI opens a small
   modal with one self-contained mega-prompt. You paste it into a
   fresh Cursor Agent chat (MCP enabled), and the MCP server submits
   the result back to the platform — every part of the flow lives in
   Cursor, never the Direct API.
2. **Build Agent** — The Build page (`/documents/{id}/build`) uses the
   same paste-per-action handoff for Cursor, or a headless Claude
   Code CLI run when `build_provider = claude_code`.

> The backend never issues an LLM call on your behalf when
> `llm_provider = cursor`. Zero tokens are spent on OpenRouter or any
> other Direct-API route. If a pipeline tries to, `orchestrated_call_llm`
> raises — that invariant is verified by
> `backend/scripts/api_smoke.py`.

---

## Prerequisites

| Requirement | How to get it |
|-------------|---------------|
| Cursor IDE | Download from [cursor.com](https://cursor.com) |
| Cursor Pro / Business plan | Required for Agent mode and MCP |
| Platform backend running | `docker compose up` or a local dev server on `http://localhost:8000` |
| Python 3.11+ for MCP server | System Python or virtualenv |
| MCP server dependencies | `cd mcp-server && pip install -r requirements.txt` |

---

## Step 1: Configure the MCP Server in Cursor

> The in-app **Build** page (`/documents/{id}/build`) exposes a
> "Copy MCP config" action that pulls this snippet from
> `GET /api/orchestration/mcp-config`. That endpoint is the single
> source of truth; if the doc drifts from the Build page, the
> endpoint wins.

### Option A: Project-level config (recommended)

Create `.cursor/mcp.json` in your project root (run Cursor from the
repo root so `mcp-server/server.py` resolves):

```json
{
  "mcpServers": {
    "fs-intelligence-platform": {
      "command": "python",
      "args": ["mcp-server/server.py"],
      "env": { "BACKEND_URL": "http://localhost:8000" }
    }
  }
}
```

### Option B: Global config

Add to `~/.cursor/mcp.json` (or `%APPDATA%\Cursor\mcp.json` on
Windows) using absolute paths.

```json
{
  "mcpServers": {
    "fs-intelligence-platform": {
      "command": "python",
      "args": ["C:/path/to/fs_intelligence_platform/mcp-server/server.py"],
      "env": { "BACKEND_URL": "http://localhost:8000" }
    }
  }
}
```

### Verify connection

1. Open Cursor and the project folder.
2. Open the MCP panel (`Ctrl+Shift+P` → "MCP: Show Servers").
3. You should see **fs-intelligence-platform** with a green status.
4. Open the tool list — you should see 95+ tools including
   `claim_cursor_task`, `submit_generate_fs`, `submit_analyze`,
   `submit_refine`, `submit_reverse_fs`, `submit_impact`, and
   `fail_cursor_task`.

---

## Step 2: Select Cursor as your Document LLM

Go to **Settings → Document LLM** and choose **Cursor**. Save. That's
the whole configuration — there is no worker to start, no badge to
keep alive, no session to babysit. Every LLM-backed action in the UI
now routes through a `CursorTask`.

---

## Step 3: The Paste-Per-Action Flow

Any action that needs the Document LLM works the same way:

1. Click the button in the UI (`Generate FS`, `Analyze`, `Refine`,
   `Reverse FS`, upload a new version for `Impact`).
2. The backend mints a `CursorTaskDB` row and returns
   `{mode: "cursor_task", task_id, prompt, mcp_snippet, status}`.
3. A **CursorTaskModal** opens in the browser with:
   - a ready-to-paste mega-prompt,
   - a `Copy prompt` button,
   - a live status banner (`pending` → `claimed` → `done`).
4. You paste the prompt into a **fresh Cursor Agent chat** with the
   MCP server connected.
5. Cursor calls `claim_cursor_task`, does the work inside your
   subscription, and calls the appropriate `submit_*` MCP tool.
6. The modal auto-detects `status = done` and navigates you to the
   result (the new FSDocument, the refined doc, the impact dashboard,
   etc.).

Five supported actions, each with its own `CursorTaskKind`:

| UI action | HTTP endpoint minting the task | MCP submit tool |
|-----------|--------------------------------|-----------------|
| Generate FS | `POST /api/cursor-tasks/generate-fs` *(or `POST /api/idea/generate` via the Create page)* | `submit_generate_fs` |
| Analyze | `POST /api/fs/{id}/analyze` *(or `POST /api/cursor-tasks/analyze/{id}`)* | `submit_analyze` |
| Refine | `POST /api/fs/{id}/refine` *(or `POST /api/cursor-tasks/refine/{id}`)* | `submit_refine` |
| Reverse FS | `POST /api/cursor-tasks/reverse-fs/{upload_id}` | `submit_reverse_fs` |
| Impact | `POST /api/fs/{id}/version` *(or `POST /api/cursor-tasks/impact/{version_id}`)* | `submit_impact` |

If Cursor cannot complete a task, it calls `fail_cursor_task` with a
reason; the modal surfaces the error and lets you retry.

---

## Step 4: Build with Cursor

> Open the page from the **Document detail** screen via the **Build with
> Cursor** CTA. The CTA is shown as the primary button when your saved
> `build_provider = cursor`; the **Build with Claude** button is rendered
> alongside as a secondary so you can override per document. Pick whichever
> matches the agent you want to drive this run.

The Build page (`/documents/{id}/build`) has the following layout:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ← Document   Build agent                  [ Kickoff instructions ]       │
│              spec.md · COMPLETE                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ ✔ Pre-build check passed — ready to ship.                               │
├──────────────────────────────────────────────────────────────────────────┤
│ Stack: [ Next.js + FastAPI ]      Output folder: [ ./output ]           │
├──────────────────────────────────────────────────────────────────────────┤
│ ⚙ Agent runtime                                                          │
│   [ Cursor ]  [ Claude Code ]                                            │
│   ┌────────────────────────────────────────────────────────────────────┐ │
│   │ .cursor/mcp.json            [ Copy MCP config ]                   │ │
│   │ { "mcpServers": { "fs-intelligence-platform": { … } } }           │ │
│   │                                                                    │ │
│   │ Agent prompt                [ Copy agent prompt ]                  │ │
│   │ Use the start_build_loop prompt for document … auto_proceed='true'│ │
│   └────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────┤
│ ☑ Build state                                                            │
│   PENDING / RUNNING / COMPLETE / FAILED · Phase X · Task N / M · …       │
└──────────────────────────────────────────────────────────────────────────┘
```

What each control does:

- **Tabs** — `Cursor` and `Claude Code`. The active tab is driven by the
  URL `?provider=cursor|claude_code` if present, otherwise it falls back
  to `Settings → Build → build_provider`. Switching the tab updates the
  URL and re-renders the snippet/prompt below.
- **Stack / Output folder** — these are passed to
  `GET /api/orchestration/mcp-config?document_id=…&stack=…&output_folder=…`,
  so the snippets and the kickoff prompt always render with the real
  values (no `<document_id>` placeholders).
- **Copy MCP config** — copies the JSON snippet you should drop at
  `.cursor/mcp.json`.
- **Copy agent prompt** — copies the one-line `start_build_loop` prompt
  with `auto_proceed='true'`. Paste it into a fresh Cursor Agent chat;
  Cursor will drive the full task-by-task build using the existing build
  tools (`autonomous_build_from_fs`, `get_task_context`, `register_file`,
  `verify_task_completion`, `post_build_check`, …).
- **Kickoff instructions** (top right) — opens a modal titled
  **Setup steps** with the install steps, the agent prompt/CLI command,
  and a single **Copy** button so you can hand off the kickoff in one
  paste.
- **Build state** — polls `GET /api/fs/{id}/build-state` while a build
  is `RUNNING` (Claude tab only) and surfaces phase / task counters.

When `build_provider = api` the Build CTA is intentionally hidden from
the document detail page — builds are never executed on the Direct API.

---

## Token economy guarantee

The backend will **never** call OpenRouter (or any Direct-API
endpoint) when your active LLM is Cursor:

- `pipeline_call_llm` / `pipeline_call_llm_json` always route through
  `orchestrated_call_llm`.
- `orchestrated_call_llm` consults the provider registry; the Cursor
  provider raises `CursorLLMUnsupported` because there is no
  server-side LLM to call for this provider.
- Every LLM-touching HTTP route branches on `llm_provider` **before**
  the pipeline runs, returning a `CursorTask` envelope instead.
- `backend/scripts/api_smoke.py` asserts zero invocations of the
  Direct LLM client across all three providers; the suite
  `tests/test_orchestration_routing.py` + `tests/test_orchestration_e2e.py`
  pins this guarantee in CI.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| MCP server not visible in Cursor | Check `.cursor/mcp.json` path and that Python is on PATH |
| `Backend request failed` inside a tool | Ensure backend is running on the configured `BACKEND_URL` |
| Modal is stuck on `pending` | Make sure you pasted the prompt into a **new** Cursor Agent chat with MCP connected. The MCP snippet in the modal shows the exact tools Cursor must call |
| Modal shows `failed` | Open the detail panel; Cursor emitted `fail_cursor_task`. Click **Retry** to mint a fresh task |
| Build button is greyed | Set `build_provider` to `cursor` or `claude_code` under Settings → Build |

---

## Appendix — internals of the paste-per-action bridge

- **Backend** — `backend/app/api/cursor_task_router.py`. Mints, polls,
  cancels, claims, submits, fails tasks. A background sweeper
  marks `PENDING`/`CLAIMED` rows older than `CURSOR_TASK_TTL_SEC`
  as `EXPIRED` so the UI stops polling forever.
- **Prompt builders** — `backend/app/orchestration/cursor_prompts.py`
  emits one self-contained markdown prompt per action with strict
  JSON output schemas and embedded MCP tool call instructions.
- **MCP tools** — `mcp-server/tools/cursor_tasks.py` exposes the
  `claim_cursor_task` / `submit_*` / `fail_cursor_task` lifecycle.
- **Frontend modal** — `frontend/src/components/CursorTaskModal.tsx`
  shows the prompt, copies it, polls `GET /api/cursor-tasks/{id}`,
  and navigates on `status = done`.
- **Frontend branching** — the Create, Documents,
  Ambiguities/Analyze, Refine, Impact, and Reverse FS pages all call
  `isCursorTaskEnvelope(res.data)` and open the modal when the
  backend returns a task envelope.
