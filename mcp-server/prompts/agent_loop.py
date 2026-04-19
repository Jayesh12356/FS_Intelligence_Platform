"""Built-in MCP prompts for autonomous execution loops.

Each public prompt delegates to a dedicated module under
``prompts.playbooks`` so the prompt-engineering surface is auditable and
testable in isolation. Set env ``LEGACY_MCP_PLAYBOOKS=1`` to restore the
pre-v2 inline bodies (emergency rollback only).

Registered prompts:
  - start_build_loop
  - start_full_autonomous_loop
  - refine_and_analyze
  - fix_single_ambiguity
  - implement_task
  - handle_requirement_change
  - quick_analysis
  - project_overview
"""

from __future__ import annotations

import os

from fastmcp import FastMCP

from .playbooks import (
    build_loop,
    fix_ambiguity,
    full_autonomous,
    implement_task as implement_task_playbook,
    project_overview as project_overview_playbook,
    quick_analysis as quick_analysis_playbook,
    refine_analyze,
    requirement_change,
)


def _use_legacy() -> bool:
    return os.getenv("LEGACY_MCP_PLAYBOOKS", "0") in {"1", "true", "True"}


def register(mcp: FastMCP) -> None:
    @mcp.prompt()
    async def start_build_loop(
        document_id: str,
        stack: str = "Next.js + FastAPI",
        output_folder: str = "./output",
        auto_proceed: str = "true",
    ) -> str:
        """Start the full audit-plan-build-verify loop for one FS document."""
        if _use_legacy():
            return _legacy_start_build_loop(
                document_id, stack, output_folder, auto_proceed
            )
        return build_loop.build(
            document_id=document_id,
            stack=stack,
            output_folder=output_folder,
            auto_proceed=auto_proceed,
        )

    @mcp.prompt()
    async def start_full_autonomous_loop(
        idea: str,
        stack: str = "Next.js + FastAPI",
        output_folder: str = "./output",
        industry: str = "",
        complexity: str = "enterprise",
    ) -> str:
        """Zero-touch idea-to-production loop: generate FS, analyze, refine, build, export."""
        if _use_legacy():
            return _legacy_start_full_autonomous_loop(
                idea, stack, output_folder, industry, complexity
            )
        return full_autonomous.build(
            idea=idea,
            stack=stack,
            output_folder=output_folder,
            industry=industry,
            complexity=complexity,
        )

    @mcp.prompt()
    async def refine_and_analyze(document_id: str) -> str:
        """Focused loop: refine the FS, accept all fixes, re-analyze, and check quality."""
        if _use_legacy():
            return _legacy_refine_and_analyze(document_id)
        return refine_analyze.build(document_id=document_id)

    @mcp.prompt()
    async def fix_single_ambiguity(document_id: str, flag_id: str) -> str:
        """Focused workflow to resolve one ambiguity flag deterministically."""
        if _use_legacy():
            return _legacy_fix_single_ambiguity(document_id, flag_id)
        return fix_ambiguity.build(document_id=document_id, flag_id=flag_id)

    @mcp.prompt()
    async def implement_task(document_id: str, task_id: str) -> str:
        """Focused workflow to implement and verify one task."""
        if _use_legacy():
            return _legacy_implement_task(document_id, task_id)
        return implement_task_playbook.build(
            document_id=document_id, task_id=task_id
        )

    @mcp.prompt()
    async def handle_requirement_change(
        document_id: str,
        new_requirement: str,
    ) -> str:
        """Autonomous workflow for handling a new or changed requirement."""
        if _use_legacy():
            return _legacy_handle_requirement_change(
                document_id, new_requirement
            )
        return requirement_change.build(
            document_id=document_id, new_requirement=new_requirement
        )

    @mcp.prompt()
    async def quick_analysis(document_id: str) -> str:
        """Quick analysis-only flow: analyze, resolve all issues, report quality. No build."""
        if _use_legacy():
            return _legacy_quick_analysis(document_id)
        return quick_analysis_playbook.build(document_id=document_id)

    @mcp.prompt()
    async def project_overview() -> str:
        """Get a complete overview of all documents, projects, and system health."""
        if _use_legacy():
            return _LEGACY_PROJECT_OVERVIEW
        return project_overview_playbook.build()


# ---------------------------------------------------------------------------
# Legacy bodies preserved verbatim for rollback (LEGACY_MCP_PLAYBOOKS=1).
# Do NOT modify; if you need to change behaviour, update the playbook module
# and leave these as-is for emergency rollback.
# ---------------------------------------------------------------------------


def _legacy_start_build_loop(
    document_id: str,
    stack: str,
    output_folder: str,
    auto_proceed: str,
) -> str:
    proceed_gate = (
        "Proceed immediately — pre_build_check already validated safety."
        if auto_proceed.lower() == "true"
        else 'Show numbered plan with task_id + section_id.\nWait for "proceed" confirmation.'
    )
    return f"""
# AUTONOMOUS BUILD SESSION (legacy)
# Document: {document_id}
# Stack:    {stack}
# Output:   {output_folder}

{proceed_gate}
"""


def _legacy_start_full_autonomous_loop(
    idea: str,
    stack: str,
    output_folder: str,
    industry: str,
    complexity: str,
) -> str:
    industry_line = f"\n# Industry: {industry}" if industry else ""
    return f"""
# FULL AUTONOMOUS SESSION (legacy)
# Idea:       {idea}
# Stack:      {stack}
# Output:     {output_folder}{industry_line}
# Complexity: {complexity}
"""


def _legacy_refine_and_analyze(document_id: str) -> str:
    return f"# REFINE & ANALYZE LOOP (legacy) — Document {document_id}"


def _legacy_fix_single_ambiguity(document_id: str, flag_id: str) -> str:
    return (
        f"# FIX AMBIGUITY (legacy) — Document {document_id} / Flag {flag_id}"
    )


def _legacy_implement_task(document_id: str, task_id: str) -> str:
    return f"# IMPLEMENT TASK (legacy) — Document {document_id} / Task {task_id}"


def _legacy_handle_requirement_change(
    document_id: str, new_requirement: str
) -> str:
    return (
        f"# REQUIREMENT CHANGE (legacy)\n# Document: {document_id}\n"
        f'# New Requirement: "{new_requirement}"'
    )


def _legacy_quick_analysis(document_id: str) -> str:
    return f"# QUICK ANALYSIS (legacy) — Document {document_id}"


_LEGACY_PROJECT_OVERVIEW = "# SYSTEM OVERVIEW (legacy)"
