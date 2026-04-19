"""Tests for /api/fs/{doc_id}/audit-log."""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_audit_log_unknown_doc_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/fs/{uuid.uuid4()}/audit-log")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_audit_log_contains_upload_event(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/fs/upload",
        files={"file": ("audit.txt", io.BytesIO(b"body"), "text/plain")},
    )
    doc_id = resp.json()["data"]["id"]

    log = await client.get(f"/api/fs/{doc_id}/audit-log")
    assert log.status_code == 200
    data = log.json()["data"]
    assert "events" in data
    assert "total" in data
    # Upload event is always recorded on a fresh document.
    event_types = {e.get("event_type") for e in data["events"]}
    assert event_types & {"UPLOADED", "uploaded", "CREATED"}
