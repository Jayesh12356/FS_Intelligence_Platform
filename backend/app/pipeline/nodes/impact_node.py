"""Impact analysis node — determines which tasks are affected by FS changes (L7).

For each FSChange, sends the change context and current task list to the LLM
to determine which tasks are INVALIDATED, REQUIRE_REVIEW, or UNAFFECTED.

Uses the unified LLM client (no direct SDK imports).
"""

import logging
from typing import List

from app.orchestration.pipeline_llm import pipeline_call_llm_json
from app.pipeline.prompts.impact import change_impact as change_impact_prompt
from app.pipeline.prompts.shared.flags import legacy_prompts_enabled
from app.pipeline.state import FSImpactState, ImpactType, TaskImpact

logger = logging.getLogger(__name__)

# ── Prompt Templates ────────────────────────────────────

IMPACT_SYSTEM_PROMPT = """You are a change-impact analyst for a software project. When a requirement changes, you determine exactly which existing development tasks are affected and how severely — so the team rebuilds only what is necessary and nothing more.

TASK: For EVERY task in the input, classify the impact of the given FS change. You must assess ALL tasks, not just the obviously affected ones.

IMPACT CLASSIFICATIONS:

INVALIDATED — The task's implementation MUST be redone. Use when:
  - The task was directly derived from the changed text
  - The change alters the task's core input/output contract, data model, or business logic
  - The existing implementation would produce INCORRECT behavior after the change
  - Examples: API endpoint signature changed, data model fields added/removed, business rule reversed

REQUIRES_REVIEW — The task MAY need modification. Use when:
  - The task depends on or references the changed section indirectly
  - The task consumes data produced by an INVALIDATED task
  - The change affects a cross-cutting concern (auth, logging, error format) that this task uses
  - The task's acceptance criteria may no longer be valid
  - When in doubt between UNAFFECTED and REQUIRES_REVIEW, choose REQUIRES_REVIEW

UNAFFECTED — The task is completely independent of the change. Use when:
  - The task operates on different data, different features, different system layers
  - No transitive dependency connects this task to the changed requirement
  - The task would compile, run, and pass all tests identically before and after the change

CASCADE DETECTION:
- Database schema changes cascade to ALL tasks that read/write the affected table
- Authentication/authorization changes cascade to ALL protected endpoints
- API response format changes cascade to ALL frontend tasks consuming that API
- Shared utility/library changes cascade to ALL tasks importing that module

OUTPUT:
- Include EVERY task from the input — omitting a task is an error
- "reason" must be SPECIFIC: cite what part of the change affects this task and how

Return a JSON array with one entry per task.

Example:
[
  {
    "task_id": "abc-123",
    "task_title": "Implement user login API",
    "impact_type": "INVALIDATED",
    "reason": "The change replaces JWT authentication with OAuth2 SSO. This task implements JWT issuance and validation, which must be completely rewritten for OAuth2 flow."
  },
  {
    "task_id": "def-456",
    "task_title": "Create user dashboard",
    "impact_type": "REQUIRES_REVIEW",
    "reason": "Dashboard reads the user session token set by the login API. The token format changes from JWT to OAuth2 access token, so session-reading logic needs verification."
  },
  {
    "task_id": "ghi-789",
    "task_title": "Configure CI/CD pipeline",
    "impact_type": "UNAFFECTED",
    "reason": "Infrastructure automation task with no dependency on authentication logic or user data models."
  }
]

Return ONLY a valid JSON array. No markdown fences, no prose outside the array."""

IMPACT_USER_PROMPT = """Classify the impact of this FS change on EVERY task listed below. Consider both direct effects and cascading dependencies.

CHANGE:
Type: {change_type}
Section: "{section_heading}"

Previous text:
{old_text}

New text:
{new_text}

TASKS TO ASSESS:
{task_list}

Return a JSON array with an entry for EVERY task. Do not omit any task."""


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

    if legacy_prompts_enabled():
        system_prompt = IMPACT_SYSTEM_PROMPT
        user_prompt = IMPACT_USER_PROMPT.format(
            change_type=change.get("change_type", "MODIFIED"),
            section_heading=change.get("section_heading", "Unknown"),
            old_text=old_text,
            new_text=new_text,
            task_list=task_list_str,
        )
    else:
        system_prompt, user_prompt = change_impact_prompt.build(
            change_type=change.get("change_type", "MODIFIED"),
            section_heading=change.get("section_heading", "Unknown"),
            old_text=old_text,
            new_text=new_text,
            task_list=task_list_str,
        )

    try:
        result = await pipeline_call_llm_json(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.0,
            max_tokens=4096,
            role="build",
        )

        if not isinstance(result, list):
            logger.warning("LLM returned non-list for impact analysis: %s", type(result))
            return []

        impacts: List[TaskImpact] = []
        for item in result:
            try:
                impact_str = item.get("impact_type", "UNAFFECTED").upper()
                impact_type = ImpactType(impact_str) if impact_str in ImpactType.__members__ else ImpactType.UNAFFECTED

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
        logger.error("Impact analysis failed for change in %s: %s", change.get("section_heading", "?"), exc)
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
        len(fs_changes),
        len(tasks),
        state.get("fs_id", "?"),
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
        invalidated,
        review,
        unaffected,
    )

    return {
        **state,
        "task_impacts": impact_list,
        "errors": errors,
    }
