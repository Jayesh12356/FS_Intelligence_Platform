"""Built-in MCP prompts for autonomous execution loops.

These prompts provide step-by-step workflows for Cursor, Claude Code, and
any MCP-connected agent. Each prompt is self-contained: it lists every tool
call needed, the expected output, exit criteria, and error recovery.
"""

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
  - Phase GATES (pre_build_check go=false, post_build_check verdict=NO-GO, quality<90 after refinement) MUST be resolved, never retried blindly.
  - Only TRANSIENT tool errors (network, timeout, 5xx) get one retry. Hard failures (validation, 4xx, guard-rail=false) must be fixed at the source.
  - Every update_build_state call MUST include current_phase (0-7) and current_task_index (int).

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

A) For each OPEN HIGH ambiguity:
  1. get_debate_results("{document_id}") for context
  2. Draft concrete, implementation-ready resolution text
  3. resolve_ambiguity(document_id, flag_id, resolution)

B) For each OPEN contradiction:
  accept_contradiction_suggestion("{document_id}", contradiction_id)
  If accept fails: resolve_contradiction("{document_id}", contradiction_id)

C) For each OPEN edge case with a suggestion:
  accept_edge_case_suggestion("{document_id}", edge_case_id)
  If accept fails: resolve_edge_case("{document_id}", edge_case_id)

After all: refresh_quality_score("{document_id}")
Exit criteria: zero OPEN HIGH ambiguities, zero OPEN contradictions, zero OPEN edge cases, AND quality >= 90.

== PHASE 3 — BUILD PLAN ==

autonomous_build_from_fs("{document_id}", "{stack}")
{proceed_gate}

== PHASE 4 — BUILD (core implementation loop) ==

update_build_state(
  current_phase=4,
  current_task_index=0,
  status="RUNNING",
  stack="{stack}",
  output_folder="{output_folder}",
  total_tasks=<total_tasks from Phase 1>,
)

For EACH task at index `i` (dependency order):

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

  h) PERSIST PROGRESS:
     update_build_state(
       current_phase=4,
       current_task_index=i + 1,
       completed_task_id=task_id,
     )

ERROR RECOVERY (if steps c-f fail):
  1. update_build_state(current_phase=4, current_task_index=i, failed_task_id=task_id).
  2. Non-critical task (effort=LOW, no dependents) → skip with warning, continue.
  3. Critical task → retry ONCE with a simpler implementation approach.
  4. If still fails → create_snapshot, skip task, continue.
  5. Skipped tasks surface in Phase 6 gap report.

