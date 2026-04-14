"""Document management MCP tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastmcp import FastMCP

from config import BACKEND_URL
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
        async with httpx.AsyncClient(timeout=150.0) as client:
            for attempt in range(3):
                try:
                    r = await client.post(f"{BACKEND_URL}/api/fs/{document_id}/analyze")
                    if r.status_code == 200:
                        return r.json()
                    if r.status_code == 503:
                        if attempt < 2:
                            await asyncio.sleep(5)
                            continue
                        return {
                            "error": "Backend unavailable after 3 retries",
                            "status_code": 503,
                            "suggestion": "Check backend logs and restart",
                        }
                    return {
                        "error": r.text,
                        "status_code": r.status_code,
                    }
                except httpx.TimeoutException:
                    if attempt < 2:
                        await asyncio.sleep(5)
                        continue
                    return {"error": "Request timed out after 150s"}
            return {"error": "All retry attempts failed"}

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

