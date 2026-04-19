"""Impact analysis prompt (v2).

Classifies every task in a task list as INVALIDATED, REQUIRES_REVIEW, or
UNAFFECTED for a single FS change.
"""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    FewShotExample,
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "impact.change_impact"

_FEW_SHOT = [
    FewShotExample(
        label="Auth overhaul cascade",
        input_snippet=(
            "CHANGE (MODIFIED — section 'Authentication'): JWT replaced by "
            "OAuth2 SSO.\n\nTASKS: T1 Implement user login API, T2 Create "
            "user dashboard, T3 Configure CI/CD pipeline."
        ),
        expected_output=(
            "[\n"
            '  {"task_id":"T1","task_title":"Implement user login API",'
            '"impact_type":"INVALIDATED","reason":"Task implements JWT '
            "issuance/validation which must be completely rewritten for "
            'the OAuth2 flow defined in the change."},\n'
            '  {"task_id":"T2","task_title":"Create user dashboard",'
            '"impact_type":"REQUIRES_REVIEW","reason":"Dashboard reads the '
            "session token set by T1; token format changes from JWT to "
            'OAuth2 access token, so session-reading logic needs verification."},\n'
            '  {"task_id":"T3","task_title":"Configure CI/CD pipeline",'
            '"impact_type":"UNAFFECTED","reason":"Infrastructure automation '
            'task with no dependency on authentication logic or user data."}\n'
            "]"
        ),
    )
]


SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a change-impact analyst for a software project. When a "
        "requirement changes you decide exactly which existing development "
        "tasks are affected and how severely, so the team rebuilds only "
        "what is necessary and nothing more."
    ),
    mission=(
        "Classify EVERY task in the input against a single FS change using "
        "three categories: INVALIDATED, REQUIRES_REVIEW, UNAFFECTED."
    ),
    constraints=[
        "Emit one object per input task — never omit a task.",
        "INVALIDATED: the existing implementation would produce incorrect behaviour after the change (contract, data model, or business rule change).",
        "REQUIRES_REVIEW: the task transitively depends on the change (imports a changed module, consumes an INVALIDATED task's output, or relies on a cross-cutting concern that shifted). When torn between UNAFFECTED and REQUIRES_REVIEW, choose REQUIRES_REVIEW.",
        "UNAFFECTED: the task would compile, run, and pass tests identically before and after the change.",
        "Cascade rules: DB schema changes cascade to every task reading/writing that table; auth/authz changes cascade to every protected endpoint; API response shape changes cascade to every frontend task consuming that API; shared-utility changes cascade to every task importing that module.",
        "`reason` must cite the specific part of the change text that affects this task and describe HOW it affects it. Generic reasons like 'uses auth' are forbidden.",
        "`task_id` and `task_title` must echo the input verbatim.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_ARRAY,
        schema={
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "task_id",
                    "task_title",
                    "impact_type",
                    "reason",
                ],
                "properties": {
                    "task_id": {"type": "string", "minLength": 1},
                    "task_title": {"type": "string", "minLength": 1},
                    "impact_type": {
                        "type": "string",
                        "enum": ["INVALIDATED", "REQUIRES_REVIEW", "UNAFFECTED"],
                    },
                    "reason": {"type": "string", "minLength": 1},
                },
            },
        },
        empty_value="[]",
    ),
    few_shot=_FEW_SHOT,
    refusal=("If the task list is empty, return `[]`. Never return prose."),
    use_xml_scaffold=True,
    thinking_protocol=(
        "Classify in four silent passes.\n"
        "Pass 1 — Read the change and identify what shifted: contract "
        "(API shape), data model, business rule, auth flow, "
        "dependency boundary, or cross-cutting concern.\n"
        "Pass 2 — For every input task, ask: 'After this change, "
        "would the existing implementation still produce correct "
        "behaviour?' If NO, mark INVALIDATED.\n"
        "Pass 3 — For tasks not invalidated, evaluate transitive "
        "exposure: imports of changed modules, consumption of an "
        "INVALIDATED task's output, reliance on a shifted "
        "cross-cutting concern. If exposed, mark REQUIRES_REVIEW. "
        "Tie-breaker: when undecided between UNAFFECTED and "
        "REQUIRES_REVIEW, choose REQUIRES_REVIEW.\n"
        "Pass 4 — Verify the count of emitted entries equals the "
        "count of input tasks, then emit JSON."
    ),
    self_check=(
        "Before returning, verify:\n"
        "1. Every input task appears exactly once with `task_id` and "
        "`task_title` echoed verbatim.\n"
        "2. INVALIDATED is justified by a direct contract/data/rule "
        "break, not a hunch.\n"
        "3. REQUIRES_REVIEW reasons cite the specific cascade path "
        "(e.g. 'consumes T1 output whose response shape changes').\n"
        "4. UNAFFECTED tasks would compile, run, and pass tests "
        "identically before and after the change.\n"
        "5. Reasons reference specific text from the change — never "
        "generic phrases like 'uses auth' or 'might be affected'."
    ),
)

USER_TEMPLATE = (
    "Classify the impact of this FS change on EVERY task listed below. "
    "Consider both direct effects and cascading dependencies.\n\nCHANGE:\n"
    'Type: {change_type}\nSection: "{section_heading}"\n\n'
    "Previous text:\n{old_text}\n\nNew text:\n{new_text}\n\n"
    "TASKS TO ASSESS:\n{task_list}\n\n"
    "Return a JSON array with an entry for EVERY task. Do not omit any task."
)


def build(
    change_type: str,
    section_heading: str,
    old_text: str,
    new_text: str,
    task_list: str,
) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(
        USER_TEMPLATE.format(
            change_type=change_type,
            section_heading=section_heading,
            old_text=old_text,
            new_text=new_text,
            task_list=task_list,
        )
    )
    return system, user


__all__ = ["NAME", "SPEC", "build"]
