"""Task decomposition node — transforms FS sections into atomic dev tasks.

For each section (skipping those with unresolved HIGH-severity ambiguities),
asks the LLM to decompose requirements into actionable developer tasks with
acceptance criteria, effort estimation, and relevant tags.
"""

import logging
import uuid
from typing import List

from app.orchestration.pipeline_llm import pipeline_call_llm_json
from app.pipeline.prompts.analysis import task as task_prompt
from app.pipeline.prompts.shared.flags import legacy_prompts_enabled
from app.pipeline.state import EffortLevel, FSAnalysisState, FSTask

logger = logging.getLogger(__name__)

# ── Prompt Templates ────────────────────────────────────

TASK_DECOMPOSITION_SYSTEM_PROMPT = """You are a staff software architect decomposing Functional Specification requirements into a developer-ready task backlog. Each task you produce will be assigned to an autonomous coding agent that implements it without human guidance — so precision is paramount.

TASK: Convert every implementable requirement in the section into atomic, independently-deliverable development tasks. Each task must be specific enough that an AI coding agent can implement it correctly on the first attempt.

MANDATORY RULES:
- If the section contains ANY actionable requirement (shall/must/should/will/needs to/requires), produce at least 1 task.
- Return [] ONLY when the section is pure boilerplate (table of contents, revision history, glossary definitions with no behavior).
- Every task title MUST start with a verb: Create, Implement, Build, Add, Configure, Design, Write.
- Each task maps to exactly ONE deliverable artifact or capability (one API endpoint, one DB model, one UI component, one integration).

TASK STRUCTURE:
1. "title" — Verb-first, specific, max 12 words. Bad: "User stuff". Good: "Implement POST /api/users/register endpoint".
2. "description" — COMPLETE implementation specification: what to build, input/output data shapes, business logic rules, error handling. NO phrases like "as described in the FS" — embed the actual requirement.
3. "acceptance_criteria" — 2-5 VERIFIABLE statements each testable with a concrete assertion. Bad: "Works correctly". Good: "Returns HTTP 409 with DUPLICATE_EMAIL error when email exists".
4. "effort" — LOW (single function, simple CRUD, < 2h), MEDIUM (full endpoint with validation, UI page with state, 2-8h), HIGH (complex multi-component feature, > 8h), UNKNOWN (requirement too vague to estimate).
5. "tags" — From: frontend, backend, db, auth, api, testing, security, devops, integration, ui, performance.

DECOMPOSITION GUIDELINES:
- Break features along LAYER boundaries: DB model -> API endpoint -> Frontend component
- 2-5 tasks per feature is the sweet spot
- Data model tasks before API tasks. Backend before frontend for same feature.
- DO NOT create generic "Write tests for X" tasks — testing criteria belong in acceptance_criteria
- DO NOT create "design" or "plan" tasks — every task must produce working code

Return ONLY a valid JSON array. No markdown fences, no prose outside the array.

Example output:
```json
[
  {
    "title": "Create user registration API endpoint",
    "description": "Build POST /api/users/register endpoint that accepts email, password, name. Hash password with bcrypt, validate email format, check for duplicates, store in users table.",
    "acceptance_criteria": [
      "Endpoint returns 201 with user ID on successful registration",
      "Returns 409 if email already exists",
      "Password is hashed before storage",
      "Email format is validated"
    ],
    "effort": "MEDIUM",
    "tags": ["backend", "api", "auth", "db"]
  }
]
```

IMPORTANT: Return ONLY a valid JSON array. No markdown, no explanations outside the JSON."""

TASK_DECOMPOSITION_USER_PROMPT = """Decompose every implementable requirement in this section into atomic dev tasks. Each task must be independently implementable and produce working code.

Section {index}: "{heading}"

{content}

Return a JSON array of tasks. If the section contains no implementable requirements, return []."""


# ── Detection Function ──────────────────────────────────


