"""Tests for tasks_router (/api/fs/{doc_id}/tasks, dependency-graph, traceability)."""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient


async def _upload(client: AsyncClient) -> str:
    up = await client.post(
        "/api/fs/upload",
        files={"file": ("tasks.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    return up.json()["data"]["id"]


@pytest.mark.asyncio
async def test_list_tasks_unknown_doc_returns_empty_or_404(client: AsyncClient) -> None:
    # Router is intentionally lenient and returns an empty payload for
    # unknown IDs; we accept that here but lock the shape.
    resp = await client.get(f"/api/fs/{uuid.uuid4()}/tasks")
    assert resp.status_code in {200, 404}
    if resp.status_code == 200:
        data = resp.json()["data"]
        assert (data.get("total") or 0) == 0


@pytest.mark.asyncio
async def test_list_tasks_empty_for_fresh_doc(client: AsyncClient) -> None:
    doc_id = await _upload(client)
    resp = await client.get(f"/api/fs/{doc_id}/tasks")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data.get("tasks") in ([], None) or isinstance(data.get("tasks"), list)
    # Counts must be 0 before analysis.
    assert (data.get("total") or 0) == 0


@pytest.mark.asyncio
async def test_dependency_graph_empty_for_fresh_doc(client: AsyncClient) -> None:
    doc_id = await _upload(client)
    resp = await client.get(f"/api/fs/{doc_id}/tasks/dependency-graph")
    assert resp.status_code == 200
    data = resp.json()["data"]
    # No tasks -> no nodes/edges.
    assert data.get("nodes") in ([], None)
    assert data.get("edges") in ([], None)


@pytest.mark.asyncio
async def test_traceability_empty_for_fresh_doc(client: AsyncClient) -> None:
    doc_id = await _upload(client)
    resp = await client.get(f"/api/fs/{doc_id}/traceability")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_get_unknown_task_returns_404(client: AsyncClient) -> None:
    doc_id = await _upload(client)
    resp = await client.get(f"/api/fs/{doc_id}/tasks/{uuid.uuid4()}")
    assert resp.status_code == 404
