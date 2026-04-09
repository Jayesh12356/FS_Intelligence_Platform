"""Rework cost estimator node — computes rework effort from task impacts (L7).

For invalidated and review-requiring tasks:
  effort_map: LOW=0.5d, MEDIUM=2d, HIGH=5d, UNKNOWN=2d
  total_rework_days = sum(effort for invalidated tasks)
  + 0.25 * sum(effort for review tasks)

Returns a ReworkEstimate with totals, affected sections, and summary.
"""

import logging
from typing import List

from app.pipeline.state import FSImpactState, ReworkEstimate

logger = logging.getLogger(__name__)

# ── Effort Map (days per effort level) ──────────────────

EFFORT_MAP: dict[str, float] = {
    "LOW": 0.5,
    "MEDIUM": 2.0,
    "HIGH": 5.0,
    "UNKNOWN": 2.0,
}

# Review tasks only need a fraction of effort for review
REVIEW_EFFORT_MULTIPLIER = 0.25


def compute_rework_estimate(
    task_impacts: List[dict],
    tasks: List[dict],
) -> ReworkEstimate:
    """Compute rework cost from task impacts.

    Args:
        task_impacts: List of TaskImpact dicts with impact_type.
        tasks: Original task list to look up effort levels.

    Returns:
        ReworkEstimate with totals and summary.
    """
    # Build task effort lookup
    task_effort: dict[str, str] = {}
    task_titles: dict[str, str] = {}
    for t in tasks:
        tid = t.get("task_id", "")
        task_effort[tid] = t.get("effort", "MEDIUM")
        task_titles[tid] = t.get("title", "")

    invalidated_count = 0
    review_count = 0
    unaffected_count = 0
    total_rework_days = 0.0
    affected_sections: set[str] = set()
    invalidated_tasks: List[str] = []
    review_tasks: List[str] = []

    for impact in task_impacts:
        impact_type = impact.get("impact_type", "UNAFFECTED")
        task_id = impact.get("task_id", "")
        effort_str = task_effort.get(task_id, "MEDIUM")
        effort_days = EFFORT_MAP.get(effort_str, 2.0)
        change_section = impact.get("change_section", "")

        if impact_type == "INVALIDATED":
            invalidated_count += 1
            total_rework_days += effort_days
            invalidated_tasks.append(
                task_titles.get(task_id, task_id)
            )
            if change_section:
                affected_sections.add(change_section)

        elif impact_type == "REQUIRES_REVIEW":
            review_count += 1
            total_rework_days += effort_days * REVIEW_EFFORT_MULTIPLIER
            review_tasks.append(
                task_titles.get(task_id, task_id)
            )
            if change_section:
                affected_sections.add(change_section)

        else:
            unaffected_count += 1

    # Round to 1 decimal place
    total_rework_days = round(total_rework_days, 1)

    # Generate summary
    summary_lines = []
    if invalidated_count > 0:
        summary_lines.append(
            f"{invalidated_count} task(s) invalidated requiring full rework"
        )
    if review_count > 0:
        summary_lines.append(
            f"{review_count} task(s) require review and possible adjustment"
        )
    if unaffected_count > 0:
        summary_lines.append(
            f"{unaffected_count} task(s) remain unaffected"
        )
    summary_lines.append(
        f"Estimated total rework: {total_rework_days} days"
    )

    changes_summary = ". ".join(summary_lines) + "."

    return ReworkEstimate(
        invalidated_count=invalidated_count,
        review_count=review_count,
        unaffected_count=unaffected_count,
        total_rework_days=total_rework_days,
        affected_sections=sorted(affected_sections),
        changes_summary=changes_summary,
    )


# ── LangGraph Node Function ─────────────────────────────


async def rework_node(state: FSImpactState) -> FSImpactState:
    """LangGraph node: compute rework cost estimate.

    Reads state.task_impacts and state.tasks,
    computes effort totals, and populates state.rework_estimate.
    """
    task_impacts = state.get("task_impacts", [])
    tasks = state.get("tasks", [])
    errors: List[str] = list(state.get("errors", []))

    logger.info(
        "Rework node: computing estimate from %d impacts for fs_id=%s",
        len(task_impacts), state.get("fs_id", "?"),
    )

    try:
        estimate = compute_rework_estimate(task_impacts, tasks)
        estimate_dict = estimate.model_dump()

        logger.info(
            "Rework node complete: %d invalidated, %d review, %.1f total rework days",
            estimate.invalidated_count,
            estimate.review_count,
            estimate.total_rework_days,
        )
    except Exception as exc:
        error_msg = f"Rework estimation failed: {exc}"
        logger.error(error_msg)
        errors.append(error_msg)
        estimate_dict = ReworkEstimate().model_dump()

    return {
        **state,
        "rework_estimate": estimate_dict,
        "errors": errors,
    }
