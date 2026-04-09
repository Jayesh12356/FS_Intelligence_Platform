"""MCP server entrypoint for FS Intelligence Platform."""

from __future__ import annotations

from fastmcp import FastMCP

from prompts import agent_loop
from resources import fs_document, task_board
from tools import analysis, collaboration, documents, exports, impact, reverse, tasks

mcp = FastMCP(
    name="fs-intelligence-platform",
    instructions=(
        "You are connected to the FS Intelligence Platform. "
        "Follow an audit-first loop: discover, analyze, plan, execute, verify, repeat."
    ),
)

documents.register(mcp)
analysis.register(mcp)
tasks.register(mcp)
impact.register(mcp)
collaboration.register(mcp)
exports.register(mcp)
reverse.register(mcp)

fs_document.register(mcp)
task_board.register(mcp)
agent_loop.register(mcp)

if __name__ == "__main__":
    mcp.run()

