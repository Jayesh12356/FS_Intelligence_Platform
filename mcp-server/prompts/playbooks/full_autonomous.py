"""Playbook: start_full_autonomous_loop — idea → production zero-touch."""

from __future__ import annotations

from ._shared import (
    BUILD_LOOP_TEMPLATE,
    GLOBAL_RULES,
    checkpoint_block,
    export_block,
    verify_block,
)


def build(
    idea: str,
    stack: str = "Next.js + FastAPI",
    output_folder: str = "./output",
    industry: str = "",
    complexity: str = "enterprise",
) -> str:
    """Render the full idea-to-production autonomous playbook."""
    industry_line = f"\n# Industry: {industry}" if industry else ""
    build_body = BUILD_LOOP_TEMPLATE.format(
        stack=stack, output_folder=output_folder
    )

    return f"""# FULL AUTONOMOUS SESSION — IDEA TO PRODUCTION
# Idea:       {idea}
# Stack:      {stack}
# Output:     {output_folder}{industry_line}
# Complexity: {complexity}

This session takes a raw product idea and delivers a fully built codebase
with zero manual intervention. Every phase has EXPLICIT exit criteria —
do NOT advance until each criterion is met.

{GLOBAL_RULES}

== PHASE 0 — GENERATE FUNCTIONAL SPECIFICATION ==

1) generate_fs_from_idea(
     idea="{idea}",
     industry="{industry or ''}",
     complexity="{complexity}",
   )
   Save the returned document_id — every subsequent call uses it.
   If the tool errors, STOP and report "FS generation failed".

2) get_document(document_id)
   Verify status=PARSED and sections exist.

EXIT CRITERIA: document_id is valid and status=PARSED.

== PHASE 1 — FULL ANALYSIS ==

1) trigger_analysis(document_id)
   Runs the 11-node LangGraph pipeline (ambiguity, contradiction,
   edge-case, quality, task decomposition, dependencies, traceability,
   duplicate detection, test-case generation).

2) Poll get_analysis_progress(document_id) every 10 seconds until all
   nodes show completed. Retry trigger_analysis at most ONCE if any
   node ends in an error state.

EXIT CRITERIA: analysis is complete for all nodes.

== PHASE 2 — QUALITY GATE ==

1) run_quality_gate(document_id)
     score >= 90 → proceed.
     score <  90 → refine_fs(document_id) up to TWO attempts.
     still < 90  → proceed with a logged warning.

2) get_ambiguities(document_id)
   For each OPEN HIGH ambiguity:
     a) get_debate_results(document_id) for context.
     b) Draft a concrete, implementation-ready resolution.
     c) resolve_ambiguity(document_id, flag_id, resolution).

3) get_contradictions(document_id)
   For each OPEN contradiction:
     accept_contradiction_suggestion(document_id, contradiction_id)
     If accept fails → resolve_contradiction(document_id, contradiction_id).

4) get_edge_cases(document_id)
   For each OPEN edge case with a suggestion:
     accept_edge_case_suggestion(document_id, edge_case_id)
     If accept fails → resolve_edge_case(document_id, edge_case_id).

5) refresh_quality_score(document_id)

EXIT CRITERIA: quality >= 90, zero OPEN HIGH ambiguities,
zero OPEN contradictions, zero OPEN edge cases.

== PHASE 3 — BUILD SETUP ==

1) get_build_state(document_id)
     status=COMPLETE → "Already built", STOP.
     status=RUNNING  → resume from current_task_index.
     otherwise       → create_build_state(document_id).

2) pre_build_check(document_id)
     go=false → fix every listed blocker; re-run until go=true.
     NEVER proceed with go=false.

3) autonomous_build_from_fs(document_id, "{stack}")
   Read the manifest. Proceed immediately.

4) check_library_for_reuse for the first 5 tasks by description.

EXIT CRITERIA: build_state exists, pre_build_check go=true, manifest in hand.

== PHASE 4 — BUILD (implementation loop) ==

update_build_state(
  current_phase=4,
  current_task_index=0,
  status="RUNNING",
  stack="{stack}",
  output_folder="{output_folder}",
  total_tasks=<total_tasks>,
)

{build_body}

EXIT CRITERIA: every task COMPLETE or explicitly skipped with logged
justification.

{checkpoint_block()}

{verify_block("<document_id>")}

{export_block("<document_id>")}

FINAL REPORT:
  FULL AUTONOMOUS BUILD COMPLETE
  Idea: {idea}
  Quality: [score]/100
  Tasks: [completed]/[total]
  Files registered: [count]
  PDF report: [download_url]
"""
