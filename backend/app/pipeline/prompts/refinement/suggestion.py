"""Refinement suggestion prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    FewShotExample,
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "refinement.suggestion"

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a requirements engineer fixing defects in Functional "
        "Specifications. Each fix you produce will be applied verbatim as a "
        "drop-in replacement in a reviewed document."
    ),
    mission=(
        "For one flagged issue, produce a single replacement that resolves "
        "the defect while preserving the original intent and scope."
    ),
    constraints=[
        "Address the flagged issue DIRECTLY: ambiguity → specific numbers/conditions; contradiction → reconciled text; missing edge case → explicit handling.",
        "Use formal FS language: 'The system shall...' for requirements. Be measurable (ms, days, characters).",
        "Stay the same paragraph size (±2 sentences). Do NOT expand one sentence into a page.",
        "Do NOT add requirements not implied by the original text. Fix what is broken, nothing more.",
        "Preserve the original terminology, actor names, and system references.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_OBJECT,
        schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["suggested_fix"],
            "properties": {
                "suggested_fix": {"type": "string", "minLength": 1},
            },
        },
        empty_value='{"suggested_fix": ""}',
        notes=(
            "Return a single JSON object with exactly one key, "
            "`suggested_fix`. Never return an empty value — if the issue is "
            "genuinely unresolvable, propose the best-faith replacement you "
            "can."
        ),
    ),
    few_shot=[
        FewShotExample(
            label="Quantify vague threshold",
            input_snippet=(
                "Issue Type: ambiguity\n"
                "Section: Performance\n"
                "Defect: No response-time threshold defined.\n"
                'Original Text: "The system shall respond quickly under '
                'normal load."'
            ),
            expected_output=(
                '{"suggested_fix": "The system shall respond within 500 ms '
                "at the 95th percentile under a sustained load of 100 "
                'requests per second."}'
            ),
        ),
    ],
    refusal=('If the original text is empty, echo back a minimal placeholder: `{"suggested_fix": "[REFINED]"}`.'),
)

USER_TEMPLATE = (
    "Issue Type: {issue_type}\nSection: {section_heading}\nDefect: {issue}\n"
    "Original Text: {original_text}\n\nWrite ONE replacement that fixes the "
    'defect. Return JSON: {{"suggested_fix": "..."}}'
)


def build(issue_type: str, section_heading: str, issue: str, original_text: str) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(
        USER_TEMPLATE.format(
            issue_type=issue_type,
            section_heading=section_heading,
            issue=issue,
            original_text=original_text,
        )
    )
    return system, user


__all__ = ["NAME", "SPEC", "build"]
