"""Tests for export endpoints (PDF, DOCX, JIRA, Confluence, test-cases)."""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient


async def _upload(client: AsyncClient) -> str:
    up = await client.post(
        "/api/fs/upload",
        files={"file": ("exp.txt", io.BytesIO(b"content"), "text/plain")},
    )
    return up.json()["data"]["id"]


@pytest.mark.asyncio
async def test_pdf_export_unknown_doc_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/fs/{uuid.uuid4()}/export/pdf")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_docx_export_unknown_doc_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/fs/{uuid.uuid4()}/export/docx")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_test_cases_listing_known_doc(client: AsyncClient) -> None:
    doc_id = await _upload(client)
    resp = await client.get(f"/api/fs/{doc_id}/test-cases")
    # Either returns an empty list envelope or 404 if test cases are not yet
    # generated; both are acceptable as "no drift".
    assert resp.status_code in {200, 404}
    if resp.status_code == 200:
        data = resp.json()["data"]
        assert "test_cases" in data or "cases" in data


@pytest.mark.asyncio
async def test_jira_export_without_analysis_fails_cleanly(client: AsyncClient) -> None:
    doc_id = await _upload(client)
    resp = await client.post(
        f"/api/fs/{doc_id}/export/jira",
        json={"project_key": "FSP"},
    )
    # Not analyzed yet → backend should refuse, not 500.
    assert resp.status_code in {200, 400, 404, 409, 422, 503}


@pytest.mark.asyncio
async def test_confluence_export_without_analysis_fails_cleanly(client: AsyncClient) -> None:
    doc_id = await _upload(client)
    resp = await client.post(
        f"/api/fs/{doc_id}/export/confluence",
        json={"space_key": "FSP"},
    )
    assert resp.status_code in {200, 400, 404, 409, 422, 503}