async def decompose_section_into_tasks(
    heading: str,
    content: str,
    section_index: int,
) -> List[FSTask]:
    """Decompose one FS section into dev tasks using the LLM.

    Args:
        heading: Section heading text.
        content: Section body text.
        section_index: Index of the section in the document.

    Returns:
        List of FSTask objects derived from this section.
    """
    if not content or len(content.strip()) < 20:
        logger.debug("Skipping section %d (%s): too short for task decomposition", section_index, heading)
        return []

    if legacy_prompts_enabled():
        system = TASK_DECOMPOSITION_SYSTEM_PROMPT
        prompt = TASK_DECOMPOSITION_USER_PROMPT.format(
            heading=heading,
            content=content,
            index=section_index + 1,
        )
    else:
        system, prompt = task_prompt.build(heading=heading, content=content, index=section_index + 1)

    try:
        result = await pipeline_call_llm_json(
            prompt=prompt,
            system=system,
            temperature=0.0,
            max_tokens=4096,
            role="build",
        )

        if not isinstance(result, list):
            logger.warning("LLM returned non-list for tasks in section %d: %s", section_index, type(result))
            return []

        tasks: List[FSTask] = []
        for item in result:
            try:
                effort_str = item.get("effort", "MEDIUM").upper()
                effort = EffortLevel(effort_str) if effort_str in EffortLevel.__members__ else EffortLevel.MEDIUM

                task = FSTask(
                    task_id=str(uuid.uuid4()),
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    section_index=section_index,
                    section_heading=heading,
                    depends_on=[],  # Populated by dependency_node
                    acceptance_criteria=item.get("acceptance_criteria", []),
                    effort=effort,
                    tags=item.get("tags", []),
                    order=0,  # Populated by dependency_node
                    can_parallel=False,  # Populated by dependency_node
                )
                tasks.append(task)
            except Exception as exc:
                logger.warning("Failed to parse task: %s — %s", item, exc)

        logger.info("Section %d (%s): generated %d tasks", section_index, heading, len(tasks))
        return tasks

    except Exception as exc:
        logger.error("Task decomposition failed for section %d: %s", section_index, exc)
        return []


# ── LangGraph Node Function ─────────────────────────────


async def task_decomposition_node(state: FSAnalysisState) -> FSAnalysisState:
    """LangGraph node: decompose FS sections into dev tasks.

    Reads state.parsed_sections and state.ambiguities,
    skips sections with unresolved HIGH ambiguities,
    and populates state.tasks.
    """
    sections = state.get("parsed_sections", [])
    ambiguities = state.get("ambiguities", [])
    all_tasks: List[dict] = []
    errors: List[str] = list(state.get("errors", []))

    # Identify sections with unresolved HIGH ambiguities
    high_ambiguity_sections = set()
    for amb in ambiguities:
        if amb.get("severity") == "HIGH" and not amb.get("resolved", False):
            high_ambiguity_sections.add(amb.get("section_index", -1))

    logger.info(
        "Task decomposition node: %d sections, %d with HIGH ambiguities, for fs_id=%s",
        len(sections),
        len(high_ambiguity_sections),
        state.get("fs_id", "?"),
    )

    for section in sections:
        heading = section.get("heading", "Untitled")
        content = section.get("content", "")
        section_index = section.get("section_index", 0)

        # Previously we skipped sections with unresolved HIGH ambiguities.
        # In real-world specs, the ambiguity detector can mark many sections as HIGH,
        # which makes task generation effectively unusable. We still generate tasks,
        # but keep the ambiguity signals for the UI to surface.
        if section_index in high_ambiguity_sections:
            logger.warning(
                "Section %d (%s) has unresolved HIGH ambiguities — generating tasks anyway",
                section_index,
                heading,
            )

        try:
            tasks = await decompose_section_into_tasks(heading, content, section_index)
            for task in tasks:
                all_tasks.append(task.model_dump())
        except Exception as exc:
            error_msg = f"Task decomposition failed for section {section_index}: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)

    logger.info(
        "Task decomposition complete: %d tasks from %d sections",
        len(all_tasks),
        len(sections),
    )

    return {
        **state,
        "tasks": all_tasks,
        "errors": errors,
    }
