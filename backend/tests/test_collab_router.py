"""Tests for collaboration endpoints: section comments + resolution."""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient


async def _upload_and_parse(client: AsyncClient) -> str:
    """Upload a tiny doc and parse so a section index exists for commenting."""
    up = await client.post(
        "/api/fs/upload",
        files={
            "file": (
                "collab.txt",
                io.BytesIO(b"1. First\nSection body one.\n2. Second\nSection body two."),
                "text/plain",
            ),
        },
    )
    doc_id = up.json()["data"]["id"]
    # Parse is synchronous for TXT uploads.
    parse = await client.post(f"/api/fs/{doc_id}/parse")
    assert parse.status_code == 200
    return doc_id


@pytest.mark.asyncio
async def test_list_comments_empty_after_upload(client: AsyncClient) -> None:
    doc_id = await _upload_and_parse(client)
    resp = await client.get(f"/api/fs/{doc_id}/comments")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "comments" in data
    assert data["comments"] == []


@pytest.mark.asyncio
async def test_add_comment_round_trip(client: AsyncClient) -> None:
    doc_id = await _upload_and_parse(client)
    add = await client.post(
        f"/api/fs/{doc_id}/sections/0/comments",
        json={"author": "alice", "text": "please clarify"},
    )
    assert add.status_code == 200
    created = add.json()["data"]
    assert created["text"] == "please clarify"
    assert created.get("resolved") in {False, None}

    listed = await client.get(f"/api/fs/{doc_id}/comments")
    assert listed.status_code == 200
    comments = listed.json()["data"]["comments"]
    assert any(c["id"] == created["id"] for c in comments)


@pytest.mark.asyncio
async def test_add_comment_on_unknown_doc_404s(client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/fs/{uuid.uuid4()}/sections/0/comments",
        json={"author": "bob", "text": "x"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_unknown_comment_404s(client: AsyncClient) -> None:
    doc_id = await _upload_and_parse(client)
    resp = await client.patch(
        f"/api/fs/{doc_id}/comments/{uuid.uuid4()}/resolve",
        json={"user": "alice"},
    )
    assert resp.status_code == 404
