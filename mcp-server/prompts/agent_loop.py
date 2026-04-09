"""Built-in MCP prompts for autonomous execution loops."""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.prompt()
    async def start_build_loop(document_id: str) -> str:
        """Start the full audit-plan-build-verify loop for one FS document."""
        return f"""
# Autonomous Build Session — Document {document_id}

Definition of done:
- Quality score >= 90
- No unresolved HIGH ambiguities
- No unresolved contradictions
- Tasks complete and traceable

Execution protocol:
1) Audit in parallel: get_quality_score, get_ambiguities, get_contradictions, get_edge_cases, get_debate_results.
2) Triage: get_tasks, get_dependency_graph, get_traceability.
3) Resolve blockers: resolve_ambiguity on HIGH flags.
4) Implement tasks in dependency order and update_task as progress changes.
5) Verify after each batch with quality + ambiguities + traceability checks.
6) On done: export_to_jira, export_to_confluence, get_pdf_report.
"""

    @mcp.prompt()
    async def fix_single_ambiguity(document_id: str, flag_id: str) -> str:
        """Focused workflow to resolve one ambiguity flag deterministically."""
        return f"""
Resolve ambiguity `{flag_id}` in document `{document_id}`:
1) Call get_ambiguities and isolate the target.
2) Call get_debate_results and inspect relevant verdict context.
3) Draft concrete implementation-ready wording.
4) Call resolve_ambiguity(document_id="{document_id}", flag_id="{flag_id}", resolution="<your text>").
5) Re-check get_ambiguities and get_quality_score.
"""

    @mcp.prompt()
    async def implement_task(document_id: str, task_id: str) -> str:
        """Focused workflow to implement and verify one task."""
        return f"""
Implement task `{task_id}` for document `{document_id}`:
1) Call get_task and read acceptance criteria.
2) Call get_traceability for source section alignment.
3) Implement code and call update_task for metadata updates.
4) Re-check get_dependency_graph and get_quality_score.
5) Validate test coverage using get_test_cases.
"""

