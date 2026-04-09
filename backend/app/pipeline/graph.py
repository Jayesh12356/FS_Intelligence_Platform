"""LangGraph analysis pipeline — stateful multi-step FS document analysis.

Pipeline graph (L6 — Analysis):
  START → parse_node → ambiguity_node → debate_node → contradiction_node
        → edge_case_node → quality_node → task_decomposition_node
        → dependency_node → traceability_node → END

Pipeline graph (L7 — Impact):
  START → version_node → impact_node → rework_node → END

Pipeline graph (L8 — Reverse FS):
  START → reverse_fs_node → reverse_quality_node → END

Usage:
    from app.pipeline.graph import run_analysis_pipeline, run_impact_pipeline, run_reverse_pipeline
    result = await run_analysis_pipeline(fs_id, sections)
    impact = await run_impact_pipeline(fs_id, version_id, old_sections, new_sections, tasks)
    reverse = await run_reverse_pipeline(code_upload_id, snapshot)
"""

import logging
from typing import Any, Dict, List

from langgraph.graph import StateGraph, START, END

from app.pipeline.state import FSAnalysisState, FSImpactState, ReverseGenState
from app.pipeline.nodes.ambiguity_node import ambiguity_node
from app.pipeline.nodes.debate_node import debate_node
from app.pipeline.nodes.contradiction_node import contradiction_node
from app.pipeline.nodes.edge_case_node import edge_case_node
from app.pipeline.nodes.quality_node import quality_node
from app.pipeline.nodes.task_node import task_decomposition_node
from app.pipeline.nodes.dependency_node import dependency_node
from app.pipeline.nodes.traceability_node import traceability_node
from app.pipeline.nodes.duplicate_node import duplicate_node
from app.pipeline.nodes.testcase_node import testcase_node
from app.pipeline.nodes.version_node import version_node
from app.pipeline.nodes.impact_node import impact_node
from app.pipeline.nodes.rework_node import rework_node
from app.pipeline.nodes.reverse_fs_node import reverse_fs_node
from app.pipeline.nodes.reverse_quality_node import reverse_quality_node

logger = logging.getLogger(__name__)


# ── Parse Node (populates sections into state) ──────────


async def parse_node(state: FSAnalysisState) -> FSAnalysisState:
    """Load parsed sections into the pipeline state.

    In L3+, sections are pre-loaded by the caller, so this node
    simply validates and passes them through.
    """
    sections = state.get("parsed_sections", [])
    errors = list(state.get("errors", []))

    if not sections:
        errors.append("No parsed sections found in pipeline state")
        logger.warning("parse_node: no sections for fs_id=%s", state.get("fs_id", "?"))

    logger.info("parse_node: %d sections loaded for fs_id=%s", len(sections), state.get("fs_id", "?"))

    return {
        **state,
        "parsed_sections": sections,
        "errors": errors,
    }


# ── Build Graph ─────────────────────────────────────────


def build_analysis_graph() -> StateGraph:
    """Build the LangGraph StateGraph for FS analysis.

    Current pipeline (L9):
      START → parse_node → ambiguity_node → debate_node
            → contradiction_node → edge_case_node → quality_node
            → task_decomposition_node → dependency_node
            → traceability_node → duplicate_node → END

    Returns:
        Compiled StateGraph ready to invoke.
    """
    graph = StateGraph(FSAnalysisState)

    # Add nodes
    graph.add_node("parse_node", parse_node)
    graph.add_node("ambiguity_node", ambiguity_node)
    graph.add_node("debate_node", debate_node)
    graph.add_node("contradiction_node", contradiction_node)
    graph.add_node("edge_case_node", edge_case_node)
    graph.add_node("quality_node", quality_node)
    graph.add_node("task_decomposition_node", task_decomposition_node)
    graph.add_node("dependency_node", dependency_node)
    graph.add_node("traceability_node", traceability_node)
    graph.add_node("duplicate_node", duplicate_node)
    graph.add_node("testcase_node", testcase_node)

    # Define edges: linear pipeline
    graph.add_edge(START, "parse_node")
    graph.add_edge("parse_node", "ambiguity_node")
    graph.add_edge("ambiguity_node", "debate_node")
    graph.add_edge("debate_node", "contradiction_node")
    graph.add_edge("contradiction_node", "edge_case_node")
    graph.add_edge("edge_case_node", "quality_node")
    graph.add_edge("quality_node", "task_decomposition_node")
    graph.add_edge("task_decomposition_node", "dependency_node")
    graph.add_edge("dependency_node", "traceability_node")
    graph.add_edge("traceability_node", "duplicate_node")
    graph.add_edge("duplicate_node", "testcase_node")
    graph.add_edge("testcase_node", END)

    return graph.compile()


# ── L7: Impact Analysis Graph ──────────────────────────


def build_impact_graph() -> StateGraph:
    """Build the LangGraph StateGraph for FS impact analysis (L7).

    Pipeline: START → version_node → impact_node → rework_node → END

    Returns:
        Compiled StateGraph ready to invoke.
    """
    graph = StateGraph(FSImpactState)

    # Add nodes
    graph.add_node("version_node", version_node)
    graph.add_node("impact_node", impact_node)
    graph.add_node("rework_node", rework_node)

    # Define edges: linear pipeline
    graph.add_edge(START, "version_node")
    graph.add_edge("version_node", "impact_node")
    graph.add_edge("impact_node", "rework_node")
    graph.add_edge("rework_node", END)

    return graph.compile()


# ── L8: Reverse FS Generation Graph ────────────────────


