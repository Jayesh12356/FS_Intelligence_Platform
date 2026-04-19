"""Task and traceability MCP tools."""

from __future__ import annotations

from collections import defaultdict
import os
from typing import Optional

from fastmcp import FastMCP

from config import (
    MCP_DRY_RUN_DEFAULT,
    MCP_MIN_QUALITY_SCORE,
    MCP_REQUIRE_TRACEABILITY,
    MCP_REQUIRE_ZERO_HIGH_AMBIGUITIES,
)
from tools._http import emit_session_event, request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_tasks(document_id: str) -> dict:
        """Use to retrieve execution backlog with effort, tags, and dependencies."""
        return await request_json("GET", f"/api/fs/{document_id}/tasks")

    @mcp.tool()
    async def get_task(document_id: str, task_id: str) -> dict:
        """Use to inspect a single task before implementation."""
        return await request_json("GET", f"/api/fs/{document_id}/tasks/{task_id}")

    @mcp.tool()
    async def update_task(
        document_id: str,
        task_id: str,
        status: str,
        title: Optional[str] = None,
    ) -> dict:
        """
        Updates a task's status. Valid values: PENDING, IN_PROGRESS, COMPLETE.
        After calling this, immediately call get_task(document_id, task_id)
        to verify status was persisted correctly.
        If returned status does not match what you set, retry once.
        Always verify before moving to next task.
        """
        payload: dict = {"status": status}
        if title is not None:
            payload["title"] = title
        updated = await request_json(
            "PATCH",
            f"/api/fs/{document_id}/tasks/{task_id}",
            json=payload,
        )
        if "error" in updated:
            return updated
        verify = await request_json(
            "GET", f"/api/fs/{document_id}/tasks/{task_id}"
        )
        return {
            "updated": updated,
            "verified_status": (verify.get("data") or {}).get("status")
            if isinstance(verify, dict) else None,
        }

    @mcp.tool()
    async def get_dependency_graph(document_id: str) -> dict:
        """Use to schedule implementation order and parallelizable work."""
        return await request_json("GET", f"/api/fs/{document_id}/tasks/dependency-graph")

    @mcp.tool()
    async def get_traceability(document_id: str) -> dict:
        """Use to verify each task maps back to source specification sections."""
        return await request_json("GET", f"/api/fs/{document_id}/traceability")

    @mcp.tool()
    async def get_test_cases(document_id: str) -> dict:
        """Use to retrieve generated validation coverage for implemented tasks."""
        return await request_json("GET", f"/api/fs/{document_id}/test-cases")

    @mcp.tool()
    async def autonomous_build_from_fs(document_id: str, target_stack: str) -> dict:
        """Use to generate a phase-gated autonomous build manifest from FS tasks."""
        session_id = os.getenv("MCP_SESSION_ID", "").strip()
        if not session_id:
            sess = await request_json(
                "POST",
                "/api/mcp/sessions",
                json={
                    "document_id": document_id,
                    "target_stack": target_stack,
                    "source": "mcp-autonomous",
                    "dry_run": MCP_DRY_RUN_DEFAULT,
                },
            )
            session_id = str((sess.get("data") or {}).get("id") or "").strip()
            if session_id:
                os.environ["MCP_SESSION_ID"] = session_id

        await emit_session_event(
            "manifest_start",
            message="Starting autonomous_build_from_fs",
            payload={"document_id": document_id, "target_stack": target_stack},
        )
        tasks_res = await get_tasks(document_id)
        if "error" in tasks_res:
            await emit_session_event("manifest_error", status="error", message=str(tasks_res.get("error")))
            return tasks_res

        deps_res = await get_dependency_graph(document_id)
        if "error" in deps_res:
            await emit_session_event("manifest_error", status="error", message=str(deps_res.get("error")))
            return deps_res

        doc_res = await request_json("GET", f"/api/fs/{document_id}")
        quality_res = await request_json("GET", f"/api/fs/{document_id}/quality-score")
        ambiguities_res = await request_json("GET", f"/api/fs/{document_id}/ambiguities")
        trace_res = await request_json("GET", f"/api/fs/{document_id}/traceability")
        sections = ((doc_res.get("data") or {}).get("sections")) if isinstance(doc_res, dict) else None
        if sections is None:
            sections = []

        tasks = ((tasks_res.get("data") or {}).get("tasks")) or []
        adjacency = ((deps_res.get("data") or {}).get("adjacency")) or {}
        quality_score = (((quality_res.get("data") or {}).get("quality_score")) or {}).get("overall", 0)
        # The backend endpoint returns the list either as the top-level
        # ``data`` array or nested under ``data.ambiguities`` depending on
        # the router version. Accept both shapes and silently fall back to
        # an empty list for any other shape (including mocks that return a
        # sentinel dict).
        raw_amb = ambiguities_res.get("data") if isinstance(ambiguities_res, dict) else None
        if isinstance(raw_amb, list):
            ambiguities = raw_amb
        elif isinstance(raw_amb, dict):
            nested = raw_amb.get("ambiguities")
            ambiguities = nested if isinstance(nested, list) else []
        else:
            ambiguities = []
        high_open = [
            a for a in ambiguities
            if isinstance(a, dict)
            and str(a.get("severity", "")).upper() == "HIGH"
            and not bool(a.get("resolved", False))
        ]
        trace_entries = ((trace_res.get("data") or {}).get("entries")) or []
        task_ids_with_trace = {e.get("task_id") for e in trace_entries}
        orphan_tasks = [t.get("task_id") for t in tasks if t.get("task_id") not in task_ids_with_trace]

        # Build phase levels by dependency depth.
        by_id = {t.get("task_id"): t for t in tasks if t.get("task_id")}
        memo: dict[str, int] = {}

        def phase_level(task_id: str) -> int:
            if task_id in memo:
                return memo[task_id]
            deps = adjacency.get(task_id, []) or []
            if not deps:
                memo[task_id] = 1
                return 1
            level = 1 + max(phase_level(dep) for dep in deps if dep in by_id)
            memo[task_id] = level
            return level

        phase_tasks: dict[int, list[dict]] = defaultdict(list)
        for task in tasks:
            tid = task.get("task_id")
            if not tid:
                continue
            phase_tasks[phase_level(tid)].append(task)

        def infer_files_to_create(task_title: str, tags: list[str]) -> list[str]:
            title = (task_title or "").lower()
            tset = set((tags or []))
            candidates: list[str] = []
            if "frontend" in tset or "ui" in tset:
                candidates.append("frontend/src/app/<feature>/page.tsx")
            if "backend" in tset or "api" in tset:
                candidates.append("backend/app/api/<feature>_router.py")
            if "db" in tset or "database" in tset:
                candidates.append("backend/app/db/models.py")
            if "test" in tset or "qa" in tset:
                candidates.append("backend/tests/test_<feature>.py")
            if "auth" in title:
                candidates.append("backend/app/api/auth_router.py")
            if "export" in title:
                candidates.append("backend/app/api/export_router.py")
            if not candidates:
                candidates.append("docs/TODO_<feature>.md")
            return candidates

        phases: list[dict] = []
        for p in sorted(phase_tasks.keys()):
            pts = sorted(phase_tasks[p], key=lambda x: (x.get("order", 0), x.get("task_id", "")))
            task_ids = [x.get("task_id") for x in pts if x.get("task_id")]
            file_hints: list[str] = []
            for item in pts:
                file_hints.extend(infer_files_to_create(item.get("title", ""), item.get("tags", []) or []))
            dedup_file_hints = sorted(set(file_hints))
            phase_obj = {
                "phase": p,
                "target_stack": target_stack,
                "tasks": task_ids,
                "files_to_create": dedup_file_hints,
                "fs_compliance_checks": [
                    f"All tasks in phase {p} map to their source FS sections",
                    f"All acceptance criteria in phase {p} are verifiably implemented",
                ],
            }
            if p > 1:
                phase_obj["depends_on"] = [p - 1]
            phases.append(phase_obj)

        # Aggregate acceptance checklist from task acceptance criteria.
        acceptance: list[str] = []
        for t in tasks:
            for criterion in (t.get("acceptance_criteria") or []):
                txt = str(criterion).strip()
                if txt:
                    acceptance.append(txt)
        acceptance_checklist = sorted(set(acceptance))

        # One compliance check per FS section.
        fs_compliance_checks: list[str] = []
        for s in sections:
            heading = s.get("heading") or f"Section {s.get('section_index', '?')}"
            idx = s.get("section_index", "?")
            fs_compliance_checks.append(
                f"Section {idx} '{heading}' has at least one implemented and traceable task."
            )
        if not fs_compliance_checks:
            # Fallback when sections are unavailable in document detail.
            section_keys = sorted({(t.get("section_index"), t.get("section_heading")) for t in tasks})
            fs_compliance_checks = [
                f"Section {idx} '{heading or 'Untitled'}' has implemented acceptance coverage."
                for idx, heading in section_keys
            ]

        guardrail_failures: list[str] = []
        if MCP_REQUIRE_ZERO_HIGH_AMBIGUITIES and high_open:
            guardrail_failures.append(
                f"Open HIGH ambiguities detected: {len(high_open)}"
            )
        if quality_score < MCP_MIN_QUALITY_SCORE:
            guardrail_failures.append(
                f"Quality score {quality_score:.2f} below minimum {MCP_MIN_QUALITY_SCORE:.2f}"
            )
        if MCP_REQUIRE_TRACEABILITY and orphan_tasks:
            guardrail_failures.append(
                f"Traceability gap: {len(orphan_tasks)} tasks without trace links"
            )

        await emit_session_event(
            "manifest_generated",
            phase=1,
            status="ok" if not guardrail_failures else "error",
            message="Autonomous manifest generated",
            payload={
                "phases": len(phases),
                "guardrail_failures": guardrail_failures,
            },
        )

        return {
            "data": {
                "document_id": document_id,
                "session_id": session_id or None,
                "target_stack": target_stack,
                "phases": phases,
                "acceptance_checklist": acceptance_checklist,
                "fs_compliance_checks": fs_compliance_checks,
                "definition_of_done": {
                    "quality_score_min": MCP_MIN_QUALITY_SCORE,
                    "all_tasks_complete": True,
                    "zero_open_ambiguities": MCP_REQUIRE_ZERO_HIGH_AMBIGUITIES,
                    "traceability_coverage": "100%",
                },
                "guardrails": {
                    "dry_run": MCP_DRY_RUN_DEFAULT,
                    "require_traceability": MCP_REQUIRE_TRACEABILITY,
                    "high_ambiguity_blocker": MCP_REQUIRE_ZERO_HIGH_AMBIGUITIES,
                    "min_quality_score": MCP_MIN_QUALITY_SCORE,
                    "failures": guardrail_failures,
                },
                "execution_rule": (
                    "Do not start phase N+1 until phase N passes all fs_compliance_checks."
                ),
            }
        }

