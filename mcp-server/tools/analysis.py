"""Analysis MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP

from tools._http import emit_session_event, request_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_ambiguities(document_id: str) -> dict:
        """Use before implementation to identify unresolved ambiguous requirements."""
        return await request_json("GET", f"/api/fs/{document_id}/ambiguities")

    @mcp.tool()
    async def resolve_ambiguity(document_id: str, flag_id: str, resolution: str) -> dict:
        """Use after deciding a concrete resolution for one ambiguity flag."""
        # Backend currently marks as resolved directly; resolution text is returned for agent log symmetry.
        result = await request_json("PATCH", f"/api/fs/{document_id}/ambiguities/{flag_id}")
        if "error" in result:
            return result
        return {"data": {"resolution": resolution, "backend_result": result.get("data", result)}}

    @mcp.tool()
    async def get_contradictions(document_id: str) -> dict:
        """Use to detect requirement conflicts that block reliable implementation."""
        return await request_json("GET", f"/api/fs/{document_id}/contradictions")

    @mcp.tool()
    async def get_edge_cases(document_id: str) -> dict:
        """Use to identify missing negative/error-path requirements."""
        return await request_json("GET", f"/api/fs/{document_id}/edge-cases")

    @mcp.tool()
    async def get_quality_score(document_id: str) -> dict:
        """Use to track quality dashboard and verify readiness threshold."""
        return await request_json("GET", f"/api/fs/{document_id}/quality-score")

    @mcp.tool()
    async def refresh_quality_score(document_id: str) -> dict:
        """
        Recomputes quality score from current resolved state.
        Call this after EVERY batch of resolve_ambiguity calls.
        Much faster than trigger_analysis — completes in < 3 seconds.
        Returns updated overall score and sub-scores.
        If overall >= 90: proceed to export phase.
        If overall < 90: call get_edge_cases to find remaining gaps.
        """
        return await request_json("GET", f"/api/fs/{document_id}/quality-score/refresh")

    @mcp.tool()
    async def refine_fs(document_id: str) -> dict:
        """
        Rewrites the FS to fix all ambiguities, contradictions,
        and edge case gaps automatically.
        Called automatically when quality score < 90.
        After calling this, always call get_quality_score
        to confirm improvement before proceeding.
        Two refinement passes maximum per build session.
        """
        refined = await request_json("POST", f"/api/fs/{document_id}/refine")
        if "error" in refined:
            return refined
        refined_data = refined.get("data") or {}
        if float(refined_data.get("refined_score", 0.0)) < float(refined_data.get("original_score", 0.0)):
            return {
                "data": {
                    "accepted": False,
                    "reason": "Refined score is lower than original",
                    "refinement": refined_data,
                }
            }
        accepted = await request_json(
            "POST",
            f"/api/fs/{document_id}/refine/accept",
            json={"refined_text": refined_data.get("refined_text", "")},
        )
        return {"data": {"refinement": refined_data, "accept_result": accepted.get("data", accepted)}}

    @mcp.tool()
    async def run_quality_gate(document_id: str) -> dict:
        """Runs pre-phase quality gate with max 2 auto-refinement attempts."""
        await emit_session_event(
            "quality_gate_started",
            message="Starting pre-phase quality gate",
            payload={"document_id": document_id},
        )
        score_res = await get_quality_score(document_id)
        if "error" in score_res:
            await emit_session_event(
                "quality_gate_warning",
                status="error",
                message="Could not fetch quality score",
                payload={"error": score_res.get("error")},
            )
            return score_res

        current = float((((score_res.get("data") or {}).get("quality_score")) or {}).get("overall", 0.0))
        if current >= 90.0:
            await emit_session_event(
                "quality_gate_passed",
                message=f"Quality gate passed: {current}",
                payload={"score": current, "attempts": 0},
            )
            return {"data": {"passed": True, "score": current, "attempts": 0}}

        attempts = 0
        while current < 90.0 and attempts < 2:
            attempts += 1
            await emit_session_event(
                f"quality_gate_refine_attempt_{attempts}",
                phase=0,
                message=f"Refinement attempt {attempts}",
                payload={"score_before": current},
            )
            refine_res = await refine_fs(document_id)
            if "error" in refine_res:
                break
            score_res = await get_quality_score(document_id)
            if "error" in score_res:
                break
            current = float((((score_res.get("data") or {}).get("quality_score")) or {}).get("overall", 0.0))

        if current >= 90.0:
            await emit_session_event(
                "quality_gate_passed",
                message=f"Quality gate passed: {current}",
                payload={"score": current, "attempts": attempts},
            )
            return {"data": {"passed": True, "score": current, "attempts": attempts}}

        await emit_session_event(
            "quality_gate_warning",
            status="error",
            message="Warning: Could not reach 90+ after 2 refinements. Proceeding.",
            payload={"score": current, "attempts": attempts},
        )
        return {
            "data": {
                "passed": False,
                "score": current,
                "attempts": attempts,
                "warning": f"Warning: Could not reach 90+ after 2 refinements. Proceeding with score: {current}",
            }
        }

    @mcp.tool()
    async def get_compliance_tags(document_id: str) -> dict:
        """Use to review compliance-sensitive sections before coding/exports."""
        dashboard = await request_json("GET", f"/api/fs/{document_id}/quality-score")
        if "error" in dashboard:
            return dashboard
        tags = ((dashboard.get("data") or {}).get("compliance_tags")) or []
        return {"data": {"compliance_tags": tags, "total": len(tags)}}

    @mcp.tool()
    async def get_debate_results(document_id: str) -> dict:
        """Use for HIGH-severity ambiguity adjudication context before resolving."""
        return await request_json("GET", f"/api/fs/{document_id}/debate-results")

