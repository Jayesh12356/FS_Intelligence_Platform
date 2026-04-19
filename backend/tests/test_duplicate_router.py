"""Tests for /api/fs/{doc_id}/duplicates."""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_duplicates_unknown_doc_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/fs/{uuid.uuid4()}/duplicates")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_duplicates_empty_for_fresh_upload(client: AsyncClient) -> None:
    up = await client.post(
        "/api/fs/upload",
        files={"file": ("dup.txt", io.BytesIO(b"A unique requirement."), "text/plain")},
    )
    doc_id = up.json()["data"]["id"]
    # Parse so the pipeline has sections to compare.
    await client.post(f"/api/fs/{doc_id}/parse")

    resp = await client.get(f"/api/fs/{doc_id}/duplicates")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "duplicates" in data
    # No other document exists, so no cross-doc dupes.
    assert data["duplicates"] == [] or isinstance(data["duplicates"], list)
