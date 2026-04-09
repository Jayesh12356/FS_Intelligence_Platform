# FS Intelligence MCP Server

Thin MCP wrapper over the FS Intelligence Platform backend APIs.

## Install

```bash
pip install -r mcp-server/requirements.txt
```

## Start Backend First

```bash
cd backend
uvicorn app.main:app --port 8000 --reload
```

## Run MCP Server

```bash
cd mcp-server
python server.py
```

## Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector python server.py
```

## Cursor Setup

- Relative-path-first config is provided in `mcp-server/.cursor/mcp.json`.
- If your Cursor setup requires project-root `.cursor/mcp.json`, copy/merge this config there.

## Claude Desktop Setup

- Use `mcp-server/claude_desktop_config.json`.
- Update `cwd` to your absolute local path (Desktop config typically requires absolute paths).

## Claude Code Setup

```bash
claude mcp add fs-intelligence-platform "python /absolute/path/to/fs_intelligence_platform/mcp-server/server.py"
```

## Tool-to-Endpoint Mapping Notes

- Ambiguity resolve endpoint currently marks resolved status directly; MCP `resolution` input is preserved in wrapper output for agent traceability.
- `get_sections` uses document detail sections when present, otherwise falls back to `parse` trigger response.
- `get_version_diff(document_id, v1_id, v2_id)` maps to backend single-version diff route using `v2_id` as the compared version.

## `autonomous_build_from_fs` Manifest Contract

Use this MCP tool to generate a phase-by-phase build manifest from FS tasks.

### Input

```json
{
  "document_id": "uuid",
  "target_stack": "Next.js + FastAPI"
}
```

### Output shape

```json
{
  "data": {
    "document_id": "uuid",
    "target_stack": "Next.js + FastAPI",
    "phases": [
      {
        "phase": 1,
        "tasks": ["task-a", "task-b"],
        "files_to_create": ["frontend/src/app/<feature>/page.tsx"],
        "fs_compliance_checks": [
          "All tasks in phase 1 map to their source FS sections",
          "All acceptance criteria in phase 1 are verifiably implemented"
        ]
      },
      {
        "phase": 2,
        "depends_on": [1],
        "tasks": ["task-c"],
        "files_to_create": ["backend/app/api/<feature>_router.py"],
        "fs_compliance_checks": [
          "All tasks in phase 2 map to their source FS sections",
          "All acceptance criteria in phase 2 are verifiably implemented"
        ]
      }
    ],
    "acceptance_checklist": ["..."],
    "fs_compliance_checks": ["one check per section"],
    "definition_of_done": {
      "quality_score_min": 90,
      "all_tasks_complete": true,
      "zero_open_ambiguities": true,
      "traceability_coverage": "100%"
    },
    "execution_rule": "Do not start phase N+1 until phase N passes all fs_compliance_checks."
  }
}
```

### Example call

```text
autonomous_build_from_fs(
  document_id="f45f9e86-3e93-4b6f-ae90-66a0d4f5f2b5",
  target_stack="Next.js + FastAPI"
)
```

### Phase-gating rule

- Never advance to phase 2 until all phase 1 `fs_compliance_checks` pass.
- If any check fails, fix and re-validate in the same phase.
- Only mark complete when `definition_of_done` is satisfied.

## Real-time Monitoring (Local)

- Backend monitoring endpoints:
  - `POST /api/mcp/sessions`
  - `POST /api/mcp/sessions/{session_id}/events`
  - `GET /api/mcp/sessions`
  - `GET /api/mcp/sessions/{session_id}/events`
  - `GET /api/mcp/sessions/{session_id}/events/stream` (SSE)
- Frontend live dashboard route: `/monitoring`.
- MCP wrappers emit event telemetry automatically when `MCP_SESSION_ID` is set.
- If no session id exists, `autonomous_build_from_fs` attempts to create one.

