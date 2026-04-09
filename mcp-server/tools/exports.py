"""Export MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def export_to_jira(document_id: str) -> dict:
        """Use to publish generated tasks to Jira (or simulated mode)."""
        return await request_json("POST", f"/api/fs/{document_id}/export/jira")

    @mcp.tool()
    async def export_to_confluence(document_id: str) -> dict:
        """Use to publish analysis summary to Confluence (or simulated mode)."""
        return await request_json("POST", f"/api/fs/{document_id}/export/confluence")

    @mcp.tool()
    async def get_pdf_report(document_id: str) -> dict:
        """Use to generate and retrieve PDF report metadata/download URL."""
        return await request_json("GET", f"/api/fs/{document_id}/export/pdf")

    @mcp.tool()
    async def get_docx_report(document_id: str) -> dict:
        """Use to generate and retrieve DOCX report metadata/download URL."""
        return await request_json("GET", f"/api/fs/{document_id}/export/docx")

    @mcp.tool()
    async def export_test_cases_csv(document_id: str) -> dict:
        """Use to get downloadable CSV route for generated test cases."""
        # Endpoint streams CSV directly; return stable URL for agent use.
        return {"data": {"download_url": f"/api/fs/{document_id}/test-cases/csv"}}

