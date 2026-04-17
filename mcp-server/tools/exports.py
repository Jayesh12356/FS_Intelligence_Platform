"""Export MCP tools."""

from __future__ import annotations

import csv
import io

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
        """
        Fetch all test cases for the document and return them as CSV text
        (plus a download URL for the backend streaming endpoint).

        Returns {data: {download_url, filename, csv, row_count, headers}}.
        Agents can write csv to disk or forward to the user directly.
        """
        res = await request_json("GET", f"/api/fs/{document_id}/test-cases")
        if "error" in res:
            return res

        data = res.get("data") or {}
        cases = data.get("test_cases") if isinstance(data, dict) else []
        if cases is None:
            cases = []

        headers = [
            "Task ID", "Title", "Type", "Preconditions",
            "Steps", "Expected Result", "Section",
        ]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        for tc in cases:
            steps = tc.get("steps") or []
            writer.writerow([
                tc.get("task_id", ""),
                tc.get("title", ""),
                tc.get("test_type", "UNIT"),
                tc.get("preconditions") or "",
                " | ".join(str(s) for s in steps),
                tc.get("expected_result") or "",
                tc.get("section_heading") or "",
            ])

        return {
            "data": {
                "download_url": f"/api/fs/{document_id}/test-cases/csv",
                "filename": f"test_cases_{document_id}.csv",
                "headers": headers,
                "row_count": len(cases),
                "csv": buf.getvalue(),
            }
        }

