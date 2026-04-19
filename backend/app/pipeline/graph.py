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

import asyncio
import hashlib
import json
import logging
import threading
import uuid as _uuid_mod
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Dict, List

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pipeline.nodes.ambiguity_node import ambiguity_node
from app.pipeline.nodes.contradiction_node import contradiction_node
from app.pipeline.nodes.debate_node import debate_node
from app.pipeline.nodes.dependency_node import dependency_node
from app.pipeline.nodes.duplicate_node import duplicate_node
from app.pipeline.nodes.edge_case_node import edge_case_node
from app.pipeline.nodes.impact_node import impact_node
from app.pipeline.nodes.quality_node import quality_node
from app.pipeline.nodes.reverse_fs_node import reverse_fs_node
from app.pipeline.nodes.reverse_quality_node import reverse_quality_node
from app.pipeline.nodes.rework_node import rework_node
from app.pipeline.nodes.task_node import task_decomposition_node
from app.pipeline.nodes.testcase_node import testcase_node
from app.pipeline.nodes.traceability_node import traceability_node
from app.pipeline.nodes.version_node import version_node
from app.pipeline.state import FSAnalysisState, FSImpactState, ReverseGenState

logger = logging.getLogger(__name__)


# ── Analysis Progress Tracking (in-memory, per document) ─

ANALYSIS_NODE_ORDER = [
    "parse_node",
    "ambiguity_node",
    "debate_node",
    "contradiction_node",
    "edge_case_node",
    "quality_node",
    "task_decomposition_node",
    "dependency_node",
    "traceability_node",
    "duplicate_node",
    "testcase_node",
]

ANALYSIS_NODE_LABELS: dict[str, str] = {
    "parse_node": "Loading Sections",
    "ambiguity_node": "Detecting Ambiguities",
    "debate_node": "Adversarial Debate",
    "contradiction_node": "Cross-Reference Contradictions",
    "edge_case_node": "Edge Case Analysis",
    "quality_node": "Quality Scoring",
    "task_decomposition_node": "Task Decomposition",
    "dependency_node": "Dependency Mapping",
    "traceability_node": "Traceability Matrix",
    "duplicate_node": "Duplicate Detection",
    "testcase_node": "Test Case Generation",
}

_analysis_progress: dict[str, dict] = {}
_analysis_progress_lock = threading.Lock()


def get_analysis_progress(fs_id: str) -> dict | None:
    with _analysis_progress_lock:
        entry = _analysis_progress.get(fs_id)
        if entry is None:
            return None
        return {
            "completed_nodes": list(entry.get("completed_nodes", [])),
            "current_node": entry.get("current_node"),
            "total_nodes": entry.get("total_nodes", 0),
            "logs": list(entry.get("logs", [])),
        }


def _update_progress(fs_id: str, *, node: str, phase: str, log: str | None = None) -> None:
    with _analysis_progress_lock:
        entry = _analysis_progress.setdefault(
            fs_id,
            {
                "completed_nodes": [],
                "current_node": None,
                "total_nodes": len(ANALYSIS_NODE_ORDER),
                "logs": [],
            },
        )
        if phase == "start":
            entry["current_node"] = node
            msg = f"Started: {ANALYSIS_NODE_LABELS.get(node, node)}"
        elif phase == "complete":
            if node not in entry["completed_nodes"]:
                entry["completed_nodes"].append(node)
            entry["current_node"] = None
            msg = f"Completed: {ANALYSIS_NODE_LABELS.get(node, node)}"
        elif phase == "cached":
            if node not in entry["completed_nodes"]:
                entry["completed_nodes"].append(node)
            entry["current_node"] = None
            msg = f"Cached: {ANALYSIS_NODE_LABELS.get(node, node)}"
        else:
            msg = log or phase

        ts = datetime.now(UTC).strftime("%H:%M:%S")
        entry["logs"].append(f"[{ts}] {msg}")
        if len(entry["logs"]) > 100:
            entry["logs"] = entry["logs"][-80:]


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


