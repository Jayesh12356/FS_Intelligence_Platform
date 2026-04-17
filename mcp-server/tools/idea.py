"""Idea-to-FS generation MCP tools."""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def generate_fs_from_idea(
        idea: str,
        industry: Optional[str] = None,
        complexity: Optional[str] = None,
    ) -> dict:
        """Generate a complete Functional Specification from a product idea.

        Returns the new document_id, filename, generated FS text, and section
        count.  The document is created in PARSED status so you can immediately
        call trigger_analysis on the returned document_id.

        Args:
            idea: Product idea description (minimum 10 characters).
            industry: Optional target industry (e.g. FinTech, HealthTech).
            complexity: Optional complexity level: simple | moderate | enterprise.
        """
        body: dict = {"idea": idea}
        if industry:
            body["industry"] = industry
        if complexity:
            body["complexity"] = complexity
        return await request_json("POST", "/api/idea/generate", json=body)

    @mcp.tool()
    async def generate_fs_guided(
        idea: str,
        session_id: Optional[str] = None,
        step: int = 0,
        answers: Optional[dict] = None,
        industry: Optional[str] = None,
        complexity: Optional[str] = None,
    ) -> dict:
        """Multi-step guided FS generation with discovery questions.

        Step 0 (no session_id): Provide the idea to receive tailored discovery
        questions and a session_id.

        Step 1+ (with session_id and answers): Submit answers to generate the
        full FS document.  Returns document_id when generation completes.

        Args:
            idea: Product idea (required for step 0, included for context on later steps).
            session_id: Session ID returned from step 0 (required for step >= 1).
            step: Current step number (0 = start, 1 = submit answers).
            answers: Dict of question_id -> answer text (required for step >= 1).
            industry: Optional target industry.
            complexity: Optional complexity level.
        """
        body: dict = {"idea": idea, "step": step}
        if session_id:
            body["session_id"] = session_id
        if answers:
            body["answers"] = answers
        if industry:
            body["industry"] = industry
        if complexity:
            body["complexity"] = complexity
        return await request_json("POST", "/api/idea/guided", json=body)
