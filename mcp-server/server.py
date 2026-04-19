"""MCP server entrypoint for FS Intelligence Platform."""

from __future__ import annotations

from fastmcp import FastMCP

from prompts import agent_loop
from resources import fs_document, task_board
from tools import analysis, approval, build, collaboration, cursor_tasks, documents, duplicates, exports, idea, impact, orchestration, projects, reverse, tasks

mcp = FastMCP(
    name="fs-intelligence-platform",
    instructions=(
        "You are connected to the FS Intelligence Platform — an enterprise system that "
        "analyzes Functional Specifications, decomposes them into tasks, and orchestrates "
        "autonomous product builds. Follow the audit-first protocol: "
        "(1) DISCOVER — fetch document, sections, quality score, and blockers. "
        "(2) ANALYZE — resolve ambiguities, contradictions, and edge cases until quality >= 90. "
        "(3) PLAN — decompose into tasks, build dependency graph, check library for reuse. "
        "(4) EXECUTE — implement each task in dependency order, register files, verify completion. "
        "(5) VERIFY — run post_build_check, confirm traceability, export artifacts. "
        "Never skip a phase. Never mark a task complete without calling verify_task_completion. "
        "If quality drops below 90 at any checkpoint, stop and fix before continuing."
    ),
)

documents.register(mcp)
idea.register(mcp)
analysis.register(mcp)
tasks.register(mcp)
impact.register(mcp)
collaboration.register(mcp)
approval.register(mcp)
exports.register(mcp)
reverse.register(mcp)
build.register(mcp)
duplicates.register(mcp)
orchestration.register(mcp)
projects.register(mcp)
cursor_tasks.register(mcp)

fs_document.register(mcp)
task_board.register(mcp)
agent_loop.register(mcp)

if __name__ == "__main__":
    mcp.run()