def _compute_input_hash(node_name: str, state: dict) -> str:
    """Hash the relevant input fields for a given node to detect changes."""
    keys_by_node: dict[str, list[str]] = {
        "parse_node": ["fs_id", "parsed_sections"],
        "ambiguity_node": ["parsed_sections"],
        "debate_node": ["ambiguities"],
        "contradiction_node": ["parsed_sections"],
        "edge_case_node": ["parsed_sections"],
        "quality_node": ["ambiguities", "contradictions", "edge_cases", "parsed_sections"],
        "task_decomposition_node": ["parsed_sections", "ambiguities"],
        "dependency_node": ["tasks"],
        "traceability_node": ["tasks", "parsed_sections"],
        "duplicate_node": ["fs_id", "parsed_sections"],
        "testcase_node": ["tasks", "fs_id"],
    }
    relevant_keys = keys_by_node.get(node_name, ["fs_id"])
    data = {}
    for k in relevant_keys:
        v = state.get(k)
        if isinstance(v, list):
            data[k] = len(v)
            if v:
                data[k + "_sample"] = str(v[0])[:200]
        elif isinstance(v, dict):
            data[k] = sorted(v.keys())[:10]
        else:
            data[k] = str(v)[:200]
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def _get_cached_result(
    fs_id: "_uuid_mod.UUID",
    node_name: str,
    input_hash: str,
    db: AsyncSession,
) -> dict | None:
    """Fetch a cached node result.

    ``fs_id`` MUST be a :class:`uuid.UUID` instance — ``PipelineCacheDB.document_id``
    is a ``UUID(as_uuid=True)`` column whose SQLAlchemy bind processor calls
    ``.hex`` on the value. Passing a ``str`` here historically raised
    ``AttributeError: 'str' object has no attribute 'hex'`` and silently
    disabled the entire pipeline cache; see ``tests/test_pipeline_cache_roundtrip``.
    """
    from app.db.models import PipelineCacheDB

    row = (
        await db.execute(
            select(PipelineCacheDB).where(
                PipelineCacheDB.document_id == fs_id,
                PipelineCacheDB.node_name == node_name,
                PipelineCacheDB.input_hash == input_hash,
            )
        )
    ).scalar_one_or_none()
    if not row:
        return None
    # SQLite does not persist tzinfo, so rows may come back naive. Treat
    # naive datetimes as UTC so comparison with ``datetime.now(UTC)``
    # stays correct on both Postgres and SQLite.
    if row.expires_at:
        expiry = row.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry < datetime.now(UTC):
            await db.delete(row)
            await db.commit()
            return None
    return row.result_data


