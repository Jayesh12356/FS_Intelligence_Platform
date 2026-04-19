"""Tiny TODO-API scenario used for end-to-end triple-provider acceptance.

We keep this scenario intentionally small so every provider run stays inside
a few thousand tokens yet still exercises the full pipeline (sections,
ambiguities, tasks, dependencies, quality, build).
"""

from __future__ import annotations

from typing import Final

IDEA_TEXT: Final[str] = (
    "A tiny in-memory TODO list REST API, built with Python FastAPI. "
    "Exactly three endpoints: GET /todos returns the current list of todos, "
    'POST /todos accepts a JSON body {"text": string} and appends a new todo '
    "with a server-generated integer id, and DELETE /todos/{id} removes the "
    "todo with the matching id (404 if missing). A GET /health endpoint "
    'returns {"status": "ok"}. Todos live in a module-level Python list; '
    "there is no database, no authentication, no pagination. "
    "Acceptance: all four endpoints behave as described, invalid JSON returns "
    "422, deleting an unknown id returns 404, and the server starts with an "
    "empty todo list."
)

INDUSTRY: Final[str] = "developer_tools"
COMPLEXITY: Final[str] = "simple"

PROJECTS: Final[list[dict]] = [
    {
        "key": "api",
        "provider": "api",
        "name": "E2E-API-Todo",
        "description": "Triple-provider E2E run, Direct-API leg",
        "idea_mode": "quick",
    },
    {
        "key": "claude",
        "provider": "claude_code",
        "name": "E2E-Claude-Todo",
        "description": "Triple-provider E2E run, Claude Code leg",
        "idea_mode": "guided",
    },
    {
        "key": "cursor",
        "provider": "cursor",
        "name": "E2E-Cursor-Todo",
        "description": "Triple-provider E2E run, Cursor (MCP) leg",
        "idea_mode": "quick",
    },
]

GUIDED_ANSWERS: Final[dict[str, str]] = {
    "target_users": "backend developers evaluating a demo API",
    "primary_goals": "provide a minimal CRUD REST surface for TODO items",
    "key_features": "list, create, delete todos, plus a health check",
    "scale": "single-process, in-memory, up to 1000 todos",
    "tech_stack": "Python 3.12, FastAPI, uvicorn",
    "non_functional": "p95 latency under 50ms on a laptop",
    "constraints": "no database, no auth, single instance",
    "integrations": "none",
    "deployment": "local uvicorn run",
    "security": "none beyond HTTPS at the proxy layer",
}

# Only the Direct-API project runs the full server-side pipeline.
#
# claude_code: token-sensitive (CLI may fall back to Anthropic API). Smoke-only.
# cursor:      paid by the user's Cursor subscription INSIDE the IDE. The
#              backend refuses server-side LLM calls when cursor is active
#              (see CursorProvider.call_llm). The driver verifies the refusal
#              and leaves the full analyze/build run to the real Cursor IDE
#              (Phase 6 acceptance).
PROJECT_SMOKE_ONLY: Final[set[str]] = {"claude_code", "cursor"}
PROJECT_FULL: Final[set[str]] = {"api"}


EXPECTED: Final[dict] = {
    "min_sections": 3,
    "max_sections": 20,
    "min_tasks": 3,
    "max_tasks": 20,
    "min_quality": 70.0,
    "target_quality": 90.0,
    "max_refine_attempts": 3,
    "max_high_ambiguities_after_refine": 2,
}

ENDPOINT_MATRIX: Final[list[str]] = [
    "GET /health",
    "GET /",
    "GET /api/orchestration/providers",
    "GET /api/orchestration/config",
    "PUT /api/orchestration/config",
    "POST /api/orchestration/test/{provider}",
    "GET /api/orchestration/capabilities",
    "GET /api/orchestration/mcp-config",
    "POST /api/projects",
    "GET /api/projects",
    "GET /api/projects/{id}",
    "PATCH /api/projects/{id}",
    "POST /api/projects/{id}/documents/{doc_id}",
    "POST /api/idea/generate",
    "POST /api/idea/guided",
    "GET /api/fs",
    "GET /api/fs/{id}",
    "GET /api/fs/{id}/status",
    "POST /api/fs/{id}/analyze",
    "GET /api/fs/{id}/ambiguities",
    "GET /api/fs/{id}/contradictions",
    "GET /api/fs/{id}/edge-cases",
    "GET /api/fs/{id}/quality-score",
    "POST /api/fs/{id}/refine",
    "GET /api/fs/{id}/tasks",
    "GET /api/fs/{id}/tasks/dependency-graph",
    "GET /api/fs/{id}/traceability",
    "POST /api/fs/{id}/sections/{section}/comments",
    "GET /api/fs/{id}/comments",
    "PATCH /api/fs/{id}/comments/{cid}/resolve",
    "POST /api/fs/{id}/submit-for-approval",
    "POST /api/fs/{id}/approve",
    "GET /api/fs/{id}/approval-status",
    "POST /api/fs/{id}/build-state",
    "GET /api/fs/{id}/build-state",
    "GET /api/fs/{id}/build-prompt",
    "GET /api/fs/{id}/pre-build-check",
    "GET /api/fs/{id}/post-build-check",
    "POST /api/fs/{id}/file-registry",
    "GET /api/fs/{id}/file-registry",
    "POST /api/fs/{id}/snapshots",
    "GET /api/fs/{id}/export/pdf",
    "GET /api/fs/{id}/export/docx",
    "POST /api/fs/{id}/export/jira",
    "POST /api/fs/{id}/export/confluence",
    "GET /api/fs/{id}/test-cases",
    "POST /api/code/upload",
    "POST /api/code/{id}/generate-fs",
    "GET /api/code/{id}/generated-fs",
    "GET /api/code/{id}/report",
    "GET /api/code/uploads",
    "GET /api/library",
    "GET /api/duplicates",
    "POST /api/mcp/sessions",
    "GET /api/mcp/sessions",
    "POST /api/mcp/sessions/{sid}/events",
    "GET /api/mcp/sessions/{sid}/events",
    "GET /api/audit",
    "GET /api/activity",
]