NOTE: The "retry ONCE" rule above applies ONLY to step (d) IMPLEMENT failures.
      It does NOT override gates like verify_task_completion failures or
      post_build_check NO-GO verdicts — those must be resolved, not retried.

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
update_build_state(
  current_phase=7,
  current_task_index=<total_tasks>,
  status="COMPLETE",
)

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
    async def start_full_autonomous_loop(
        idea: str,
        stack: str = "Next.js + FastAPI",
        output_folder: str = "./output",
        industry: str = "",
        complexity: str = "enterprise",
    ) -> str:
        """Zero-touch idea-to-production loop: generate FS, analyze, refine, build, export."""
        industry_line = f'\n# Industry: {industry}' if industry else ''
        return f"""
# FULL AUTONOMOUS SESSION — IDEA TO PRODUCTION
# Idea:       {idea}
# Stack:      {stack}
# Output:     {output_folder}{industry_line}
# Complexity: {complexity}

This session takes a raw product idea and delivers a fully built codebase with
zero manual intervention.  Every phase has explicit exit criteria — do NOT
advance until the criteria are met.

CRITICAL RULES:
  - NEVER write code before Phase 4.
  - NEVER mark a task COMPLETE without calling verify_task_completion first.
  - Phase gates (pre_build_check go=false, post_build_check verdict=NO-GO) MUST be resolved, never retried blindly.
  - Only TRANSIENT tool errors (network, timeout, 5xx) get one retry. Hard failures must be fixed.
  - Every update_build_state call MUST include current_phase and current_task_index.

== PHASE 0 — GENERATE FUNCTIONAL SPECIFICATION ==

1) generate_fs_from_idea(
     idea="{idea}",
     industry="{industry or ''}",
     complexity="{complexity}"
   )
   Save the returned document_id — every subsequent call uses it.
   If error: STOP and report "FS generation failed".

2) Confirm: get_document(document_id)
   Verify status = PARSED and sections exist.

EXIT CRITERIA: document_id is valid and status = PARSED.

== PHASE 1 — FULL ANALYSIS ==

1) trigger_analysis(document_id)
   This runs the 11-node LangGraph pipeline (ambiguity, contradiction,
   edge-case, quality, task decomposition, dependencies, traceability,
   duplicate detection, test-case generation).

2) Poll: get_analysis_progress(document_id) every 10 seconds until
   all nodes show completed.  If error state, retry trigger_analysis once.

EXIT CRITERIA: analysis is complete for all nodes.

== PHASE 2 — QUALITY GATE ==

1) run_quality_gate(document_id)
   - If score >= 90: proceed.
   - If score < 90: refine_fs(document_id) — up to 2 attempts.
   - If still < 90: proceed with warning.

2) get_ambiguities(document_id)
   For each OPEN HIGH ambiguity:
     a) get_debate_results(document_id) for context.
     b) Draft a concrete, implementation-ready resolution.
     c) resolve_ambiguity(document_id, flag_id, resolution).

3) get_contradictions(document_id)
   For each OPEN contradiction:
     accept_contradiction_suggestion(document_id, contradiction_id)
     If accept fails: resolve_contradiction(document_id, contradiction_id)

4) get_edge_cases(document_id)
   For each OPEN edge case with a suggestion:
     accept_edge_case_suggestion(document_id, edge_case_id)
     If accept fails: resolve_edge_case(document_id, edge_case_id)

5) refresh_quality_score(document_id)

EXIT CRITERIA: quality >= 90, zero OPEN HIGH ambiguities, zero OPEN contradictions, zero OPEN edge cases.

== PHASE 3 — BUILD SETUP ==

1) get_build_state(document_id)
   - status=COMPLETE → "Already built", STOP.
   - status=RUNNING → Resume from current position.
   - Otherwise → create_build_state(document_id).

2) pre_build_check(document_id)
   - go=false → Fix every listed blocker, re-run until go=true.
   - NEVER proceed with go=false.

3) autonomous_build_from_fs(document_id, "{stack}")
   Read the manifest. Proceed immediately.

4) check_library_for_reuse for the first 5 tasks by description.

== PHASE 4 — BUILD (implementation loop) ==

update_build_state(
  current_phase=4,
  current_task_index=0,
  status="RUNNING",
  stack="{stack}",
  output_folder="{output_folder}",
  total_tasks=<total_tasks>,
)

For EACH task at index `i` (dependency order):
  a) SKIP if already in completed_task_ids.
  b) check_library_for_reuse — adapt if reuse_score > 0.85.
  c) get_task_context(document_id, task_id) — read EVERYTHING.
  d) IMPLEMENT in {output_folder}. Follow acceptance criteria exactly.
  e) register_file for EVERY file created or modified.
  f) verify_task_completion(document_id, task_id) — fix failures, re-verify.
  g) update_task(document_id, task_id, status="COMPLETE").
  h) update_build_state(current_phase=4, current_task_index=i + 1, completed_task_id=task_id).

ERROR RECOVERY (step d implementation failures only):
  1. update_build_state(current_phase=4, current_task_index=i, failed_task_id=task_id).
  2. Non-critical (effort=LOW, no dependents) → skip with warning.
  3. Critical → retry ONCE with simpler approach.
  4. Still fails → create_snapshot, skip, continue.

NOTE: verify_task_completion failures (step f) must be FIXED — not retried once.

== PHASE 5 — CHECKPOINT (every 5 tasks) ==

refresh_quality_score — must stay >= 90.
get_traceability — zero orphaned tasks.
get_build_state — confirm progress.

== PHASE 6 — VERIFY ==

post_build_check(document_id)
If verdict=NO-GO → fix gaps, re-run until GO.

== PHASE 7 — EXPORT ==

export_to_jira(document_id)
get_pdf_report(document_id)
update_build_state(
  current_phase=7,
  current_task_index=<total_tasks>,
  status="COMPLETE",
)

Final report:
  FULL AUTONOMOUS BUILD COMPLETE
  Idea: {idea}
  Quality: [score]/100
  Tasks: [completed]/[total]
  Files registered: [count]
  PDF report: [download_url]
"""

    @mcp.prompt()
    async def refine_and_analyze(document_id: str) -> str:
        """Focused loop: refine the FS, accept all fixes, re-analyze, and check quality."""
        return f"""
# REFINE & ANALYZE LOOP — Document {document_id}

This prompt runs a tight refine→accept→re-analyze→quality-check loop.
Use it whenever quality is below 90 or after making manual edits.

== STEP 1 — BASELINE ==
get_quality_score("{document_id}")
Record current score as baseline_score.

== STEP 2 — REFINE ==
refine_fs("{document_id}")
If refinement is accepted, continue. If rejected (score dropped), STOP.

== STEP 3 — RESOLVE ALL OPEN ITEMS ==

A) get_contradictions("{document_id}")
   For each OPEN: accept_contradiction_suggestion("{document_id}", id)

B) get_edge_cases("{document_id}")
   For each OPEN: accept_edge_case_suggestion("{document_id}", id)

C) get_ambiguities("{document_id}")
   For each OPEN HIGH: resolve_ambiguity("{document_id}", id, "<concrete resolution>")

== STEP 4 — RE-ANALYZE ==
trigger_analysis("{document_id}")
Poll get_analysis_progress("{document_id}") until all nodes completed.

== STEP 5 — QUALITY CHECK ==
refresh_quality_score("{document_id}")
Record new score as refined_score.

If refined_score >= 90:
  Report: "Quality reached {{refined_score}}. Ready for build."
If refined_score < 90 AND refined_score > baseline_score:
  Report: "Quality improved {{baseline_score}} → {{refined_score}} but still < 90. Run again or proceed with caution."
If refined_score <= baseline_score:
  Report: "Quality did not improve. Manual review recommended."
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
  update_build_state(
    current_phase=4,
    current_task_index=<next_index>,
    completed_task_id="{task_id}",
  )
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
Wait for completion (poll get_analysis_progress until all nodes completed).
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
  h) update_build_state(current_phase=4, current_task_index=<next_index>, completed_task_id=task_id)

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

    @mcp.prompt()
    async def quick_analysis(document_id: str) -> str:
        """Quick analysis-only flow: analyze, resolve all issues, report quality. No build."""
        return f"""
