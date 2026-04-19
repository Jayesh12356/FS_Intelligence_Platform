"""Verify the headless Claude build bridges into the MCP Sessions UI.

Symptom this test guards against (reported by the user): "build logs
show nothing but build was completed". The cause was the headless
runner spawning the Claude CLI without an ``MCP_SESSION_ID``, which
made every ``emit_session_event`` call inside the MCP tools no-op.

This test:
  * Patches ``_run_cli`` so we never spawn an actual subprocess.
  * Captures the env passed to ``_run_cli`` and asserts both
    ``MCP_SESSION_ID`` and ``BACKEND_URL`` are present.
  * Confirms an ``MCPSessionDB`` row was created and finalised, and that
    ``BUILD_STARTED`` + ``BUILD_COMPLETED`` audit events bookend the run.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.api.build_router import _run_claude_build
from app.db.models import (
    AuditEventDB,
    AuditEventType,
    BuildStateDB,
    BuildStatus,
    FSDocument,
    FSDocumentStatus,
    MCPSessionDB,
    MCPSessionStatus,
)


@pytest.mark.asyncio
async def test_run_claude_build_bridges_session_and_emits_bookends(
    test_db, monkeypatch, tmp_path
) -> None:
    fs = FSDocument(filename="bridge.md", status=FSDocumentStatus.COMPLETE)
    test_db.add(fs)
    await test_db.commit()
    await test_db.refresh(fs)

    bs = BuildStateDB(
        document_id=fs.id,
        status=BuildStatus.PENDING,
        current_phase=0,
        total_tasks=2,
        stack="Next.js + FastAPI",
    )
    test_db.add(bs)
    await test_db.commit()

    # Force ``_run_claude_build`` to use OUR test session for its async
    # session factory so the inserts land in the same DB the assertions
    # query later. Without this, the function opens a new session bound
    # to the production engine.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_session_factory():
        yield test_db

    monkeypatch.setattr(
        "app.db.base.async_session_factory", _fake_session_factory
    )

    captured_env: dict[str, str] = {}

    def _fake_run_cli(args, timeout=120, cwd=None, env=None):
        if env is not None:
            captured_env.update(env)
        return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")

    with patch(
        "app.orchestration.providers.claude_code_provider._run_cli",
        new=_fake_run_cli,
    ), patch(
        "app.orchestration.providers.claude_code_provider._resolve_cli_invocation",
        return_value=["claude"],
    ):
        await _run_claude_build(
            fs.id,
            prompt="<role>test</role>",
            mcp_config={"mcpServers": {}},
            output_folder=str(tmp_path),
            stack="Next.js + FastAPI",
        )

    # 1) MCP_SESSION_ID + BACKEND_URL flow into the subprocess env.
    assert "MCP_SESSION_ID" in captured_env, (
        "MCP_SESSION_ID must be exported so emit_session_event has a target"
    )
    assert "BACKEND_URL" in captured_env, (
        "BACKEND_URL must be exported so the MCP server can call back into us"
    )

    # 2) An MCPSessionDB row exists and finished cleanly.
    sessions = (
        await test_db.execute(
            select(MCPSessionDB).where(MCPSessionDB.fs_id == fs.id)
        )
    ).scalars().all()
    assert len(sessions) == 1, "Exactly one MCPSessionDB row per build"
    assert sessions[0].status == MCPSessionStatus.PASSED
    assert str(sessions[0].id) == captured_env["MCP_SESSION_ID"]

    # 3) Audit events bookend the run.
    events = (
        await test_db.execute(
            select(AuditEventDB).where(AuditEventDB.fs_id == fs.id)
        )
    ).scalars().all()
    types = {e.event_type for e in events}
    assert AuditEventType.BUILD_STARTED in types
    assert AuditEventType.BUILD_COMPLETED in types

    # 4) Build state is finalised to COMPLETE.
    refreshed = (
        await test_db.execute(
            select(BuildStateDB).where(BuildStateDB.document_id == fs.id)
        )
    ).scalar_one()
    assert refreshed.status == BuildStatus.COMPLETE
