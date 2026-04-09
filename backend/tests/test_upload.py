"""Tests for FS document upload, list, get, delete, and health endpoints."""

import io

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root(client: AsyncClient):
    """Root endpoint returns API info."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "FS Intelligence Platform"


@pytest.mark.asyncio
async def test_upload_txt_file(client: AsyncClient):
    """Upload a TXT file and verify response."""
    content = b"This is a test functional specification document."
    files = {"file": ("test_spec.txt", io.BytesIO(content), "text/plain")}

    response = await client.post("/api/fs/upload", files=files)
    assert response.status_code == 200

    body = response.json()
    assert body["error"] is None
    assert body["data"]["filename"] == "test_spec.txt"
    assert body["data"]["status"] == "UPLOADED"
    assert "id" in body["data"]


@pytest.mark.asyncio
async def test_upload_invalid_extension(client: AsyncClient):
    """Upload a file with invalid extension returns 400."""
    content = b"not a valid file type"
    files = {"file": ("test.exe", io.BytesIO(content), "application/octet-stream")}

    response = await client.post("/api/fs/upload", files=files)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient):
    """List documents after upload returns the document."""
    # Upload first
    content = b"Test FS document content."
    files = {"file": ("list_test.txt", io.BytesIO(content), "text/plain")}
    upload_resp = await client.post("/api/fs/upload", files=files)
    assert upload_resp.status_code == 200

    # List
    response = await client.get("/api/fs/")
    assert response.status_code == 200

    body = response.json()
    assert body["data"]["total"] >= 1
    filenames = [d["filename"] for d in body["data"]["documents"]]
    assert "list_test.txt" in filenames


@pytest.mark.asyncio
async def test_get_document(client: AsyncClient):
    """Get a specific document by ID."""
    # Upload
    content = b"Test content for get."
    files = {"file": ("get_test.txt", io.BytesIO(content), "text/plain")}
    upload_resp = await client.post("/api/fs/upload", files=files)
    doc_id = upload_resp.json()["data"]["id"]

    # Get
    response = await client.get(f"/api/fs/{doc_id}")
    assert response.status_code == 200

    body = response.json()
    assert body["data"]["id"] == doc_id
    assert body["data"]["filename"] == "get_test.txt"


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient):
    """Get a non-existent document returns 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/fs/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient):
    """Soft-delete a document and verify it disappears from list."""
    # Upload
    content = b"Test content for delete."
    files = {"file": ("delete_test.txt", io.BytesIO(content), "text/plain")}
    upload_resp = await client.post("/api/fs/upload", files=files)
    doc_id = upload_resp.json()["data"]["id"]

    # Delete
    del_response = await client.delete(f"/api/fs/{doc_id}")
    assert del_response.status_code == 200
    assert del_response.json()["data"]["deleted"] is True

    # Verify not in list
    list_response = await client.get("/api/fs/")
    ids = [d["id"] for d in list_response.json()["data"]["documents"]]
    assert doc_id not in ids

    # Verify get returns 404
    get_response = await client.get(f"/api/fs/{doc_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_get_document_status(client: AsyncClient):
    """Get the processing status of a document."""
    # Upload
    content = b"Status check test."
    files = {"file": ("status_test.txt", io.BytesIO(content), "text/plain")}
    upload_resp = await client.post("/api/fs/upload", files=files)
    doc_id = upload_resp.json()["data"]["id"]

    # Check status
    response = await client.get(f"/api/fs/{doc_id}/status")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "UPLOADED"