# QUICK ANALYSIS — Document {document_id}
#
# This prompt runs a complete analysis cycle without building anything.
# Use it to assess document quality, find issues, and resolve them.

== STEP 1 — DISCOVER ==

Call ALL of these in parallel:
  get_document("{document_id}")
  get_quality_score("{document_id}")
  get_tasks("{document_id}")
  get_ambiguities("{document_id}")
  get_contradictions("{document_id}")
  get_edge_cases("{document_id}")

Record:
  - Document title and status
  - Quality score (overall, completeness, clarity, consistency)
  - Task count
  - Open ambiguity count (total, HIGH severity)
  - Open contradiction count
  - Open edge case count

== STEP 2 — RESOLVE BLOCKERS (only if issues exist) ==

IF open contradictions > 0:
  For each: accept_contradiction_suggestion("{document_id}", id)
  If accept fails: resolve_contradiction("{document_id}", id)

IF open edge cases > 0:
  For each: accept_edge_case_suggestion("{document_id}", id)
  If accept fails: resolve_edge_case("{document_id}", id)

IF open HIGH ambiguities > 0:
  For each:
    a) Read the flagged_text, reason, and severity from step 1 results
    b) Draft a concrete, implementation-ready resolution
    c) resolve_ambiguity("{document_id}", flag_id, resolution)

== STEP 3 — REFRESH ==

refresh_quality_score("{document_id}")

== STEP 4 — REPORT ==

Generate a summary:
  ANALYSIS COMPLETE
  Document: [filename]
  Quality: [score]/100 (completeness: [x], clarity: [y], consistency: [z])
  Tasks: [count]
  Ambiguities resolved: [count]
  Contradictions resolved: [count]
  Edge cases resolved: [count]
  Status: [READY FOR BUILD | NEEDS ATTENTION | CRITICAL ISSUES]
    - READY FOR BUILD: quality >= 90 and zero open HIGH issues
    - NEEDS ATTENTION: quality 70-89 or some open issues remain
    - CRITICAL ISSUES: quality < 70 or many unresolvable issues
"""

    @mcp.prompt()
    async def project_overview() -> str:
        """Get a complete overview of all documents, projects, and system health."""
        return """
# SYSTEM OVERVIEW

Get a complete picture of the FS Intelligence Platform state.

== STEP 1 — DISCOVER ==

Call ALL of these in parallel:
  list_documents()
  list_projects()
  list_code_uploads()

== STEP 2 — DOCUMENT HEALTH ==

For each document returned:
  get_quality_score(document_id)
  get_analysis_progress(document_id)

Collect: document name, status, quality score, analysis state.

== STEP 3 — REPORT ==

Generate a dashboard:

  PLATFORM OVERVIEW
  ═══════════════════════════════════════
  Documents: [total] ([parsed] parsed, [analyzed] analyzed)
  Projects: [total]
  Code Uploads: [total]

  DOCUMENT HEALTH
  ┌─────────────────────────┬────────┬─────────┬──────────┐
  │ Document                │ Status │ Quality │ Analysis │
  ├─────────────────────────┼────────┼─────────┼──────────┤
  │ [name]                  │ [stat] │ [score] │ [state]  │
  └─────────────────────────┴────────┴─────────┴──────────┘

  RECOMMENDATIONS
  - Documents below quality 90: [list]
  - Documents not yet analyzed: [list]
  - Documents ready for build: [list]
"""
