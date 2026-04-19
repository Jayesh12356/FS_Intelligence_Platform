"""Playbook: quick_analysis — analyze + resolve + report, no build."""

from __future__ import annotations


def build(document_id: str) -> str:
    """Render the analysis-only playbook (no code generation)."""
    return f"""# QUICK ANALYSIS — Document {document_id}

Runs a complete analysis cycle WITHOUT building anything. Use it to
assess document quality, surface issues, and resolve them.

DO NOT:
  - Call trigger_analysis. This playbook assumes the document has
    already been analyzed — it only resolves open findings.
  - Resolve ambiguities without reading flagged_text + reason first.
  - Skip STEP 3 (refresh_quality_score). Without it, the final report
    is stale.

== STEP 1 — DISCOVER (PARALLEL) ==

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
  - Open ambiguity count (total and HIGH severity)
  - Open contradiction count
  - Open edge-case count

== STEP 2 — RESOLVE BLOCKERS (only if issues exist) ==

IF open contradictions > 0:
  For each: accept_contradiction_suggestion("{document_id}", id).
  If accept fails → resolve_contradiction("{document_id}", id).

IF open edge cases > 0:
  For each: accept_edge_case_suggestion("{document_id}", id).
  If accept fails → resolve_edge_case("{document_id}", id).

IF open HIGH ambiguities > 0:
  For each flag:
    a) Read flagged_text, reason, severity from STEP 1 results.
    b) Draft a concrete, implementation-ready resolution.
    c) resolve_ambiguity("{document_id}", flag_id, resolution).

== STEP 3 — REFRESH ==

refresh_quality_score("{document_id}")

== STEP 4 — REPORT ==

Produce this exact summary:

  ANALYSIS COMPLETE
  Document: [filename]
  Quality: [score]/100
    completeness: [x] / clarity: [y] / consistency: [z]
  Tasks: [count]
  Ambiguities resolved: [count]
  Contradictions resolved: [count]
  Edge cases resolved: [count]
  Status: [READY FOR BUILD | NEEDS ATTENTION | CRITICAL ISSUES]

Status key:
  READY FOR BUILD   - quality >= 90 AND zero open HIGH issues.
  NEEDS ATTENTION   - quality 70-89 OR some open issues remain.
  CRITICAL ISSUES   - quality < 70 OR many unresolvable issues.
"""
