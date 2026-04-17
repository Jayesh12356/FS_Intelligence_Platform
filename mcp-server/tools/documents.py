"""Document management MCP tools."""

from __future__ import annotations

import asyncio
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
        """
        Triggers the full 11-node LangGraph analysis pipeline.
        If analysis is already running, waits for completion.
        Automatically retries up to 3 times on 503 errors.
        Returns final analysis state when complete.
        Use this to start analysis or get fresh results after
        uploading a new version or resolving contradictions.
        Always call get_quality_score immediately after this.
        If score < 90, the build loop will auto-refine before
        starting any code generation.
        """
        last: dict = {"error": "Not attempted", "status_code": 500}
        for attempt in range(3):
            res = await request_json("POST", f"/api/fs/{document_id}/analyze")
            if "error" not in res:
                return res
            last = res
            status_code = int(res.get("status_code") or 0)
            if status_code in (503, 504) and attempt < 2:
                await asyncio.sleep(5)
                continue
            break
        return last

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
            return await request_json("POST", f"/api/fs/{document_id}/parse")
        return {"data": {"sections": sections, "total": len(sections)}}

    @mcp.tool()
    async def delete_document(document_id: str) -> dict:
        """Permanently delete a document and all associated analysis data."""
        return await request_json("DELETE", f"/api/fs/{document_id}")

    @mcp.tool()
    async def reset_document_status(document_id: str) -> dict:
        """Reset a document back to 'uploaded' status so it can be re-analyzed."""
        return await request_json("POST", f"/api/fs/{document_id}/reset-status")

    @mcp.tool()
    async def edit_section(document_id: str, section_index: int, heading: str = "", content: str = "") -> dict:
        """Edit a specific section's heading and/or content by index."""
        body: dict = {}
        if heading:
            body["heading"] = heading
        if content:
            body["content"] = content
        return await request_json("PATCH", f"/api/fs/{document_id}/sections/{section_index}", json=body)

    @mcp.tool()
    async def add_section(document_id: str, heading: str, content: str) -> dict:
        """Append a new section to the document."""
        return await request_json(
            "POST",
            f"/api/fs/{document_id}/sections",
            json={"heading": heading, "content": content},
        )

