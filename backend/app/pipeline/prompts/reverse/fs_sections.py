"""Reverse-FS section generation prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "reverse.fs_sections"

REQUIRED_HEADINGS = (
    "Purpose",
    "Actors",
    "Preconditions",
    "Functional Requirements",
    "Alternate Flows & Error Handling",
    "Data Requirements",
    "Non-Functional Requirements",
)

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a senior technical writer producing a Functional "
        "Specification from code analysis. Your voice is formal and "
        "implementation-independent — you describe WHAT the system does, "
        "never HOW the code achieves it."
    ),
    mission=(
        "Write a complete FS section for one feature using the exact "
        "structure below, based on the inferred module behaviours."
    ),
    constraints=[
        "Use these exact headings, in order: " + ", ".join(REQUIRED_HEADINGS) + ".",
        "Functional Requirements: numbered list using 'The system shall...' language. Each requirement is specific, testable, and atomic.",
        "Preconditions: numbered list of conditions that must be true before the feature executes.",
        "Alternate Flows & Error Handling: numbered list of failure paths.",
        "Data Requirements: table OR list of entities with name, type, constraints, source/destination.",
        "Non-Functional Requirements: use 'shall' language with specific thresholds when the code reveals them (timeouts, page sizes, retries).",
        "NEVER include code snippets, function names, class names, or file paths.",
        "NEVER say 'the code does X' — say 'the system shall do X'.",
        "Write for a reader who has never seen the codebase. Keep each section 150-400 words.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.MARKDOWN,
        empty_value="",
        notes=("Return plain text with the seven required headings. Do NOT wrap in JSON or code fences."),
    ),
    few_shot=[],
    refusal=(
        "If the flow metadata is empty, write a section with each required "
        "heading and a single line: 'Not yet specified.' Never return "
        "prose outside the defined structure."
    ),
)

USER_TEMPLATE = (
    "Write a formal Functional Specification section for this feature. "
    "Describe WHAT the system does, not how the code works.\n\n"
    "Feature: {flow_name}\nDescription: {flow_description}\n\n"
    "Involved components:\n{involved_modules}\n\nComponent details:\n"
    "{module_details}\n\nReturn a complete FS section using the required "
    "structure (Purpose, Actors, Preconditions, Functional Requirements, "
    "Alternate Flows, Data Requirements, Non-Functional Requirements)."
)


def build(
    flow_name: str,
    flow_description: str,
    involved_modules: str,
    module_details: str,
) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(
        USER_TEMPLATE.format(
            flow_name=flow_name,
            flow_description=flow_description,
            involved_modules=involved_modules,
            module_details=module_details,
        )
    )
    return system, user


__all__ = ["NAME", "SPEC", "REQUIRED_HEADINGS", "build"]
