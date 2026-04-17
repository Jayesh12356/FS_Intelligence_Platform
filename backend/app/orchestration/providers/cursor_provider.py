"""Cursor Provider — MCP-driven analysis and builds from the Cursor IDE.

Cursor connects to our MCP server and drives the full workflow:
analysis, refinement, task decomposition, and builds. When selected as
the LLM provider, server-side LLM calls are delegated through Direct API
(same engine the MCP tools use), while Cursor's agent orchestrates the flow.
"""

import logging
from typing import Any

from app.orchestration.base import BuildResult, ExecutionProvider

logger = logging.getLogger(__name__)


class CursorProvider(ExecutionProvider):
    """Cursor connects to our MCP server for analysis and builds.

    When selected as the LLM provider, backend pipeline LLM calls are
    routed through Direct API (the same path MCP tools use internally),
    while Cursor's agent drives the orchestration via MCP tools.
    """

    name = "cursor"
    display_name = "Cursor (IDE Agent + Plan Mode)"
    capabilities = ["llm", "build"]
    llm_selectable = True
    health_note = (
        "Checks backend MCP endpoint. Cursor drives analysis and builds "
        "via MCP tools; server-side LLM calls use Direct API as the engine."
    )

    async def call_llm(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        """Route LLM calls through Direct API when Cursor is the selected provider.

        Cursor's agent drives the workflow via MCP tools. Those tools trigger
        backend endpoints that need LLM calls — this method handles them by
        delegating to Direct API, which is the same engine the MCP tools use.
        """
        from app.llm import get_llm_client
        client = get_llm_client()
        return await client.call_llm(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            role=kwargs.get("role", "primary"),
        )

    async def build_task(
        self,
        task_context: dict,
        output_folder: str,
        **kwargs: Any,
    ) -> BuildResult:
        """Cursor build tasks are executed via MCP tool calls from Cursor's agent.

        The platform generates the build prompt and Cursor's agent mode executes it,
        calling our MCP server's tools (register_file, verify_task_completion, etc.).
        This method returns a placeholder — the actual execution happens through the
        MCP protocol initiated by the user in Cursor.
        """
        logger.info(
            "Cursor build task prepared for: %s (execute via Cursor agent mode)",
            task_context.get("title", "Unknown"),
        )
        return BuildResult(
            success=True,
            output="Build task prepared. Execute in Cursor using the start_build_loop prompt.",
        )

    async def check_health(self) -> bool:
        """Cursor health is determined by whether the MCP server can be reached.

        Since Cursor connects TO our MCP server (not the other way around),
        we check if the MCP monitoring endpoint is responsive. The base URL
        is pulled from ``settings.BACKEND_SELF_URL`` (falling back to
        ``http://localhost:8000``) so deployments can configure it.
        """
        try:
            import httpx

            from app.config import get_settings

            settings = get_settings()
            base = getattr(settings, "BACKEND_SELF_URL", None) or "http://localhost:8000"
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{base.rstrip('/')}/api/mcp/sessions")
                return resp.status_code == 200
        except Exception as exc:
            logger.debug("CursorProvider health check failed: %s", exc)
            return False
