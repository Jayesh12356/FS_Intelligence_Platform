"""Orchestration MCP tools — inspect & manage provider/tool configuration."""

from __future__ import annotations

from typing import Any, Optional

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_providers() -> dict[str, Any]:
        """
        Return all registered orchestration providers (llm, build, frontend)
        with their capabilities and current health.

        Use before selecting a provider via update_tool_config.
        Each entry exposes: name, display_name, capabilities[], healthy, health_note.
        """
        return await request_json("GET", "/api/orchestration/providers")

    @mcp.tool()
    async def get_tool_config() -> dict[str, Any]:
        """
        Return the active orchestration configuration:
        llm_provider, build_provider, frontend_provider,
        fallback_chain, cursor_config, claude_code_config.
        """
        return await request_json("GET", "/api/orchestration/config")

    @mcp.tool()
    async def update_tool_config(
        llm_provider: Optional[str] = None,
        build_provider: Optional[str] = None,
        frontend_provider: Optional[str] = None,
        fallback_chain: Optional[list[str]] = None,
        cursor_config: Optional[dict[str, Any]] = None,
        claude_code_config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Partial update of orchestration configuration.
        Only include fields you want to change.

        Validation rules:
          - provider names must be registered (see list_providers).
          - fallback_chain items must be registered providers.
          - cursor_config / claude_code_config must be objects (dicts).

        Returns the updated ToolConfig.
        """
        payload: dict[str, Any] = {}
        if llm_provider is not None:
            payload["llm_provider"] = llm_provider
        if build_provider is not None:
            payload["build_provider"] = build_provider
        if frontend_provider is not None:
            payload["frontend_provider"] = frontend_provider
        if fallback_chain is not None:
            payload["fallback_chain"] = fallback_chain
        if cursor_config is not None:
            payload["cursor_config"] = cursor_config
        if claude_code_config is not None:
            payload["claude_code_config"] = claude_code_config
        if not payload:
            return {"error": "update_tool_config called without any fields", "status_code": 400}
        return await request_json("PUT", "/api/orchestration/config", json=payload)

    @mcp.tool()
    async def test_provider(provider_name: str) -> dict[str, Any]:
        """
        Run a health / connectivity check against a single provider.

        Returns {provider, display_name, healthy, capabilities, error}.
        Use this to diagnose why a fallback chain is degraded.
        """
        return await request_json(
            "POST", f"/api/orchestration/test/{provider_name}"
        )

    @mcp.tool()
    async def get_provider_capabilities() -> dict[str, Any]:
        """
        Return the capability map: { capability: [provider_name, ...] }.
        Helpful to pick the right provider per workflow.
        """
        return await request_json("GET", "/api/orchestration/capabilities")
