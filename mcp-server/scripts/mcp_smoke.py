"""Smoke test for every registered MCP tool.

Boots the FastAPI backend in-process (SQLite), routes the MCP tools'
``httpx.AsyncClient`` calls through an ASGI transport so no network is
needed, and then:

1. Lists every tool + prompt the MCP server registers.
2. Walks the full Cursor paste-per-action lifecycle through the
   MCP tools — ``generate_fs`` (create → claim → submit), ``analyze``,
   ``refine``, ``reverse_fs``, ``impact`` — plus ``fail_cursor_task``
   and ``get_cursor_task``.
3. Calls a handful of non-LLM MCP tools (``list_projects``,
   ``list_documents``, ``list_providers``) to confirm end-to-end
   routing works.

Exits 0 on success, 1 on any unexpected behaviour.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import tempfile
import traceback
import uuid
from contextlib import AsyncExitStack
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

_THIS = os.path.dirname(os.path.abspath(__file__))
_MCP_ROOT = os.path.dirname(_THIS)
_PROJECT_ROOT = os.path.dirname(_MCP_ROOT)
_BACKEND = os.path.join(_PROJECT_ROOT, "backend")

for p in (_MCP_ROOT, _BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)


import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base, get_db  # noqa: E402
from app.main import app as backend_app  # noqa: E402

# Import the MCP server module lazily so we can patch httpx first
import tools._http as _mcp_http  # noqa: E402

from server import mcp  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────


class _Counter:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def ok(self, label: str) -> None:
        self.passed.append(label)
        print(f"  PASS {label}")

    def fail(self, label: str, err: str = "") -> None:
        self.failed.append((label, err))
        print(f"  FAIL {label}: {err}")

    def check(self, cond: bool, label: str, err: str = "") -> None:
        (self.ok if cond else self.fail)(label, err) if not cond else self.ok(label)


_FAKE_FS = (
    "# Tiny FS\n\n## Goals\nA tiny todo list for one user.\n\n"
    "## Features\n- Add a task\n- Remove a task\n"
)


async def _setup_backend(stack: AsyncExitStack) -> AsyncSession:
    temp_db = os.path.join(tempfile.gettempdir(), f"mcp_smoke_{uuid.uuid4().hex}.db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{temp_db}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = await stack.enter_async_context(session_factory())

    async def _override_get_db():
        yield session

    backend_app.dependency_overrides[get_db] = _override_get_db

    async def _cleanup_engine() -> None:
        await engine.dispose()
        try:
            os.remove(temp_db)
        except OSError:
            pass

    stack.callback(backend_app.dependency_overrides.clear)
    stack.push_async_callback(_cleanup_engine)
    return session


def _install_asgi_httpx(stack: AsyncExitStack) -> None:
    """Make every ``httpx.AsyncClient()`` call inside the MCP tools talk
    to the in-process FastAPI app instead of hitting the network."""

    transport = ASGITransport(app=backend_app)

    class _InProcClient(httpx.AsyncClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", transport)
            kwargs.setdefault("base_url", "http://mcp-smoke")
            super().__init__(*args, **kwargs)

    patcher = patch.object(_mcp_http.httpx, "AsyncClient", _InProcClient)
    patcher.start()
    stack.callback(patcher.stop)

    # Default the backend URL used in request_json.
    patcher2 = patch.object(_mcp_http, "BACKEND_URL", "http://mcp-smoke")
    patcher2.start()
    stack.callback(patcher2.stop)


async def _call_tool(name: str, arguments: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    result = await mcp.call_tool(name, arguments or {})
    # fastmcp wraps results as ToolResult with `.data` or `.structured_content`.
    if hasattr(result, "data") and result.data is not None:
        return result.data  # type: ignore[no-any-return]
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return result.structured_content  # type: ignore[no-any-return]
    if hasattr(result, "content"):
        # List of content blocks; try to decode text payloads as JSON-ish.
        import json as _json

        pieces = []
        for block in result.content or []:
            text = getattr(block, "text", None)
            if text is not None:
                pieces.append(text)
        joined = "\n".join(pieces)
        try:
            return _json.loads(joined) if joined else {}
        except Exception:  # noqa: BLE001
            return {"_raw": joined}
    return {}


async def _upload_and_parse(session_client: httpx.AsyncClient) -> str:
    """Upload a tiny FS + parse it so Analyze/Refine have text to work with."""
    buf = io.BytesIO(_FAKE_FS.encode("utf-8"))
    r = await session_client.post(
        "/api/fs/upload",
        files={"file": ("tiny.txt", buf, "text/plain")},
    )
    r.raise_for_status()
    doc_id = r.json()["data"]["id"]
    p = await session_client.post(f"/api/fs/{doc_id}/parse")
    p.raise_for_status()
    return doc_id


async def _create_parsed_code_upload(session) -> str:  # type: ignore[no-untyped-def]
    """Insert a PARSED CodeUpload directly so reverse_fs has a target."""
    from app.db.models import CodeUploadDB, CodeUploadStatus

    up = CodeUploadDB(
        id=uuid.uuid4(),
        filename="repo.zip",
        zip_path="/tmp/repo.zip",
        status=CodeUploadStatus.PARSED,
        file_size=2048,
        primary_language="python",
        total_files=2,
        total_lines=40,
        languages={"python": 2},
        snapshot_data={"files": [{"path": "a.py", "language": "python", "content": "print(1)"}]},
    )
    session.add(up)
    await session.commit()
    return str(up.id)


async def _create_new_version(session, doc_id: str) -> str:  # type: ignore[no-untyped-def]
    from app.db.models import FSVersion

    version = FSVersion(
        id=uuid.uuid4(),
        fs_id=uuid.UUID(doc_id),
        version_number=2,
        parsed_text="# Tiny FS (v2)\n\n## Goals\nSupport shared lists.\n",
    )
    session.add(version)
    await session.commit()
    return str(version.id)


# ── Lifecycles ────────────────────────────────────────────────────────


async def _walk_generate_fs(counter: _Counter) -> None:
    env = await _call_tool(
        "create_cursor_task_generate_fs", {"idea": "A tiny todo list"}
    ) if False else None
    # Fallback: cursor_tasks.py only exposes the *lifecycle* tools (claim,
    # submit, fail, get). Create the task via the HTTP API.
    async with httpx.AsyncClient(
        transport=ASGITransport(app=backend_app),
        base_url="http://mcp-smoke",
    ) as c:
        r = await c.post("/api/cursor-tasks/generate-fs", json={"idea": "A tiny todo list"})
        r.raise_for_status()
        env = r.json()["data"]
    task_id = env["task_id"]

    claim = await _call_tool("claim_cursor_task", {"task_id": task_id})
    counter.check(
        claim.get("data", {}).get("status") == "claimed",
        "claim_cursor_task (generate_fs)",
        str(claim),
    )

    submit = await _call_tool(
        "submit_generate_fs",
        {"task_id": task_id, "fs_markdown": _FAKE_FS},
    )
    counter.check(
        submit.get("data", {}).get("status") == "done",
        "submit_generate_fs",
        str(submit),
    )

    poll = await _call_tool("get_cursor_task", {"task_id": task_id})
    counter.check(
        poll.get("data", {}).get("status") == "done",
        "get_cursor_task (generate_fs)",
        str(poll),
    )


async def _walk_analyze(counter: _Counter, doc_id: str) -> None:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=backend_app), base_url="http://mcp-smoke",
    ) as c:
        r = await c.post(f"/api/cursor-tasks/analyze/{doc_id}")
        r.raise_for_status()
        task_id = r.json()["data"]["task_id"]
    await _call_tool("claim_cursor_task", {"task_id": task_id})
    submit = await _call_tool(
        "submit_analyze",
        {
            "task_id": task_id,
            "quality_score": {
                "overall": 85,
                "clarity": 80,
                "completeness": 90,
                "consistency": 85,
                "risks": [],
            },
            "ambiguities": [],
            "contradictions": [],
            "edge_cases": [],
            "tasks": [],
        },
    )
    counter.check(
        submit.get("data", {}).get("status") == "done",
        "submit_analyze",
        str(submit),
    )


async def _walk_refine(counter: _Counter, doc_id: str) -> None:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=backend_app), base_url="http://mcp-smoke",
    ) as c:
        r = await c.post(f"/api/cursor-tasks/refine/{doc_id}")
        r.raise_for_status()
        task_id = r.json()["data"]["task_id"]
    await _call_tool("claim_cursor_task", {"task_id": task_id})
    submit = await _call_tool(
        "submit_refine",
        {
            "task_id": task_id,
            "refined_markdown": _FAKE_FS + "\n\n## Clarifications\nNone needed.\n",
            "summary": "Minor phrasing.",
            "changed_sections": ["Goals"],
        },
    )
    counter.check(
        submit.get("data", {}).get("status") == "done",
        "submit_refine",
        str(submit),
    )


async def _walk_reverse_fs(counter: _Counter, upload_id: str) -> None:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=backend_app), base_url="http://mcp-smoke",
    ) as c:
        r = await c.post(f"/api/cursor-tasks/reverse-fs/{upload_id}")
        r.raise_for_status()
        task_id = r.json()["data"]["task_id"]
    await _call_tool("claim_cursor_task", {"task_id": task_id})
    submit = await _call_tool(
        "submit_reverse_fs",
        {
            "task_id": task_id,
            "fs_markdown": "# Reverse FS\n\n## Summary\nTwo python files.",
            "report": {
                "coverage": 0.9,
                "confidence": 0.8,
                "primary_language": "python",
                "modules": [],
                "user_flows": [],
                "gaps": [],
                "notes": "",
            },
        },
    )
    counter.check(
        submit.get("data", {}).get("status") == "done",
        "submit_reverse_fs",
        str(submit),
    )


async def _walk_impact(counter: _Counter, version_id: str) -> None:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=backend_app), base_url="http://mcp-smoke",
    ) as c:
        r = await c.post(f"/api/cursor-tasks/impact/{version_id}")
        r.raise_for_status()
        task_id = r.json()["data"]["task_id"]
    await _call_tool("claim_cursor_task", {"task_id": task_id})
    submit = await _call_tool(
        "submit_impact",
        {
            "task_id": task_id,
            "fs_changes": [
                {
                    "change_type": "MODIFIED",
                    "section_id": "goals",
                    "section_heading": "Goals",
                    "section_index": 1,
                    "old_text": "A tiny todo list for one user.",
                    "new_text": "Support shared lists.",
                }
            ],
            "task_impacts": [],
            "rework_estimate": {
                "invalidated_count": 0,
                "review_count": 1,
                "unaffected_count": 0,
                "total_rework_days": 0.5,
                "affected_sections": ["Goals"],
                "changes_summary": "Scope expanded.",
            },
        },
    )
    counter.check(
        submit.get("data", {}).get("status") == "done",
        "submit_impact",
        str(submit),
    )


async def _walk_fail_path(counter: _Counter) -> None:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=backend_app), base_url="http://mcp-smoke",
    ) as c:
        r = await c.post("/api/cursor-tasks/generate-fs", json={"idea": "never completes"})
        r.raise_for_status()
        task_id = r.json()["data"]["task_id"]
    fail = await _call_tool(
        "fail_cursor_task", {"task_id": task_id, "error": "Cursor gave up"}
    )
    counter.check(
        fail.get("data", {}).get("status") == "failed",
        "fail_cursor_task",
        str(fail),
    )


# ── Main ──────────────────────────────────────────────────────────────


async def main() -> int:
    print("=" * 62)
    print("FS Intelligence Platform — MCP smoke test (0.4.0)")
    print("=" * 62)

    counter = _Counter()

    async with AsyncExitStack() as stack:
        session = await _setup_backend(stack)
        _install_asgi_httpx(stack)

        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        counter.check(len(tools) >= 85, f"tool count = {len(tools)} (>=85)")
        for required in (
            "claim_cursor_task",
            "submit_generate_fs",
            "submit_analyze",
            "submit_reverse_fs",
            "submit_refine",
            "submit_impact",
            "fail_cursor_task",
            "get_cursor_task",
        ):
            counter.check(required in tool_names, f"tool registered: {required}")

        prompts = await mcp.list_prompts()
        counter.check(len(prompts) >= 1, f"prompt count = {len(prompts)}")

        # Default provider for the backend pipelines (not Cursor) — we
        # still want ``list_documents`` etc. to succeed.
        with patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="api"),
        ):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=backend_app),
                base_url="http://mcp-smoke",
            ) as c:
                doc_id = await _upload_and_parse(c)
            counter.ok(f"upload+parse -> {doc_id}")

            upload_id = await _create_parsed_code_upload(session)
            version_id = await _create_new_version(session, doc_id)

            # Non-LLM tools
            projects = await _call_tool("list_projects")
            counter.check(
                isinstance(projects, dict) and projects.get("error") is None,
                "tool: list_projects",
                str(projects),
            )
            docs = await _call_tool("list_documents")
            counter.check(
                isinstance(docs, dict) and docs.get("error") is None,
                "tool: list_documents",
                str(docs),
            )
            providers = await _call_tool("list_providers")
            counter.check(
                isinstance(providers, dict) and providers.get("error") is None,
                "tool: list_providers",
                str(providers),
            )

            # Cursor task lifecycles
            await _walk_generate_fs(counter)
            await _walk_analyze(counter, doc_id)
            await _walk_refine(counter, doc_id)
            await _walk_reverse_fs(counter, upload_id)
            await _walk_impact(counter, version_id)
            await _walk_fail_path(counter)

    print("\n" + "=" * 62)
    print(f"Summary: {len(counter.passed)} passed, {len(counter.failed)} failed")
    print("=" * 62)
    return 0 if not counter.failed else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        print(f"FATAL: {exc}")
        sys.exit(1)
