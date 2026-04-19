"""Playbook: implement_task — focused single-task implementation + verify."""

from __future__ import annotations


def build(document_id: str, task_id: str) -> str:
    """Render the focused implement-one-task playbook."""
    return f"""# IMPLEMENT TASK — Document {document_id} / Task {task_id}

Implement one task end-to-end with full traceability and verification.

DO NOT:
  - Write code before STEP 1 (CONTEXT) is complete.
  - Skip dependencies. If any dependency task is not COMPLETE, finish
    those first (call this playbook recursively).
  - Forget register_file. Every file you create or modify must be
    registered, or traceability breaks.
  - Mark the task COMPLETE without a passing verify_task_completion.

STEP 1 — GATHER CONTEXT:
  get_task_context("{document_id}", "{task_id}")
  Returns: title, description, acceptance criteria, FS section text,
  test cases, dependency task statuses, already-registered files,
  target stack. READ ALL OF IT before writing any code.

STEP 2 — CHECK DEPENDENCIES:
  If any dependency task is not COMPLETE, implement those first by
  calling implement_task for each. Never start a task whose
  dependencies are unfinished.

STEP 3 — REUSE CHECK:
  check_library_for_reuse(document_id="{document_id}",
                          description=<task.description>)
  If reuse_score > 0.85, adapt the library pattern instead of writing
  from scratch. Record the library_id on registered files.

STEP 4 — IMPLEMENT:
  Write production-quality code that satisfies EVERY acceptance
  criterion. Follow the target stack's conventions. Use the FS section
  text as the source of truth — not your assumptions.

STEP 5 — REGISTER:
  register_file(
    document_id="{document_id}",
    task_id="{task_id}",
    section_id=<from context>,
    path=<file path>,
    type=<"source" | "test" | "config" | "migration">,
  )
  Do this for EVERY file created or modified.

STEP 6 — VERIFY:
  verify_task_completion("{document_id}", "{task_id}")
  If ANY check fails: fix the code, re-verify. DO NOT mark the task
  complete while any check still fails.

STEP 7 — MARK DONE:
  update_task(
    document_id="{document_id}",
    task_id="{task_id}",
    status="COMPLETE",
  )
  update_build_state(
    current_phase=4,
    current_task_index=<next_index>,
    completed_task_id="{task_id}",
  )
  Confirm with get_task that status=COMPLETE persisted.
"""
