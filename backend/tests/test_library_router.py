"""Tests for /api/library/... endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_library_search_empty_returns_shape(client: AsyncClient) -> None:
    resp = await client.get("/api/library/search?q=login")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data or "results" in data


@pytest.mark.asyncio
async def test_library_get_unknown_item_404s(client: AsyncClient) -> None:
    resp = await client.get(f"/api/library/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_library_suggestions_requires_known_doc(client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/fs/{uuid.uuid4()}/suggestions",
        json={"query": "auth"},
    )
    assert resp.status_code in {404, 422}
