"""Traceability matrix node — maps tasks back to source FS sections.

Builds a TraceabilityMatrix linking each FSTask to its originating
FS section. Stored as state.traceability_matrix.
"""

import logging
from typing import List

from app.pipeline.state import FSAnalysisState, TraceabilityEntry

logger = logging.getLogger(__name__)


# ── LangGraph Node Function ─────────────────────────────


async def traceability_node(state: FSAnalysisState) -> FSAnalysisState:
    """LangGraph node: build traceability matrix from tasks to sections.

    Reads state.tasks and state.parsed_sections, builds a mapping
    from each task back to its source section.
    """
    tasks = state.get("tasks", [])
    sections = state.get("parsed_sections", [])
    errors: List[str] = list(state.get("errors", []))

    logger.info(
        "Traceability node: mapping %d tasks to %d sections for fs_id=%s",
        len(tasks), len(sections), state.get("fs_id", "?"),
    )

    # Build section index lookup
    section_map = {}
    for s in sections:
        section_map[s.get("section_index", -1)] = s.get("heading", "Untitled")

    # Build traceability entries
    matrix: List[dict] = []
    for task in tasks:
        section_idx = task.get("section_index", 0)
        section_heading = task.get("section_heading", section_map.get(section_idx, "Unknown"))

        entry = TraceabilityEntry(
            task_id=task.get("task_id", ""),
            task_title=task.get("title", ""),
            section_index=section_idx,
            section_heading=section_heading,
        )
        matrix.append(entry.model_dump())

    logger.info(
        "Traceability node complete: %d entries in matrix",
        len(matrix),
    )

    return {
        **state,
        "traceability_matrix": matrix,
        "errors": errors,
    }
