"""Versioning and impact MCP tools."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def upload_version(document_id: str, file_path: str) -> dict:
        """Use to upload a new document version for impact analysis."""
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return {"error": f"File not found: {file_path}", "status_code": 400}
        with p.open("rb") as fh:
            return await request_json(
                "POST",
                f"/api/fs/{document_id}/version",
                files={"file": (p.name, fh, "application/octet-stream")},
            )

    @mcp.tool()
    async def list_versions(document_id: str) -> dict:
        """Use to inspect available FS versions for a document."""
        return await request_json("GET", f"/api/fs/{document_id}/versions")

    @mcp.tool()
    async def get_version_diff(document_id: str, v1_id: str, v2_id: str) -> dict:
        """Use to compare versions; v2_id is primary in current backend endpoint model."""
        primary = v2_id or v1_id
        return await request_json("GET", f"/api/fs/{document_id}/versions/{primary}/diff")

    @mcp.tool()
    async def get_impact_analysis(document_id: str, version_id: str) -> dict:
        """Use to evaluate task invalidation/review impact for a version change."""
        return await request_json("GET", f"/api/fs/{document_id}/impact/{version_id}")

    @mcp.tool()
    async def get_rework_estimate(document_id: str, version_id: str) -> dict:
        """Use to estimate rework effort after version changes."""
        return await request_json("GET", f"/api/fs/{document_id}/impact/{version_id}/rework")

