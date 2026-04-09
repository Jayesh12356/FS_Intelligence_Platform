"""Impact analysis node — determines which tasks are affected by FS changes (L7).

For each FSChange, sends the change context and current task list to the LLM
to determine which tasks are INVALIDATED, REQUIRE_REVIEW, or UNAFFECTED.

Uses the unified LLM client (no direct SDK imports).
"""

import logging
from typing import List

from app.llm import get_llm_client
from app.pipeline.state import FSImpactState, ImpactType, TaskImpact

logger = logging.getLogger(__name__)

# ── Prompt Templates ────────────────────────────────────

IMPACT_SYSTEM_PROMPT = """You are an expert software systems analyst determining the impact of requirement changes on development tasks.

Given a change in a Functional Specification (FS) document and a list of existing development tasks, you must determine which tasks are affected.

For each task, classify the impact as:
- **INVALIDATED**: The task is directly based on the changed requirement and MUST be redone. The change fundamentally alters what this task requires.
- **REQUIRES_REVIEW**: The task is related to the changed requirement and SHOULD be reviewed. The change may affect this task indirectly.
- **UNAFFECTED**: The task is not impacted by this change.

Guidelines:
- A task derived from a changed section is likely INVALIDATED
- A task that depends on or references a changed section is likely REQUIRES_REVIEW
- Tasks from completely unrelated sections are UNAFFECTED
- When in doubt, classify as REQUIRES_REVIEW (err on the side of caution)
- Consider cross-cutting concerns (auth changes affect many tasks, DB schema changes cascade)

Return a JSON array of impact assessments. Include ALL tasks from the input (not just affected ones).

Example output:
```json
[
  {
    "task_id": "abc-123",
    "task_title": "Implement user login API",
    "impact_type": "INVALIDATED",
    "reason": "The authentication method changed from JWT to OAuth2, requiring a complete rewrite."
  },
  {
    "task_id": "def-456",
    "task_title": "Create user dashboard",
    "impact_type": "REQUIRES_REVIEW",
    "reason": "Dashboard references user data that may be affected by the auth change."
  },
  {
    "task_id": "ghi-789",
    "task_title": "Setup CI/CD pipeline",
    "impact_type": "UNAFFECTED",
    "reason": "Infrastructure task not related to authentication changes."
  }
]
```

IMPORTANT: Return ONLY a valid JSON array. No markdown, no explanations outside the JSON."""

IMPACT_USER_PROMPT = """Analyze the impact of the following FS change on the listed development tasks:

## Change Details
**Type**: {change_type}
**Section**: {section_heading}

### Previous Text:
{old_text}

### New Text:
{new_text}

---

## Current Tasks:
{task_list}

---

For EACH task above, determine: INVALIDATED, REQUIRES_REVIEW, or UNAFFECTED. Return a JSON array with ALL tasks."""


# ── Impact Analysis Function ───────────────────────────


async def analyze_change_impact(
    change: dict,
    tasks: List[dict],
) -> List[TaskImpact]:
    """Analyze the impact of a single FS change on the task list.

    Args:
        change: FSChange dict with change_type, section_heading, old_text, new_text.
        tasks: List of task dicts from the analysis pipeline.

    Returns:
        List of TaskImpact objects for affected tasks.
    """
    if not tasks:
        logger.debug("No tasks to analyze impact against")
        return []

    client = get_llm_client()

    # Build task list string for prompt
    task_lines = []
    for t in tasks:
        task_lines.append(
            f"- **{t.get('task_id', '?')}** | {t.get('title', 'Untitled')} "
            f"(Section: {t.get('section_heading', '?')}, Effort: {t.get('effort', '?')})"
        )
    task_list_str = "\n".join(task_lines)

    old_text = change.get("old_text") or "(section did not exist)"
    new_text = change.get("new_text") or "(section was deleted)"

    prompt = IMPACT_USER_PROMPT.format(
        change_type=change.get("change_type", "MODIFIED"),
        section_heading=change.get("section_heading", "Unknown"),
        old_text=old_text,
        new_text=new_text,
        task_list=task_list_str,
    )

    try:
        result = await client.call_llm_json(
            prompt=prompt,
            system=IMPACT_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=4096,
        )

        if not isinstance(result, list):
            logger.warning("LLM returned non-list for impact analysis: %s", type(result))
            return []

        impacts: List[TaskImpact] = []
        for item in result:
            try:
                impact_str = item.get("impact_type", "UNAFFECTED").upper()
                impact_type = (
                    ImpactType(impact_str)
                    if impact_str in ImpactType.__members__
                    else ImpactType.UNAFFECTED
                )

                impact = TaskImpact(
                    task_id=item.get("task_id", ""),
                    task_title=item.get("task_title", ""),
                    impact_type=impact_type,
                    reason=item.get("reason", ""),
                    change_section=change.get("section_heading", ""),
                )
                impacts.append(impact)
            except Exception as exc:
                logger.warning("Failed to parse task impact: %s — %s", item, exc)

        return impacts

    except Exception as exc:
        logger.error("Impact analysis failed for change in %s: %s",
                      change.get("section_heading", "?"), exc)
        raise


# ── LangGraph Node Function ─────────────────────────────


async def impact_node(state: FSImpactState) -> FSImpactState:
    """LangGraph node: determine impact of FS changes on tasks.

    Reads state.fs_changes and state.tasks,
    runs LLM-powered impact analysis for each change,
    and populates state.task_impacts.
    """
    fs_changes = state.get("fs_changes", [])
    tasks = state.get("tasks", [])
    errors: List[str] = list(state.get("errors", []))

    logger.info(
        "Impact node: analyzing %d changes against %d tasks for fs_id=%s",
        len(fs_changes), len(tasks), state.get("fs_id", "?"),
    )

    if not fs_changes:
        logger.info("Impact node: no changes to analyze")
        return {
            **state,
            "task_impacts": [],
            "errors": errors,
        }

    if not tasks:
        logger.info("Impact node: no tasks to impact-check")
        return {
            **state,
            "task_impacts": [],
            "errors": errors,
        }

    # Aggregate impacts across all changes
    all_impacts: dict[str, dict] = {}  # task_id -> worst impact

    for change in fs_changes:
        try:
            impacts = await analyze_change_impact(change, tasks)
            for impact in impacts:
                existing = all_impacts.get(impact.task_id)
                if existing is None:
                    all_impacts[impact.task_id] = impact.model_dump()
                else:
                    # Keep the worst impact (INVALIDATED > REQUIRES_REVIEW > UNAFFECTED)
                    priority = {"INVALIDATED": 3, "REQUIRES_REVIEW": 2, "UNAFFECTED": 1}
                    existing_priority = priority.get(existing.get("impact_type", "UNAFFECTED"), 0)
                    new_priority = priority.get(impact.impact_type.value, 0)
                    if new_priority > existing_priority:
                        all_impacts[impact.task_id] = impact.model_dump()
        except Exception as exc:
            error_msg = f"Impact analysis failed for change in {change.get('section_heading', '?')}: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)

    impact_list = list(all_impacts.values())

    invalidated = sum(1 for i in impact_list if i.get("impact_type") == "INVALIDATED")
    review = sum(1 for i in impact_list if i.get("impact_type") == "REQUIRES_REVIEW")
    unaffected = sum(1 for i in impact_list if i.get("impact_type") == "UNAFFECTED")

    logger.info(
        "Impact node complete: %d invalidated, %d require review, %d unaffected",
        invalidated, review, unaffected,
    )

    return {
        **state,
        "task_impacts": impact_list,
        "errors": errors,
    }
