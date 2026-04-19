"""Guided idea → full FS prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.idea.quick import REQUIRED_SECTIONS
from app.pipeline.prompts.master_template import (
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "idea.guided_fs"

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are an elite enterprise software architect. The user has "
        "already answered a 6-question discovery interview, so every "
        "section you emit must reflect their declared preferences — not "
        "generic defaults."
    ),
    mission=(
        "Using the product idea AND the user's discovery answers, generate "
        "a comprehensive, industry-grade Functional Specification tailored "
        "to the user's scale, stack, integrations, compliance, and "
        "business model."
    ),
    constraints=[
        "Required sections, in order: " + ", ".join(REQUIRED_SECTIONS) + ".",
        "Every section must reflect the user's discovery answers. If the user picked 'Python (FastAPI)', API CONTRACTS should name FastAPI routes; if compliance='HIPAA', SECURITY & AUTHENTICATION must cover PHI handling.",
        "Match the stated scale: a 50k-user target demands explicit rate limiting, pagination, caching, and horizontal scaling notes.",
        "Preserve the user's terminology for user roles, feature names, and integrations.",
        "Use numbered Markdown headings (`## 1. OVERVIEW`, etc.).",
        "Output ONLY the FS document text. No meta-commentary, no 'based on your answers…' preamble.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.MARKDOWN,
        empty_value="",
    ),
    few_shot=[],
    refusal=(
        "If both the idea and the answers are empty, return `# Functional "
        "Specification` followed by a single paragraph requesting input."
    ),
)


def build(
    idea: str,
    answers: dict,
    *,
    industry: str | None = None,
    complexity: str | None = None,
) -> tuple[str, str]:
    parts = [f"Product Idea: {idea}"]
    if industry:
        parts.append(f"Industry: {industry}")
    if complexity:
        parts.append(f"Complexity: {complexity}")
    parts.append("")
    parts.append("Discovery Answers:")
    for q_id, answer in answers.items():
        parts.append(f"  {q_id}: {answer}")
    system = SPEC.system()
    user = SPEC.user("\n".join(parts))
    return system, user


__all__ = ["NAME", "SPEC", "build"]
