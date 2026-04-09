"""FS document MCP resources."""

from __future__ import annotations

from fastmcp import FastMCP

from tools._http import request_json


def _to_markdown_list(items: list[dict], title: str, key: str) -> str:
    lines = [f"# {title}", ""]
    for idx, item in enumerate(items, start=1):
        lines.append(f"{idx}. {item.get(key, 'N/A')}")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    @mcp.resource("fs://documents")
    async def all_documents() -> str:
        """Browse all FS documents in the platform."""
        result = await request_json("GET", "/api/fs/")
        if "error" in result:
            return f"Error: {result['error']}"
        docs = ((result.get("data") or {}).get("documents")) or []
        lines = ["# FS Documents", ""]
        for doc in docs:
            lines.append(f"- `{doc.get('id')}` | {doc.get('filename')} | {doc.get('status')}")
        return "\n".join(lines)

    @mcp.resource("fs://documents/{document_id}/tasks")
    async def document_tasks(document_id: str) -> str:
        """Full task board for a document as formatted markdown."""
        result = await request_json("GET", f"/api/fs/{document_id}/tasks")
        if "error" in result:
            return f"Error: {result['error']}"
        tasks = ((result.get("data") or {}).get("tasks")) or []
        lines = [f"# Task Board: {document_id}", ""]
        for t in tasks:
            lines.append(f"- `{t.get('task_id')}` [{t.get('effort')}] {t.get('title')}")
            lines.append(f"  - Section: {t.get('section_heading')}")
            deps = t.get("depends_on") or []
            lines.append(f"  - Depends on: {', '.join(deps) if deps else 'None'}")
        return "\n".join(lines)

    @mcp.resource("fs://documents/{document_id}/analysis-summary")
    async def analysis_summary(document_id: str) -> str:
        """Quality score + ambiguity/contradiction/edge-case summary with top effort tasks."""
        quality = await request_json("GET", f"/api/fs/{document_id}/quality-score")
        ambiguities = await request_json("GET", f"/api/fs/{document_id}/ambiguities")
        contradictions = await request_json("GET", f"/api/fs/{document_id}/contradictions")
        edge_cases = await request_json("GET", f"/api/fs/{document_id}/edge-cases")
        tasks = await request_json("GET", f"/api/fs/{document_id}/tasks")
        if any("error" in x for x in [quality, ambiguities, contradictions, edge_cases, tasks]):
            return "Error: failed to gather one or more analysis artifacts."

        q = ((quality.get("data") or {}).get("quality_score")) or {}
        amb = (ambiguities.get("data") or [])
        con = (contradictions.get("data") or [])
        edg = (edge_cases.get("data") or [])
        task_list = ((tasks.get("data") or {}).get("tasks")) or []
        top = sorted(task_list, key=lambda t: {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(t.get("effort", ""), 0), reverse=True)[:5]

        lines = [
            f"# Analysis Summary: {document_id}",
            "",
            f"- Quality overall: {q.get('overall', 0):.2f}",
            f"- Completeness: {q.get('completeness', 0):.2f}",
            f"- Clarity: {q.get('clarity', 0):.2f}",
            f"- Consistency: {q.get('consistency', 0):.2f}",
            f"- Ambiguities: {len(amb)}",
            f"- Contradictions: {len(con)}",
            f"- Edge cases: {len(edg)}",
            "",
            "## Top Tasks By Effort",
        ]
        for t in top:
            lines.append(f"- [{t.get('effort')}] `{t.get('task_id')}` {t.get('title')}")
        return "\n".join(lines)

