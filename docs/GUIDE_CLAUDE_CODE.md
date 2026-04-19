# Claude Code -- Fully Autonomous Workflow Guide

Claude Code is the only provider that can cover **both** product roles
at once: **Document LLM** (Generate FS, Analyze, Reverse FS run through
the local `claude` CLI) and **Build Agent** (the CLI in agent mode
drives the full build loop over MCP). If you have a Claude
subscription and want a single hands-free provider end-to-end, this is
the setup to pick.

> New in 0.3.3: the Build page exposes a **Run Build Now** button when
> Build Agent is set to Claude Code. Clicking it POSTs to
> `/api/fs/{doc_id}/build/run`, which spawns `claude -p <build-prompt>
> --mcp-config <…> --allowedTools mcp__…` headlessly and reflects
> progress on the existing `build-state` polling stream. No manual
> terminal session needed for the default flow.
>
> New in 0.4.x: the Build page now polls `GET /api/fs/{id}/build-state`
> live (3s cadence) once you click **Run Build Now**, and the prompt /
> CLI command come from
> `GET /api/orchestration/mcp-config?document_id=…&stack=…&output_folder=…`
> with `auto_proceed='true'` baked in — the same source of truth as the
> in-app **Kickoff instructions** modal and the
> `reports/cursor_ide_kickoff.md` file. No more `<document_id>`
> placeholders to hand-edit.

---

## Prerequisites

| Requirement | How to get it |
|-------------|---------------|
| Claude Code CLI | `npm install -g @anthropic-ai/claude-code` |
| Anthropic subscription | Active Claude Pro / Team / Enterprise plan |
| CLI authentication | Run `claude login` and complete the browser flow |
| Platform backend running | `docker compose up` or local dev server on `http://localhost:8000` |
| Platform frontend (optional, recommended) | `cd frontend && npm run dev` on `http://localhost:3000` — open `/documents/{id}/build` for a one-click MCP config copy |

Verify the CLI works:

```bash
claude --version
```

---

## Option A: Claude Code via Web UI (recommended for first run)

This option uses the web UI for input and Claude Code CLI as the LLM engine behind the scenes.

### 1. Configure the provider

1. Open `http://localhost:3000/settings`.
2. Under **Document LLM**, select **Claude Code**.
3. Under **Build Agent**, select **Claude Code** (or Cursor, if you
   prefer to steer the build live in the IDE).
4. Click **Save Config**.
4. Set environment variables in your backend `.env`:

```
CLAUDE_CODE_CLI_PATH=claude
LLM_TIMEOUT_S=120
LLM_RETRY_ATTEMPTS=3
```

> Orchestration is always on in 0.4.0; there is no `ORCHESTRATION_ENABLED`
> or `ORCHESTRATION_STRICT_LLM` flag. Selecting **Claude Code** in Settings
> is enough to route every LLM call to the local `claude` CLI, and a
> failure will **never** silently fall back to Direct API.

5. Restart the backend.

### 2. Generate an FS from an idea

1. Go to `http://localhost:3000/create`.
2. Enter your product idea, select industry and complexity.
3. Click **Generate Functional Specification**.
4. The LLM call is routed through Claude Code CLI automatically.

### 3. Analyze

1. Open the generated document at `http://localhost:3000/documents/{id}`.
2. Click **Analyze**. The 11-node pipeline runs, each LLM call going through Claude CLI.
3. Wait for completion (progress stepper updates in real time).

### 4. Review and refine

1. Review ambiguities, contradictions, edge cases, and quality score on the document page.
2. Click **Refine** to run AI-powered refinement (also through Claude CLI).
3. Accept the refined text when satisfied.

### 5. Export

Use the web UI export buttons (JIRA, Confluence, PDF, DOCX). For autonomous build, use Option B with MCP.

---

## Option B: Claude Code with MCP (fully headless)

This option runs entirely from the terminal. Claude Code connects to the platform's MCP server and drives every step autonomously.

### 1. Start the platform

```bash
docker compose up -d
```

Or run the backend and MCP server separately:

```bash
cd backend && uvicorn app.main:app --port 8000 &
cd mcp-server && python server.py &
```

### 2. Create an MCP config file

> The snippet below is identical to the one served by
> `GET /api/orchestration/mcp-config` — the same endpoint that powers
> the in-app **Build** page (`/documents/{id}/build`). If you ever see
> the guide drift from the Build page, the endpoint wins.

Create `mcp-config.json` in your project root (run Claude Code from the
repo root so `mcp-server/server.py` resolves):

```json
{
  "mcpServers": {
    "fs-intelligence-platform": {
      "command": "python",
      "args": ["mcp-server/server.py"],
      "env": {
        "BACKEND_URL": "http://localhost:8000"
      }
    }
  }
}
```

If you prefer to launch Claude Code from a different directory, use an
absolute path in `args` instead — everything else stays the same.

### 3. Run the full autonomous loop

From your terminal, invoke Claude Code with the MCP config and the full autonomous prompt:

```bash
claude --mcp-config mcp-config.json -p "
Use the start_full_autonomous_loop prompt with:
  idea: A real-time collaborative project management tool with Gantt charts and AI task estimation
  stack: Next.js + FastAPI
  output_folder: ./output
  industry: SaaS
  complexity: enterprise
"
```

Claude Code will:
1. Generate the FS document from your idea.
2. Trigger the full 11-node analysis pipeline.
3. Run the quality gate and refine until score >= 90.
4. Resolve any HIGH ambiguities.
5. Execute the build loop for every task in dependency order.
6. Register files, verify completions, and run post-build checks.
7. Export to JIRA and generate a PDF report.

### 4. Build an existing FS document

If you already have an analyzed document, use `start_build_loop`:

```bash
claude --mcp-config mcp-config.json -p "
Use the start_build_loop prompt with:
  document_id: <your-document-uuid>
  stack: Next.js + FastAPI
  output_folder: ./output
"
```

### 5. Handle requirement changes

```bash
claude --mcp-config mcp-config.json -p "
Use the handle_requirement_change prompt with:
  document_id: <your-document-uuid>
  new_requirement: Users must be able to export dashboards as PNG images
"
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Claude CLI not found` | Run `npm install -g @anthropic-ai/claude-code` |
| `Claude CLI failed: not logged in` | Run `claude login` |
| `LLMError: Provider claude_code failed` | Check CLI auth: `claude --version` |
| `LLMError: Provider claude_code failed` surfaces in UI | Intentional — 0.4.0 never falls back to Direct API. Fix CLI auth or switch to Direct API in Settings. |
| Analysis times out | Increase `MCP_TIMEOUT_SECONDS` in MCP server env. Default is 25s; analysis can take 60-150s. |

---

## Architecture

```
Terminal / Claude Code CLI
  │
  ├─ --mcp-config ──► MCP Server (mcp-server/server.py)
  │                      │
  │                      ├─ generate_fs_from_idea ──► POST /api/idea/generate
  │                      ├─ trigger_analysis ───────► POST /api/fs/{id}/analyze
  │                      ├─ run_quality_gate ───────► refine + score check
  │                      ├─ build tools ────────────► build state, register, verify
  │                      └─ export tools ──────────► JIRA, PDF, Confluence
  │
  └─ -p ──► Direct LLM call (used by backend when llm_provider=claude_code)
                      Backend runs Claude CLI for each pipeline node LLM call
```
