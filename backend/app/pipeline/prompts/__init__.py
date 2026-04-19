"""Centralised prompt library.

Every LLM prompt in the backend (analysis nodes, refinement, idea, reverse
FS, impact, MCP playbooks) is defined here via :func:`master_template.build`
so the project has a single, auditable source of truth for prompt shape
and output contracts.

Each sub-module exports two helpers::

    def build(ctx) -> tuple[str, str]:  # (system, user)
    SPEC: PromptSpec  # so tests can assert structural invariants

and a ``NAME`` constant so the validation harness can iterate.
"""
