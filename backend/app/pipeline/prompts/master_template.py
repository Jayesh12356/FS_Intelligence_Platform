"""Master prompt template.

Every backend LLM prompt derives from :class:`PromptSpec`. The template
enforces five invariants shared by every node:

1. A named role with explicit seniority anchors (no "as an AI" voice).
2. A one-sentence mission so the model cannot drift off-task.
3. Hard constraints surfaced before the task, not buried below.
4. A strict output contract (JSON array/object or markdown shape) with
   "no fences / no prose" directive and an optional JSON schema hint.
5. A refusal rule describing what to do on malformed input so the model
   returns a valid empty payload instead of prose.

The template also gives tests a single surface to assert structural
invariants (e.g. "every prompt must mention no markdown fences" or
"every JSON contract must declare additionalProperties=false").
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class OutputShape(StrEnum):
    JSON_ARRAY = "json_array"
    JSON_OBJECT = "json_object"
    MARKDOWN = "markdown"


@dataclass
class FewShotExample:
    """One synthetic input -> expected output pair."""

    label: str
    input_snippet: str
    expected_output: str


@dataclass
class OutputContract:
    """Describes the allowed shape of the model's reply."""

    shape: OutputShape
    schema: dict[str, Any] | None = None
    empty_value: str = "[]"
    notes: str = ""

    def schema_hash(self) -> str:
        """Stable short hash used in tests and logs."""
        payload = json.dumps(
            {
                "shape": self.shape.value,
                "schema": self.schema or {},
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:10]


@dataclass
class PromptSpec:
    """Structured specification for a single prompt surface.

    The new optional fields (``thinking_protocol``, ``self_check``,
    ``use_xml_scaffold``) drive an Anthropic-style XML rendering with
    ``<role>``/``<mission>``/``<context>``/``<instructions>``/
    ``<thinking_protocol>``/``<output_format>``/``<examples>``/
    ``<self_check>`` tags. They default to off, so legacy prompts
    render byte-identical to the previous version. The 8 analysis
    prompts and the build-path prompts opt in to gain the lift.
    """

    name: str
    role: str
    mission: str
    constraints: list[str] = field(default_factory=list)
    output_contract: OutputContract | None = None
    few_shot: list[FewShotExample] = field(default_factory=list)
    refusal: str = (
        "If the input is empty, unreadable, or off-topic, return the empty "
        "value for the declared output shape. Never apologise in prose."
    )
    extras: list[str] = field(default_factory=list)
    # New, opt-in prompt-engineering primitives.
    thinking_protocol: str = ""
    self_check: str = ""
    use_xml_scaffold: bool = False

    def system(self) -> str:
        if self.use_xml_scaffold:
            return build_system_xml(self)
        return build_system(self)

    def user(self, body: str, *, context: dict[str, Any] | None = None) -> str:
        return build_user(body, context or {}, self.output_contract)


def _contract_block(contract: OutputContract | None) -> str:
    if contract is None:
        return ""
    lines = [
        "",
        "OUTPUT CONTRACT",
        "---------------",
    ]
    if contract.shape == OutputShape.JSON_ARRAY:
        lines.append(
            "Return a SINGLE JSON array. No markdown fences, no prose before "
            "or after. Empty array `[]` if there is nothing to report."
        )
    elif contract.shape == OutputShape.JSON_OBJECT:
        lines.append(
            "Return a SINGLE JSON object. No markdown fences, no prose before "
            "or after. Empty object `{}` is valid only if the task explicitly "
            "allows it."
        )
    else:
        lines.append(
            "Return plain Markdown only. No JSON wrapper, no code fences unless the section explicitly calls for them."
        )
    if contract.schema is not None:
        lines.append("")
        lines.append("Schema (informational — do NOT echo it):")
        lines.append(json.dumps(contract.schema, indent=2))
        lines.append(
            "Every emitted object must satisfy the schema exactly. Fields "
            "marked `additionalProperties: false` must not be extended."
        )
    if contract.notes:
        lines.append("")
        lines.append(contract.notes)
    return "\n".join(lines)


def _few_shot_block(examples: list[FewShotExample]) -> str:
    if not examples:
        return ""
    parts = ["", "EXAMPLES", "--------"]
    for ex in examples:
        parts.append(f"Example — {ex.label}")
        parts.append("Input:")
        parts.append(ex.input_snippet.strip())
        parts.append("Output:")
        parts.append(ex.expected_output.strip())
        parts.append("")
    return "\n".join(parts).rstrip()


def build_system(spec: PromptSpec) -> str:
    """Render the system prompt for a :class:`PromptSpec`."""

    sections: list[str] = []
    sections.append(spec.role.strip())
    sections.append("")
    sections.append(f"MISSION — {spec.mission.strip()}")

    if spec.constraints:
        sections.append("")
        sections.append("HARD CONSTRAINTS")
        sections.append("----------------")
        for c in spec.constraints:
            sections.append(f"- {c.strip()}")

    if spec.extras:
        for block in spec.extras:
            sections.append("")
            sections.append(block.strip())

    contract_block = _contract_block(spec.output_contract)
    if contract_block:
        sections.append(contract_block)

    few_shot_block = _few_shot_block(spec.few_shot)
    if few_shot_block:
        sections.append("")
        sections.append(few_shot_block)

    sections.append("")
    sections.append("REFUSAL")
    sections.append("-------")
    sections.append(spec.refusal.strip())

    return "\n".join(sections).strip()


def build_user(
    body: str,
    context: dict[str, Any] | None,
    contract: OutputContract | None,
) -> str:
    """Render the user prompt from a body and optional context."""

    parts: list[str] = []
    if context:
        ctx_lines = [f"- {k}: {v}" for k, v in context.items() if v is not None]
        if ctx_lines:
            parts.append("CONTEXT")
            parts.extend(ctx_lines)
            parts.append("")
    parts.append(body.strip())
    if contract is not None:
        parts.append("")
        if contract.shape == OutputShape.JSON_ARRAY:
            parts.append(f"Reminder: respond with a single JSON array only. Empty is {contract.empty_value}.")
        elif contract.shape == OutputShape.JSON_OBJECT:
            parts.append(f"Reminder: respond with a single JSON object only. Empty is {contract.empty_value}.")
    return "\n".join(parts)


def _xml_output_format(contract: OutputContract | None) -> str:
    if contract is None:
        return ""
    if contract.shape == OutputShape.JSON_ARRAY:
        opener = (
            "Return a SINGLE JSON array. No markdown fences, no prose before "
            "or after. Empty array `[]` if there is nothing to report."
        )
    elif contract.shape == OutputShape.JSON_OBJECT:
        opener = (
            "Return a SINGLE JSON object. No markdown fences, no prose before "
            "or after. Empty object `{}` is valid only if the task explicitly "
            "allows it."
        )
    else:
        opener = (
            "Return plain Markdown only. No JSON wrapper, no code fences "
            "unless the section explicitly calls for them."
        )
    parts = [opener]
    if contract.schema is not None:
        parts.append("")
        parts.append("Schema (informational — do NOT echo it):")
        parts.append(json.dumps(contract.schema, indent=2))
        parts.append(
            "Every emitted object must satisfy the schema exactly. Fields "
            "marked `additionalProperties: false` must not be extended."
        )
    if contract.notes:
        parts.append("")
        parts.append(contract.notes)
    return "\n".join(parts)


def _xml_examples(examples: list[FewShotExample]) -> str:
    if not examples:
        return ""
    parts: list[str] = []
    for ex in examples:
        parts.append(f"<example label=\"{ex.label}\">")
        parts.append("  <input>")
        parts.append(ex.input_snippet.strip())
        parts.append("  </input>")
        parts.append("  <output>")
        parts.append(ex.expected_output.strip())
        parts.append("  </output>")
        parts.append("</example>")
    return "\n".join(parts)


def build_system_xml(spec: PromptSpec) -> str:
    """Render the system prompt using XML-scaffolded sections.

    The XML tags are anchors for the model (Claude/GPT both attend to
    them as soft section markers) and for our test suite, which asserts
    the presence of `<role>`, `<mission>`, and `<output_format>` for
    every uplifted prompt.
    """

    sections: list[str] = []
    sections.append("<role>")
    sections.append(spec.role.strip())
    sections.append("</role>")

    sections.append("")
    sections.append("<mission>")
    sections.append(f"MISSION — {spec.mission.strip()}")
    sections.append("</mission>")

    if spec.constraints:
        sections.append("")
        sections.append("<instructions>")
        sections.append("HARD CONSTRAINTS — violations invalidate your output:")
        for c in spec.constraints:
            sections.append(f"- {c.strip()}")
        sections.append("</instructions>")

    if spec.extras:
        sections.append("")
        sections.append("<context>")
        for block in spec.extras:
            sections.append(block.strip())
            sections.append("")
        # drop trailing blank
        while sections and sections[-1] == "":
            sections.pop()
        sections.append("</context>")

    if spec.thinking_protocol:
        sections.append("")
        sections.append("<thinking_protocol>")
        sections.append(spec.thinking_protocol.strip())
        sections.append("</thinking_protocol>")

    output_block = _xml_output_format(spec.output_contract)
    if output_block:
        sections.append("")
        sections.append("<output_format>")
        sections.append("OUTPUT CONTRACT")
        sections.append(output_block)
        sections.append("</output_format>")

    examples_block = _xml_examples(spec.few_shot)
    if examples_block:
        sections.append("")
        sections.append("<examples>")
        sections.append(examples_block)
        sections.append("</examples>")

    if spec.self_check:
        sections.append("")
        sections.append("<self_check>")
        sections.append(spec.self_check.strip())
        sections.append("</self_check>")

    sections.append("")
    sections.append("<refusal>")
    sections.append("REFUSAL")
    sections.append(spec.refusal.strip())
    sections.append("</refusal>")

    return "\n".join(sections).strip()


__all__ = [
    "FewShotExample",
    "OutputContract",
    "OutputShape",
    "PromptSpec",
    "build_system",
    "build_system_xml",
    "build_user",
]
