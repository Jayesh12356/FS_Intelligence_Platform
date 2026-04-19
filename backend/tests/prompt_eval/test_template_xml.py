"""XML-scaffold opt-in tests for v2 prompts.

Two contracts are checked:

1. ``PromptSpec`` is backwards compatible. A spec that does NOT set
   ``use_xml_scaffold=True`` renders byte-identical to the legacy
   build_system output.

2. Every analysis + impact prompt the platform ships HAS opted in to
   the XML scaffold and therefore exposes the structural anchors
   (``<role>``, ``<mission>``, ``<output_format>``) plus the new
   thinking/self_check sections that uplift quality.
"""

from __future__ import annotations

import pytest

from app.pipeline.prompts.analysis import (
    ambiguity, contradiction, dependency, edge_case,
    quality, task, testcase,
)
from app.pipeline.prompts.impact import change_impact
from app.pipeline.prompts.master_template import (
    OutputContract,
    OutputShape,
    PromptSpec,
    build_system,
    build_system_xml,
)


UPLIFTED_SPECS = [
    ("analysis.ambiguity", ambiguity.SPEC),
    ("analysis.contradiction", contradiction.SPEC),
    ("analysis.edge_case", edge_case.SPEC),
    ("analysis.dependency", dependency.SPEC),
    ("analysis.task", task.SPEC),
    ("analysis.testcase", testcase.SPEC),
    ("analysis.quality.compliance", quality.SPEC),
    ("impact.change_impact", change_impact.SPEC),
]


# ---------------------------------------------------------------------------
# Backwards compatibility — legacy specs render identically.
# ---------------------------------------------------------------------------


def _legacy_spec() -> PromptSpec:
    return PromptSpec(
        name="legacy.test",
        role="You are a test role.",
        mission="One-line mission.",
        constraints=["Never lie.", "Be terse."],
        output_contract=OutputContract(shape=OutputShape.JSON_ARRAY),
    )


def test_legacy_spec_renders_with_legacy_template() -> None:
    spec = _legacy_spec()
    rendered = spec.system()
    assert rendered == build_system(spec), (
        "Legacy specs must keep using build_system to preserve byte-"
        "for-byte stability of golden snapshots."
    )
    # Sanity: legacy template uses uppercase headers, not XML tags.
    assert "<role>" not in rendered
    assert "MISSION" in rendered


def test_opt_in_xml_renders_with_xml_template() -> None:
    spec = _legacy_spec()
    spec.use_xml_scaffold = True
    rendered = spec.system()
    assert rendered == build_system_xml(spec)
    assert "<role>" in rendered
    assert "<mission>" in rendered
    assert "<output_format>" in rendered


# ---------------------------------------------------------------------------
# Every uplifted prompt has the XML anchors AND the new uplift sections.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name, spec", UPLIFTED_SPECS, ids=[n for n, _ in UPLIFTED_SPECS])
def test_uplifted_prompt_has_xml_anchors(name: str, spec: PromptSpec) -> None:
    assert spec.use_xml_scaffold, f"{name}: must opt into XML scaffold"
    rendered = spec.system()
    for tag in ("<role>", "<mission>", "<instructions>", "<output_format>", "<refusal>"):
        assert tag in rendered, f"{name}: missing required XML anchor {tag}"


@pytest.mark.parametrize("name, spec", UPLIFTED_SPECS, ids=[n for n, _ in UPLIFTED_SPECS])
def test_uplifted_prompt_has_thinking_and_self_check(
    name: str, spec: PromptSpec
) -> None:
    assert spec.thinking_protocol.strip(), (
        f"{name}: thinking_protocol must be populated to drive CoT"
    )
    assert spec.self_check.strip(), (
        f"{name}: self_check must be populated to gate output quality"
    )
    rendered = spec.system()
    assert "<thinking_protocol>" in rendered
    assert "<self_check>" in rendered


@pytest.mark.parametrize("name, spec", UPLIFTED_SPECS, ids=[n for n, _ in UPLIFTED_SPECS])
def test_uplifted_prompt_keeps_legacy_section_markers(
    name: str, spec: PromptSpec
) -> None:
    """Golden + structural tests still grep for these uppercase markers,
    so the XML render keeps them inside the tags."""
    rendered = spec.system()
    for marker in ("MISSION", "HARD CONSTRAINTS", "OUTPUT CONTRACT", "REFUSAL"):
        assert marker in rendered, (
            f"{name}: legacy marker {marker!r} must appear inside the XML "
            "scaffold so back-compat tests keep passing."
        )
