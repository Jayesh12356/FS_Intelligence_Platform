"""MCP tools for the Cursor paste-per-action lifecycle (0.4.0).

These tools let the Cursor IDE act as the Document LLM for Generate
FS, Analyze and Reverse FS. The user pastes a prompt minted by the
platform; Cursor then:

1. ``claim_cursor_task`` — tells the backend it is handling the task
   (PENDING → CLAIMED).
2. ``submit_generate_fs`` / ``submit_analyze`` / ``submit_reverse_fs``
   — posts the agent's output. Backend persists it (FSDocument, etc.)
   and marks the task DONE with a ``result_ref``.
3. ``fail_cursor_task`` — abort signal when the agent cannot finish.

The backend never calls any Direct API on this path, so Cursor users
pay zero OpenRouter tokens.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from tools._http import request_json


def register(mcp: FastMCP) -> None:  # noqa: C901 — tool definitions are grouped intentionally
    @mcp.tool()
    async def claim_cursor_task(task_id: str) -> dict:
        """Claim a Cursor task so the platform stops waiting on PENDING.

        Call this *immediately* after the user pastes the task prompt
        in Cursor. The backend transitions the task from PENDING to
        CLAIMED and returns the ``input_payload`` you need (idea/
        doc_id/upload_id, etc.) plus the task ``kind``.

        Args:
            task_id: UUID of the Cursor task shown in the mega-prompt.
        """
        return await request_json(
            "POST", f"/api/cursor-tasks/{task_id}/claim"
        )

    @mcp.tool()
    async def submit_generate_fs(task_id: str, fs_markdown: str) -> dict:
        """Submit the generated FS markdown for a ``generate_fs`` task.

        The backend creates a new FSDocument in PARSED status, marks
        the task DONE, and sets ``result_ref`` to the new FSDocument
        id. The UI is polling and will navigate to the document on
        DONE.

        Args:
            task_id: UUID of the Cursor task.
            fs_markdown: The full Functional Specification document
                in markdown format (must be at least ~20 characters).
        """
        return await request_json(
            "POST",
            f"/api/cursor-tasks/{task_id}/submit/generate-fs",
            json={"fs_markdown": fs_markdown},
        )

    @mcp.tool()
    async def submit_analyze(
        task_id: str,
        quality_score: dict[str, Any],
        ambiguities: list[dict[str, Any]] | None = None,
        contradictions: list[dict[str, Any]] | None = None,
        edge_cases: list[dict[str, Any]] | None = None,
        tasks: list[dict[str, Any]] | None = None,
    ) -> dict:
        """Submit analysis results for an ``analyze`` task.

        The backend persists Ambiguities, Contradictions, EdgeCaseGaps,
        FSTasks, and TraceabilityEntries under the original FSDocument
        and marks the task DONE.

        Args:
            task_id: UUID of the Cursor task.
            quality_score: ``{overall, clarity, completeness, consistency, risks[]}``.
            ambiguities: List of ambiguity objects — see the
                mega-prompt for the exact schema (section_index,
                section_heading, flagged_text, reason, severity,
                clarification_question).
            contradictions: List of contradiction objects (section_a_*,
                section_b_*, description, severity, suggested_resolution).
            edge_cases: List of edge-case objects (section_index,
                section_heading, scenario_description, impact,
                suggested_addition).
            tasks: List of FS tasks (task_id, title, description,
                section_index, section_heading, depends_on[],
                acceptance_criteria[], effort, tags[], can_parallel).
        """
        payload = {
            "quality_score": quality_score,
            "ambiguities": ambiguities or [],
            "contradictions": contradictions or [],
            "edge_cases": edge_cases or [],
            "tasks": tasks or [],
        }
        return await request_json(
            "POST",
            f"/api/cursor-tasks/{task_id}/submit/analyze",
            json={"payload": payload},
        )

    @mcp.tool()
    async def submit_reverse_fs(
        task_id: str,
        fs_markdown: str,
        report: dict[str, Any],
    ) -> dict:
        """Submit a reverse-engineered FS for a ``reverse_fs`` task.

        The backend creates a new FSDocument from ``fs_markdown``,
        attaches it to the originating CodeUpload, updates coverage/
        confidence from ``report``, and marks the task DONE.

        Args:
            task_id: UUID of the Cursor task.
            fs_markdown: Reverse-engineered Functional Specification
                in markdown format.
            report: ``{coverage, confidence, primary_language, modules[],
                user_flows[], gaps[], notes}``.
        """
        return await request_json(
            "POST",
            f"/api/cursor-tasks/{task_id}/submit/reverse-fs",
            json={"fs_markdown": fs_markdown, "report": report},
        )

    @mcp.tool()
    async def submit_refine(
        task_id: str,
        refined_markdown: str,
        summary: str = "",
        changed_sections: list[str] | None = None,
    ) -> dict:
        """Submit a refined FS markdown for a ``refine`` task.

        The backend creates a new FSDocument (PARSED) from
        ``refined_markdown`` and marks the task DONE with
        ``result_ref`` pointing at the new FSDocument id. The UI will
        navigate to the refined document on DONE.

        Args:
            task_id: UUID of the Cursor task.
            refined_markdown: Full refined FS in markdown form (must
                be at least ~20 characters).
            summary: Short rationale for what was changed and why.
            changed_sections: Section headings that were rewritten.
        """
        return await request_json(
            "POST",
            f"/api/cursor-tasks/{task_id}/submit/refine",
            json={
                "refined_markdown": refined_markdown,
                "summary": summary,
                "changed_sections": changed_sections or [],
            },
        )

    @mcp.tool()
    async def submit_impact(
        task_id: str,
        fs_changes: list[dict[str, Any]] | None = None,
        task_impacts: list[dict[str, Any]] | None = None,
        rework_estimate: dict[str, Any] | None = None,
    ) -> dict:
        """Submit impact-analysis results for an ``impact`` task.

        The backend persists FSChanges, TaskImpacts and a single
        ReworkEstimate row against the FSVersion referenced by the
        task, and marks the task DONE.

        Args:
            task_id: UUID of the Cursor task.
            fs_changes: ``[{change_type, section_id, section_heading,
                section_index, old_text, new_text}, ...]``.
            task_impacts: ``[{task_id, task_title, impact_type, reason,
                change_section}, ...]`` where ``impact_type`` is one of
                ``INVALIDATED`` / ``REQUIRES_REVIEW`` / ``UNAFFECTED``.
            rework_estimate: ``{invalidated_count, review_count,
                unaffected_count, total_rework_days, affected_sections[],
                changes_summary}``.
        """
        payload = {
            "fs_changes": fs_changes or [],
            "task_impacts": task_impacts or [],
            "rework_estimate": rework_estimate
            or {
                "invalidated_count": 0,
                "review_count": 0,
                "unaffected_count": 0,
                "total_rework_days": 0.0,
                "affected_sections": [],
                "changes_summary": "",
            },
        }
        return await request_json(
            "POST",
            f"/api/cursor-tasks/{task_id}/submit/impact",
            json={"payload": payload},
        )

    @mcp.tool()
    async def fail_cursor_task(task_id: str, error: str) -> dict:
        """Report that a Cursor task cannot be completed.

        Use this when Cursor hits a hard stop (insufficient context,
        unsafe request, etc.). The backend marks the task FAILED and
        records the ``error`` for the UI.

        Args:
            task_id: UUID of the Cursor task.
            error: Human-readable reason the task failed.
        """
        return await request_json(
            "POST",
            f"/api/cursor-tasks/{task_id}/fail",
            json={"error": error},
        )

    @mcp.tool()
    async def get_cursor_task(task_id: str) -> dict:
        """Look up the current state of a Cursor task by id.

        Useful when the agent wants to re-check an inputs payload or
        confirm a task is still PENDING/CLAIMED before submitting.
        """
        return await request_json("GET", f"/api/cursor-tasks/{task_id}")
