"""MCP playbook prompts (v2) — precise autonomous workflows.

Each playbook is a standalone module exposing a single `build(...) -> str`
function that renders the final prompt string the agent receives. Keeping
each playbook in its own module makes them individually auditable and
testable, and lets the master template evolve without touching call sites.

All playbooks share the following contract:

- Every phase has EXPLICIT exit criteria that must be met before moving on.
- Every phase lists the EXACT MCP tool calls to make, in order.
- A `DO NOT` block at the top enumerates prohibited shortcuts.
- Retry semantics are stated once in common terms: only transient tool
  errors (network, timeout, 5xx) get a single retry. Hard failures
  (validation, 4xx, guard-rail failures) must be fixed at the source.
"""

from . import (
    build_loop,
    full_autonomous,
    refine_analyze,
    fix_ambiguity,
    implement_task,
    requirement_change,
    quick_analysis,
    project_overview,
)

__all__ = [
    "build_loop",
    "full_autonomous",
    "refine_analyze",
    "fix_ambiguity",
    "implement_task",
    "requirement_change",
    "quick_analysis",
    "project_overview",
]
