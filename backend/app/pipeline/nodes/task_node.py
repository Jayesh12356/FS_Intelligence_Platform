"""Task decomposition node — transforms FS sections into atomic dev tasks.

For each section (skipping those with unresolved HIGH-severity ambiguities),
asks the LLM to decompose requirements into actionable developer tasks with
acceptance criteria, effort estimation, and relevant tags.
"""

import logging
import uuid
from typing import List

from app.llm import get_llm_client
from app.pipeline.state import EffortLevel, FSAnalysisState, FSTask

logger = logging.getLogger(__name__)

# ── Prompt Templates ────────────────────────────────────

TASK_DECOMPOSITION_SYSTEM_PROMPT = """You are an expert software architect and project manager decomposing Functional Specification (FS) requirements into actionable developer tasks.

For each FS section, produce ATOMIC, implementable dev tasks. Each task should be:
- **Specific**: Clear enough for a developer to start immediately
- **Testable**: Has concrete acceptance criteria
- **Scoped**: Covers one piece of functionality (not too broad, not too granular)

Hard requirement:
- If the section contains any actionable product requirement (e.g. "shall", "must", "should", "will", "needs to", "requires"), you MUST return at least 1 task.
- Only return [] when the section is purely non-requirement content (e.g. headings, intro text with no behavior, or empty filler).

For each task, provide:
1. **title**: Short, actionable title (e.g., "Implement user login API endpoint")
2. **description**: Detailed description of what to implement, including technical approach
3. **acceptance_criteria**: List of verifiable acceptance criteria (at least 2)
4. **effort**: Effort complexity — LOW (< 2 hours), MEDIUM (2-8 hours), HIGH (> 8 hours), UNKNOWN (not enough info)
5. **tags**: List of relevant tags from: frontend, backend, db, auth, api, testing, security, devops, integration, ui, performance

Guidelines:
- Break large features into 2-5 smaller tasks
- Each task should be completable independently (when dependencies are resolved)
- Include data model tasks, API tasks, frontend tasks, and testing tasks as needed
- Don't create tasks for trivially obvious things (like "create a file")
- Focus on the substantive implementation work

Return your analysis as a JSON array of tasks. If the section has no implementable requirements, return [].

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

TASK_DECOMPOSITION_USER_PROMPT = """Decompose the following FS section into atomic developer tasks:

## Section {index}: {heading}

{content}

---
Return a JSON array of tasks. If no implementable tasks, return []."""


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

    client = get_llm_client()
    prompt = TASK_DECOMPOSITION_USER_PROMPT.format(
        heading=heading,
        content=content,
        index=section_index + 1,
    )

    try:
        result = await client.call_llm_json(
            prompt=prompt,
            system=TASK_DECOMPOSITION_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=4096,
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
        len(sections), len(high_ambiguity_sections), state.get("fs_id", "?"),
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
        len(all_tasks), len(sections),
    )

    return {
        **state,
        "tasks": all_tasks,
        "errors": errors,
    }
