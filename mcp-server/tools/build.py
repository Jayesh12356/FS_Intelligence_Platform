"""Build-engine MCP tools — state, file registry, pre/post checks, snapshots, cache, reuse.

Every tool in this module follows the WHEN/WHAT/PITFALLS/NEXT docstring
contract so an autonomous agent reading the MCP catalogue can chain
calls without re-reading source. We also emit explicit session events
(separate from the generic ``tool_request`` traffic) so the Build
Sessions tab in /monitoring shows phase-level human messages instead
of a wall of HTTP traces.
"""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from config import BACKEND_URL  # noqa: F401  (re-exported for tests)
from tools._http import emit_session_event, request_json


def register(mcp: FastMCP) -> None:
    # ── Build State ────────────────────────────────────

    @mcp.tool()
    async def get_build_state(document_id: str) -> dict:
        """
        WHEN: Call this FIRST at session start, before any other build tool.
        WHAT: Returns current build progress — status, phase, completed/failed
              task ids, total tasks, stack, output_folder.
        PITFALLS:
          * status=COMPLETE means the build is already done — do NOT rebuild.
            Report "Already built" to the user and STOP.
          * status=RUNNING with completed_task_ids set means resume — skip
            those tasks and continue from current_task_index.
          * status=PENDING or empty body means call create_build_state next.
        NEXT: create_build_state (when missing), or run_quality_gate /
              pre_build_check before writing any code.
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
        WHEN: After EVERY phase transition AND after every task you mark
              complete or failed. Also at the end of the build with
              status="COMPLETE" or "FAILED".
        WHAT: Persists progress so a crashed session can resume from the
              same task. Also drives the per-document Lifecycle timeline
              + Activity log (each phase change emits BUILD_PHASE_CHANGED;
              each completed_task_id emits BUILD_TASK_COMPLETED).
        PITFALLS:
          * Do not skip this between tasks — without it, the user sees no
            progress and a crash forces a full rebuild.
          * Pass completed_task_id (singular) — the backend appends to the
            list and dedupes.
          * Pass status="COMPLETE" exactly once at the end so the build
            CTA on the doc detail page flips to "Built".
        NEXT: register_file for each artifact, then verify_task_completion.
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

        await emit_session_event(
            "phase_changed" if completed_task_id is None else "task_completed",
            phase=current_phase,
            message=(
                f"Task {completed_task_id} complete (phase {current_phase}, idx {current_task_index})"
                if completed_task_id
                else f"Phase {current_phase} · task {current_task_index}"
                + (f"/{total_tasks}" if total_tasks else "")
            ),
            payload={
                "current_phase": current_phase,
                "current_task_index": current_task_index,
                "completed_task_id": completed_task_id,
                "failed_task_id": failed_task_id,
                "status": status,
            },
        )
        result = await request_json(
            "PATCH", f"/api/fs/{document_id}/build-state", json=payload
        )
        if status in ("COMPLETE", "FAILED"):
            await emit_session_event(
                "build_finished" if status == "COMPLETE" else "build_failed",
                phase=current_phase,
                status="ok" if status == "COMPLETE" else "error",
                message=f"Build {status.lower()}",
                payload={"final_status": status},
            )
        return result

    @mcp.tool()
    async def create_build_state(document_id: str) -> dict:
        """
        WHEN: get_build_state returned None / status=PENDING, OR the user
              explicitly asked to restart from scratch.
        WHAT: Creates (or resets) the build_state row to PENDING with
              total_tasks pre-populated from FSTaskDB.
        PITFALLS:
          * Resetting wipes completed_task_ids — only call this on a
            fresh build, not in the middle of a resume.
        NEXT: update_build_state(status="RUNNING") at the start of Phase 4.
        """
        await emit_session_event(
            "build_state_created",
            message="Initialising build state",
            payload={"document_id": document_id},
        )
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
        WHEN: Immediately after creating or modifying ANY file during
              Phase 4. Once per file per task.
        WHAT: Persists task <-> file mapping so future requirement changes
              can do surgical updates (only re-touch the registered files).
              Also emits FILE_REGISTERED on the activity timeline.
        PITFALLS:
          * file_path MUST be relative to project root (e.g.
            "frontend/src/components/Button.tsx"). Absolute paths break
            cross-machine traceability.
          * file_type values that the platform understands:
            ``component | api | model | test | config | util | docs``.
          * Registering 0 files for a task makes verify_task_completion
            fail the "At least one file registered" check.
        NEXT: After all files are registered, call verify_task_completion.
        """
        await emit_session_event(
            "file_registered",
            message=f"+ {file_path}",
            payload={
                "task_id": task_id,
                "section_id": section_id,
                "file_path": file_path,
                "file_type": file_type,
            },
        )
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
        WHEN: A task needs updating because its FS section changed.
        WHAT: Returns the list of files previously registered to this task.
        PITFALLS:
          * Trust this list — touching files NOT in the list risks
            collateral damage to other tasks.
        NEXT: Modify only the returned files, then re-register any new
              files you create as part of the change.
        """
        return await request_json(
            "GET",
            f"/api/fs/{document_id}/file-registry",
            params={"task_id": task_id},
        )

    @mcp.tool()
    async def get_files_for_section(document_id: str, section_id: str) -> dict:
        """
        WHEN: An entire FS section changed (e.g. via revert_to_version
              or accept_edge_case_suggestion).
        WHAT: Returns every file registered against any task under the
              section — your blast radius for surgical updates.
        PITFALLS: Same as get_files_for_task — do NOT touch unrelated files.
        NEXT: place_new_requirement → get_impact_analysis → modify only
              the returned files.
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
        WHEN: Right before implementing a task in Phase 4.
        WHAT: Returns ONE rich payload with task details, the FS section
              text, test cases, dependency statuses, registered files for
              the task so far, and the target stack. Replaces a cluster
              of 4-5 separate calls.
        PITFALLS:
          * Inspect dependencies — if any has status != COMPLETE, do that
            task first, do not implement the current one yet.
          * acceptance_criteria is a list of strings, not free text — every
            item must be satisfied before verify_task_completion will pass.
        NEXT: check_library_for_reuse with task description → write code
              → register_file each artifact → verify_task_completion.
        """
        return await request_json(
            "GET", f"/api/fs/{document_id}/tasks/{task_id}/context"
        )

    # ── Task Completion Verification ───────────────────

    @mcp.tool()
    async def verify_task_completion(document_id: str, task_id: str) -> dict:
        """
        WHEN: Before calling update_build_state(completed_task_id=...) or
              update_task(status=COMPLETE).
        WHAT: Runs deterministic checks — at least one file registered,
              tests exist, every dependency COMPLETE, acceptance criteria
              addressed. Returns ``ready_for_complete`` plus a per-check
              breakdown. On verdict GO it also emits BUILD_TASK_COMPLETED
              so the activity log shows the verification, not just the
              status flip.
        PITFALLS:
          * NEVER mark a task COMPLETE while ready_for_complete=false.
            Read the failing checks list and fix each one first.
        NEXT: If GO, update_build_state(completed_task_id=task_id, status
              "RUNNING"). If NO-GO, fix gaps then call this tool again.
        """
        await emit_session_event(
            "task_verify_started",
            message=f"Verifying task {task_id}",
            payload={"task_id": task_id},
        )
        result = await request_json(
            "GET", f"/api/fs/{document_id}/tasks/{task_id}/verify"
        )
        ready = (result.get("data") or {}).get("ready_for_complete", False)
        await emit_session_event(
            "task_verified",
            status="ok" if ready else "error",
            message=(
                f"Task {task_id}: {'READY' if ready else 'NOT READY'}"
            ),
            payload=result.get("data"),
        )
        return result

    # ── Smart Requirement Placement ────────────────────

    @mcp.tool()
    async def place_new_requirement(
        document_id: str,
        new_requirement: str,
        context: str = "",
    ) -> dict:
        """
        WHEN: A new requirement arrives mid-build.
        WHAT: Uses semantic similarity to find which FS section the new
              requirement belongs to. Returns section_id, insertion_position,
              affected_tasks.
        PITFALLS:
          * Do not blindly trust placement when section_score < 0.6 — ask
            the user to confirm the section first.
        NEXT: upload_version with the updated FS text, then
              get_impact_analysis. Only ``affected_tasks`` need touching.
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
        WHEN: Right after PRE-FLIGHT, before Phase 4.
        WHAT: Returns ``go=true`` only when every safety check passes
              (quality >= 90, no open HIGH ambiguities, every section
              covered by at least one task, etc.).
        PITFALLS:
          * NEVER start Phase 4 with go=false. Building on an unstable
            spec produces tasks that will fail verify_task_completion.
          * Common fixes: refine_fs (quality), resolve_ambiguity (open
            HIGHs), trigger_analysis (uncovered sections).
        NEXT: When go=true, update_build_state(status="RUNNING") and
              proceed to Phase 4.
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
        WHEN: After every task is COMPLETE and you believe the build is
              done.
        WHAT: Returns ``verdict=GO`` only when traceability is complete
              (every section has tasks, every task has files, etc.).
        PITFALLS:
          * NO-GO is not optional — read each gap and fix it. Calling
              export_to_jira / get_pdf_report before GO ships an
              incomplete product.
        NEXT: When GO, run any final integration / smoke step the agent
              is wired up for, then export artifacts.
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
        WHEN: Before any risky operation — uploading a new FS version,
              bulk task updates, applying requirement changes.
        WHAT: Captures task statuses + file registry as a restorable point.
        PITFALLS: Save the returned snapshot_id — without it rollback
              becomes guesswork.
        NEXT: Perform the risky op, then re-check quality. Rollback if
              quality dropped > 5 points.
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
        WHEN: Quality dropped > 5 after a risky op, or bulk changes
              produced verifier errors.
        WHAT: Restores task statuses + file registry to the snapshot.
        PITFALLS: Rollback does NOT undo file content on disk — you may
              still need to delete generated files manually.
        NEXT: get_quality_score to confirm the restore worked.
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
        WHEN: FS content has substantially changed and you need genuinely
              fresh pipeline output.
        WHAT: Forces every analysis node to re-run on the next analyze.
        PITFALLS: Costs tokens — only clear when content actually changed.
        NEXT: Call trigger_analysis to regenerate everything from scratch.
        """
        return await request_json("DELETE", f"/api/fs/{document_id}/pipeline-cache")

    @mcp.tool()
    async def get_pipeline_cache_status(document_id: str) -> dict:
        """
        WHEN: Deciding whether a re-analyze will be cheap or expensive.
        WHAT: Lists which pipeline nodes have cached results.
        NEXT: clear_pipeline_cache only the nodes you really need fresh.
        """
        return await request_json("GET", f"/api/fs/{document_id}/pipeline-cache")

    # ── Library Reuse Check ────────────────────────────

    @mcp.tool()
    async def check_library_for_reuse(
        document_id: str,
        task_description: str,
    ) -> dict:
        """
        WHEN: Before writing ANY new code in Phase 4. Once per task.
        WHAT: Searches the cross-product requirement library for similar
              implementations. Returns similar_tasks, reuse_score,
              recommendation ("adapt_existing" when score > 0.85).
        PITFALLS:
          * If recommendation == "adapt_existing", do exactly that —
              copying the proven pattern saves 40-60% of token cost
              AND avoids a class of bugs already fixed elsewhere.
          * Empty library / score 0 is OK — fall through to building new.
        NEXT: If reuse, fetch the snippet from the library entry and
              adapt. If new, get_task_context then implement.
        """
        await emit_session_event(
            "library_lookup",
            message=f"Library scan: {task_description[:60]}",
            payload={"document_id": document_id},
        )
        keywords = " ".join(task_description.split()[:10])
        library_res = await request_json(
            "GET", "/api/library/search", params={"q": keywords, "limit": "5"}
        )
        if "error" in library_res:
            return {
                "data": {
                    "similar_tasks": [],
                    "reuse_score": 0.0,
                    "suggested_code": None,
                    "note": "Library empty or unavailable",
                }
            }

        items = (library_res.get("data") or {}).get("results", [])
        if not items:
            return {
                "data": {
                    "similar_tasks": [],
                    "reuse_score": 0.0,
                    "suggested_code": None,
                }
            }

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
