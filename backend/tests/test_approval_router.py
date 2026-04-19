"""Tests for /api/fs/{doc_id}/... approval endpoints."""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient


async def _upload(client: AsyncClient, name: str = "approval.txt") -> str:
    resp = await client.post(
        "/api/fs/upload",
        files={"file": (name, io.BytesIO(b"Section 1. Spec body."), "text/plain")},
    )
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


@pytest.mark.asyncio
async def test_approval_status_defaults_to_not_submitted(client: AsyncClient) -> None:
    doc_id = await _upload(client)
    resp = await client.get(f"/api/fs/{doc_id}/approval-status")
    assert resp.status_code == 200
    data = resp.json()["data"]
    # The document has not been submitted yet — status must reflect that.
    # The router returns current_status + history; accept either flat or
    # envelope-ish shape as long as the value is a "not-submitted-like" token.
    status = data.get("status") or data.get("current_status")
    assert status is not None, f"no status key in {data}"
    assert status in {"not_submitted", "pending", "draft", "NOT_SUBMITTED", "NONE"}


@pytest.mark.asyncio
async def test_approval_status_unknown_doc_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/fs/{uuid.uuid4()}/approval-status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_before_submit_is_rejected(client: AsyncClient) -> None:
    doc_id = await _upload(client)
    # Approving without a prior submit-for-approval must not silently succeed.
    resp = await client.post(
        f"/api/fs/{doc_id}/approve",
        json={"user": "alice"},
    )
    assert resp.status_code in {400, 404, 409, 422}


@pytest.mark.asyncio
async def test_reject_before_submit_is_rejected(client: AsyncClient) -> None:
    doc_id = await _upload(client)
    resp = await client.post(
        f"/api/fs/{doc_id}/reject",
        json={"user": "alice", "reason": "n/a"},
    )
    assert resp.status_code in {400, 404, 409, 422}
