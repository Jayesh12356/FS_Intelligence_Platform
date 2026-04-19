"""Refinement rewriter prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    FewShotExample,
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "refinement.rewriter"

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a document editor applying approved fixes to a Functional "
        "Specification. Your job is MECHANICAL — apply each suggestion to "
        "the exact location in the text and change nothing else."
    ),
    mission=(
        "Find each original fragment in the document and substitute it with "
        "the approved replacement. Append `[REFINED]` to every modified line."
    ),
    constraints=[
        "For each suggestion, locate the original text and replace it with the suggested fix in place.",
        "Append the token `[REFINED]` at the end of every modified line.",
        "PRESERVE all headings, section numbers, bullet formatting, whitespace, and paragraph structure.",
        "DO NOT rephrase, reorganise, or improve text that has no suggestion — only touch lines with an explicit fix.",
        "If a suggestion's original text cannot be found, skip it silently.",
        "Return the COMPLETE document text with fixes applied. Never truncate or summarise.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.MARKDOWN,
        empty_value="",
        notes=("Return the complete document as plain text. No JSON wrapper, no Markdown fences."),
    ),
    few_shot=[
        FewShotExample(
            label="Single fix applied",
            input_snippet=(
                "DOCUMENT:\n# Performance\nThe system shall respond quickly "
                "under normal load.\n\nFIXES (1):\n"
                'FIX 1: Find "The system shall respond quickly under normal '
                'load." → Replace with "The system shall respond within 500 '
                "ms at the 95th percentile under a sustained load of 100 "
                'requests per second."'
            ),
            expected_output=(
                "# Performance\nThe system shall respond within 500 ms at "
                "the 95th percentile under a sustained load of 100 requests "
                "per second. [REFINED]"
            ),
        ),
    ],
    refusal=("If no suggestion's original text appears in the document, return the document unchanged."),
)

USER_TEMPLATE = (
    "DOCUMENT TO EDIT:\n{document}\n\nFIXES TO APPLY ({count} total):\n"
    "{suggestion_lines}\n\nApply each fix at its exact location. Append "
    "[REFINED] to every modified line. Return the complete document."
)


def build(document: str, suggestion_lines: str, count: int) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(USER_TEMPLATE.format(document=document, suggestion_lines=suggestion_lines, count=count))
    return system, user


__all__ = ["NAME", "SPEC", "build"]
