"""Guided discovery questions prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    FewShotExample,
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "idea.guided_questions"

DIMENSIONS = (
    "target_users",
    "scale_performance",
    "integrations",
    "tech_stack",
    "compliance_security",
    "monetization",
)

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are an expert business analyst conducting a requirements "
        "discovery session. Your questions decide how tailored the final FS "
        "will be — so they must be high-signal."
    ),
    mission=(
        "Given a product idea, generate exactly 6 targeted clarifying "
        "questions, one per dimension, that maximise FS quality."
    ),
    constraints=[
        "Exactly 6 questions, ids `q1`..`q6`.",
        "Each question covers a different dimension: " + ", ".join(DIMENSIONS) + ".",
        "Questions must be specific and probe concrete numbers or trade-offs, never generic 'what do you want to build?' prompts.",
        "`options` is a 3-4 item array of plausible answers users can click, OR empty if the question needs an open-ended response.",
        "Options must be short (<= 8 words each) and mutually distinct.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_ARRAY,
        schema={
            "type": "array",
            "minItems": 6,
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "question", "dimension", "options"],
                "properties": {
                    "id": {"type": "string", "pattern": "^q[1-6]$"},
                    "question": {"type": "string", "minLength": 1},
                    "dimension": {"type": "string", "enum": list(DIMENSIONS)},
                    "options": {
                        "type": "array",
                        "maxItems": 4,
                        "items": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
        empty_value="[]",
    ),
    few_shot=[
        FewShotExample(
            label="Task-tracker idea",
            input_snippet='Product Idea: "A lightweight task tracker for small teams."',
            expected_output=(
                '[{"id": "q1", "question": "Who is the primary user — solo '
                'professionals, 2-10 person teams, or 10+ person teams?", '
                '"dimension": "target_users", "options": ["Solo", "2-10 '
                'team", "10-50 team", "50+ team"]}, '
                '{"id": "q2", "question": "What is the expected peak '
                'concurrent user count in year one?", "dimension": '
                '"scale_performance", "options": ["<100", "100-1k", "1k-10k", '
                '"10k+"]}, '
                '{"id": "q3", "question": "Which third-party integrations '
                'are must-have on day one?", "dimension": "integrations", '
                '"options": ["Slack", "Google Calendar", "GitHub", "None"]}, '
                '{"id": "q4", "question": "What is the preferred backend '
                'stack?", "dimension": "tech_stack", "options": ["Node.js", '
                '"Python (FastAPI)", "Go", "No preference"]}, '
                '{"id": "q5", "question": "Which compliance regimes must '
                'the product honour at launch?", "dimension": '
                '"compliance_security", "options": ["None", "GDPR", "HIPAA", '
                '"SOC 2"]}, '
                '{"id": "q6", "question": "Which monetisation model will '
                'you ship with?", "dimension": "monetization", "options": '
                '["Free forever", "Freemium + paid tier", "Flat subscription", '
                '"Enterprise sales"]}]'
            ),
        ),
    ],
    refusal=(
        "If the idea is empty, still return 6 generic discovery questions "
        "covering the required dimensions; never return fewer than 6 items."
    ),
)


def build(idea: str) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(f"Product Idea: {idea}")
    return system, user


__all__ = ["NAME", "SPEC", "DIMENSIONS", "build"]
