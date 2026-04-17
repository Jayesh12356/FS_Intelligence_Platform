"""Tests for /api/projects CRUD and assignment endpoints."""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_project_happy_path(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/projects",
        json={"name": "Alpha", "description": "first project"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["name"] == "Alpha"
    assert body["data"]["document_count"] == 0


@pytest.mark.asyncio
async def test_create_project_duplicate_name_conflict(client: AsyncClient) -> None:
    await client.post("/api/projects", json={"name": "Beta"})
    resp = await client.post("/api/projects", json={"name": "Beta"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_projects_returns_total(client: AsyncClient) -> None:
    await client.post("/api/projects", json={"name": "Gamma"})
    await client.post("/api/projects", json={"name": "Delta"})
    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] >= 2
    names = {p["name"] for p in body["data"]["projects"]}
    assert {"Gamma", "Delta"}.issubset(names)


@pytest.mark.asyncio
async def test_get_project_not_found(client: AsyncClient) -> None:
    resp = await client.get(f"/api/projects/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_project_bad_body_is_422(client: AsyncClient) -> None:
    created = (await client.post("/api/projects", json={"name": "Epsilon"})).json()["data"]
    resp = await client.patch(
        f"/api/projects/{created['id']}",
        json={"name": 123},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_assign_document_to_project_happy_path(client: AsyncClient) -> None:
    proj = (await client.post("/api/projects", json={"name": "Zeta"})).json()["data"]
    upload = await client.post(
        "/api/fs/upload",
        files={"file": ("z.txt", io.BytesIO(b"content"), "text/plain")},
    )
    doc_id = upload.json()["data"]["id"]
    resp = await client.post(f"/api/projects/{proj['id']}/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["project_id"] == proj["id"]


@pytest.mark.asyncio
async def test_assign_document_to_missing_project_404(client: AsyncClient) -> None:
    upload = await client.post(
        "/api/fs/upload",
        files={"file": ("y.txt", io.BytesIO(b"content"), "text/plain")},
    )
    doc_id = upload.json()["data"]["id"]
    resp = await client.post(
        f"/api/projects/{uuid.uuid4()}/documents/{doc_id}",
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_project_unlinks_documents(client: AsyncClient) -> None:
    proj = (await client.post("/api/projects", json={"name": "Theta"})).json()["data"]
    upload = await client.post(
        "/api/fs/upload",
        files={"file": ("theta.txt", io.BytesIO(b"c"), "text/plain")},
    )
    doc_id = upload.json()["data"]["id"]
    await client.post(f"/api/projects/{proj['id']}/documents/{doc_id}")

    del_resp = await client.delete(f"/api/projects/{proj['id']}")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["deleted"] is True

    doc_resp = await client.get(f"/api/fs/{doc_id}")
    assert doc_resp.status_code == 200
