"""Reverse-FS user-flow identification prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "reverse.user_flows"

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a software architect identifying the distinct user-facing "
        "features in a codebase by analysing module summaries. A 'user flow' "
        "is a complete end-to-end capability that delivers value to a user "
        "or system consumer."
    ),
    mission=("From a set of module summaries, enumerate the 3-10 most valuable user flows that span multiple modules."),
    constraints=[
        "Each flow has a clear TRIGGER (user action, API call, scheduled job, event) and a clear OUTCOME (data displayed, record created, notification sent, file exported).",
        "A flow spans multiple modules. If only one module is involved, it is a utility, not a flow — do not emit it.",
        "Merge closely related sub-flows (e.g. 'Create Order' + 'Validate Order' = one 'Order Processing' flow).",
        "`flow_name` is 2-4 words.",
        "`description` is one sentence naming trigger, action, and outcome.",
        "`involved_modules` lists modules in execution order.",
        "`entry_points` names the specific function or endpoint where the flow begins.",
        "Target 3-10 flows. Prefer user-facing features over internal utilities, background jobs, or infra setup.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_ARRAY,
        schema={
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "flow_name",
                    "description",
                    "involved_modules",
                    "entry_points",
                ],
                "properties": {
                    "flow_name": {"type": "string", "minLength": 1},
                    "description": {"type": "string", "minLength": 1},
                    "involved_modules": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "entry_points": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        empty_value="[]",
    ),
    few_shot=[],
    refusal=("If the module summaries describe only utilities (no user-facing flows), return `[]`."),
)

USER_TEMPLATE = (
    "Identify the distinct user-facing features in this codebase based on "
    "the module summaries below.\n\nModule summaries:\n{module_summaries}"
    "\n\nCodebase stats: {primary_language}, {total_files} files, "
    "{total_lines} lines.\n\nReturn a JSON array of user flows."
)


def build(
    module_summaries: str,
    primary_language: str,
    total_files: int,
    total_lines: int,
) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(
        USER_TEMPLATE.format(
            module_summaries=module_summaries,
            primary_language=primary_language,
            total_files=total_files,
            total_lines=total_lines,
        )
    )
    return system, user


__all__ = ["NAME", "SPEC", "build"]
