"""Approval and rejection MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def reject_document(document_id: str, reason: str) -> dict:
        """Reject a document with a stated reason, moving it back for rework."""
        return await request_json(
            "POST",
            f"/api/fs/{document_id}/reject",
            json={"reason": reason, "user_id": "mcp-agent"},
        )

    @mcp.tool()
    async def get_approval_status(document_id: str) -> dict:
        """Check the current approval workflow status for a document."""
        return await request_json("GET", f"/api/fs/{document_id}/approval-status")