async def _set_cache(
    fs_id: "_uuid_mod.UUID",
    node_name: str,
    input_hash: str,
    result_data: dict,
    db: AsyncSession,
) -> None:
    """Write (or refresh) a cached node result. See ``_get_cached_result`` for the
    UUID contract."""
    from app.db.models import PipelineCacheDB

    existing = (
        await db.execute(
            select(PipelineCacheDB).where(
                PipelineCacheDB.document_id == fs_id,
                PipelineCacheDB.node_name == node_name,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.input_hash = input_hash
        existing.result_data = result_data
        existing.created_at = datetime.now(UTC)
        existing.expires_at = datetime.now(UTC) + timedelta(hours=24)
    else:
        import uuid as _uuid

        db.add(
            PipelineCacheDB(
                id=_uuid.uuid4(),
                document_id=fs_id,
                node_name=node_name,
                input_hash=input_hash,
                result_data=result_data,
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
    await db.commit()


_CACHEABLE_OUTPUT_KEYS: dict[str, list[str]] = {
    "ambiguity_node": ["ambiguities"],
    "debate_node": ["ambiguities", "debate_results"],
    "contradiction_node": ["contradictions"],
    "edge_case_node": ["edge_cases"],
    "quality_node": ["quality_score", "compliance_tags"],
    "task_decomposition_node": ["tasks"],
    "dependency_node": ["tasks"],
    "traceability_node": ["traceability_matrix"],
    "duplicate_node": ["duplicates"],
    "testcase_node": ["test_cases"],
}


async def _load_project_context(fs_id: str, db: AsyncSession) -> List[Dict[str, Any]]:
    """Load summaries of sibling documents in the same project for context."""
    from app.db.models import FSDocument, FSDocumentStatus

    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == _uuid_mod.UUID(fs_id)))
    doc = doc_result.scalar_one_or_none()
    if not doc or not doc.project_id:
        return []

    siblings_result = await db.execute(
        select(FSDocument)
        .where(
            FSDocument.project_id == doc.project_id,
            FSDocument.id != doc.id,
            FSDocument.status.in_([FSDocumentStatus.COMPLETE, FSDocumentStatus.PARSED]),
        )
        .order_by(FSDocument.order_in_project)
    )
    siblings = siblings_result.scalars().all()
    if not siblings:
        return []

    context = []
    for sib in siblings:
        text_preview = (sib.parsed_text or "")[:2000]
        context.append(
            {
                "document_id": str(sib.id),
                "filename": sib.filename,
                "status": sib.status.value if hasattr(sib.status, "value") else str(sib.status),
                "text_preview": text_preview,
            }
        )
    logger.info(
        "Loaded project context: %d sibling docs for fs_id=%s (project=%s)",
        len(context),
        fs_id,
        doc.project_id,
    )
    return context


SELECTIVE_NODE_SET = {
    "parse_node",
    "ambiguity_node",
    "debate_node",
    "edge_case_node",
}


async def run_analysis_pipeline(
    fs_id: str,
    sections: List[Dict[str, Any]],
    db: AsyncSession | None = None,
    cancel_event: "asyncio.Event | None" = None,
    changed_indices: "set[int] | None" = None,
) -> FSAnalysisState:
    """Run the full analysis pipeline on a parsed document.

    When a db session is provided, each node checks PipelineCacheDB before
    running. On cache hit the LLM call is skipped entirely, saving tokens.

    Args:
        fs_id: Document ID.
        sections: List of parsed section dicts with heading, content, section_index.
        db: Optional async DB session for pipeline caching.
        cancel_event: When set, the pipeline stops before the next node.
        changed_indices: When provided, only per-section nodes (ambiguity,
            debate, edge-case) run, and only on the listed section indices.
            Cross-cutting nodes (contradiction, quality, tasks, etc.) are
            skipped so existing results are preserved.

    Returns:
        Final pipeline state with all analysis results populated.
    """
    graph = get_compiled_graph()

    if changed_indices:
        sections = [s for s in sections if s.get("section_index") in changed_indices]
        logger.info(
            "Selective analysis: restricted to %d sections (%s)",
            len(sections),
            sorted(changed_indices),
        )

    project_context: List[Dict[str, Any]] = []
    if db is not None:
        try:
            project_context = await _load_project_context(fs_id, db)
        except Exception as exc:
            logger.warning("Failed to load project context for %s: %s", fs_id, exc)

    initial_state: FSAnalysisState = {
        "fs_id": fs_id,
        "parsed_sections": sections,
        "project_context": project_context,
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

    logger.info(
        "Starting analysis pipeline for fs_id=%s (%d sections, %d project context docs)",
        fs_id,
        len(sections),
        len(project_context),
    )

    with _analysis_progress_lock:
        _analysis_progress.pop(fs_id, None)
    _update_progress(fs_id, node="", phase="log", log="Pipeline starting")

    if db is not None:
        node_order = ANALYSIS_NODE_ORDER
        if changed_indices:
            node_order = [n for n in ANALYSIS_NODE_ORDER if n in SELECTIVE_NODE_SET]
        node_fns: dict[str, Callable] = {
            "parse_node": parse_node,
            "ambiguity_node": ambiguity_node,
            "debate_node": debate_node,
            "contradiction_node": contradiction_node,
            "edge_case_node": edge_case_node,
            "quality_node": quality_node,
            "task_decomposition_node": task_decomposition_node,
            "dependency_node": dependency_node,
            "traceability_node": traceability_node,
            "duplicate_node": duplicate_node,
            "testcase_node": testcase_node,
        }
        state = dict(initial_state)
        cache_hits = 0
        # Parse ``fs_id`` into a real ``uuid.UUID`` object. The cache columns
        # use ``UUID(as_uuid=True)`` and the SQLAlchemy bind processor calls
        # ``.hex`` on the bound value — passing a string silently disables the
        # entire cache with an ``AttributeError``.
        import uuid as _uuid

        try:
            if isinstance(fs_id, _uuid.UUID):
                fs_uuid = fs_id
            else:
                fs_uuid = _uuid.UUID(str(fs_id))
        except (ValueError, AttributeError, TypeError):
            fs_uuid = None

        for node_name in node_order:
            if cancel_event and cancel_event.is_set():
                logger.warning("Analysis cancelled for fs_id=%s at node %s", fs_id, node_name)
                state["errors"].append(f"Analysis cancelled before {node_name}")
                break
            if fs_uuid and node_name in _CACHEABLE_OUTPUT_KEYS:
                input_hash = _compute_input_hash(node_name, state)
                try:
                    cached = await _get_cached_result(fs_uuid, node_name, input_hash, db)
                except Exception:
                    cached = None
                if cached:
                    for key in _CACHEABLE_OUTPUT_KEYS[node_name]:
                        if key in cached:
                            state[key] = cached[key]
                    cache_hits += 1
                    logger.info("Cache HIT for %s (fs_id=%s)", node_name, fs_id)
                    _update_progress(fs_id, node=node_name, phase="cached")
                    continue

            _update_progress(fs_id, node=node_name, phase="start")
            logger.info("Running node %s for fs_id=%s", node_name, fs_id)
            fn = node_fns[node_name]
            state = await fn(state)
            _update_progress(fs_id, node=node_name, phase="complete")

            if fs_uuid and node_name in _CACHEABLE_OUTPUT_KEYS:
                output_data = {k: state.get(k) for k in _CACHEABLE_OUTPUT_KEYS[node_name]}
                try:
                    await _set_cache(fs_uuid, node_name, input_hash, output_data, db)
                except Exception as exc:
                    logger.warning("Cache write failed for %s: %s", node_name, exc)

        if cache_hits:
            logger.info("Pipeline used %d cache hits for fs_id=%s", cache_hits, fs_id)
        result = state
    else:
        result = await graph.ainvoke(initial_state)

    _update_progress(fs_id, node="", phase="log", log="Pipeline complete")

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
        fs_id,
        version_id,
        len(old_sections),
        len(new_sections),
        len(tasks),
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
        code_upload_id,
        snapshot.get("total_files", 0),
    )

    result = await graph.ainvoke(initial_state)

    logger.info(
        "Reverse pipeline complete for code_upload_id=%s: %d sections, %d errors",
        code_upload_id,
        len(result.get("generated_sections", [])),
        len(result.get("errors", [])),
    )

    return result
