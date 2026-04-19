"""Token-leak guard: Direct API must never be called for cursor / claude_code.

Scope
-----

This test pins down the contract that when ``llm_provider`` is
``cursor`` or ``claude_code``:

* ``/api/idea/generate`` (quick) — cursor returns a ``cursor_task``
  envelope; claude_code runs the pipeline via its CLI (mocked).
* ``/api/idea/guided`` (step 0) — same as above.
* ``/api/fs/{doc_id}/analyze`` — cursor returns a ``cursor_task``
  envelope (no pipeline); claude_code is tested elsewhere.
* ``/api/code/{upload_id}/generate-fs`` — cursor returns a
  ``cursor_task`` envelope; the reverse pipeline is skipped.

The ``boom_direct_api`` fixture monkeypatches :class:`LLMClient.call_llm`
to raise immediately — any invocation is a test failure.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.db.models import (
    CodeUploadDB,
    CodeUploadStatus,
    FSDocument,
    FSDocumentStatus,
)


@pytest.fixture
def boom_direct_api(monkeypatch: pytest.MonkeyPatch):
    """Make any Direct API call explode — acts as a tripwire."""

    async def _boom(*_args, **_kwargs):  # pragma: no cover — must not run
        raise AssertionError(
            "Direct API LLMClient.call_llm was invoked during a test that forbids it. This is a token-leak regression."
        )

    from app.llm.client import LLMClient

    monkeypatch.setattr(LLMClient, "call_llm", _boom)
    yield


@pytest.fixture
def orchestration_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRATION_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _provider_ctx(provider_name: str):
    """Patch the provider resolver at every site where it is bound.

    * ``idea_router`` imports the resolver at module load, so patching
      only the source module would miss its local binding.
    * ``analysis_router`` and ``code_router`` import inside the
      function body, so patching the source module is sufficient.
    """
    from contextlib import ExitStack

    class _Ctx:
        def __enter__(self):
            self._stack = ExitStack()
            self._stack.__enter__()
            mock = AsyncMock(return_value=provider_name)
            self._stack.enter_context(
                patch(
                    "app.orchestration.config_resolver.get_configured_llm_provider_name",
                    new=mock,
                )
            )
            self._stack.enter_context(patch("app.api.idea_router.get_configured_llm_provider_name", new=mock))
            return self

        def __exit__(self, *args):
            return self._stack.__exit__(*args)

    return _Ctx()


# ── Cursor paths — must return an envelope, never call Direct API ────


@pytest.mark.asyncio
async def test_generate_fs_with_cursor_returns_task_envelope(client: AsyncClient, boom_direct_api, orchestration_on):
    with _provider_ctx("cursor"):
        resp = await client.post(
            "/api/idea/generate",
            json={"idea": "A tiny todo app for one user."},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body["data"]
    assert data["mode"] == "cursor_task"
    assert data["kind"] == "generate_fs"
    assert data["prompt"], "Prompt must be non-empty"
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_guided_step0_with_cursor_returns_task_envelope(client: AsyncClient, boom_direct_api, orchestration_on):
    with _provider_ctx("cursor"):
        resp = await client.post(
            "/api/idea/guided",
            json={"idea": "A tiny todo app for one user.", "step": 0},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["mode"] == "cursor_task"
    assert data["kind"] == "generate_fs"


@pytest.mark.asyncio
async def test_analyze_with_cursor_returns_task_envelope(
    client: AsyncClient, test_db, boom_direct_api, orchestration_on
):
    doc = FSDocument(
        id=uuid.uuid4(),
        filename="sample.md",
        original_text="# Spec\nDo stuff.",
        parsed_text="# Spec\nDo stuff.",
        status=FSDocumentStatus.PARSED,
        file_size=20,
        content_type="text/markdown",
    )
    test_db.add(doc)
    await test_db.commit()

    with _provider_ctx("cursor"):
        resp = await client.post(f"/api/fs/{doc.id}/analyze")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["mode"] == "cursor_task"
    assert data["kind"] == "analyze"


@pytest.mark.asyncio
async def test_reverse_fs_with_cursor_returns_task_envelope(
    client: AsyncClient, test_db, boom_direct_api, orchestration_on
):
    upload = CodeUploadDB(
        id=uuid.uuid4(),
        filename="x.zip",
        zip_path="/tmp/x.zip",
        status=CodeUploadStatus.PARSED,
        file_size=1024,
        primary_language="python",
        total_files=1,
        total_lines=10,
        languages={"python": 1},
        snapshot_data={"files": [{"path": "a.py", "language": "python", "content": "print('x')"}]},
    )
    test_db.add(upload)
    await test_db.commit()

    with _provider_ctx("cursor"):
        resp = await client.post(f"/api/code/{upload.id}/generate-fs")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["mode"] == "cursor_task"
    assert data["kind"] == "reverse_fs"


# ── Claude Code path — bridge must raise if CLI fails, never try Direct API


@pytest.mark.asyncio
async def test_generate_fs_with_claude_code_does_not_fallback(client: AsyncClient, boom_direct_api, orchestration_on):
    from app.orchestration import get_tool_registry

    prov = get_tool_registry().get("claude_code")
    assert prov is not None

    with (
        _provider_ctx("claude_code"),
        patch.object(
            prov,
            "call_llm",
            new=AsyncMock(side_effect=RuntimeError("cli down")),
        ),
    ):
        resp = await client.post(
            "/api/idea/generate",
            json={"idea": "A tiny todo app for one user."},
        )
    # The bridge raises LLMError -> errors.py maps to 502 (llm_error) or
    # 503 (claude_cli_unavailable) depending on the shape.
    assert resp.status_code in (502, 503), resp.text
    body = resp.json()
    assert "error" in body or "detail" in body
