# Cursor IDE — Manual Acceptance Kickoff

Document: `62f7e853-2bfc-45f9-a724-ee01834e5b3d`

MCP session: `35648f24-ba82-452c-a051-cd1726f14035`

## 1. MCP config

Place this JSON at `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "fs-intelligence-platform": {
      "command": "python",
      "args": [
        "mcp-server/server.py"
      ],
      "env": {
        "BACKEND_URL": "http://localhost:8000"
      }
    }
  }
}
```

## 2. Agent prompt

Paste into Cursor Agent Mode:

```
Use the start_build_loop prompt for document 62f7e853-2bfc-45f9-a724-ee01834e5b3d with stack='Next.js + FastAPI' and output_folder='./output' and auto_proceed='true'.
```

> The `auto_proceed='true'` suffix is appended automatically by both
> `GET /api/orchestration/build-prompt` and
> `GET /api/orchestration/mcp-config?document_id=…&stack=…&output_folder=…`,
> which is also the source the in-app **Build** page
> (`/documents/{id}/build`) and **Kickoff instructions** modal pull from.
> Always render through one of those endpoints rather than typing the
> document id by hand — that way every entry point (web UI, this
> report, the MCP modal) stays in sync.

## 3. Monitoring

The driver is polling `/api/mcp/sessions/35648f24-ba82-452c-a051-cd1726f14035/events` every 10s. When the build completes in Cursor, run `e2e_full --phases=cursor_verify` to assert file_registry + post-build-check.

For Claude Code instead of Cursor, open the Build page, switch to the
**Claude Code** tab, and click **Run Build Now** — that POSTs
`/api/fs/{id}/build/run` and surfaces progress via the live
`GET /api/fs/{id}/build-state` poller embedded directly underneath the
tabs. No external terminal session needed.
