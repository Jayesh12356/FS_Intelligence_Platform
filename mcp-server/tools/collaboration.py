"""Collaboration and governance MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_comments(document_id: str) -> dict:
        """Use to inspect section discussions and unresolved feedback."""
        return await request_json("GET", f"/api/fs/{document_id}/comments")

    @mcp.tool()
    async def add_comment(document_id: str, section_id: int, content: str) -> dict:
        """Use to add review remarks against a specific section index."""
        return await request_json(
            "POST",
            f"/api/fs/{document_id}/sections/{section_id}/comments",
            json={"text": content, "user_id": "mcp-agent"},
        )

    @mcp.tool()
    async def resolve_comment(document_id: str, comment_id: str) -> dict:
        """Use to close a comment once addressed in code/spec."""
        return await request_json("PATCH", f"/api/fs/{document_id}/comments/{comment_id}/resolve")

    @mcp.tool()
    async def submit_for_approval(document_id: str) -> dict:
        """Use to move a completed document into approval workflow."""
        return await request_json(
            "POST",
            f"/api/fs/{document_id}/submit-for-approval",
            json={"approver_id": "mcp-agent", "comment": "Submitted via MCP"},
        )

    @mcp.tool()
    async def approve_document(document_id: str, approval_id: str) -> dict:
        """Use to approve a pending document after checks are complete."""
        return await request_json(
            "POST",
            f"/api/fs/{document_id}/approve",
            json={"approver_id": f"mcp-agent:{approval_id}", "comment": "Approved via MCP"},
        )

    @mcp.tool()
    async def get_audit_trail(document_id: str) -> dict:
        """Use to review chronological system actions for governance/debugging."""
        return await request_json("GET", f"/api/fs/{document_id}/audit-log")

