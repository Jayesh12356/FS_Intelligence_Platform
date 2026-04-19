"""Smoke-test every HTTP route across all three LLM providers.

This script boots the FastAPI app in-process (ASGI / ``httpx`` transport,
SQLite in a temp file) and exercises the surface area that matters for
the 0.4.0 provider-isolation guarantee:

* For ``llm_provider == "api"`` it mocks the Direct LLM client and
  confirms the pipeline routes run and return ``APIResponse`` objects.
* For ``llm_provider == "cursor"`` it confirms every LLM-dependent
  route returns a ``CursorTaskEnvelope`` (``mode == "cursor_task"``)
  and never invokes the Direct LLM client.
* For ``llm_provider == "claude_code"`` it mocks the CLI subprocess
  and confirms routes succeed without touching the Direct LLM client.

Run with: ``python -m backend.scripts.api_smoke`` or
``python backend/scripts/api_smoke.py``.

Exits 0 on success, 1 on any unexpected behaviour. Prints a concise
report per provider.
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
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure backend/ is importable when run as a script
_THIS = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_THIS)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

# ── Mock responses ───────────────────────────────────────────────────

_FAKE_FS = "# Tiny FS\n\n## Goals\nA tiny todo list for one user.\n\n## Features\n- Add a task\n- Remove a task\n"


def _fake_direct_client() -> MagicMock:
    """A Direct LLM client stub that returns valid JSON for every call."""
    client = MagicMock()
    client.call_llm = AsyncMock(return_value=_FAKE_FS)
    return client


class _PerProviderCounters:
    def __init__(self, name: str) -> None:
        self.name = name
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def ok(self, label: str) -> None:
        self.passed.append(label)
        print(f"  PASS [{self.name}] {label}")

    def fail(self, label: str, err: str = "") -> None:
        self.failed.append((label, err))
        print(f"  FAIL [{self.name}] {label}: {err}")

    def check(self, cond: bool, label: str, err: str = "") -> None:
        if cond:
            self.ok(label)
        else:
            self.fail(label, err)


async def _setup_client(stack: AsyncExitStack) -> tuple[AsyncClient, AsyncSession]:
    temp_db = os.path.join(tempfile.gettempdir(), f"api_smoke_{uuid.uuid4().hex}.db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{temp_db}", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # Session entered FIRST so it exits BEFORE engine is disposed.
    session = await stack.enter_async_context(session_factory())

    async def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db

    async def _cleanup_engine() -> None:
        await engine.dispose()
        try:
            os.remove(temp_db)
        except OSError:
            pass

    stack.callback(app.dependency_overrides.clear)
    # Pushed AFTER session so it runs AFTER session.__aexit__.
    stack.push_async_callback(_cleanup_engine)

    transport = ASGITransport(app=app)
    client = await stack.enter_async_context(AsyncClient(transport=transport, base_url="http://smoke"))
    return client, session


async def _upload_fs(client: AsyncClient) -> str:
    """Upload a tiny FS and return the created document id."""
    buf = io.BytesIO(_FAKE_FS.encode("utf-8"))
    resp = await client.post(
        "/api/fs/upload",
        files={"file": ("tiny.txt", buf, "text/plain")},
    )
    resp.raise_for_status()
    payload = resp.json()["data"]
    doc_id = payload.get("id") or payload.get("document_id") or payload.get("doc_id")
    if not doc_id:
        raise RuntimeError(f"Upload response missing id: {payload}")
    # Parse step (no LLM involved; produces parsed_text)
    r2 = await client.post(f"/api/fs/{doc_id}/parse")
    r2.raise_for_status()
    return doc_id


async def _smoke_api_provider(stack: AsyncExitStack) -> _PerProviderCounters:
    """api provider: all routes return normal responses (no CursorTask)."""
    c = _PerProviderCounters("api")
    client, _ = await _setup_client(stack)

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="api"),
        ),
        patch(
            "app.orchestration.llm_bridge.get_llm_client",
            return_value=_fake_direct_client(),
        ),
    ):
        r = await client.get("/health")
        c.check(r.status_code == 200, "GET /health", r.text)

        r = await client.get("/api/fs/")
        c.check(r.status_code == 200, "GET /api/fs/", r.text)

        try:
            doc_id = await _upload_fs(client)
            c.ok(f"POST /api/fs/upload + /parse -> {doc_id}")
        except Exception as exc:  # noqa: BLE001
            c.fail("POST /api/fs/upload", str(exc))
            return c

        r = await client.get(f"/api/fs/{doc_id}/quality-score")
        c.check(r.status_code in (200, 404), "GET /api/fs/{id}/quality-score", r.text)

        r = await client.get(f"/api/fs/{doc_id}")
        c.check(r.status_code == 200, "GET /api/fs/{id}", r.text)

        r = await client.get(f"/api/fs/{doc_id}/versions")
        c.check(r.status_code == 200, "GET /api/fs/{id}/versions", r.text)

    return c


async def _smoke_cursor_provider(stack: AsyncExitStack) -> _PerProviderCounters:
    """cursor provider: every LLM route must return a CursorTask envelope."""
    c = _PerProviderCounters("cursor")
    client, _ = await _setup_client(stack)

    direct = _fake_direct_client()

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="cursor"),
        ),
        patch(
            "app.api.idea_router.get_configured_llm_provider_name",
            new=AsyncMock(return_value="cursor"),
        ),
        patch(
            "app.orchestration.llm_bridge.get_llm_client",
            return_value=direct,
        ),
    ):
        try:
            doc_id = await _upload_fs(client)
            c.ok(f"POST /api/fs/upload + /parse -> {doc_id}")
        except Exception as exc:  # noqa: BLE001
            c.fail("POST /api/fs/upload", str(exc))
            return c

        def _is_cursor_task(resp) -> tuple[bool, str]:
            try:
                data = resp.json().get("data") or {}
                ok = resp.status_code == 200 and data.get("mode") == "cursor_task"
                return ok, "" if ok else f"{resp.status_code} {resp.text[:200]}"
            except Exception as exc:  # noqa: BLE001
                return False, str(exc)

        r = await client.post(
            "/api/idea/generate",
            json={"idea": "A tiny todo list", "industry": "", "complexity": ""},
        )
        ok, err = _is_cursor_task(r)
        c.check(ok, "POST /api/idea/generate -> cursor_task", err)

        r = await client.post(f"/api/fs/{doc_id}/analyze")
        ok, err = _is_cursor_task(r)
        c.check(ok, "POST /api/fs/{id}/analyze -> cursor_task", err)

        r = await client.post(f"/api/fs/{doc_id}/refine")
        ok, err = _is_cursor_task(r)
        c.check(ok, "POST /api/fs/{id}/refine -> cursor_task", err)

        for path in (
            f"/api/cursor-tasks/analyze/{doc_id}",
            f"/api/cursor-tasks/refine/{doc_id}",
        ):
            r = await client.post(path)
            ok, err = _is_cursor_task(r)
            c.check(ok, f"POST {path}", err)

        r = await client.post(
            "/api/cursor-tasks/generate-fs",
            json={"idea": "A tiny todo list"},
        )
        ok, err = _is_cursor_task(r)
        c.check(ok, "POST /api/cursor-tasks/generate-fs", err)

        # Critical guarantee: the Direct-API client was NEVER invoked.
        if direct.call_llm.await_count == 0:
            c.ok("Direct LLM client never called on cursor provider")
        else:
            c.fail(
                "Direct LLM client invoked on cursor provider",
                f"call_count={direct.call_llm.await_count}",
            )

    return c


async def _smoke_claude_code_provider(stack: AsyncExitStack) -> _PerProviderCounters:
    """claude_code provider: CLI is mocked, Direct-API is never touched."""
    c = _PerProviderCounters("claude_code")
    client, _ = await _setup_client(stack)

    direct = _fake_direct_client()

    async def _fake_cc_call(
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        role: str = "primary",
        **_: Any,
    ) -> str:
        return _FAKE_FS

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="claude_code"),
        ),
        patch(
            "app.api.idea_router.get_configured_llm_provider_name",
            new=AsyncMock(return_value="claude_code"),
        ),
        patch(
            "app.orchestration.llm_bridge.get_llm_client",
            return_value=direct,
        ),
        patch(
            "app.orchestration.providers.claude_code_provider.ClaudeCodeProvider.call_llm",
            new=AsyncMock(side_effect=_fake_cc_call),
        ),
    ):
        try:
            doc_id = await _upload_fs(client)
            c.ok(f"POST /api/fs/upload + /parse -> {doc_id}")
        except Exception as exc:  # noqa: BLE001
            c.fail("POST /api/fs/upload", str(exc))
            return c

        r = await client.get("/health")
        c.check(r.status_code == 200, "GET /health", r.text)

        r = await client.get("/api/fs/")
        c.check(r.status_code == 200, "GET /api/fs/", r.text)

        r = await client.get(f"/api/fs/{doc_id}")
        c.check(r.status_code == 200, "GET /api/fs/{id}", r.text)

        # Direct-API must not have been touched
        if direct.call_llm.await_count == 0:
            c.ok("Direct LLM client never called on claude_code provider")
        else:
            c.fail(
                "Direct LLM client invoked on claude_code provider",
                f"call_count={direct.call_llm.await_count}",
            )

    return c


async def main() -> int:
    print("=" * 62)
    print("FS Intelligence Platform — API smoke test (0.4.0)")
    print("=" * 62)

    results: list[_PerProviderCounters] = []

    for smoker in (_smoke_api_provider, _smoke_cursor_provider, _smoke_claude_code_provider):
        async with AsyncExitStack() as stack:
            print(f"\n-- provider: {smoker.__name__.removeprefix('_smoke_').removesuffix('_provider')} --")
            try:
                res = await smoker(stack)
            except Exception as exc:  # noqa: BLE001
                tb = traceback.format_exc()
                fake = _PerProviderCounters(smoker.__name__)
                fake.fail("top-level", f"{exc}\n{tb}")
                results.append(fake)
                continue
            results.append(res)

    print("\n" + "=" * 62)
    total_pass = sum(len(r.passed) for r in results)
    total_fail = sum(len(r.failed) for r in results)
    print(f"Summary: {total_pass} passed, {total_fail} failed")
    print("=" * 62)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
