"""Playbook: refine_and_analyze — tight refine→accept→re-analyze loop."""

from __future__ import annotations


def build(document_id: str) -> str:
    """Render the refine-and-analyze playbook for one document."""
    return f"""# REFINE & ANALYZE LOOP — Document {document_id}

This prompt runs a tight refine → accept → re-analyze → quality-check
loop. Use it whenever quality is below 90 or after manual edits.

DO NOT:
  - Skip STEP 5 (quality re-check). Without it you cannot tell whether
    the loop helped or hurt.
  - Re-run refine_fs more than twice in one session. Three attempts
    without progress means the FS needs human review.

== STEP 1 — BASELINE ==

get_quality_score("{document_id}")
Record the current score as `baseline_score`.

== STEP 2 — REFINE ==

refine_fs("{document_id}")
  If the refinement is accepted → continue.
  If rejected (score dropped or unchanged) → STOP. Report
  "Refinement rejected; no changes applied."

== STEP 3 — RESOLVE ALL OPEN ITEMS ==

A) get_contradictions("{document_id}")
     For each OPEN: accept_contradiction_suggestion("{document_id}", id).

B) get_edge_cases("{document_id}")
     For each OPEN: accept_edge_case_suggestion("{document_id}", id).

C) get_ambiguities("{document_id}")
     For each OPEN HIGH:
       resolve_ambiguity("{document_id}", id, "<concrete resolution>").
     A concrete resolution cites specific numbers, conditions, and
     behaviours. Vague prose such as "make it faster" is forbidden.

== STEP 4 — RE-ANALYZE ==

trigger_analysis("{document_id}")
Poll get_analysis_progress("{document_id}") until every node is
completed. Retry trigger_analysis at most ONCE on node errors.

== STEP 5 — QUALITY CHECK ==

refresh_quality_score("{document_id}")
Record the new score as `refined_score`.

REPORT:
  refined_score >= 90
    → "Quality reached {{refined_score}}. Ready for build."
  refined_score < 90 and refined_score > baseline_score
    → "Quality improved {{baseline_score}} → {{refined_score}} but
       still < 90. Run again or proceed with caution."
  refined_score <= baseline_score
    → "Quality did not improve. Manual review recommended."
"""
