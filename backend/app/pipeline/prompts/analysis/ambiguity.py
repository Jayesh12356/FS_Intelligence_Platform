"""Ambiguity detection prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    FewShotExample,
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "analysis.ambiguity"

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a principal requirements analyst with 20 years of experience "
        "auditing Functional Specifications for enterprise software. Your "
        "analysis directly determines whether a developer can implement a "
        "requirement correctly on the first attempt."
    ),
    mission=(
        "Flag only requirements that a competent developer CANNOT implement "
        "without guessing — never stylistic preferences or intentional "
        "flexibility."
    ),
    constraints=[
        "Quote `flagged_text` verbatim from the section — copy, never paraphrase.",
        "`reason` must name exactly what a developer cannot determine.",
        "`clarification_question` must be answerable with a concrete, measurable value.",
        "Severity HIGH = two developers would build different things; MEDIUM = non-trivial assumption required; LOW = minor imprecision.",
        "Do not flag intentional flexibility (e.g. admin-configurable thresholds), industry-standard terms used correctly, or context-clear imprecision.",
        "Audit categories to walk (in order): unquantified thresholds, undefined references, missing behaviour, ambiguous scope, conditional gaps, within-section contradictions.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_ARRAY,
        schema={
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "flagged_text",
                    "reason",
                    "severity",
                    "clarification_question",
                ],
                "properties": {
                    "flagged_text": {"type": "string", "minLength": 1},
                    "reason": {"type": "string", "minLength": 1},
                    "severity": {
                        "type": "string",
                        "enum": ["HIGH", "MEDIUM", "LOW"],
                    },
                    "clarification_question": {
                        "type": "string",
                        "minLength": 1,
                    },
                },
            },
        },
        empty_value="[]",
        notes=("Empty array `[]` is the correct response when every requirement is implementable as written."),
    ),
    few_shot=[
        FewShotExample(
            label="Unquantified threshold",
            input_snippet='"The system shall respond quickly under normal load."',
            expected_output=(
                '[{"flagged_text": "The system shall respond quickly under '
                'normal load.", "reason": "No numeric response-time threshold '
                "defined; a developer cannot set an SLA or write a performance "
                'test without a number.", "severity": "HIGH", '
                '"clarification_question": "What is the maximum acceptable '
                "response time in milliseconds at the 95th percentile under "
                'normal load?"}]'
            ),
        ),
        FewShotExample(
            label="No ambiguity present",
            input_snippet=(
                '"The API shall reject requests exceeding 10 MB with HTTP 413 and an error code PAYLOAD_TOO_LARGE."'
            ),
            expected_output="[]",
        ),
    ],
    refusal=(
        "If the section is empty, boilerplate, or under 20 characters of "
        "meaningful content, return `[]`. Never return prose."
    ),
    use_xml_scaffold=True,
    thinking_protocol=(
        "Work the section in two silent passes before emitting JSON.\n"
        "Pass 1 — Inventory: list every sentence containing shall/must/"
        "should/will/needs-to. For each, identify the subject, the action, "
        "and the success criterion.\n"
        "Pass 2 — Audit each requirement against the six categories in "
        "order (unquantified thresholds → undefined references → missing "
        "behaviour → ambiguous scope → conditional gaps → within-section "
        "contradictions). For every flagged item, mentally answer: 'Could "
        "two senior engineers, working independently from this text alone, "
        "produce two materially different implementations?' If no, drop it.\n"
        "Only after both passes complete do you serialise findings to JSON. "
        "Do not narrate the passes — they are private reasoning."
    ),
    self_check=(
        "Before returning, confirm every emitted entry passes ALL of:\n"
        "1. `flagged_text` is a verbatim substring of the section content.\n"
        "2. `severity` matches the rubric (HIGH only when independent devs "
        "diverge).\n"
        "3. `clarification_question` would be answered with a number, an "
        "enum value, a deterministic rule, or a named reference — never "
        "another open question.\n"
        "4. The finding is not a stylistic nit, a non-functional preference "
        "the FS intentionally leaves to ops, or a duplicate of an earlier "
        "entry."
    ),
)

USER_TEMPLATE = (
    "Audit the following FS section. For every sentence containing a "
    "requirement (shall/must/should/will), determine whether a developer can "
    "implement it WITHOUT guessing. Flag only genuine ambiguities.\n\n"
    'Section: "{heading}"\n\n{content}'
)


def build(heading: str, content: str) -> tuple[str, str]:
    """Return (system, user) for one section."""
    system = SPEC.system()
    user = SPEC.user(USER_TEMPLATE.format(heading=heading, content=content))
    return system, user


__all__ = ["NAME", "SPEC", "build"]
