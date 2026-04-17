"""Tests for /api/orchestration endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_providers_returns_registered(client: AsyncClient) -> None:
    resp = await client.get("/api/orchestration/providers")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)
    names = {p["name"] for p in data}
    # Core providers registered in app.orchestration: api, cursor, claude_code.
    assert {"api", "cursor", "claude_code"}.issubset(names)
    for p in data:
        assert "display_name" in p
        assert "capabilities" in p
        assert isinstance(p["capabilities"], list)


@pytest.mark.asyncio
async def test_get_config_creates_default(client: AsyncClient) -> None:
    resp = await client.get("/api/orchestration/config")
    assert resp.status_code == 200
    data = resp.json()["data"]
    for field in (
        "llm_provider", "build_provider", "frontend_provider",
        "fallback_chain", "cursor_config", "claude_code_config",
    ):
        assert field in data


@pytest.mark.asyncio
async def test_update_config_happy_path(client: AsyncClient) -> None:
    payload = {
        "llm_provider": "api",
        "fallback_chain": ["api", "claude_code"],
        "cursor_config": {"mcp_session_ttl_s": 7200},
    }
    resp = await client.put("/api/orchestration/config", json=payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["llm_provider"] == "api"
    assert data["fallback_chain"] == ["api", "claude_code"]
    assert data["cursor_config"].get("mcp_session_ttl_s") == 7200


@pytest.mark.asyncio
async def test_update_config_rejects_unknown_llm_provider(client: AsyncClient) -> None:
    resp = await client.put(
        "/api/orchestration/config",
        json={"llm_provider": "definitely-not-a-provider"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_test_provider_unknown_returns_404(client: AsyncClient) -> None:
    resp = await client.post("/api/orchestration/test/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_capabilities_map(client: AsyncClient) -> None:
    resp = await client.get("/api/orchestration/capabilities")
    assert resp.status_code == 200
    cap_map = resp.json()["data"]
    assert isinstance(cap_map, dict)
    assert "llm" in cap_map
    assert isinstance(cap_map["llm"], list)
