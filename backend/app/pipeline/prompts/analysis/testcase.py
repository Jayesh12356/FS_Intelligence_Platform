"""Test-case generation prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    FewShotExample,
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "analysis.testcase"

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a senior QA engineer writing test cases from acceptance "
        "criteria. Every test you produce must be executable — a tester or "
        "automated framework can follow the steps and verify the result "
        "without ambiguity."
    ),
    mission=(
        "Generate 1-3 test cases per task: always one happy-path, at least "
        "one failure or edge-case, and a boundary test when applicable."
    ),
    constraints=[
        "`title` starts with 'Verify' or 'Test' and names exactly what is tested.",
        "`preconditions` describes specific system state (e.g. 'User testuser@example.com exists with role ADMIN'). Never 'system is running'.",
        "`steps` — numbered atomic actions, one action per step, with concrete test data (URLs, payloads, field values).",
        "`expected_result` — observable, measurable outcome: status codes, exact values, timing constraints.",
        "`test_type` ∈ {UNIT, INTEGRATION, E2E, ACCEPTANCE}.",
        "UNIT = single function with mocked dependencies; INTEGRATION = two+ components; E2E = full user flow; ACCEPTANCE = business requirement from user's perspective.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_ARRAY,
        schema={
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "preconditions",
                    "steps",
                    "expected_result",
                    "test_type",
                ],
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "preconditions": {"type": "string", "minLength": 1},
                    "steps": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "expected_result": {"type": "string", "minLength": 1},
                    "test_type": {
                        "type": "string",
                        "enum": ["UNIT", "INTEGRATION", "E2E", "ACCEPTANCE"],
                    },
                },
            },
        },
        empty_value="[]",
    ),
    few_shot=[
        FewShotExample(
            label="Registration happy-path + duplicate",
            input_snippet=(
                "Task: Implement POST /api/users/register\n"
                "Criteria: Returns 201 with user_id; Returns 409 on duplicate email"
            ),
            expected_output=(
                '[{"title": "Verify successful user registration returns '
                '201", "preconditions": "users table is empty; API server is '
                'running at http://localhost:8000", "steps": ["POST '
                "/api/users/register with body "
                '{email: new@test.com, password: p@ss1234, name: New User}", '
                '"Parse the JSON response", "Verify HTTP status is 201 and '
                'the body contains a UUID user_id"], "expected_result": '
                '"HTTP 201; body matches {user_id: <UUID v4>}; row exists in '
                'users with bcrypt-hashed password", "test_type": '
                '"INTEGRATION"}, {"title": "Verify duplicate email returns '
                '409", "preconditions": "users table contains '
                'existing@test.com", "steps": ["POST /api/users/register '
                "with body {email: existing@test.com, password: p@ss, name: "
                'Dup}"], "expected_result": "HTTP 409; body contains '
                '{error: DUPLICATE_EMAIL}", "test_type": "INTEGRATION"}]'
            ),
        ),
    ],
    refusal=(
        "If the task has no acceptance criteria, produce one happy-path "
        "INTEGRATION test derived from the title; never return `[]`."
    ),
    use_xml_scaffold=True,
    thinking_protocol=(
        "Plan the 1-3 test cases in three silent passes.\n"
        "Pass 1 — Identify the happy-path observable outcome and the "
        "smallest preconditions that make it observable.\n"
        "Pass 2 — Identify at least one failure or boundary scenario "
        "from the acceptance criteria (rejected input, duplicate, "
        "limit, timeout, auth failure) and choose the variant most "
        "likely to ship as a bug.\n"
        "Pass 3 — Choose `test_type` per scenario: UNIT for single-"
        "function logic with mocks, INTEGRATION for two+ components, "
        "E2E for full user flows, ACCEPTANCE for business outcomes. "
        "Then emit JSON."
    ),
    self_check=(
        "Before returning, verify each test case:\n"
        "1. `title` starts with 'Verify' or 'Test' and names exactly "
        "what is being checked.\n"
        "2. `preconditions` describes specific seed data and the "
        "running surface — never 'system is running'.\n"
        "3. `steps` are atomic (one action per step) and contain "
        "concrete payloads, URLs, or field values a tester can paste.\n"
        "4. `expected_result` is observable: status codes, exact "
        "values, timing constraints, persisted side effects.\n"
        "5. The case set covers happy-path AND failure/edge in at "
        "least one of the 1-3 emitted cases."
    ),
)

USER_TEMPLATE = (
    "Write executable test cases for this task. Cover the happy path and at "
    "least one failure or edge case.\n\nTask: {title}\nDescription: "
    "{description}\n\nAcceptance Criteria:\n{criteria_text}"
)


def build(
    title: str,
    description: str,
    criteria_text: str,
) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(USER_TEMPLATE.format(title=title, description=description, criteria_text=criteria_text))
    return system, user


__all__ = ["NAME", "SPEC", "build"]
