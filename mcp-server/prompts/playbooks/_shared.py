"""Shared header fragments used by every MCP playbook prompt (v2)."""

from __future__ import annotations

GLOBAL_RULES = """GLOBAL RULES (apply to every phase):
  - NEVER write code before the IMPLEMENT phase of this playbook.
  - NEVER mark a task COMPLETE without calling verify_task_completion first.
  - NEVER proceed past a phase gate while its EXIT CRITERIA are not met.
  - Only TRANSIENT tool errors (network, timeout, 5xx) get ONE retry. Hard
    failures (validation, 4xx, guard-rails reporting go=false) MUST be
    fixed at the source, not retried.
  - Every update_build_state call MUST include current_phase (int 0-7) and
    current_task_index (int).
  - Tool calls that can run in parallel are listed in a single "PARALLEL"
    block — dispatch them concurrently, never sequentially."""


BUILD_LOOP_TEMPLATE = """For EACH task at index `i` (in dependency order):

  a) SKIP CHECK
       If task_id is already in get_build_state().completed_task_ids → skip.

  b) REUSE CHECK
       check_library_for_reuse(document_id, task_description).
       If reuse_score > 0.85 → adapt the library pattern instead of
       writing from scratch. Record the library_id in the registered file
       metadata for traceability.

  c) CONTEXT
       get_task_context(document_id, task_id).
       Returns: task details, acceptance criteria, FS section text,
       test cases, dependency statuses, registered files, target stack.
       READ ALL OF IT before writing code.

  d) IMPLEMENT
       Write code in {output_folder}. Follow every acceptance criterion
       exactly. Use the stack "{stack}". Produce clean, production-quality
       code — no placeholders, no TODOs, no hardcoded secrets.

  e) REGISTER
       register_file(document_id, task_id, section_id, path, type)
       for EVERY file created or modified. Missing registrations break
       traceability and will fail post_build_check.

  f) VERIFY
       verify_task_completion(document_id, task_id).
       If ANY check fails → fix the gap, re-verify. DO NOT retry a failed
       verification — the underlying code must change.

  g) MARK COMPLETE
       update_task(document_id, task_id, status="COMPLETE")
       Confirm persistence with get_task.

  h) PERSIST PROGRESS
       update_build_state(current_phase=4, current_task_index=i + 1,
                          completed_task_id=task_id)

ERROR RECOVERY (applies to step (d) IMPLEMENT failures ONLY):
  1. update_build_state(current_phase=4, current_task_index=i,
                        failed_task_id=task_id).
  2. If task is non-critical (effort=LOW, no dependents) → skip with
     a logged warning and continue.
  3. If task is critical → retry ONCE with a simpler implementation
     approach.
  4. If still failing → create_snapshot, skip the task, continue. The
     skip surfaces in the Phase 6 gap report.

NOTE: Verification failures (step f), post_build_check NO-GO verdicts,
and pre_build_check go=false are GATES, not retriable errors."""


def checkpoint_block() -> str:
    return """== PHASE 5 — CHECKPOINT (every 5 completed tasks) ==

  refresh_quality_score   must stay >= 90 (if it drops:
                          get_edge_cases, fix gaps, re-check).
  get_traceability        zero orphaned tasks.
  get_build_state         confirm completed_task_ids matches expectations.

EXIT CRITERIA: quality >= 90, zero orphaned tasks, build_state consistent."""


def verify_block(doc_id_placeholder: str) -> str:
    return f"""== PHASE 6 — VERIFY ==

  post_build_check("{doc_id_placeholder}")
  If verdict=NO-GO → fix every listed gap, re-run post_build_check.
  Loop until verdict=GO. Do NOT proceed to export with NO-GO.

EXIT CRITERIA: post_build_check verdict=GO."""


def export_block(doc_id_placeholder: str) -> str:
    return f"""== PHASE 7 — EXPORT & REPORT ==

  export_to_jira("{doc_id_placeholder}")
  get_pdf_report("{doc_id_placeholder}")
  update_build_state(current_phase=7,
                     current_task_index=<total_tasks>,
                     status="COMPLETE")

EXIT CRITERIA: status=COMPLETE persisted, PDF and Jira export URLs
returned to the user."""
