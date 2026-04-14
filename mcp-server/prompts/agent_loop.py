"""Built-in MCP prompts for autonomous execution loops."""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.prompt()
    async def start_build_loop(
        document_id: str,
        stack: str = "Next.js + FastAPI",
        output_folder: str = "./output",
        auto_proceed: str = "true",
    ) -> str:
        """Start the full audit-plan-build-verify loop for one FS document."""
        proceed_gate = (
            'Proceed immediately — pre_build_check already validated safety.'
            if auto_proceed.lower() == "true"
            else 'Show numbered plan with task_id + section_id.\nWait for "proceed" confirmation.'
        )
        return f"""
# AUTONOMOUS BUILD SESSION
# Document: {document_id}
# Stack:    {stack}
# Output:   {output_folder}

DEFINITION OF DONE (all must be true before session ends):
  1. Quality score >= 90
  2. Zero unresolved HIGH ambiguities
  3. Zero unresolved contradictions
  4. Every task status = COMPLETE (or explicitly skipped with justification)
  5. Every task has >= 1 registered file
  6. post_build_check verdict = GO

CRITICAL RULES:
  - NEVER write code before completing PRE-FLIGHT and PHASE 1-2.
  - NEVER mark a task COMPLETE without calling verify_task_completion first.
  - NEVER proceed past a phase gate when its exit criteria are not met.
  - If ANY tool call returns an error, retry once. If it fails again, log it and continue.

== PRE-FLIGHT ==

1) get_build_state("{document_id}")
   - status=COMPLETE → Report "Already built", STOP.
   - status=RUNNING + failed_task_ids non-empty → Resume: retry failed tasks first.
   - status=RUNNING + no failures → Resume from current_task_index.
   - status=PENDING or missing → create_build_state("{document_id}"), continue.

2) run_quality_gate("{document_id}")
   - If quality < 90: call refine_fs("{document_id}") up to 2 times.
   - If still < 90 after refinement: proceed with warning logged.

3) pre_build_check("{document_id}")
   - If go=false → Fix EVERY listed blocker. Re-run until go=true.
   - NEVER proceed with go=false.

4) check_library_for_reuse for the first 5 tasks by description.
   Note reusable patterns for Phase 4.

== PHASE 1 — AUDIT ==

Call ALL of these in parallel (one batch of tool calls):
  get_quality_score("{document_id}")
  get_ambiguities("{document_id}")
  get_contradictions("{document_id}")
  get_sections("{document_id}")
  get_tasks("{document_id}")
  get_dependency_graph("{document_id}")

Record: total_tasks, quality_score, HIGH_ambiguity_count, contradiction_count.

== PHASE 2 — CLEAR BLOCKERS ==

For each OPEN HIGH ambiguity:
  1. get_debate_results("{document_id}") for context
  2. Draft concrete, implementation-ready resolution text
  3. resolve_ambiguity(document_id, flag_id, resolution)
After resolving all: refresh_quality_score("{document_id}")
Exit criteria: zero OPEN HIGH ambiguities AND quality >= 90.

== PHASE 3 — BUILD PLAN ==

autonomous_build_from_fs("{document_id}", "{stack}")
{proceed_gate}

== PHASE 4 — BUILD (core implementation loop) ==

update_build_state(status="RUNNING", stack="{stack}", output_folder="{output_folder}")

For EACH task in dependency order:

  a) SKIP CHECK: If task_id is in get_build_state().completed_task_ids → skip.

  b) REUSE CHECK: check_library_for_reuse(document_id, task_description).
     If reuse_score > 0.85 → adapt the pattern instead of writing from scratch.

  c) CONTEXT: get_task_context("{document_id}", task_id)
     This returns: task details, acceptance criteria, FS section text,
     test cases, dependency statuses, existing registered files, target stack.

  d) IMPLEMENT: Write code in {output_folder}. Follow acceptance criteria exactly.
     Use the stack specified. Create clean, production-quality code.

  e) REGISTER: register_file(document_id, task_id, section_id, path, type)
     for EVERY file created or modified. Missing registrations = traceability gaps.

  f) VERIFY: verify_task_completion("{document_id}", task_id)
     If ANY check fails → fix the gap, re-verify. Do NOT proceed with failures.

  g) MARK COMPLETE: update_task(document_id, task_id, status="COMPLETE")
     Confirm with get_task that status persisted.

  h) PERSIST PROGRESS: update_build_state with completed_task_id.

ERROR RECOVERY (if steps c-f fail):
  1. update_build_state with failed_task_id.
  2. Non-critical task (effort=LOW, no dependents) → skip with warning, continue.
  3. Critical task → retry ONCE with a simpler implementation approach.
  4. If still fails → create_snapshot, skip task, continue.
  5. Skipped tasks surface in Phase 6 gap report.

== PHASE 5 — CHECKPOINT (every 5 completed tasks) ==

refresh_quality_score → must stay >= 90 (if drops: get_edge_cases, fix gaps).
get_traceability → zero orphaned tasks.
get_build_state → confirm completed_task_ids matches expectations.

== PHASE 6 — VERIFY ==

post_build_check("{document_id}")
If verdict=NO-GO → fix every listed gap, re-run post_build_check.
Loop until verdict=GO. Do NOT proceed to export with NO-GO.

== PHASE 7 — EXPORT & REPORT ==

export_to_jira("{document_id}")
get_pdf_report("{document_id}")
update_build_state(status="COMPLETE")

Final report:
  BUILD COMPLETE
  Quality: [score]/100
  Tasks: [completed]/[total]
  Files registered: [count]
  Patterns reused from library: [count]
  Skipped (with justification): [count]
  PDF report: [download_url]
"""

    @mcp.prompt()
    async def fix_single_ambiguity(document_id: str, flag_id: str) -> str:
        """Focused workflow to resolve one ambiguity flag deterministically."""
        return f"""
Resolve ambiguity flag `{flag_id}` in document `{document_id}`.

STEPS:
1) get_ambiguities("{document_id}") — find the flag with id={flag_id}. Read its flagged_text, reason, and severity.
2) get_debate_results("{document_id}") — check if this flag was debated. Read the arbiter's reasoning.
3) Draft a resolution: a CONCRETE, IMPLEMENTATION-READY replacement for the ambiguous text.
   - Use specific numbers, conditions, and behaviors (no vague language).
   - The resolution must be a complete sentence or paragraph that a developer can implement directly.
   - Example BAD resolution: "Make it faster" — Example GOOD resolution: "The API shall respond within 200ms at the 95th percentile under 1000 concurrent users."
4) resolve_ambiguity(document_id="{document_id}", flag_id="{flag_id}", resolution="<your resolution text>")
5) VERIFY: get_ambiguities("{document_id}") — confirm the flag is now resolved.
6) refresh_quality_score("{document_id}") — confirm quality improved or held.
"""

    @mcp.prompt()
    async def implement_task(document_id: str, task_id: str) -> str:
        """Focused workflow to implement and verify one task."""
        return f"""
Implement task `{task_id}` for document `{document_id}`.

STEP 1 — GATHER CONTEXT:
  get_task_context("{document_id}", "{task_id}")
  This returns: task title, description, acceptance criteria, original FS section text,
  test cases, dependency task statuses, already-registered files, and target stack.
  READ ALL OF IT before writing any code.

STEP 2 — CHECK DEPENDENCIES:
  If any dependency task is not COMPLETE, implement those first (call implement_task for each).
  Never implement a task whose dependencies are unfinished.

STEP 3 — IMPLEMENT:
  Write production-quality code that satisfies EVERY acceptance criterion.
  Follow the target stack conventions. Use the FS section text as the source of truth.
  If a reusable pattern was noted (from check_library_for_reuse), adapt it.

STEP 4 — REGISTER:
  register_file(document_id="{document_id}", task_id="{task_id}", section_id=<from context>,
                path=<file path>, type=<"source"|"test"|"config"|"migration">)
  for EVERY file created or modified. Missing registrations break traceability.

STEP 5 — VERIFY:
  verify_task_completion("{document_id}", "{task_id}")
  If ANY check fails: fix the code, re-verify. Do NOT proceed with failures.

STEP 6 — MARK DONE:
  update_task(document_id="{document_id}", task_id="{task_id}", status="COMPLETE")
  update_build_state with completed_task_id="{task_id}"
  Confirm with get_task that status=COMPLETE persisted.
"""

    @mcp.prompt()
    async def handle_requirement_change(
        document_id: str,
        new_requirement: str,
    ) -> str:
        """Autonomous workflow for handling a new or changed requirement."""
        return f"""
# REQUIREMENT CHANGE SESSION
# Document: {document_id}
# New Requirement: "{new_requirement}"

This workflow safely integrates a new or changed requirement into an existing build.
Every step has a rollback safety net. Do NOT skip steps.

== STEP 1 — SAFETY SNAPSHOT ==
create_snapshot("{document_id}", reason="pre-requirement-change")
Save the returned snapshot_id — you will need it for rollback.

== STEP 2 — PLACE REQUIREMENT ==
place_new_requirement("{document_id}", "{new_requirement}")
Read the response: best_section (where to insert), affected_tasks (what will change).
If affected_tasks is empty, the requirement is additive — proceed with less caution.

== STEP 3 — UPDATE FS DOCUMENT ==
get_document("{document_id}") to get current FS text.
Insert the new requirement into the identified section using formal FS language:
  "The system shall [new behavior] when [condition]."
Upload the updated text as a new version via upload_version.
Save the returned version_id.

== STEP 4 — IMPACT ANALYSIS ==
get_impact_analysis("{document_id}", version_id)
Classify every task: INVALIDATED, REQUIRES_REVIEW, or UNAFFECTED.
Count: invalidated_count, review_count.

== STEP 5 — RE-ANALYZE ==
trigger_analysis("{document_id}")
Wait for completion (poll get_document status until COMPLETE).
refresh_quality_score("{document_id}") — record new score.

== STEP 6 — RE-IMPLEMENT AFFECTED TASKS ==
For each INVALIDATED task (in dependency order):
  a) update_task status=IN_PROGRESS
  b) get_task_context for updated FS section text + new acceptance criteria
  c) get_files_for_task to find existing files to modify (not rewrite from scratch)
  d) Modify ONLY the affected files — preserve working code
  e) register_file for any NEW files created
  f) verify_task_completion — all criteria must pass
  g) update_task status=COMPLETE
  h) update_build_state with completed_task_id

For each REQUIRES_REVIEW task:
  a) get_task_context — read updated section
  b) If acceptance criteria still pass with no code changes → skip (no action needed)
  c) If changes needed → follow the INVALIDATED flow above

== STEP 7 — REGRESSION CHECK ==
post_build_check("{document_id}")
get_quality_score("{document_id}")

ROLLBACK TRIGGER: If quality dropped > 5 points from snapshot OR verdict=NO-GO:
  rollback_to_snapshot("{document_id}", snapshot_id)
  Report: "Requirement change caused regression. Rolled back to snapshot [snapshot_id]."

SUCCESS: If verdict=GO and quality stable:
  Report: "Requirement change applied. [invalidated_count] tasks re-implemented.
           Quality: [old_score] → [new_score]. Verdict: GO."
"""
