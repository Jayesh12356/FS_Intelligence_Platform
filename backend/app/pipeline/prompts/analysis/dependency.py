"""Dependency inference prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    FewShotExample,
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "analysis.dependency"

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a build-order planner for a software project. Given a set "
        "of development tasks, you determine the minimum set of dependencies "
        "so tasks execute in the correct order — and ONLY the minimum set."
    ),
    mission=("For each task, list ONLY the task IDs it cannot start without. Emit no 'nice-to-have' orderings."),
    constraints=[
        "A dependency is valid only when it is a HARD blocker: B literally cannot execute without A's output.",
        "Valid dependency families: data (B reads a table A creates), API (B calls an endpoint A implements), build (B imports a module A produces), schema (B relies on a type/interface A defines).",
        "NO self-dependencies. NO cycles.",
        "Maximum useful chain depth: 5. Deeper chains almost always include unnecessary edges.",
        "Independent siblings (two unrelated API endpoints) must have empty arrays.",
        "Include EVERY task ID in the output — tasks with no dependencies get an empty array `[]`.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_OBJECT,
        schema={
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        empty_value="{}",
        notes=(
            "Keys are task IDs. Values are arrays of task IDs that must "
            "complete first. Missing keys are not allowed — every input task "
            "must appear."
        ),
    ),
    few_shot=[
        FewShotExample(
            label="DB → API → Frontend chain",
            input_snippet=(
                "- t1: Create users table and User model\n"
                "- t2: Implement POST /api/users/register endpoint\n"
                "- t3: Build registration form component"
            ),
            expected_output='{"t1": [], "t2": ["t1"], "t3": ["t2"]}',
        ),
        FewShotExample(
            label="Independent siblings",
            input_snippet=("- a1: Implement GET /api/projects endpoint\n- a2: Implement GET /api/documents endpoint"),
            expected_output='{"a1": [], "a2": []}',
        ),
    ],
    refusal=("If the task list is empty, return `{}`. Never invent task IDs that are not in the input list."),
    use_xml_scaffold=True,
    thinking_protocol=(
        "Plan dependencies in four silent passes.\n"
        "Pass 1 — Index every task and identify the artefact it produces "
        "(table, endpoint, module, schema, UI screen).\n"
        "Pass 2 — For each task B, ask: 'What must already exist at "
        "runtime for B to compile and execute?' List candidate "
        "predecessors only when the answer cites another task's "
        "concrete output (not 'general infra').\n"
        "Pass 3 — Reduce: if A→B and B→C are both true, drop A→C "
        "(transitive). Eliminate any cycles by identifying the weaker "
        "edge and dropping it.\n"
        "Pass 4 — Confirm every input task ID appears as a key, "
        "including standalone tasks with `[]`. Then emit JSON.\n"
        "Passes are private."
    ),
    self_check=(
        "Before returning, verify:\n"
        "1. The keyset equals the set of input task IDs exactly — no "
        "extras, no omissions.\n"
        "2. No self-loops; no cycles; no transitive shortcuts.\n"
        "3. Independent siblings (e.g. two unrelated read endpoints) "
        "carry empty arrays.\n"
        "4. Every dependency is justified by a HARD blocker (data, API, "
        "build, schema), not preference or scheduling convenience."
    ),
)

USER_TEMPLATE = (
    "Determine the MINIMUM dependency set for these tasks. Only add a "
    "dependency when task B literally cannot execute without task A's "
    "output.\n\nTasks:\n{task_list}"
)


def build(task_list: str) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(USER_TEMPLATE.format(task_list=task_list))
    return system, user


__all__ = ["NAME", "SPEC", "build"]
