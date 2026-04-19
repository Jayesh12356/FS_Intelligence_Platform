"""Edge-case detection prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    FewShotExample,
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "analysis.edge_case"

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a senior QA architect who writes test plans for mission-"
        "critical enterprise systems. You find the scenarios that cause "
        "production incidents — the cases the FS author forgot to specify."
    ),
    mission=(
        "Identify scenarios where the section is silent but a real user or "
        "system event would occur. Only flag gaps actually missing from the "
        "text."
    ),
    constraints=[
        "Each gap must be specific to the section's content — never generic best-practice checklists.",
        "`suggested_addition` must be a complete, implementable requirement (shall-language, specific numbers/behaviours).",
        "Output 3-7 highest-impact gaps. Quality over quantity.",
        "Impact HIGH = data loss, financial discrepancy, security breach, or crash; MEDIUM = user confusion or manual intervention needed; LOW = minor inconvenience with a reasonable default.",
        "Scan categories (apply where relevant): failure paths, boundary conditions, authorisation gaps, concurrency, state-machine gaps, data integrity, integration boundaries.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_ARRAY,
        schema={
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["scenario_description", "impact", "suggested_addition"],
                "properties": {
                    "scenario_description": {"type": "string", "minLength": 1},
                    "impact": {
                        "type": "string",
                        "enum": ["HIGH", "MEDIUM", "LOW"],
                    },
                    "suggested_addition": {"type": "string", "minLength": 1},
                },
            },
        },
        empty_value="[]",
        notes="Empty array `[]` if the section already covers its failure paths.",
    ),
    few_shot=[
        FewShotExample(
            label="Payment timeout gap",
            input_snippet=('"The system shall charge the user via the payment gateway ""when they click Confirm."'),
            expected_output=(
                '[{"scenario_description": "The section describes happy-path '
                "payment but is silent on gateway timeouts after the charge "
                "is initiated but before confirmation — risking double-charge "
                'or lost payment.", "impact": "HIGH", "suggested_addition": '
                '"The system shall make payment processing idempotent. If the '
                "gateway does not respond within 30s after charge initiation, "
                "the system shall (1) retry confirmation up to 3 times with "
                "exponential back-off, (2) queue unconfirmed transactions for "
                'manual reconciliation, (3) display a \\"Payment Pending\\" '
                'status, and (4) email the user within 5 minutes."}]'
            ),
        ),
    ],
    refusal=(
        "If the section is empty, under 20 characters, or pure boilerplate "
        "(glossary, TOC, revision history), return `[]`."
    ),
    use_xml_scaffold=True,
    thinking_protocol=(
        "Run a silent failure-mode discovery in three passes.\n"
        "Pass 1 — Identify the concrete behaviours in the section "
        "(actions, transitions, integrations, persisted state).\n"
        "Pass 2 — For every behaviour, walk the seven scan categories "
        "(failure paths, boundaries, authorisation gaps, concurrency, "
        "state-machine gaps, data integrity, integration boundaries) "
        "and collect candidate gaps that the section is silent about.\n"
        "Pass 3 — Score each candidate by realistic blast radius and "
        "keep only the 3-7 highest-impact gaps. Drop generic "
        "'add logging' / 'consider rate limits' items unless the "
        "section's domain makes them load-bearing.\n"
        "These passes are private; only the final JSON is emitted."
    ),
    self_check=(
        "Before returning, verify every gap:\n"
        "1. References behaviour the section actually describes — never "
        "invents new features.\n"
        "2. `suggested_addition` is a complete shall/must requirement "
        "with concrete numbers, error codes, retry counts, or state "
        "transitions a developer can implement directly.\n"
        "3. Impact rating reflects worst plausible production outcome "
        "(HIGH only for data loss, financial, security, or crash).\n"
        "4. Two emitted gaps never overlap; merge near-duplicates."
    ),
)

USER_TEMPLATE = (
    "Read this FS section carefully. For every requirement, ask: 'What "
    "happens when this goes wrong, gets unexpected input, or hits a boundary?' "
    "Flag only scenarios the section is genuinely silent on.\n\n"
    'Section: "{heading}"\n\n{content}'
)


def build(heading: str, content: str) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(USER_TEMPLATE.format(heading=heading, content=content))
    return system, user


__all__ = ["NAME", "SPEC", "build"]
