"""Versioning and impact MCP tools."""

from __future__ import annotations

import difflib
from pathlib import Path

from fastmcp import FastMCP

from tools._http import request_json


async def _fetch_version_text(document_id: str, version_id: str) -> dict:
    return await request_json(
        "GET", f"/api/fs/{document_id}/versions/{version_id}/text"
    )


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
    async def get_version_diff(document_id: str, v1_id: str = "", v2_id: str = "") -> dict:
        """
        Compare two FS versions for a document.

        Modes:
          * v1_id + v2_id → unified text diff between v1 and v2 (synthesised client-side
            from /versions/{id}/text, since backend diff endpoint only compares to predecessor).
          * only v2_id     → structured diff vs. v2's predecessor (backend /versions/{id}/diff).
          * only v1_id     → structured diff vs. v1's predecessor (backend /versions/{id}/diff).
        """
        v1 = (v1_id or "").strip()
        v2 = (v2_id or "").strip()
        if not v1 and not v2:
            return {"error": "Provide at least one of v1_id or v2_id", "status_code": 400}

        if v1 and v2:
            v1_res, v2_res = await _fetch_version_text(document_id, v1), await _fetch_version_text(document_id, v2)
            if "error" in v1_res:
                return v1_res
            if "error" in v2_res:
                return v2_res
            v1_text = ((v1_res.get("data") or {}).get("parsed_text")) or ""
            v2_text = ((v2_res.get("data") or {}).get("parsed_text")) or ""
            diff_lines = list(
                difflib.unified_diff(
                    v1_text.splitlines(),
                    v2_text.splitlines(),
                    fromfile=f"version/{v1}",
                    tofile=f"version/{v2}",
                    lineterm="",
                )
            )
            return {
                "data": {
                    "mode": "pairwise",
                    "v1_id": v1,
                    "v2_id": v2,
                    "unified_diff": "\n".join(diff_lines),
                    "lines_v1": len(v1_text.splitlines()),
                    "lines_v2": len(v2_text.splitlines()),
                }
            }

        primary = v2 or v1
        return await request_json("GET", f"/api/fs/{document_id}/versions/{primary}/diff")

    @mcp.tool()
    async def get_impact_analysis(document_id: str, version_id: str) -> dict:
        """Use to evaluate task invalidation/review impact for a version change."""
        return await request_json("GET", f"/api/fs/{document_id}/impact/{version_id}")

    @mcp.tool()
    async def get_rework_estimate(document_id: str, version_id: str) -> dict:
        """Use to estimate rework effort after version changes."""
        return await request_json("GET", f"/api/fs/{document_id}/impact/{version_id}/rework")

    @mcp.tool()
    async def get_version_text(document_id: str, version_id: str) -> dict:
        """Retrieve the full text content for a specific document version."""
        return await request_json("GET", f"/api/fs/{document_id}/versions/{version_id}/text")

    @mcp.tool()
    async def revert_to_version(document_id: str, version_id: str) -> dict:
        """Revert the document to a previous version's content."""
        return await request_json("POST", f"/api/fs/{document_id}/versions/{version_id}/revert")

