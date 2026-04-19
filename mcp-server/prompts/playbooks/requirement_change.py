"""Playbook: handle_requirement_change — safe new/changed requirement flow."""

from __future__ import annotations


def build(document_id: str, new_requirement: str) -> str:
    """Render the requirement-change playbook with rollback safety net."""
    return f"""# REQUIREMENT CHANGE SESSION
# Document:        {document_id}
# New Requirement: "{new_requirement}"

This workflow safely integrates a new or changed requirement into an
existing build. Every step has a rollback safety net — DO NOT skip steps.

DO NOT:
  - Apply changes without a snapshot (STEP 1). The snapshot is your
    only rollback path.
  - Re-implement tasks classified UNAFFECTED.
  - Rewrite whole modules when get_files_for_task shows which files
    actually need touching — modify ONLY the affected files.

== STEP 1 — SAFETY SNAPSHOT ==

create_snapshot("{document_id}", reason="pre-requirement-change")
Save the returned snapshot_id — you need it for rollback.

== STEP 2 — PLACE REQUIREMENT ==

place_new_requirement("{document_id}", "{new_requirement}")
Read the response:
  - best_section    (where the requirement belongs)
  - affected_tasks  (which existing tasks will change)
If affected_tasks is empty, the requirement is additive — proceed with
less caution, but still complete every remaining step.

== STEP 3 — UPDATE FS DOCUMENT ==

1) get_document("{document_id}") to retrieve the current FS text.
2) Insert the new requirement into best_section using formal FS
   language: "The system shall [new behaviour] when [condition]."
3) upload_version with the updated text.
4) Save the returned version_id.

== STEP 4 — IMPACT ANALYSIS ==

get_impact_analysis("{document_id}", version_id)
For every task, one of three classifications is returned:
  INVALIDATED        - must be re-implemented
  REQUIRES_REVIEW    - verify whether re-implementation is needed
  UNAFFECTED         - leave untouched
Count: invalidated_count, review_count.

== STEP 5 — RE-ANALYZE ==

trigger_analysis("{document_id}")
Poll get_analysis_progress until every node is completed.
refresh_quality_score("{document_id}") — record new_score.

== STEP 6 — RE-IMPLEMENT AFFECTED TASKS ==

For each INVALIDATED task (in dependency order):
  a) update_task status=IN_PROGRESS
  b) get_task_context                 — updated FS section + criteria
  c) get_files_for_task               — existing files to modify
  d) MODIFY ONLY the affected files   — preserve working code
  e) register_file for any NEW files created
  f) verify_task_completion           — all checks must pass
  g) update_task status=COMPLETE
  h) update_build_state(current_phase=4,
                        current_task_index=<next_index>,
                        completed_task_id=task_id)

For each REQUIRES_REVIEW task:
  a) get_task_context — read the updated section
  b) If acceptance criteria still pass with no code changes → skip.
  c) Otherwise → follow the INVALIDATED flow above.

== STEP 7 — REGRESSION CHECK ==

post_build_check("{document_id}")
get_quality_score("{document_id}")

ROLLBACK TRIGGER: if quality dropped > 5 points from snapshot OR
verdict=NO-GO:
  rollback_to_snapshot("{document_id}", snapshot_id)
  Report: "Requirement change caused regression. Rolled back to
           snapshot [snapshot_id]."

SUCCESS: if verdict=GO and quality stable:
  Report: "Requirement change applied. [invalidated_count] tasks
           re-implemented. Quality: [old_score] → [new_score].
           Verdict: GO."
"""
