"""Structural (CI) tests for every v2 prompt.

These run offline and assert that every PromptSpec:
  - Declares role, mission, constraints, output_contract.
  - Renders a non-empty system prompt containing the mandatory markers
    (``MISSION``, ``OUTPUT CONTRACT``, ``REFUSAL``).
  - Produces a deterministic user prompt when ``build(...)`` is invoked.
  - Has a self-consistent JSON schema when the contract is JSON.

Call this from CI on every commit. For live-LLM tests see
``test_live.py`` (guarded by PROMPT_EVAL_LIVE=1).
"""

from __future__ import annotations

import json
from typing import Any, Callable

import pytest

from app.pipeline.prompts.analysis import (
    ambiguity as ambiguity_prompt,
)
from app.pipeline.prompts.analysis import (
    contradiction as contradiction_prompt,
)
from app.pipeline.prompts.analysis import (
    dependency as dependency_prompt,
)
from app.pipeline.prompts.analysis import (
    edge_case as edge_case_prompt,
)
from app.pipeline.prompts.analysis import (
    quality as quality_prompt,
)
from app.pipeline.prompts.analysis import (
    task as task_prompt,
)
from app.pipeline.prompts.analysis import (
    testcase as testcase_prompt,
)
from app.pipeline.prompts.idea import (
    guided_fs as guided_fs_prompt,
)
from app.pipeline.prompts.idea import (
    guided_questions as guided_questions_prompt,
)
from app.pipeline.prompts.idea import (
    quick as quick_prompt,
)
from app.pipeline.prompts.impact import change_impact as change_impact_prompt
from app.pipeline.prompts.master_template import (
    OutputShape,
    PromptSpec,
)
from app.pipeline.prompts.refinement import (
    rewriter as rewriter_prompt,
)
from app.pipeline.prompts.refinement import (
    suggestion as suggestion_prompt,
)
from app.pipeline.prompts.reverse import (
    fs_sections as fs_sections_prompt,
)
from app.pipeline.prompts.reverse import (
    module_summary as module_summary_prompt,
)
from app.pipeline.prompts.reverse import (
    user_flows as user_flows_prompt,
)

# ---------------------------------------------------------------------------
# Fixtures — one (PromptSpec, build_callable, sample_kwargs) per surface.
# ---------------------------------------------------------------------------


def _sample_for(name: str) -> dict[str, Any]:
    """Realistic but minimal kwargs so build(...) always renders.

    Must match the real call-site signature of each prompt's build(...).
    """
    samples: dict[str, dict[str, Any]] = {
        "analysis.ambiguity": {
            "heading": "Performance",
            "content": "The system shall be fast.",
        },
        "analysis.contradiction": {
            "heading_a": "API",
            "content_a": "The system shall respond in 1s.",
            "index_a": 1,
            "heading_b": "API",
            "content_b": "The system shall respond in 5s.",
            "index_b": 2,
        },
        "analysis.edge_case": {
            "heading": "Upload",
            "content": "User uploads a file.",
        },
        "analysis.quality.compliance": {
            "heading": "Logging",
            "content": "REQ-1: The system shall log events.",
        },
        "analysis.task": {
            "heading": "Auth",
            "content": "The system shall authenticate users.",
            "index": 1,
        },
        "analysis.dependency": {
            "task_list": "- t1: Create DB schema\n- t2: Insert records",
        },
        "analysis.testcase": {
            "title": "Login",
            "description": "Authenticate user",
            "criteria_text": "Return 200 on valid creds",
        },
        "refinement.suggestion": {
            "issue_type": "AMBIGUITY",
            "section_heading": "Performance",
            "issue": "Vague phrase: 'fast'.",
            "original_text": "The system shall be fast.",
        },
        "refinement.rewriter": {
            "document": "# FS\n\n## Performance\nThe system shall be fast.",
            "suggestion_lines": ("1. Replace 'fast' with 'respond within 200ms at p95'."),
            "count": 1,
        },
        "idea.quick": {
            "idea": "A task tracker",
            "industry": "SaaS",
            "complexity": "standard",
        },
        "idea.guided_questions": {
            "idea": "A task tracker",
        },
        "idea.guided_fs": {
            "idea": "A task tracker",
            "answers": {"Users?": "Teams"},
            "industry": None,
            "complexity": "standard",
        },
        "reverse.module_summary": {
            "file_path": "src/auth.py",
            "language": "python",
            "entities": "- function: login — login(u,p)",
            "code_excerpt": "def login(u, p): ...",
        },
        "reverse.user_flows": {
            "module_summaries": "### auth\nPurpose: Manages auth",
            "primary_language": "python",
            "total_files": 10,
            "total_lines": 1000,
        },
        "reverse.fs_sections": {
            "flow_name": "User Login",
            "flow_description": "User submits credentials",
            "involved_modules": "- auth",
            "module_details": "**auth** Purpose: Manages auth",
        },
        "impact.change_impact": {
            "change_type": "MODIFIED",
            "section_heading": "Auth",
            "old_text": "JWT",
            "new_text": "OAuth2",
            "task_list": "- **t1** | Login (Section: Auth, Effort: MEDIUM)",
        },
    }
    return samples[name]


