"""Tests for /api/idea endpoints (quick + guided)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class _FakeIdea:
    """Patches idea generation calls so tests never hit an LLM."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.api import idea_router

        async def fake_quick(idea: str, industry=None, complexity=None) -> str:
            return "# Intro\nA generated functional specification.\n\n# Requirements\nItem 1."

        async def fake_questions(idea: str) -> list[dict]:
            return [
                {"id": "scope", "question": "What is the scope?", "type": "text"},
                {"id": "users", "question": "Who are the users?", "type": "text"},
            ]

        async def fake_guided(idea: str, answers: dict, industry=None, complexity=None) -> str:
            return "# Generated\nFrom guided mode."

        monkeypatch.setattr(idea_router, "generate_fs_quick", fake_quick)
        monkeypatch.setattr(idea_router, "generate_guided_questions", fake_questions)
        monkeypatch.setattr(idea_router, "generate_fs_guided", fake_guided)


@pytest.mark.asyncio
async def test_quick_generate_happy_path(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeIdea(monkeypatch)
    resp = await client.post(
        "/api/idea/generate",
        json={"idea": "A dashboard for monitoring build pipelines across teams."},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["document_id"]
    assert data["fs_text"].startswith("# Intro")
    assert data["section_count"] >= 1


@pytest.mark.asyncio
async def test_quick_generate_rejects_short_idea(client: AsyncClient) -> None:
    resp = await client.post("/api/idea/generate", json={"idea": "tiny"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_guided_step0_requires_idea(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeIdea(monkeypatch)
    resp = await client.post("/api/idea/guided", json={"step": 0, "idea": ""})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_guided_step0_returns_questions(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeIdea(monkeypatch)
    resp = await client.post(
        "/api/idea/guided",
        json={"step": 0, "idea": "A platform to centralise product specs."},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"]
    assert data["step"] == 0
    assert len(data["questions"]) >= 1


@pytest.mark.asyncio
async def test_guided_step1_without_session_400(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeIdea(monkeypatch)
    resp = await client.post("/api/idea/guided", json={"step": 1, "idea": ""})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_guided_step1_unknown_session_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeIdea(monkeypatch)
    resp = await client.post(
        "/api/idea/guided",
        json={
            "step": 1,
            "session_id": "00000000-0000-0000-0000-000000000000",
            "answers": {"scope": "x"},
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_guided_full_flow_produces_document(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeIdea(monkeypatch)
    first = await client.post(
        "/api/idea/guided",
        json={"step": 0, "idea": "A platform to centralise product specs."},
    )
    session_id = first.json()["data"]["session_id"]

    second = await client.post(
        "/api/idea/guided",
        json={
            "step": 1,
            "session_id": session_id,
            "answers": {"scope": "internal tools", "users": "engineers"},
        },
    )
    assert second.status_code == 200
    data = second.json()["data"]
    assert data.get("document_id")
    assert data.get("fs_text", "").startswith("# Generated")
