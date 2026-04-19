"""Tests for /health."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_returns_200_with_expected_shape(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    data = body["data"]
    # Top-level rollup.
    assert data.get("status") in {"healthy", "unhealthy", "degraded", "unknown"}
    # Each sub-service is a top-level key alongside status; we require the
    # three observability pillars: db, llm, qdrant.
    required = {"db", "llm", "qdrant"}
    assert required <= set(data.keys()), f"missing sub-services: {required - set(data.keys())}"
    for name in required:
        svc = data[name]
        assert isinstance(svc, dict)
        assert svc.get("status") in {"healthy", "unhealthy", "degraded", "unknown", "skipped"}
