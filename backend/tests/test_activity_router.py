"""Tests for /api/activity-log."""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient

from app.db.base import Base


@pytest.mark.asyncio
async def test_activity_log_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/activity-log")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["events"] == []


@pytest.mark.asyncio
async def test_activity_log_after_upload_has_event(client: AsyncClient) -> None:
    upload = await client.post(
        "/api/fs/upload",
        files={"file": ("activity.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert upload.status_code == 200
    resp = await client.get("/api/activity-log?limit=10")
    assert resp.status_code == 200
    events = resp.json()["data"]["events"]
    # The upload endpoint should have written at least one audit event.
    assert any(e["event_type"] == "UPLOADED" for e in events)


@pytest.mark.asyncio
async def test_activity_log_event_type_filter(client: AsyncClient) -> None:
    await client.post(
        "/api/fs/upload",
        files={"file": ("etype.txt", io.BytesIO(b"x"), "text/plain")},
    )
    resp = await client.get("/api/activity-log?event_type=UPLOADED")
    assert resp.status_code == 200
    events = resp.json()["data"]["events"]
    for e in events:
        assert e["event_type"] == "UPLOADED"


@pytest.mark.asyncio
async def test_activity_log_document_name_filter_escapes_wildcards(
    client: AsyncClient,
) -> None:
    # Upload a regular file; then query with % / _ — they should not match every row.
    await client.post(
        "/api/fs/upload",
        files={"file": ("plain.txt", io.BytesIO(b"x"), "text/plain")},
    )
    resp = await client.get("/api/activity-log?document_name=%25")
    assert resp.status_code == 200
    # No filename actually contains a literal '%', so event list should be empty.
    assert resp.json()["data"]["events"] == []


@pytest.mark.asyncio
async def test_activity_log_bounds_validation(client: AsyncClient) -> None:
    bad_limit = await client.get("/api/activity-log?limit=0")
    assert bad_limit.status_code == 422

    bad_offset = await client.get("/api/activity-log?offset=-1")
    assert bad_offset.status_code == 422


_ = (Base, uuid)  # keep imports referenced for lint compatibility
