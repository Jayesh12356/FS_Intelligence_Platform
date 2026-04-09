"""Reverse-FS MCP tools."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def upload_codebase(zip_path: str) -> dict:
        """Use to upload a code archive and create a reverse-generation job."""
        p = Path(zip_path)
        if not p.exists() or not p.is_file():
            return {"error": f"File not found: {zip_path}", "status_code": 400}
        with p.open("rb") as fh:
            return await request_json(
                "POST",
                "/api/code/upload",
                files={"file": (p.name, fh, "application/zip")},
            )

    @mcp.tool()
    async def generate_reverse_fs(code_upload_id: str) -> dict:
        """Use to trigger reverse FS generation from an uploaded codebase."""
        return await request_json("POST", f"/api/code/{code_upload_id}/generate-fs")

    @mcp.tool()
    async def get_generated_fs(code_upload_id: str) -> dict:
        """Use to read generated functional specification sections for a code upload."""
        return await request_json("GET", f"/api/code/{code_upload_id}/generated-fs")

    @mcp.tool()
    async def get_reverse_quality_report(code_upload_id: str) -> dict:
        """Use to inspect reverse-generation quality coverage, confidence, and gaps."""
        return await request_json("GET", f"/api/code/{code_upload_id}/report")

    @mcp.tool()
    async def list_code_uploads() -> dict:
        """Use to discover all reverse code-upload jobs and statuses."""
        return await request_json("GET", "/api/code/uploads")

