"""Regression tests for the Cursor paste-per-action MCP handoff.

Background: in the wild, a Cursor agent fell back to writing the
reverse-FS deliverable to a JSON file at the workspace root with the
note *"The MCP tool submit_reverse_fs referenced in the task is not
available in this environment"*. That silently broke the platform's
handshake — the user pasted, the agent "completed", but nothing landed
in the database.

These tests pin every layer of the fix so it cannot silently regress:

* ``build_mcp_snippet`` returns a JSON-parseable, ``BACKEND_URL``-aware
  config that targets the same MCP server as the build flow
  (``fs-intelligence-platform``).
* Every Cursor prompt embeds the Phase-0 MCP availability gate, the
  exact submit-tool name, the explicit ``claim_cursor_task`` step, and
  the no-write-to-disk rule.
* The reverse-FS prompt specifically forbids the
  ``reverse_fs_output.json`` workspace-root fallback by name.
* ``/api/cursor-tasks/reverse-fs/{upload_id}`` returns an envelope
  whose ``mcp_snippet`` is JSON-parseable and matches the snippet
  helper.
"""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient

from app.db.models import CodeUploadDB, CodeUploadStatus
from app.orchestration.cursor_prompts import (
    MCP_SERVER_NAME,
    SUBMIT_TOOL_BY_KIND,
    build_analyze_prompt,
    build_generate_fs_prompt,
    build_impact_prompt,
    build_mcp_setup_instructions,
    build_mcp_snippet,
    build_refine_prompt,
    build_reverse_fs_prompt,
)


def test_mcp_snippet_is_valid_json_with_env() -> None:
    raw = build_mcp_snippet()
    parsed = json.loads(raw)
    server = parsed["mcpServers"][MCP_SERVER_NAME]
    assert server["command"] == "python"
    assert server["args"] == ["mcp-server/server.py"]
    # The fix that prevents Cursor from spinning up a server pointed
    # at the wrong backend port: BACKEND_URL must be present.
    assert "BACKEND_URL" in server["env"]
    assert server["env"]["BACKEND_URL"].startswith("http")


def test_mcp_snippet_honors_explicit_backend_url() -> None:
    raw = build_mcp_snippet(backend_url="https://platform.example.com")
    parsed = json.loads(raw)
    assert (
        parsed["mcpServers"][MCP_SERVER_NAME]["env"]["BACKEND_URL"]
        == "https://platform.example.com"
    )


def test_mcp_setup_instructions_mention_workspace_and_restart() -> None:
    steps = build_mcp_setup_instructions()
    joined = "\n".join(steps).lower()
    assert "workspace" in joined
    assert ".cursor/mcp.json" in joined
    assert "restart" in joined  # full Cursor restart is mandatory


@pytest.mark.parametrize(
    "builder,kind",
    [
        (lambda tid: build_generate_fs_prompt(tid, idea="A todo app"), "generate_fs"),
        (lambda tid: build_analyze_prompt(tid, fs_text="# Spec"), "analyze"),
        (
            lambda tid: build_reverse_fs_prompt(
                tid,
                code_manifest={"primary_language": "python"},
                file_excerpts=[],
            ),
            "reverse_fs",
        ),
        (
            lambda tid: build_refine_prompt(tid, fs_text="# Spec", accepted_flags=[]),
            "refine",
        ),
        (
            lambda tid: build_impact_prompt(tid, old_fs_text="old", new_fs_text="new"),
            "impact",
        ),
    ],
)
def test_every_prompt_has_mcp_preflight_gate(builder, kind: str) -> None:
    """Every paste-per-action prompt must teach the agent how to fail
    cleanly when MCP isn't connected."""

    task_id = uuid.uuid4()
    body = builder(task_id)
    submit_tool = SUBMIT_TOOL_BY_KIND[kind]

    # Phase 0 gate is present and names the right tool.
    assert "Phase 0 — MCP availability check" in body
    assert submit_tool in body
    assert MCP_SERVER_NAME in body

    # The escape hatch: agent must STOP, not invent a fallback.
    assert "STOP IMMEDIATELY" in body
    # The exact wording Cursor would otherwise emit must be addressed.
    assert (
        "MCP server is not connected" in body
        or "is not connected" in body
    )

    # The claim step is now mandatory.
    assert "claim_cursor_task" in body
    assert str(task_id) in body


def test_reverse_fs_prompt_forbids_workspace_root_json_fallback() -> None:
    """The exact failure mode reported by the user: agent dumps a JSON
    file at the workspace root when MCP is missing. Block it by name."""

    task_id = uuid.uuid4()
    body = build_reverse_fs_prompt(
        task_id,
        code_manifest={"primary_language": "python"},
        file_excerpts=[
            {"path": "main.py", "language": "python", "excerpt": "print('hi')"}
        ],
    )
    lower = body.lower()
    assert "forbidden fallbacks" in lower
    assert "workspace root" in lower
    assert "json file" in lower
    assert ".json" in body  # call out the exact filename pattern
    # Pasting in chat is also banned because the platform never reads it.
    assert "pasting the deliverable into chat" in lower


@pytest.mark.asyncio
async def test_reverse_fs_envelope_has_parseable_mcp_snippet(
    client: AsyncClient, test_db
) -> None:
    upload = CodeUploadDB(
        id=uuid.uuid4(),
        filename="repo.zip",
        zip_path="/tmp/repo.zip",
        status=CodeUploadStatus.PARSED,
        file_size=2048,
        primary_language="python",
        total_files=1,
        total_lines=10,
        languages={"python": 1},
        snapshot_data={
            "files": [
                {"path": "a.py", "language": "python", "content": "print('a')"},
            ]
        },
    )
    test_db.add(upload)
    await test_db.commit()

    resp = await client.post(f"/api/cursor-tasks/reverse-fs/{upload.id}")
    assert resp.status_code == 200, resp.text
    env = resp.json()["data"]
    assert env["kind"] == "reverse_fs"

    parsed = json.loads(env["mcp_snippet"])
    server = parsed["mcpServers"][MCP_SERVER_NAME]
    assert server["args"] == ["mcp-server/server.py"]
    assert "BACKEND_URL" in server["env"]

    # The prompt embedded in the envelope must reach Cursor with the
    # full Phase 0 gate intact (no copy-paste truncation by the API).
    assert "submit_reverse_fs" in env["prompt"]
    assert "claim_cursor_task" in env["prompt"]
    assert "STOP IMMEDIATELY" in env["prompt"]
