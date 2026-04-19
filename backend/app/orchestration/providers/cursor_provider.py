"""Cursor Provider — paste-per-action LLM and build agent.

Cursor is invoked exactly once per user action via the paste-per-action
flow (see :mod:`app.api.cursor_task_router`):

1. UI click for Generate FS / Analyze / Reverse FS mints a
   :class:`CursorTaskDB` row and returns its prompt.
2. The user pastes that prompt into the Cursor IDE chat.
3. Cursor's agent uses the MCP tools (``claim_cursor_task``,
   ``submit_generate_fs`` / ``submit_analyze`` / ``submit_reverse_fs``)
   to return the result.

For the Build step, Cursor is still driven by the kickoff prompt on the
Build page via ``mcp-server/tools/build.py``.

Design invariant
----------------

``CursorProvider.call_llm`` must **never** execute an LLM call, even
indirectly. The pipeline's ``pipeline_llm.call_llm`` is a synchronous
per-node helper and cannot be adapted to a single-shot paste flow; the
correct behaviour for ``provider == "cursor"`` is for the route handler
to branch *before* touching the pipeline and return a task envelope
instead. If anything ever reaches ``call_llm`` while Cursor is selected,
we raise loudly so the token leak is obvious rather than silently
falling back to the Direct API.
"""

from __future__ import annotations

import logging
from typing import Any

from app.orchestration.base import BuildResult, ExecutionProvider

logger = logging.getLogger(__name__)


class CursorLLMUnsupported(RuntimeError):
    """Raised whenever :meth:`CursorProvider.call_llm` is invoked.

    Cursor answers LLM work through the paste-per-action flow, not
    through :func:`pipeline_llm.call_llm`. Any caller reaching this
    provider's ``call_llm`` represents a routing bug that would
    otherwise silently fall back to another provider.
    """


class CursorProvider(ExecutionProvider):
    """Cursor IDE provider — paste-per-action Document LLM + Build."""

    name = "cursor"
    display_name = "Cursor (paste-per-action via MCP)"
    capabilities = ["llm", "build"]
    llm_selectable = True
    health_note = (
        "Cursor runs Generate FS / Analyze / Reverse FS via one "
        "paste per action: the platform shows a ready-to-paste prompt, "
        "you drop it into Cursor, and Cursor submits the result through "
        "the MCP tool. Also drives Build via the Build page kickoff."
    )

    async def call_llm(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        """Unsupported — Cursor LLM is paste-per-action only."""

        raise CursorLLMUnsupported(
            "Cursor must be invoked via the paste-per-action flow "
            "(create a CursorTask and submit via MCP). pipeline_llm "
            "should not route to CursorProvider.call_llm — check that "
            "the route handler branches on llm_provider before calling "
            "the pipeline."
        )

    async def build_task(
        self,
        task_context: dict,
        output_folder: str,
        **kwargs: Any,
    ) -> BuildResult:
        logger.info(
            "Cursor build task prepared for: %s (execute via Cursor agent mode)",
            task_context.get("title", "Unknown"),
        )
        return BuildResult(
            success=True,
            output="Build task prepared. Execute in Cursor using the start_build_loop prompt.",
        )

    async def check_health(self) -> bool:
        # Paste-per-action has no long-running component to health-check.
        # Returning True lets the Settings page show Cursor as selectable
        # without probing a non-existent worker process.
        return True
