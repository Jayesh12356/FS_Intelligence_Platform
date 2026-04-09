"""Document management MCP tools."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_documents() -> dict:
        """Use first to discover available FS documents and their statuses."""
        return await request_json("GET", "/api/fs/")

    @mcp.tool()
    async def get_document(document_id: str) -> dict:
        """Use when you need full details and parsed text for one document."""
        return await request_json("GET", f"/api/fs/{document_id}")

    @mcp.tool()
    async def upload_document(file_path: str) -> dict:
        """Use to ingest a local FS file (.pdf/.docx/.txt) into the platform."""
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return {"error": f"File not found: {file_path}", "status_code": 400}
        with p.open("rb") as fh:
            return await request_json(
                "POST",
                "/api/fs/upload",
                files={"file": (p.name, fh, "application/octet-stream")},
            )

    @mcp.tool()
    async def trigger_analysis(document_id: str) -> dict:
        """Use after parse/ingest to run the full analysis pipeline."""
        return await request_json("POST", f"/api/fs/{document_id}/analyze")

    @mcp.tool()
    async def get_document_status(document_id: str) -> dict:
        """Use for polling document processing/analyze status."""
        return await request_json("GET", f"/api/fs/{document_id}/status")

    @mcp.tool()
    async def get_sections(document_id: str) -> dict:
        """Use to inspect parsed section structure before task execution."""
        doc = await request_json("GET", f"/api/fs/{document_id}")
        if "error" in doc:
            return doc
        data = doc.get("data", {}) if isinstance(doc, dict) else {}
        sections = data.get("sections")
        if sections is None:
            # If sections are not present yet, trigger parse and return parse result.
            return await request_json("POST", f"/api/fs/{document_id}/parse")
        return {"data": {"sections": sections, "total": len(sections)}}

