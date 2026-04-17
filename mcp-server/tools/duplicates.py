"""Duplicate detection and library MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_duplicates(document_id: str) -> dict:
        """Detect duplicate or near-duplicate sections within a document."""
        return await request_json("GET", f"/api/fs/{document_id}/duplicates")

    @mcp.tool()
    async def get_library_item(item_id: str) -> dict:
        """Retrieve a reusable component/pattern from the shared library."""
        return await request_json("GET", f"/api/library/{item_id}")

    @mcp.tool()
    async def get_suggestions(document_id: str) -> dict:
        """Get AI-generated improvement suggestions for a document."""
        return await request_json("POST", f"/api/fs/{document_id}/suggestions")