def _all_prompts() -> list[tuple[str, PromptSpec, Callable[..., tuple[str, str]]]]:
    entries: list[tuple[str, PromptSpec, Callable[..., tuple[str, str]]]] = [
        (ambiguity_prompt.NAME, ambiguity_prompt.SPEC, ambiguity_prompt.build),
        (
            contradiction_prompt.NAME,
            contradiction_prompt.SPEC,
            contradiction_prompt.build,
        ),
        (edge_case_prompt.NAME, edge_case_prompt.SPEC, edge_case_prompt.build),
        (quality_prompt.NAME, quality_prompt.SPEC, quality_prompt.build),
        (task_prompt.NAME, task_prompt.SPEC, task_prompt.build),
        (dependency_prompt.NAME, dependency_prompt.SPEC, dependency_prompt.build),
        (testcase_prompt.NAME, testcase_prompt.SPEC, testcase_prompt.build),
        (suggestion_prompt.NAME, suggestion_prompt.SPEC, suggestion_prompt.build),
        (rewriter_prompt.NAME, rewriter_prompt.SPEC, rewriter_prompt.build),
        (quick_prompt.NAME, quick_prompt.SPEC, quick_prompt.build),
        (
            guided_questions_prompt.NAME,
            guided_questions_prompt.SPEC,
            guided_questions_prompt.build,
        ),
        (guided_fs_prompt.NAME, guided_fs_prompt.SPEC, guided_fs_prompt.build),
        (
            module_summary_prompt.NAME,
            module_summary_prompt.SPEC,
            module_summary_prompt.build,
        ),
        (user_flows_prompt.NAME, user_flows_prompt.SPEC, user_flows_prompt.build),
        (fs_sections_prompt.NAME, fs_sections_prompt.SPEC, fs_sections_prompt.build),
        (
            change_impact_prompt.NAME,
            change_impact_prompt.SPEC,
            change_impact_prompt.build,
        ),
    ]
    return entries


PROMPTS = _all_prompts()
PROMPT_IDS = [name for name, *_ in PROMPTS]


# ---------------------------------------------------------------------------
# Core structural tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name, spec, builder", PROMPTS, ids=PROMPT_IDS)
def test_spec_has_required_fields(name: str, spec: PromptSpec, builder: Callable) -> None:
    assert spec.name == name, f"spec.name must match registration name: {name}"
    assert spec.role.strip(), "role must be non-empty"
    assert spec.mission.strip(), "mission must be non-empty"
    assert spec.constraints, "every prompt must declare hard constraints"
    assert spec.output_contract is not None, "every prompt must declare an output contract"


@pytest.mark.parametrize("name, spec, builder", PROMPTS, ids=PROMPT_IDS)
def test_system_prompt_has_required_sections(name: str, spec: PromptSpec, builder: Callable) -> None:
    system = spec.system()
    assert "MISSION" in system, f"{name}: system prompt missing MISSION"
    assert "HARD CONSTRAINTS" in system, f"{name}: system prompt missing HARD CONSTRAINTS"
    assert "OUTPUT CONTRACT" in system, f"{name}: system prompt missing OUTPUT CONTRACT"
    assert "REFUSAL" in system, f"{name}: system prompt missing REFUSAL"


@pytest.mark.parametrize("name, spec, builder", PROMPTS, ids=PROMPT_IDS)
def test_json_contract_is_self_consistent(name: str, spec: PromptSpec, builder: Callable) -> None:
    contract = spec.output_contract
    assert contract is not None
    if contract.shape in (OutputShape.JSON_ARRAY, OutputShape.JSON_OBJECT):
        assert contract.schema is not None, f"{name}: JSON contracts must declare a schema"
        serialized = json.dumps(contract.schema)
        assert "type" in serialized, f"{name}: schema missing 'type'"


@pytest.mark.parametrize("name, spec, builder", PROMPTS, ids=PROMPT_IDS)
def test_builder_renders_deterministically(name: str, spec: PromptSpec, builder: Callable) -> None:
    kwargs = _sample_for(name)
    system_a, user_a = builder(**kwargs)
    system_b, user_b = builder(**kwargs)
    assert system_a == system_b, f"{name}: system prompt is not deterministic"
    assert user_a == user_b, f"{name}: user prompt is not deterministic"
    assert system_a.strip(), f"{name}: system prompt is empty"
    assert user_a.strip(), f"{name}: user prompt is empty"


@pytest.mark.parametrize("name, spec, builder", PROMPTS, ids=PROMPT_IDS)
def test_user_prompt_reminds_of_contract(name: str, spec: PromptSpec, builder: Callable) -> None:
    kwargs = _sample_for(name)
    _, user = builder(**kwargs)
    contract = spec.output_contract
    assert contract is not None
    if contract.shape == OutputShape.JSON_ARRAY:
        assert "JSON array" in user, f"{name}: user prompt must remind of JSON array contract"
    elif contract.shape == OutputShape.JSON_OBJECT:
        assert "JSON object" in user, f"{name}: user prompt must remind of JSON object contract"


def test_all_16_surfaces_registered() -> None:
    """Guard against silent prompt drops — we intentionally check a count."""
    assert len(PROMPTS) == 16, (
        f"Expected 16 prompt surfaces (7 analysis + 2 refinement + 3 idea + 3 reverse + 1 impact), got {len(PROMPTS)}"
    )
