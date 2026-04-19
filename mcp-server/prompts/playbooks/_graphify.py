"""Graphify block — runs once before any code is written.

Why a dedicated block:
  Production builds collide with stale assumptions when an agent writes
  new modules without first surveying what already exists in the output
  folder. The block below forces a one-time structural mapping pass and
  is referenced by every playbook that ships code (build_loop,
  full_autonomous, implement_task) so the rule is consistent.

Outputs (kept in the agent's working memory, not on disk):
  * REUSE_INDEX  — list of (path, exported symbols, brief purpose).
  * ENTRYPOINTS  — process roots (server, CLI, scripts).
  * GAPS         — directories the FS expects but that do not yet exist.

The block is plain text and trivially formattable, so each playbook can
splice it directly between PRE-FLIGHT and the first IMPLEMENT phase.
"""

from __future__ import annotations

GRAPHIFY_BLOCK = """== PHASE 0 — GRAPHIFY (run ONCE before any code is written) ==

Purpose: capture a structural map of the existing scaffold so every
later phase reasons from a fresh, accurate picture instead of guessing.

PARALLEL:
  list output_folder contents (depth 4, ignore .git/.venv/node_modules)
  identify entry points (server bootstraps, CLI mains, build configs)
  identify shared utility modules and types
  read README/AGENTS/CHANGELOG if present (top 200 lines each)

Record three artefacts in working memory (do NOT write them to disk):
  REUSE_INDEX  → [{path, exported_symbols[], one_line_purpose}]
  ENTRYPOINTS  → [{path, kind: server|cli|script, framework}]
  GAPS         → [directory or module the FS expects but is missing]

USAGE RULES (applied in every IMPLEMENT step that follows):
  1. Before writing a new file, scan REUSE_INDEX for a candidate
     symbol. If a candidate exists, call check_library_for_reuse and
     adapt rather than rewrite.
  2. Before declaring a feature done, ensure its files appear in
     REUSE_INDEX (re-graph if you cannot see them).
  3. After EVERY phase exit, refresh REUSE_INDEX so the map reflects
     what you just shipped — never reason from a stale graph.

EXIT CRITERIA: REUSE_INDEX, ENTRYPOINTS, and GAPS captured. The agent
can name the entry-point file for the chosen stack and at least one
candidate file in REUSE_INDEX (or an empty index for greenfield)."""


__all__ = ["GRAPHIFY_BLOCK"]
