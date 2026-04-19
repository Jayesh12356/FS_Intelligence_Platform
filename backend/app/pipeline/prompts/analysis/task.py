"""Task decomposition prompt (v2)."""

from __future__ import annotations

from app.pipeline.prompts.master_template import (
    FewShotExample,
    OutputContract,
    OutputShape,
    PromptSpec,
)

NAME = "analysis.task"

TASK_TAGS = (
    "frontend",
    "backend",
    "db",
    "auth",
    "api",
    "testing",
    "security",
    "devops",
    "integration",
    "ui",
    "performance",
)

SPEC = PromptSpec(
    name=NAME,
    role=(
        "You are a staff software architect decomposing FS requirements into "
        "a developer-ready task backlog. Each task you emit will be assigned "
        "to an autonomous coding agent with no human in the loop, so "
        "precision is paramount."
    ),
    mission=(
        "Convert every implementable requirement into atomic, independently "
        "deliverable development tasks that an AI coding agent can ship on "
        "the first attempt."
    ),
    constraints=[
        "If the section contains any shall/must/should/will/needs-to language, emit at least one task.",
        "Return `[]` only for pure boilerplate (TOC, revision history, glossary without behaviour).",
        "`title` — verb-first (Create/Implement/Build/Add/Configure/Design/Write), max 12 words, specific.",
        "`description` — complete spec: inputs, outputs, business logic, error handling. Never 'as described in the FS'.",
        "`acceptance_criteria` — 2-5 testable assertions; each names a concrete check (status code, exact field value, timing).",
        "`effort` ∈ {LOW, MEDIUM, HIGH, UNKNOWN}. LOW = <2h, MEDIUM = 2-8h, HIGH = >8h, UNKNOWN = requirement too vague to estimate.",
        f"`tags` — non-empty subset of: {', '.join(TASK_TAGS)}.",
        "Decompose along layer boundaries: DB model → API → Frontend. Backend before frontend for the same feature. 2-5 tasks per feature.",
        "Do NOT emit generic 'Write tests for X' or 'Design Y' tasks; every task must produce shipping code.",
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_ARRAY,
        schema={
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "description",
                    "acceptance_criteria",
                    "effort",
                    "tags",
                ],
                "properties": {
                    "title": {"type": "string", "minLength": 1, "maxLength": 120},
                    "description": {"type": "string", "minLength": 20},
                    "acceptance_criteria": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 5},
                    },
                    "effort": {
                        "type": "string",
                        "enum": ["LOW", "MEDIUM", "HIGH", "UNKNOWN"],
                    },
                    "tags": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "enum": list(TASK_TAGS)},
                    },
                },
            },
        },
        empty_value="[]",
        notes="Empty array `[]` only when the section is pure boilerplate.",
    ),
    few_shot=[
        FewShotExample(
            label="Registration decomposed into two tasks",
            input_snippet=(
                '"Users shall register with email, password, and name. Email '
                "must be unique. Passwords must be hashed with bcrypt before "
                'storage."'
            ),
            expected_output=(
                '[{"title": "Create users table and User model", '
                '"description": "Add a users table with columns id (UUID PK), '
                "email (unique, citext), password_hash (text), name (text), "
                'created_at (timestamptz). Expose a User SQLAlchemy model.", '
                '"acceptance_criteria": ["Migration creates users table with '
                'a unique index on lower(email)", "User.email, '
                'User.password_hash, User.name columns are non-nullable", '
                '"Selecting by email is case-insensitive"], "effort": "LOW", '
                '"tags": ["backend", "db"]}, '
                '{"title": "Implement POST /api/users/register endpoint", '
                '"description": "Accept JSON {email, password, name}. '
                "Validate email format, bcrypt-hash password with cost 12, "
                "reject duplicates with HTTP 409 code DUPLICATE_EMAIL, insert "
                'into users table, return 201 with {user_id}.", '
                '"acceptance_criteria": ["Returns 201 with user_id on '
                'success", "Returns 409 with DUPLICATE_EMAIL when email '
                'exists", "Password is bcrypt-hashed before storage", '
                '"Invalid email format returns 400 INVALID_EMAIL"], '
                '"effort": "MEDIUM", "tags": ["backend", "api", "auth"]}]'
            ),
        ),
    ],
    refusal=("If the section is empty or under 20 characters of meaningful content, return `[]`."),
    use_xml_scaffold=True,
    thinking_protocol=(
        "Decompose in four silent passes.\n"
        "Pass 1 — Extract every implementable requirement (any "
        "shall/must/should/will/needs-to clause).\n"
        "Pass 2 — Group requirements by feature, then split each "
        "feature into layer slices: DB → API → Frontend → "
        "Integration → Tests-as-code-not-task.\n"
        "Pass 3 — For each slice, draft the title (verb-first, "
        "specific), the description (inputs, outputs, business "
        "logic, error handling), and 2-5 acceptance criteria with "
        "concrete numbers, status codes, or field values.\n"
        "Pass 4 — Validate effort and tags. Reject any task that "
        "could not be merged on the first PR by an autonomous "
        "coding agent. Refine until every task is shippable. Then "
        "serialise to JSON."
    ),
    self_check=(
        "Before returning, verify every task:\n"
        "1. Title is verb-first and ≤12 words.\n"
        "2. Description names inputs, outputs, business logic, AND "
        "error handling — never 'as described in the FS'.\n"
        "3. Acceptance criteria are testable assertions with "
        "concrete checks (status codes, exact field values, timing).\n"
        "4. Effort matches the rubric (LOW <2h, MEDIUM 2-8h, HIGH "
        ">8h, UNKNOWN only when truly ambiguous).\n"
        "5. Tags are a non-empty subset of the closed enum.\n"
        "6. Backend layer comes before frontend layer for the same "
        "feature; no generic 'write tests' or 'design X' tasks."
    ),
)

USER_TEMPLATE = (
    "Decompose every implementable requirement in this section into atomic "
    "dev tasks. Each task must be independently implementable and produce "
    'working code.\n\nSection {index}: "{heading}"\n\n{content}'
)


def build(heading: str, content: str, index: int) -> tuple[str, str]:
    system = SPEC.system()
    user = SPEC.user(USER_TEMPLATE.format(heading=heading, content=content, index=index))
    return system, user


__all__ = ["NAME", "SPEC", "TASK_TAGS", "build"]
