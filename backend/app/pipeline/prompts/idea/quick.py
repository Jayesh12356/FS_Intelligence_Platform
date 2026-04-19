"""Quick idea → full FS prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "idea.quick"

REQUIRED_SECTIONS = (
    "OVERVIEW",
    "USER ROLES & PERSONAS",
    "CORE FEATURES",
    "NON-FUNCTIONAL REQUIREMENTS",
    "API CONTRACTS",
    "DATA MODELS",
    "SECURITY & AUTHENTICATION",
    "ERROR HANDLING & EDGE CASES",
    "INTEGRATION POINTS",
    "ACCEPTANCE CRITERIA",
)

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are an elite enterprise software architect and business analyst. "
        "Your output is the first artifact a development team will build "
        "from, so it must be immediately actionable."
    ),
    mission=(
        "Transform a brief product idea into a comprehensive, industry-grade "
        "Functional Specification (FS) with all ten required sections."
    ),
    constraints=[
        "Required sections, in order: " + ", ".join(REQUIRED_SECTIONS) + ".",
        "Every section must contain deep technical AND business detail — no skeleton placeholders.",
        "Be specific: real field names, real API paths, real error codes, real numeric thresholds.",
        "Assume enterprise production scale — thousands of concurrent users. Cover rate limiting, pagination, caching, audit trails.",
        "Use numbered sections with clear Markdown headings (`## 1. OVERVIEW`, `## 2. USER ROLES`, etc.).",
        "Output ONLY the FS document text. No meta-commentary, no apologies, no summary of what you wrote.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.MARKDOWN,
        empty_value="",
        notes=("Markdown document. Each required section appears exactly once, as a numbered `## N. NAME` heading."),
    ),
    few_shot=[],
    refusal=(
        "If the idea is empty, return the string `# Functional Specification` "
        "followed by a single paragraph asking the user to provide a product "
        "idea. Never hallucinate a product."
    ),
)

USER_TEMPLATE = "Product Idea: {idea}{extras}"


def build(
    idea: str,
    *,
    industry: str | None = None,
    complexity: str | None = None,
) -> tuple[str, str]:
    extras = ""
    if industry:
        extras += f"\nIndustry: {industry}"
    if complexity:
        extras += f"\nComplexity Level: {complexity}"
    system = SPEC.system()
    user = SPEC.user(USER_TEMPLATE.format(idea=idea, extras=extras))
    return system, user


__all__ = ["NAME", "SPEC", "REQUIRED_SECTIONS", "build"]
