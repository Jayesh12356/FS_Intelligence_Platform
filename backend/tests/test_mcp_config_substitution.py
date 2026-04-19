"""GET /api/orchestration/mcp-config substitutes runtime parameters.

The Build page calls this endpoint with the document id, stack, and
output folder so users get a one-click copyable kickoff string instead
of a ``<document_id>`` placeholder. Both the Cursor and Claude blocks
must include ``auto_proceed='true'`` so the kickoff text matches the
in-app build prompt at ``/api/fs/{doc_id}/build-prompt``.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_mcp_config_default_keeps_placeholder(client: AsyncClient):
    resp = await client.get("/api/orchestration/mcp-config")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "<document_id>" in data["cursor"]["agent_prompt"]
    assert "<document_id>" in data["claude_code"]["agent_prompt"]
    assert "auto_proceed='true'" in data["cursor"]["agent_prompt"]
    assert "auto_proceed='true'" in data["claude_code"]["agent_prompt"]
    assert "auto_proceed='true'" in data["claude_code"]["cli_command"]


@pytest.mark.asyncio
async def test_mcp_config_substitutes_document_id(client: AsyncClient):
    resp = await client.get(
        "/api/orchestration/mcp-config",
        params={
            "document_id": "DEADBEEF-CAFE-FEED-FACE-DEADBEEFCAFE",
            "stack": "Vue + Django",
            "output_folder": "./build/out",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    cursor_prompt = data["cursor"]["agent_prompt"]
    claude_prompt = data["claude_code"]["agent_prompt"]
    claude_cli = data["claude_code"]["cli_command"]

    assert "<document_id>" not in cursor_prompt
    assert "<document_id>" not in claude_prompt
    assert "DEADBEEF-CAFE-FEED-FACE-DEADBEEFCAFE" in cursor_prompt
    assert "DEADBEEF-CAFE-FEED-FACE-DEADBEEFCAFE" in claude_prompt
    assert "DEADBEEF-CAFE-FEED-FACE-DEADBEEFCAFE" in claude_cli

    for body in (cursor_prompt, claude_prompt, claude_cli):
        assert "stack='Vue + Django'" in body
        assert "output_folder='./build/out'" in body
        assert "auto_proceed='true'" in body

    # Echo of the supplied parameters so the UI can display them.
    assert data["document_id"] == "DEADBEEF-CAFE-FEED-FACE-DEADBEEFCAFE"
    assert data["stack"] == "Vue + Django"
    assert data["output_folder"] == "./build/out"


@pytest.mark.asyncio
async def test_mcp_config_snippets_are_valid_json(client: AsyncClient):
    resp = await client.get("/api/orchestration/mcp-config")
    data = resp.json()["data"]
    # Each snippet is JSON-serialisable and points to the same MCP entry.
    for key in ("cursor", "claude_code"):
        block = data[key]
        encoded = json.dumps(block["snippet"])
        decoded = json.loads(encoded)
        servers = decoded["mcpServers"]
        assert "fs-intelligence-platform" in servers
        assert servers["fs-intelligence-platform"]["args"] == ["mcp-server/server.py"]
