"""Task board MCP resource."""

from __future__ import annotations

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:
    @mcp.resource("fs://task-board/{document_id}")
    async def task_board(document_id: str) -> str:
        """Compact markdown task board grouped by effort and ordering."""
        result = await request_json("GET", f"/api/fs/{document_id}/tasks")
        if "error" in result:
            return f"Error: {result['error']}"
        tasks = ((result.get("data") or {}).get("tasks")) or []
        high = [t for t in tasks if t.get("effort") == "HIGH"]
        medium = [t for t in tasks if t.get("effort") == "MEDIUM"]
        low = [t for t in tasks if t.get("effort") == "LOW"]
        lines = [f"# Task Board {document_id}", ""]
        for label, group in [("HIGH", high), ("MEDIUM", medium), ("LOW", low)]:
            lines.append(f"## {label}")
            if not group:
                lines.append("- None")
                continue
            for t in group:
                lines.append(f"- `{t.get('task_id')}` ({t.get('order')}) {t.get('title')}")
        return "\n".join(lines)