def build_reverse_graph() -> StateGraph:
    """Build the LangGraph StateGraph for reverse FS generation (L8).

    Pipeline: START → reverse_fs_node → reverse_quality_node → END

    Returns:
        Compiled StateGraph ready to invoke.
    """
    graph = StateGraph(ReverseGenState)

    # Add nodes
    graph.add_node("reverse_fs_node", reverse_fs_node)
    graph.add_node("reverse_quality_node", reverse_quality_node)

    # Define edges: linear pipeline
    graph.add_edge(START, "reverse_fs_node")
    graph.add_edge("reverse_fs_node", "reverse_quality_node")
    graph.add_edge("reverse_quality_node", END)

    return graph.compile()


# ── Entry Points ───────────────────────────────────────


# Compiled graph singletons
_compiled_graph = None
_compiled_impact_graph = None
_compiled_reverse_graph = None


def get_compiled_graph():
    """Get or create the compiled analysis graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_analysis_graph()
    return _compiled_graph


def get_compiled_impact_graph():
    """Get or create the compiled impact graph."""
    global _compiled_impact_graph
    if _compiled_impact_graph is None:
        _compiled_impact_graph = build_impact_graph()
    return _compiled_impact_graph


def get_compiled_reverse_graph():
    """Get or create the compiled reverse generation graph."""
    global _compiled_reverse_graph
    if _compiled_reverse_graph is None:
        _compiled_reverse_graph = build_reverse_graph()
    return _compiled_reverse_graph


async def run_analysis_pipeline(
    fs_id: str,
    sections: List[Dict[str, Any]],
) -> FSAnalysisState:
    """Run the full analysis pipeline on a parsed document.

    Args:
        fs_id: Document ID.
        sections: List of parsed section dicts with heading, content, section_index.

    Returns:
        Final pipeline state with all analysis results populated.
    """
    graph = get_compiled_graph()

    initial_state: FSAnalysisState = {
        "fs_id": fs_id,
        "parsed_sections": sections,
        "ambiguities": [],
        "debate_results": [],
        "contradictions": [],
        "edge_cases": [],
        "quality_score": {},
        "compliance_tags": [],
        "tasks": [],
        "traceability_matrix": [],
        "duplicates": [],
        "test_cases": [],
        "errors": [],
    }

    logger.info("Starting analysis pipeline for fs_id=%s (%d sections)", fs_id, len(sections))

    result = await graph.ainvoke(initial_state)

    logger.info(
        "Pipeline complete for fs_id=%s: %d ambiguities, %d debate_results, %d contradictions, "
        "%d edge_cases, %d compliance_tags, %d tasks, %d traceability entries, %d duplicates, "
        "%d test_cases, %d errors",
        fs_id,
        len(result.get("ambiguities", [])),
        len(result.get("debate_results", [])),
        len(result.get("contradictions", [])),
        len(result.get("edge_cases", [])),
        len(result.get("compliance_tags", [])),
        len(result.get("tasks", [])),
        len(result.get("traceability_matrix", [])),
        len(result.get("duplicates", [])),
        len(result.get("test_cases", [])),
        len(result.get("errors", [])),
    )

    return result


async def run_impact_pipeline(
    fs_id: str,
    version_id: str,
    old_sections: List[Dict[str, Any]],
    new_sections: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
) -> FSImpactState:
    """Run the impact analysis pipeline on a version change.

    Args:
        fs_id: Document ID.
        version_id: New version ID.
        old_sections: Sections from the previous version.
        new_sections: Sections from the new version.
        tasks: Current task list from analysis.

    Returns:
        Final pipeline state with changes, impacts, and rework estimate.
    """
    graph = get_compiled_impact_graph()

    initial_state: FSImpactState = {
        "fs_id": fs_id,
        "version_id": version_id,
        "old_sections": old_sections,
        "new_sections": new_sections,
        "tasks": tasks,
        "fs_changes": [],
        "task_impacts": [],
        "rework_estimate": {},
        "errors": [],
    }

    logger.info(
        "Starting impact pipeline for fs_id=%s version=%s (%d old sections, %d new sections, %d tasks)",
        fs_id, version_id, len(old_sections), len(new_sections), len(tasks),
    )

    result = await graph.ainvoke(initial_state)

    logger.info(
        "Impact pipeline complete for fs_id=%s: %d changes, %d impacts, %d errors",
        fs_id,
        len(result.get("fs_changes", [])),
        len(result.get("task_impacts", [])),
        len(result.get("errors", [])),
    )

    return result


async def run_reverse_pipeline(
    code_upload_id: str,
    snapshot: dict,
) -> ReverseGenState:
    """Run the reverse FS generation pipeline on a parsed codebase.

    Args:
        code_upload_id: Code upload ID.
        snapshot: CodebaseSnapshot as dict.

    Returns:
        Final pipeline state with generated sections and quality report.
    """
    graph = get_compiled_reverse_graph()

    initial_state: ReverseGenState = {
        "code_upload_id": code_upload_id,
        "snapshot": snapshot,
        "module_summaries": [],
        "user_flows": [],
        "generated_sections": [],
        "raw_fs_text": "",
        "report": {},
        "errors": [],
    }

    logger.info(
        "Starting reverse pipeline for code_upload_id=%s (%d files)",
        code_upload_id, snapshot.get("total_files", 0),
    )

    result = await graph.ainvoke(initial_state)

    logger.info(
        "Reverse pipeline complete for code_upload_id=%s: %d sections, %d errors",
        code_upload_id,
        len(result.get("generated_sections", [])),
        len(result.get("errors", [])),
    )

    return result
