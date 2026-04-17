"""Project management MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_projects() -> dict:
        """List all projects in the platform."""
        return await request_json("GET", "/api/projects")

    @mcp.tool()
    async def create_project(name: str, description: str = "") -> dict:
        """Create a new project to organize documents."""
        body: dict = {"name": name}
        if description:
            body["description"] = description
        return await request_json("POST", "/api/projects", json=body)

    @mcp.tool()
    async def get_project(project_id: str) -> dict:
        """Get details for a specific project including its documents."""
        return await request_json("GET", f"/api/projects/{project_id}")

    @mcp.tool()
    async def assign_document_to_project(project_id: str, document_id: str) -> dict:
        """Assign an existing document to a project."""
        return await request_json("POST", f"/api/projects/{project_id}/documents/{document_id}")
