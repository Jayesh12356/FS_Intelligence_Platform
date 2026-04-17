# Cursor -- MCP-Driven Autonomous Workflow Guide

Cursor connects to the FS Intelligence Platform through its MCP server. You start one agent session, give it your idea, and Cursor drives the entire pipeline: FS generation, analysis, refinement, and build. You watch it work.

---

## Prerequisites

| Requirement | How to get it |
|-------------|---------------|
| Cursor IDE | Download from [cursor.com](https://cursor.com) |
| Cursor Pro / Business plan | Required for agent mode and MCP |
| Platform backend running | `docker compose up` or local dev server on `http://localhost:8000` |
| Python 3.11+ for MCP server | System Python or virtualenv |
| MCP server dependencies | `cd mcp-server && pip install -r requirements.txt` |

---

## Step 1: Configure the MCP Server in Cursor

### Option A: Project-level config (recommended)

Create `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "fs-intelligence-platform": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "./mcp-server",
      "env": {
        "BACKEND_URL": "http://localhost:8000"
      }
    }
  }
}
```

### Option B: Global config

Add to `~/.cursor/mcp.json` (or `%APPDATA%\Cursor\mcp.json` on Windows):

```json
{
  "mcpServers": {
    "fs-intelligence-platform": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "C:/path/to/fs_intelligence_platform/mcp-server",
      "env": {
        "BACKEND_URL": "http://localhost:8000"
      }
    }
  }
}
```

### Verify connection

1. Open Cursor and the project folder.
2. Open the MCP panel (Ctrl+Shift+P → "MCP: Show Servers").
3. You should see **fs-intelligence-platform** with a green status.
4. Open the tool list -- you should see 60+ tools including `generate_fs_from_idea`, `trigger_analysis`, `autonomous_build_from_fs`.

---

## Step 2: Full Autonomous Pipeline (Idea to Production)

Open Cursor Agent Mode (Ctrl+I or the composer panel) and paste:

```
Use the start_full_autonomous_loop prompt with:
  idea: A real-time collaborative project management tool with Gantt charts, resource allocation, and AI-powered task estimation for enterprise teams
  stack: Next.js + FastAPI
  output_folder: ./output
  industry: SaaS
  complexity: enterprise
```

Cursor will execute:

1. **Generate FS** -- Calls `generate_fs_from_idea` to create a full specification from your idea.
2. **Analyze** -- Calls `trigger_analysis` to run the 11-node pipeline (ambiguity detection, contradiction analysis, edge cases, quality scoring, task decomposition, dependency mapping, traceability, duplicate detection, test case generation).
3. **Quality gate** -- Calls `run_quality_gate` and `refine_fs` until quality >= 90.
4. **Resolve blockers** -- Resolves HIGH ambiguities using debate results as context.
5. **Build setup** -- Runs `pre_build_check`, `autonomous_build_from_fs`, checks library for reuse.
6. **Build** -- Implements every task in dependency order, registers files, verifies completions.
7. **Verify** -- Runs `post_build_check` until verdict = GO.
8. **Export** -- Exports to JIRA and generates PDF report.

---

## Step 3: Build from an Existing FS Document

If you already uploaded and analyzed a document through the web UI:

```
Use the start_build_loop prompt with:
  document_id: <paste-your-document-uuid-here>
  stack: Next.js + FastAPI
  output_folder: ./output
```

Cursor handles quality gate, blocker resolution, and the full build loop.

---

## Step 4: Individual Operations

### Implement a single task

```
Use the implement_task prompt with:
  document_id: <uuid>
  task_id: <task-id>
```

### Fix one ambiguity

```
Use the fix_single_ambiguity prompt with:
  document_id: <uuid>
  flag_id: <flag-id>
```

### Handle a requirement change

```
Use the handle_requirement_change prompt with:
  document_id: <uuid>
  new_requirement: Users must be able to export dashboards as PNG images
```

---

## Monitoring Progress

While Cursor works, you can monitor from the web UI:

1. **Document page** (`/documents/{id}`) -- See analysis results, quality score, ambiguities, tasks.
2. **Monitoring page** (`/monitoring`) -- Track MCP session activity, tool calls, build progress.
3. **Analysis progress** -- Real-time stepper shows which pipeline node is executing.

---

## Available MCP Tools (62 total)

### Idea generation
| Tool | Purpose |
|------|---------|
| `generate_fs_from_idea` | Create FS from a product idea (quick mode) |
| `generate_fs_guided` | Multi-step guided FS generation with discovery questions |

### Document lifecycle
| Tool | Purpose |
|------|---------|
| `list_documents` | List all FS documents |
| `get_document` | Full document details and parsed text |
| `upload_document` | Ingest a local .pdf/.docx/.txt file |
| `trigger_analysis` | Run the full 11-node analysis pipeline |
| `get_document_status` | Poll processing status |
| `get_sections` | View parsed sections |

### Analysis and refinement
| Tool | Purpose |
|------|---------|
| `get_ambiguities` | List ambiguity flags |
| `resolve_ambiguity` | Resolve one ambiguity with concrete text |
| `get_contradictions` | Detect requirement conflicts |
| `get_edge_cases` | Identify missing scenarios |
| `get_quality_score` | Quality dashboard |
| `refresh_quality_score` | Recompute score (fast) |
| `refine_fs` | AI-powered document refinement |
| `run_quality_gate` | Auto-refine loop until score >= 90 |
| `get_compliance_tags` | Compliance classification |
| `get_debate_results` | Adversarial debate outcomes |

### Tasks and dependencies
| Tool | Purpose |
|------|---------|
| `get_tasks` | Full task backlog |
| `get_task` | Single task details |
| `update_task` | Change task status |
| `get_dependency_graph` | Task ordering and dependencies |
| `get_traceability` | Task-to-section mapping |
| `get_test_cases` | Generated test cases |

### Build orchestration
| Tool | Purpose |
|------|---------|
| `autonomous_build_from_fs` | Generate build manifest |
| `get_build_state` / `create_build_state` / `update_build_state` | Build progress tracking |
| `register_file` | Link files to tasks and sections |
| `get_task_context` | Full implementation context for a task |
| `verify_task_completion` | Pre-complete verification |
| `pre_build_check` / `post_build_check` | Safety gates |
| `create_snapshot` / `rollback_to_snapshot` | Rollback points |
| `check_library_for_reuse` | Search for reusable patterns |

### Impact and versioning
| Tool | Purpose |
|------|---------|
| `upload_version` | Upload new FS version |
| `get_version_diff` | Section-level diff |
| `get_impact_analysis` | Task invalidation analysis |
| `get_rework_estimate` | Rework cost estimation |

### Exports
| Tool | Purpose |
|------|---------|
| `export_to_jira` | Push tasks to JIRA |
| `export_to_confluence` | Publish to Confluence |
| `get_pdf_report` / `get_docx_report` | Download reports |
| `export_test_cases_csv` | Export test cases |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| MCP server not visible in Cursor | Check `.cursor/mcp.json` path and that Python is on PATH |
| `Backend request failed` | Ensure backend is running on the configured `BACKEND_URL` |
| Analysis times out | Backend may need more time; check backend logs for errors |
| Tools show but return errors | Verify database is running (`docker compose up db`) |
| Build loop skips tasks | Check `get_build_state` -- tasks may already be in `completed_task_ids` |

---

## Architecture

```
Cursor IDE (Agent Mode)
  │
  └─ MCP Protocol ──► MCP Server (mcp-server/server.py)
                         │
                         ├─ generate_fs_from_idea ──► POST /api/idea/generate
                         ├─ trigger_analysis ───────► POST /api/fs/{id}/analyze
                         ├─ run_quality_gate ───────► refine + score check
                         ├─ build tools ────────────► build state, register, verify
                         └─ export tools ──────────► JIRA, PDF, Confluence
                                │
                        FastAPI Backend (port 8000)
                                │
                         ┌──────┴──────┐
                         │             │
                    PostgreSQL      Qdrant
                   (relational)   (vectors)
```
