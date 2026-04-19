"""Playbook: start_build_loop — audit → plan → build → verify for one FS."""

from __future__ import annotations

from ._graphify import GRAPHIFY_BLOCK
from ._shared import (
    BUILD_LOOP_TEMPLATE,
    GLOBAL_RULES,
    checkpoint_block,
    export_block,
    verify_block,
)


def build(
    document_id: str,
    stack: str = "Next.js + FastAPI",
    output_folder: str = "./output",
    auto_proceed: str = "true",
) -> str:
    """Render the autonomous build-loop playbook for one FS document."""
    proceed_gate = (
        "Proceed immediately — pre_build_check already validated safety."
        if str(auto_proceed).lower() == "true"
        else (
            "Show a numbered plan with task_id + section_id.\n"
            'Wait for "proceed" confirmation before starting Phase 4.'
        )
    )
    build_body = BUILD_LOOP_TEMPLATE.format(
        stack=stack, output_folder=output_folder
    )

    return f"""# AUTONOMOUS BUILD SESSION
# Document: {document_id}
# Stack:    {stack}
# Output:   {output_folder}

DEFINITION OF DONE (all must be true before the session ends):
  1. Quality score >= 90
  2. Zero unresolved HIGH-severity ambiguities
  3. Zero unresolved contradictions
  4. Every task status=COMPLETE (or explicitly skipped with justification)
  5. Every task has >= 1 registered file
  6. post_build_check verdict=GO
  7. Post-build self-heal loop (Phase 6.5) passed twice in a row, so
     the user can boot the product without ANY manual fixes.

{GLOBAL_RULES}

== PRE-FLIGHT ==

1) get_build_state("{document_id}")
     status=COMPLETE                 → Report "Already built", STOP.
     status=RUNNING + failed_task_ids→ Resume: retry failed tasks first.
     status=RUNNING + no failures    → Resume from current_task_index.
     status=PENDING or missing       → create_build_state("{document_id}").

2) run_quality_gate("{document_id}")
     If quality < 90: call refine_fs("{document_id}") up to TWO times.
     If still < 90 after two refinements: proceed WITH a logged warning.

3) pre_build_check("{document_id}")
     If go=false → fix EVERY listed blocker, re-run until go=true.
     NEVER proceed with go=false.

4) check_library_for_reuse for the first 5 tasks by description.
     Record reusable patterns for Phase 4.

5) update_build_state(current_phase=0, status="RUNNING") so the
   monitoring UI shows the session entered PRE-FLIGHT.

EXIT CRITERIA: build_state exists, quality >= 90 (or warning logged),
pre_build_check go=true.

{GRAPHIFY_BLOCK}

After Phase 0:
  update_build_state(current_phase=1)

== PHASE 1 — AUDIT ==

PARALLEL:
  get_quality_score("{document_id}")
  get_ambiguities("{document_id}")
  get_contradictions("{document_id}")
  get_sections("{document_id}")
  get_tasks("{document_id}")
  get_dependency_graph("{document_id}")

Record: total_tasks, quality_score, HIGH_ambiguity_count,
contradiction_count, edge_case_count.

EXIT CRITERIA: all six calls returned, counters recorded.

== PHASE 2 — CLEAR BLOCKERS ==

A) For each OPEN HIGH ambiguity:
     1. get_debate_results("{document_id}") for context.
     2. Draft a concrete, implementation-ready resolution.
     3. resolve_ambiguity(document_id, flag_id, resolution).

B) For each OPEN contradiction:
     accept_contradiction_suggestion("{document_id}", contradiction_id)
     If accept fails → resolve_contradiction("{document_id}", contradiction_id).

C) For each OPEN edge case with a suggestion:
     accept_edge_case_suggestion("{document_id}", edge_case_id)
     If accept fails → resolve_edge_case("{document_id}", edge_case_id).

After all three sub-phases: refresh_quality_score("{document_id}").

EXIT CRITERIA: zero OPEN HIGH ambiguities, zero OPEN contradictions,
zero OPEN edge cases, quality >= 90.

== PHASE 3 — BUILD PLAN ==

autonomous_build_from_fs("{document_id}", "{stack}")

{proceed_gate}

EXIT CRITERIA: a manifest of tasks in dependency order is in hand.

== PHASE 4 — BUILD (core implementation loop) ==

update_build_state(
  current_phase=4,
  current_task_index=0,
  status="RUNNING",
  stack="{stack}",
  output_folder="{output_folder}",
  total_tasks=<total_tasks from Phase 1>,
)

{build_body}

EXIT CRITERIA: every task either COMPLETE or explicitly skipped with a
logged justification; completed_task_ids length matches expectations.

After Phase 4 completes:
  update_build_state(current_phase=5)

{checkpoint_block()}

After Phase 5 completes:
  update_build_state(current_phase=6)

{verify_block(document_id)}

== PHASE 6.5 — POST-BUILD SELF-HEAL LOOP (run until two clean passes) ==

Goal: the user must be able to clone {output_folder}, follow the README,
and have the product run end-to-end without any extra manual effort.

For each iteration:
  a) BOOT BACKEND
       Install deps, run migrations (if any), start the backend server,
       run its full test suite. Every endpoint named in the FS must
       return the expected status, schema, and side effects.

  b) BOOT FRONTEND
       Install deps, build, start the frontend, walk every primary user
       flow named in the FS. The UI must satisfy the acceptance
       criteria of the corresponding tasks.

  c) RUN INTEGRATION / E2E TESTS
       Execute any test cases authored from get_test_cases. Any failure
       counts as a failed iteration.

  d) IF ANY STEP FAILED:
       1. Locate the failing task via get_traceability + the FS section.
       2. Patch the code, register every changed file with register_file.
       3. verify_task_completion on the affected task — must return GO.
       4. update_build_state(current_phase=6, last_updated=now,
                              failed_task_id=<task_id_if_critical>).
       5. Restart this loop from (a).

  e) IF ALL STEPS PASSED:
       Increment a private counter `clean_passes`. Repeat the loop.
       When clean_passes reaches 2 IN A ROW, exit Phase 6.5.

After Phase 6.5 completes:
  update_build_state(current_phase=7)

EXIT CRITERIA: clean_passes >= 2; backend tests, frontend flows, and
integration tests all green twice consecutively.

{export_block(document_id)}

FINAL REPORT:
  BUILD COMPLETE
  Quality: [score]/100
  Tasks: [completed]/[total]
  Files registered: [count]
  Patterns reused from library: [count]
  Skipped (with justification): [count]
  PDF report: [download_url]
"""
