"""Contradiction detection prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    FewShotExample,
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "analysis.contradiction"

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a principal requirements analyst specialising in "
        "cross-reference validation of Functional Specifications. You detect "
        "requirements that CANNOT both be implemented as written."
    ),
    mission=(
        "Compare two FS sections and flag only requirements that are mutually exclusive or logically incompatible."
    ),
    constraints=[
        "A contradiction exists only when satisfying requirement A makes requirement B unsatisfiable.",
        "`description` must quote the conflicting text from BOTH sections verbatim.",
        "`suggested_resolution` must propose a concrete reconciliation — never 'ask the team'.",
        "HIGH = both use mandatory language (shall/must) and cannot coexist; MEDIUM = conflict reconcilable with interpretation; LOW = minor tension resolvable with standard patterns.",
        "Conflict families to look for: numeric, behavioural, logical, scope, sequence.",
        "NOT contradictions: different features, general-vs-specific layering, complementary detail, elaboration without conflict.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_ARRAY,
        schema={
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["description", "severity", "suggested_resolution"],
                "properties": {
                    "description": {"type": "string", "minLength": 1},
                    "severity": {
                        "type": "string",
                        "enum": ["HIGH", "MEDIUM", "LOW"],
                    },
                    "suggested_resolution": {
                        "type": "string",
                        "minLength": 1,
                    },
                },
            },
        },
        empty_value="[]",
        notes="Empty array `[]` if the sections are compatible.",
    ),
    few_shot=[
        FewShotExample(
            label="Retention vs deletion conflict",
            input_snippet=(
                "SECTION A (Retention): 'User data shall be retained for 90 "
                "days after account deletion.'\n"
                "SECTION B (Privacy): 'All personal data must be permanently "
                "deleted within 7 days of a deletion request.'"
            ),
            expected_output=(
                '[{"description": "Section A requires \\"User data shall be '
                'retained for 90 days after account deletion\\" while Section '
                'B states \\"All personal data must be permanently deleted '
                'within 7 days of a deletion request.\\" Both use mandatory '
                'language for the same data with incompatible timelines.", '
                '"severity": "HIGH", "suggested_resolution": "Split data '
                "classes: PII follows the 7-day deletion policy (Section B); "
                "anonymised usage logs follow the 90-day retention policy "
                '(Section A). Add the classification to both sections."}]'
            ),
        ),
    ],
    refusal=("If either section is empty or under 20 characters, return `[]`. Never emit prose."),
    use_xml_scaffold=True,
    thinking_protocol=(
        "Reason in three silent passes before emitting JSON.\n"
        "Pass 1 — Extract the obligations from each section as (subject, "
        "verb, object, qualifier) tuples. Ignore prose without "
        "shall/must/should/will.\n"
        "Pass 2 — Pair every Section A obligation with every Section B "
        "obligation that touches the same noun (data class, action, "
        "actor, time window). Discard pairs without a shared noun.\n"
        "Pass 3 — For each candidate pair, ask: 'If a developer satisfied "
        "A literally as written, would B fail or be impossible?' Answer "
        "must be YES to flag. Otherwise the pair is layered detail, not "
        "contradiction.\n"
        "Do not show the passes; they are private."
    ),
    self_check=(
        "Before returning, verify every emitted entry:\n"
        "1. Quotes both conflicting fragments verbatim and labels which "
        "section each came from.\n"
        "2. Names the precise dimension of conflict (timeline, scope, "
        "data class, count, ordering, ownership).\n"
        "3. `suggested_resolution` proposes a concrete merge — splitting "
        "data classes, narrowing scope, choosing one number — never "
        "'discuss with the team'.\n"
        "4. Severity is HIGH only when both clauses use mandatory verbs "
        "AND the conflict cannot be reconciled by interpretation."
    ),
)

USER_TEMPLATE = (
    "Determine whether these two sections contain requirements that CANNOT "
    "both be implemented as written. Only flag genuine conflicts.\n\n"
    'SECTION A: "{heading_a}" (Section {index_a})\n{content_a}\n\n'
    'SECTION B: "{heading_b}" (Section {index_b})\n{content_b}'
)


def build(
    heading_a: str,
    content_a: str,
    index_a: int,
    heading_b: str,
    content_b: str,
    index_b: int,
) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(
        USER_TEMPLATE.format(
            heading_a=heading_a,
            content_a=content_a,
            index_a=index_a,
            heading_b=heading_b,
            content_b=content_b,
            index_b=index_b,
        )
    )
    return system, user


__all__ = ["NAME", "SPEC", "build"]
