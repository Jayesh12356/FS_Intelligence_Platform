"""Playbook: project_overview — platform-wide dashboard."""

from __future__ import annotations


def build() -> str:
    """Render the platform-wide overview playbook."""
    return """# SYSTEM OVERVIEW

Produce a complete picture of FS Intelligence Platform state so the user
knows exactly where to invest attention next.

DO NOT:
  - Call tools sequentially when they are listed as PARALLEL.
  - Emit a report that omits quality scores — the dashboard's value
    comes from the score column.

== STEP 1 — DISCOVER (PARALLEL) ==

  list_documents()
  list_projects()
  list_code_uploads()

== STEP 2 — DOCUMENT HEALTH ==

For each document returned:
  get_quality_score(document_id)
  get_analysis_progress(document_id)

Collect: document name, status, quality score, analysis state.

== STEP 3 — REPORT ==

Produce this exact dashboard layout:

  PLATFORM OVERVIEW
  ===============================================================
  Documents: [total] ([parsed] parsed, [analyzed] analyzed)
  Projects: [total]
  Code Uploads: [total]

  DOCUMENT HEALTH
  +-------------------------+--------+---------+----------+
  | Document                | Status | Quality | Analysis |
  +-------------------------+--------+---------+----------+
  | [name]                  | [stat] | [score] | [state]  |
  +-------------------------+--------+---------+----------+

  RECOMMENDATIONS
  - Documents below quality 90: [list]
  - Documents not yet analyzed:  [list]
  - Documents ready for build:   [list]
"""
