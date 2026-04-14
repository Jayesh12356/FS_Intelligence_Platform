"""Build-engine MCP tools — state, file registry, pre/post checks, snapshots, cache, reuse."""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from config import BACKEND_URL
from tools._http import emit_session_event, request_json


def register(mcp: FastMCP) -> None:
    # ── Build State ────────────────────────────────────

    @mcp.tool()
    async def get_build_state(document_id: str) -> dict:
        """
        Returns current build progress for a document.
        Always call this FIRST at session start.
        If status=RUNNING and completed_task_ids is non-empty:
          skip those tasks — they are already done.
          resume from current_task_index.
        If status=COMPLETE: build already done, skip entirely.
        If status=PENDING or missing: start fresh build.
        This prevents rebuilding completed work on restart.
        """
        return await request_json("GET", f"/api/fs/{document_id}/build-state")

    @mcp.tool()
    async def update_build_state(
        document_id: str,
        current_phase: int,
        current_task_index: int,
        completed_task_id: Optional[str] = None,
        failed_task_id: Optional[str] = None,
        status: Optional[str] = None,
        stack: Optional[str] = None,
        output_folder: Optional[str] = None,
        total_tasks: Optional[int] = None,
    ) -> dict:
        """
        Call after EVERY completed task to persist progress.
        Pass completed_task_id to add it to the completed list.
        If Cursor crashes and restarts, get_build_state will
        return exactly where to resume.
        Never skip calling this after each task.
        """
        payload: dict = {
            "current_phase": current_phase,
            "current_task_index": current_task_index,
        }
        if completed_task_id:
            payload["completed_task_id"] = completed_task_id
        if failed_task_id:
            payload["failed_task_id"] = failed_task_id
        if status:
            payload["status"] = status
        if stack:
            payload["stack"] = stack
        if output_folder:
            payload["output_folder"] = output_folder
        if total_tasks is not None:
            payload["total_tasks"] = total_tasks
        return await request_json("PATCH", f"/api/fs/{document_id}/build-state", json=payload)

    @mcp.tool()
    async def create_build_state(document_id: str) -> dict:
        """
        Creates or resets a build state for a document.
        Call when starting a fresh build.
        If a build state already exists, it is reset to PENDING.
        """
        return await request_json("POST", f"/api/fs/{document_id}/build-state")

    # ── File Registry ──────────────────────────────────

    @mcp.tool()
    async def register_file(
        document_id: str,
        task_id: str,
        section_id: str,
        file_path: str,
        file_type: str,
    ) -> dict:
        """
        Register every file you create against its task_id.
        Call immediately after creating or modifying any file.
        file_type: component/api/model/test/config/util
        file_path: relative path from project root
        This creates the map used for surgical updates
        when requirements change in future.
        """
        return await request_json(
            "POST",
            f"/api/fs/{document_id}/file-registry",
            json={
                "task_id": task_id,
                "section_id": section_id,
                "file_path": file_path,
                "file_type": file_type,
            },
        )

    @mcp.tool()
    async def get_files_for_task(document_id: str, task_id: str) -> dict:
        """
        Returns all files created for a specific task.
        Use this when a task needs updating — only touch
        these files, nothing else.
        """
        return await request_json(
            "GET",
            f"/api/fs/{document_id}/file-registry",
            params={"task_id": task_id},
        )

    @mcp.tool()
    async def get_files_for_section(document_id: str, section_id: str) -> dict:
        """
        Returns all files linked to a FS section.
        Use this when a section requirement changes —
        only these files need updating.
        Prevents touching unrelated code.
        """
        return await request_json(
            "GET",
            f"/api/fs/{document_id}/file-registry",
            params={"section_id": section_id},
        )

    # ── Task Context ─────────────────────────────────────

    @mcp.tool()
    async def get_task_context(document_id: str, task_id: str) -> dict:
        """
        Returns everything needed to implement a task in one call:
        full task details, original FS section text, test cases,
        dependency statuses, existing files, and target stack.
        Call this INSTEAD of separate get_task + get_traceability +
        get_test_cases calls. Fewer tokens, richer context.
        """
        return await request_json(
            "GET", f"/api/fs/{document_id}/tasks/{task_id}/context"
        )

    # ── Task Completion Verification ───────────────────

    @mcp.tool()
    async def verify_task_completion(document_id: str, task_id: str) -> dict:
        """
        Checks if a task is truly ready to be marked COMPLETE.
        Verifies: files registered, test coverage exists,
        all dependencies COMPLETE, acceptance criteria covered.
        Call BEFORE update_task(status=COMPLETE).
        If ready_for_complete=false: read the checks list
        and fix each failing check before marking COMPLETE.
        """
        return await request_json(
            "GET", f"/api/fs/{document_id}/tasks/{task_id}/verify"
        )

    # ── Smart Requirement Placement ────────────────────

    @mcp.tool()
    async def place_new_requirement(
        document_id: str,
        new_requirement: str,
        context: str = "",
    ) -> dict:
        """
        When a new requirement is added, call this FIRST.
        It finds exactly which FS section the requirement
        belongs to using semantic similarity.
        Returns: section_id, insertion_position, affected_tasks
        Then call upload_version with the updated FS text.
        Then call get_impact_analysis — only affected_tasks
        will need updating, not the entire product.
        Use context to provide surrounding information about
        the new requirement for better placement accuracy.
        """
        return await request_json(
            "POST",
            f"/api/fs/{document_id}/place-requirement",
            json={"new_requirement": new_requirement, "context": context},
        )

    # ── Pre-Build Validator ────────────────────────────

    @mcp.tool()
    async def pre_build_check(document_id: str) -> dict:
        """
        Run this BEFORE writing any code.
        Returns go=true only when ALL checks pass.
        If go=false: read blockers list and fix each one.
        Common fixes:
        - quality < 90: call refine_fs first
        - open ambiguities: call resolve_ambiguity for each
        - uncovered sections: call trigger_analysis to regenerate tasks
        Never start Phase 4 if go=false.
        This prevents building on a broken foundation.
        """
        await emit_session_event(
            "pre_build_check_started",
            message="Running pre-build validation",
            payload={"document_id": document_id},
        )
        result = await request_json("GET", f"/api/fs/{document_id}/pre-build-check")
        go = (result.get("data") or {}).get("go", False)
        await emit_session_event(
            "pre_build_check_done",
            status="ok" if go else "error",
            message=f"Pre-build: {'GO' if go else 'BLOCKED'}",
            payload=result.get("data"),
        )
        return result

    # ── Post-Build Verifier ────────────────────────────

    @mcp.tool()
    async def post_build_check(document_id: str) -> dict:
        """
        Run after ALL tasks marked COMPLETE.
        Returns verdict=GO only when product is truly done.
        If verdict=NO-GO: read gaps list.
        Each gap tells you exactly what's missing.
        Fix gaps then call post_build_check again.
        Only call export_to_jira and get_pdf_report
        after verdict=GO is confirmed.
        """
        await emit_session_event(
            "post_build_check_started",
            message="Running post-build verification",
            payload={"document_id": document_id},
        )
        result = await request_json("GET", f"/api/fs/{document_id}/post-build-check")
        verdict = (result.get("data") or {}).get("verdict", "NO-GO")
        await emit_session_event(
            "post_build_check_done",
            status="ok" if verdict == "GO" else "error",
            message=f"Post-build: {verdict}",
            payload=result.get("data"),
        )
        return result

    # ── Snapshots / Rollback ───────────────────────────

    @mcp.tool()
    async def create_snapshot(document_id: str, reason: str) -> dict:
        """
        Creates a rollback point before risky operations.
        Call before: uploading new FS version, bulk task
        updates, or applying requirement changes.
        Returns snapshot_id — save this.
        If changes make things worse, call rollback_to_snapshot.
        """
        await emit_session_event(
            "snapshot_created",
            message=f"Snapshot: {reason}",
            payload={"document_id": document_id},
        )
        return await request_json(
            "POST",
            f"/api/fs/{document_id}/snapshots",
            json={"reason": reason},
        )

    @mcp.tool()
    async def rollback_to_snapshot(document_id: str, snapshot_id: str) -> dict:
        """
        Restores task states and file registry to snapshot.
        Call when post-change quality drops > 5 points
        or when bulk changes produce errors.
        After rollback: call get_quality_score to confirm
        restoration was successful.
        """
        await emit_session_event(
            "rollback_started",
            status="error",
            message="Rolling back to snapshot",
            payload={"snapshot_id": snapshot_id},
        )
        result = await request_json(
            "POST",
            f"/api/fs/{document_id}/snapshots/{snapshot_id}/rollback",
        )
        await emit_session_event(
            "rollback_done",
            message="Rollback complete",
            payload=result.get("data"),
        )
        return result

    # ── Pipeline Cache ─────────────────────────────────

    @mcp.tool()
    async def clear_pipeline_cache(document_id: str) -> dict:
        """
        Forces fresh re-run of all pipeline nodes.
        Call when FS content has substantially changed
        and you need genuinely fresh analysis.
        Without clearing: unchanged nodes return cached
        results (saves tokens and time).
        """
        return await request_json("DELETE", f"/api/fs/{document_id}/pipeline-cache")

    @mcp.tool()
    async def get_pipeline_cache_status(document_id: str) -> dict:
        """
        Shows which pipeline nodes have cached results.
        Use to understand which nodes will be skipped on re-run.
        """
        return await request_json("GET", f"/api/fs/{document_id}/pipeline-cache")

    # ── Library Reuse Check ────────────────────────────

    @mcp.tool()
    async def check_library_for_reuse(
        document_id: str,
        task_description: str,
    ) -> dict:
        """
        Before implementing any task, call this.
        Searches requirement library for similar
        implementations from previous products.
        Returns: similar_tasks, reuse_score, suggested_code
        If reuse_score > 0.85: adapt existing implementation
        instead of writing from scratch.
        Saves 40-60% of token cost on repeated patterns
        like auth, CRUD operations, dashboard stats.
        """
        keywords = " ".join(task_description.split()[:10])
        library_res = await request_json(
            "GET", "/api/library/search", params={"q": keywords, "limit": "5"}
        )
        if "error" in library_res:
            return {"data": {"similar_tasks": [], "reuse_score": 0.0, "suggested_code": None, "note": "Library empty or unavailable"}}

        items = (library_res.get("data") or {}).get("results", [])
        if not items:
            return {"data": {"similar_tasks": [], "reuse_score": 0.0, "suggested_code": None}}

        scored = [
            {
                "entry_id": item.get("id", ""),
                "text": item.get("text", ""),
                "score": round(float(item.get("score", 0.0)), 3),
                "section_heading": item.get("section_heading", ""),
            }
            for item in items
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        best_score = scored[0]["score"] if scored else 0.0

        return {
            "data": {
                "similar_tasks": scored[:5],
                "reuse_score": round(best_score, 3),
                "suggested_code": None,
                "recommendation": "adapt_existing" if best_score > 0.85 else "build_new",
            }
        }
