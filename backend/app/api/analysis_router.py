"""Analysis API — trigger analysis, list/resolve ambiguities, L4+L5 endpoints."""

import asyncio
import asyncio as _asyncio
import hashlib
import logging
import uuid
from datetime import UTC, datetime
from uuid import UUID as _UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.audit import log_audit_event
from app.db.base import get_db
from app.db.models import (
    AmbiguityFlagDB,
    AmbiguitySeverity,
    AuditEventType,
    ComplianceTagDB,
    ContradictionDB,
    DebateResultDB,
    DuplicateFlagDB,
    EdgeCaseGapDB,
    EffortLevel,
    FSDocument,
    FSDocumentStatus,
    FSTaskDB,
    FSVersion,
    TestCaseDB,
    TestType,
    TraceabilityEntryDB,
)
from app.models.schemas import (
    AcceptRefinementRequest,
    AmbiguityFlagSchema,
    AmbiguityResolveRequest,
    AnalysisResponse,
    APIResponse,
    ComplianceTagSchema,
    ContradictionSchema,
    DebateResultSchema,
    DebateResultsResponse,
    EdgeCaseGapSchema,
    QualityDashboardResponse,
    QualityScoreSchema,
    RefinementDiffLineSchema,
    RefinementResponse,
    RefinementSuggestionSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fs", tags=["analysis"])

_cancel_events: dict[_UUID, _asyncio.Event] = {}


@router.get("/{doc_id}/analysis-progress")
async def get_analysis_progress_endpoint(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    from app.pipeline.graph import ANALYSIS_NODE_LABELS, ANALYSIS_NODE_ORDER, get_analysis_progress

    result = await db.execute(select(FSDocument.status).where(FSDocument.id == doc_id))
    status_val = result.scalar_one_or_none()
    if status_val is None:
        raise HTTPException(status_code=404, detail="Document not found")

    doc_status = status_val.value if hasattr(status_val, "value") else str(status_val)

    progress = get_analysis_progress(str(doc_id))
    if progress:
        return {
            "data": {
                "status": doc_status,
                "current_node": progress.get("current_node"),
                "completed_nodes": progress.get("completed_nodes", []),
                "total_nodes": progress.get("total_nodes", len(ANALYSIS_NODE_ORDER)),
                "node_labels": ANALYSIS_NODE_LABELS,
                "logs": progress.get("logs", [])[-40:],
            }
        }

    return {
        "data": {
            "status": doc_status,
            "current_node": None,
            "completed_nodes": ANALYSIS_NODE_ORDER if doc_status == "COMPLETE" else [],
            "total_nodes": len(ANALYSIS_NODE_ORDER),
            "node_labels": ANALYSIS_NODE_LABELS,
            "logs": [],
        }
    }


async def _refresh_quality_score_internal(doc_id: uuid.UUID, db: AsyncSession) -> dict:
    ambiguities_result = await db.execute(select(AmbiguityFlagDB).where(AmbiguityFlagDB.fs_id == doc_id))
    ambiguities = ambiguities_result.scalars().all()

    contradictions_result = await db.execute(select(ContradictionDB).where(ContradictionDB.fs_id == doc_id))
    contradictions = contradictions_result.scalars().all()

    edge_cases_result = await db.execute(select(EdgeCaseGapDB).where(EdgeCaseGapDB.fs_id == doc_id))
    edge_cases = edge_cases_result.scalars().all()

    from app.parsers.router import parse_document as do_parse
    from app.pipeline.nodes.quality_node import compute_quality_score

    try:
        parsed = await do_parse(str(doc_id), db)
        total_sections = len(parsed.sections)
    except Exception:
        total_sections = 1

    open_ambiguities = [a for a in ambiguities if not a.resolved]
    open_contradictions = [c for c in contradictions if not c.resolved]
    open_edge_cases = [e for e in edge_cases if not e.resolved]

    score = compute_quality_score(
        total_sections=total_sections,
        ambiguities=[{"section_index": a.section_index} for a in open_ambiguities],
        contradictions=[{"section_a_index": c.section_a_index} for c in open_contradictions],
        edge_cases=[{"section_index": e.section_index} for e in open_edge_cases],
    )

    return {
        "overall": score.overall,
        "completeness": score.completeness,
        "clarity": score.clarity,
        "consistency": score.consistency,
        "open_ambiguities": len(open_ambiguities),
        "open_contradictions": len(open_contradictions),
        "open_edge_cases": len(open_edge_cases),
    }


async def _build_analysis_response_from_db(
    doc_id: uuid.UUID,
    doc: FSDocument,
    db: AsyncSession,
) -> AnalysisResponse:
    flags_result = await db.execute(select(AmbiguityFlagDB).where(AmbiguityFlagDB.fs_id == doc_id))
    flags = flags_result.scalars().all()

    contradictions_result = await db.execute(select(ContradictionDB).where(ContradictionDB.fs_id == doc_id))
    contradictions = contradictions_result.scalars().all()

    edge_cases_result = await db.execute(select(EdgeCaseGapDB).where(EdgeCaseGapDB.fs_id == doc_id))
    edge_cases = edge_cases_result.scalars().all()

    tasks_result = await db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc_id))
    tasks = tasks_result.scalars().all()

    from app.parsers.router import parse_document as do_parse
    from app.pipeline.nodes.quality_node import compute_quality_score

    try:
        parsed = await do_parse(str(doc.id), db)
        total_sections = len(parsed.sections)
    except Exception:
        all_indices = set()
        for a in flags:
            all_indices.add(a.section_index)
        for e in edge_cases:
            all_indices.add(e.section_index)
        total_sections = max(len(all_indices), 1)

    quality = compute_quality_score(
        total_sections=total_sections,
        ambiguities=[{"section_index": a.section_index} for a in flags if not a.resolved],
        contradictions=[{"section_a_index": c.section_a_index} for c in contradictions if not c.resolved],
        edge_cases=[{"section_index": e.section_index} for e in edge_cases if not e.resolved],
    )

    flag_schemas = [
        AmbiguityFlagSchema(
            id=f.id,
            section_index=f.section_index,
            section_heading=f.section_heading,
            flagged_text=f.flagged_text,
            reason=f.reason,
            severity=f.severity.value,
            clarification_question=f.clarification_question,
            resolved=f.resolved,
        )
        for f in flags
    ]

    high_count = sum(1 for f in flags if (f.severity == AmbiguitySeverity.HIGH and not f.resolved))
    medium_count = sum(1 for f in flags if (f.severity == AmbiguitySeverity.MEDIUM and not f.resolved))
    low_count = sum(1 for f in flags if (f.severity == AmbiguitySeverity.LOW and not f.resolved))

    return AnalysisResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status.value,
        ambiguities_count=len(flags),
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        ambiguities=flag_schemas,
        contradictions_count=len(contradictions),
        edge_cases_count=len(edge_cases),
        tasks_count=len(tasks),
        quality_score=QualityScoreSchema(
            completeness=quality.completeness,
            clarity=quality.clarity,
            consistency=quality.consistency,
            overall=quality.overall,
        ),
    )


async def _safe_audit(
    db: AsyncSession,
    fs_id: uuid.UUID,
    event_type: AuditEventType,
    payload: dict | None = None,
    user_id: str = "system",
) -> None:
    """Best-effort audit emit. Never let telemetry kill the request."""
    try:
        await log_audit_event(db, fs_id, event_type, user_id=user_id, payload=payload)
    except Exception:
        logger.exception("audit emit failed for fs_id=%s type=%s", fs_id, event_type)


async def _persist_refined_version(
    doc: FSDocument,
    refined_text: str,
    db: AsyncSession,
    *,
    trigger: str = "refine",
) -> FSVersion:
    versions_result = await db.execute(
        select(FSVersion).where(FSVersion.fs_id == doc.id).order_by(FSVersion.version_number.desc())
    )
    existing_versions = versions_result.scalars().all()
    next_version = (existing_versions[0].version_number + 1) if existing_versions else 2

    if not existing_versions:
        baseline = FSVersion(
            fs_id=doc.id,
            version_number=1,
            parsed_text=doc.parsed_text or doc.original_text or "",
            file_path=doc.file_path,
            file_size=doc.file_size,
            content_type=doc.content_type,
            content_hash=hashlib.sha256((doc.parsed_text or doc.original_text or "").encode()).hexdigest()[:32],
            diff_summary="Baseline before refinement",
        )
        db.add(baseline)
        await db.flush()

    version = FSVersion(
        fs_id=doc.id,
        version_number=next_version,
        parsed_text=refined_text,
        file_path=doc.file_path,
        file_size=doc.file_size,
        content_type=doc.content_type,
        content_hash=hashlib.sha256(refined_text.encode()).hexdigest()[:32],
        diff_summary="Refinement pipeline accepted as latest FS version",
    )
    db.add(version)

    # Latest always becomes active working text.
    doc.parsed_text = refined_text
    doc.original_text = refined_text
    # NOTE: we deliberately do **not** demote ``status`` to PARSED here.
    # When the doc was already COMPLETE, the analysis artefacts (tasks,
    # ambiguities, …) are still attached and the user wants the Build
    # CTA to remain visible. Instead we flip ``analysis_stale`` so the
    # UI can render a soft "re-analyze to refresh metrics" banner. A
    # fresh analyze run (``analyze_document`` success branch) clears the
    # flag again.
    if doc.status == FSDocumentStatus.COMPLETE:
        doc.analysis_stale = True
    await db.flush()
    await db.refresh(version)
    await _safe_audit(
        db,
        doc.id,
        AuditEventType.ANALYSIS_REFINED,
        payload={
            "trigger": trigger,
            "version_number": version.version_number,
            "stale": bool(getattr(doc, "analysis_stale", False)),
        },
    )
    return version


@router.post("/{doc_id}/analyze", response_model=APIResponse)
async def analyze_document(
    doc_id: uuid.UUID,
    sections_filter: str = Query(
        None, alias="sections", description="Comma-separated section indices to re-analyze selectively"
    ),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Trigger the full 11-node LangGraph analysis pipeline on a parsed document.

    Pipeline order:
        parse_node → ambiguity_node → debate_node → contradiction_node →
        edge_case_node → quality_node → task_decomposition_node →
        dependency_node → traceability_node → duplicate_node → testcase_node

    Passing ``?sections=1,3`` runs only the per-section nodes (ambiguity,
    contradiction, edge_case, task_decomposition, traceability, duplicate,
    testcase) over the specified section indices and keeps existing results
    for all other sections.

    Persists all results to PostgreSQL. Transitions document status
    PARSED → ANALYZING → COMPLETE (or ERROR on failure).
    """
    from app.orchestration.config_resolver import get_configured_llm_provider_name
    from app.pipeline.graph import run_analysis_pipeline

    # Load document
    result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # When Cursor is the active provider, branch to the paste-per-action
    # flow. A single prompt is generated; the pipeline is NOT run. The
    # UI opens the Cursor task modal with ``mode=cursor_task`` and polls
    # ``GET /api/cursor-tasks/{task_id}`` until the user pastes and
    # Cursor submits the analysis via MCP.
    provider = (await get_configured_llm_provider_name()) or "api"
    if provider == "cursor":
        from app.db.models import (
            CursorTaskDB,
            CursorTaskKind,
            CursorTaskStatus,
        )
        from app.orchestration.cursor_prompts import (
            build_analyze_prompt,
            build_mcp_snippet,
        )

        fs_text = doc.parsed_text or doc.original_text or ""
        if not fs_text.strip():
            raise HTTPException(
                status_code=400,
                detail="FS document has no parsed text yet; upload / parse it first.",
            )
        task_id = uuid.uuid4()
        prompt = build_analyze_prompt(task_id=task_id, fs_text=fs_text)
        task = CursorTaskDB(
            id=task_id,
            kind=CursorTaskKind.ANALYZE,
            status=CursorTaskStatus.PENDING,
            related_id=doc.id,
            input_payload={"doc_id": str(doc.id)},
            prompt_text=prompt,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        logger.info("Analyze route branched to Cursor paste-per-action task %s", task.id)
        return APIResponse(
            data={
                "mode": "cursor_task",
                "task_id": str(task.id),
                "kind": "analyze",
                "prompt": task.prompt_text,
                "mcp_snippet": build_mcp_snippet(),
                "status": task.status.value.lower(),
            }
        )

    if doc.status not in (
        FSDocumentStatus.PARSED,
        FSDocumentStatus.COMPLETE,
        FSDocumentStatus.ANALYZING,
        FSDocumentStatus.ERROR,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Document must be parsed before analysis. Current status: {doc.status.value}",
        )

    if doc.status == FSDocumentStatus.COMPLETE:
        existing = await _build_analysis_response_from_db(doc_id, doc, db)
        return APIResponse(data=existing)

    if doc.status == FSDocumentStatus.ANALYZING:
        from datetime import datetime, timedelta

        stuck_threshold = timedelta(minutes=3)
        now = datetime.now(UTC)
        last_update = doc.updated_at.replace(tzinfo=UTC) if doc.updated_at.tzinfo is None else doc.updated_at
        if (now - last_update) > stuck_threshold:
            logger.warning("Document %s stuck in ANALYZING for >3min — resetting to PARSED", doc_id)
            doc.status = FSDocumentStatus.PARSED
            await db.commit()
        else:
            max_wait_seconds = 60
            elapsed = 0
            while elapsed < max_wait_seconds:
                await asyncio.sleep(3)
                elapsed += 3
                await db.refresh(doc)
                if doc.status == FSDocumentStatus.COMPLETE:
                    existing = await _build_analysis_response_from_db(doc_id, doc, db)
                    return APIResponse(data=existing)
                if doc.status == FSDocumentStatus.ERROR:
                    doc.status = FSDocumentStatus.PARSED
                    await db.commit()
                    break
            if doc.status == FSDocumentStatus.ANALYZING:
                doc.status = FSDocumentStatus.PARSED
                await db.commit()

    # Status PARSED/ERROR: start fresh analysis
    doc.status = FSDocumentStatus.ANALYZING
    await db.commit()

    # Load parsed sections — either from disk (uploaded) or from stored text (idea-generated)
    if doc.file_path:
        from app.parsers.router import parse_document as do_parse

        parsed = await do_parse(str(doc.id), db)
        sections = [
            {"heading": s.heading, "content": s.content, "section_index": s.section_index} for s in parsed.sections
        ]
    elif doc.parsed_text:
        from app.parsers.section_extractor import extract_sections_from_text

        extracted = extract_sections_from_text(doc.parsed_text)
        sections = [{"heading": s.heading, "content": s.content, "section_index": s.section_index} for s in extracted]
    else:
        doc.status = FSDocumentStatus.ERROR
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail="Document has neither a file path nor parsed text. Re-upload or re-generate.",
        )

    changed_indices: set[int] | None = None
    if sections_filter:
        try:
            changed_indices = {int(x.strip()) for x in sections_filter.split(",") if x.strip()}
            from sqlalchemy import delete as sql_delete

            from app.db.models import PipelineCacheDB

            await db.execute(sql_delete(PipelineCacheDB).where(PipelineCacheDB.document_id == doc_id))
            await db.commit()
            logger.info("Selective analysis for sections %s (cache cleared)", changed_indices)
        except (ValueError, TypeError):
            changed_indices = None

    # Run the LangGraph pipeline
    cancel_evt = _asyncio.Event()
    _cancel_events[doc_id] = cancel_evt
    try:
        try:
            pipeline_result = await run_analysis_pipeline(
                str(doc.id),
                sections,
                db=db,
                cancel_event=cancel_evt,
                changed_indices=changed_indices,
            )
        except Exception as exc:
            doc.status = FSDocumentStatus.ERROR
            await db.commit()
            logger.error("Analysis pipeline failed for %s: %s", doc_id, exc)
            return JSONResponse(
                status_code=503,
                content={
                    "error": "Analysis failed",
                    "reason": str(exc),
                    "retry_after": 10,
                },
            )
    finally:
        _cancel_events.pop(doc_id, None)

    if cancel_evt.is_set():
        doc.status = FSDocumentStatus.PARSED
        await db.commit()
        return APIResponse(
            data=AnalysisResponse(
                id=doc.id,
                filename=doc.filename,
                status="PARSED",
                ambiguities_count=0,
                high_count=0,
                medium_count=0,
                low_count=0,
                ambiguities=[],
                contradictions_count=0,
                edge_cases_count=0,
                tasks_count=0,
                quality_score=None,
            ),
        )

    # ── Delete existing results for this document (re-analysis) ──
    if changed_indices:
        # Selective: only replace per-section rows for the listed indices.
        # Cross-cutting results (tasks, quality, dependencies, traceability,
        # duplicates, test cases) are preserved.
        per_section_models = [
            (AmbiguityFlagDB, "section_index"),
            (EdgeCaseGapDB, "section_index"),
            (DebateResultDB, "section_index"),
        ]
        for model_class, col in per_section_models:
            existing = await db.execute(
                select(model_class).where(
                    model_class.fs_id == doc_id,
                    getattr(model_class, col).in_(list(changed_indices)),
                )
            )
            for row in existing.scalars().all():
                await db.delete(row)
    else:
        for model_class in [
            AmbiguityFlagDB,
            ContradictionDB,
            EdgeCaseGapDB,
            ComplianceTagDB,
            FSTaskDB,
            TraceabilityEntryDB,
            DebateResultDB,
            DuplicateFlagDB,
            TestCaseDB,
        ]:
            existing = await db.execute(select(model_class).where(model_class.fs_id == doc_id))
            for row in existing.scalars().all():
                await db.delete(row)

    # ── Persist ambiguity flags ──
    ambiguity_dicts = pipeline_result.get("ambiguities", [])
    db_flags = []
    for amb in ambiguity_dicts:
        severity_str = amb.get("severity", "MEDIUM")
        try:
            severity = AmbiguitySeverity(severity_str)
        except ValueError:
            severity = AmbiguitySeverity.MEDIUM

        flag = AmbiguityFlagDB(
            fs_id=doc_id,
            section_index=amb.get("section_index", 0),
            section_heading=amb.get("section_heading", ""),
            flagged_text=amb.get("flagged_text", ""),
            reason=amb.get("reason", ""),
            severity=severity,
            clarification_question=amb.get("clarification_question", ""),
            resolved=False,
        )
        db.add(flag)
        db_flags.append(flag)

    # ── Persist contradictions (L4) ──
    contradiction_dicts = pipeline_result.get("contradictions", [])
    db_contradictions = []
    for c in contradiction_dicts:
        severity_str = c.get("severity", "MEDIUM")
        try:
            severity = AmbiguitySeverity(severity_str)
        except ValueError:
            severity = AmbiguitySeverity.MEDIUM

        contradiction = ContradictionDB(
            fs_id=doc_id,
            section_a_index=c.get("section_a_index", 0),
            section_a_heading=c.get("section_a_heading", ""),
            section_b_index=c.get("section_b_index", 0),
            section_b_heading=c.get("section_b_heading", ""),
            description=c.get("description", ""),
            severity=severity,
            suggested_resolution=c.get("suggested_resolution", ""),
            resolved=False,
        )
        db.add(contradiction)
        db_contradictions.append(contradiction)

    # ── Persist edge case gaps (L4) ──
    edge_case_dicts = pipeline_result.get("edge_cases", [])
    db_edge_cases = []
    for ec in edge_case_dicts:
        impact_str = ec.get("impact", "MEDIUM")
        try:
            impact = AmbiguitySeverity(impact_str)
        except ValueError:
            impact = AmbiguitySeverity.MEDIUM

        edge_case = EdgeCaseGapDB(
            fs_id=doc_id,
            section_index=ec.get("section_index", 0),
            section_heading=ec.get("section_heading", ""),
            scenario_description=ec.get("scenario_description", ""),
            impact=impact,
            suggested_addition=ec.get("suggested_addition", ""),
            resolved=False,
        )
        db.add(edge_case)
        db_edge_cases.append(edge_case)

    # ── Persist compliance tags (L4) ──
    compliance_dicts = pipeline_result.get("compliance_tags", [])
    db_compliance = []
    for ct in compliance_dicts:
        tag = ComplianceTagDB(
            fs_id=doc_id,
            section_index=ct.get("section_index", 0),
            section_heading=ct.get("section_heading", ""),
            tag=ct.get("tag", ""),
            reason=ct.get("reason", ""),
        )
        db.add(tag)
        db_compliance.append(tag)

    # ── Persist tasks (L5) ──
    task_dicts = pipeline_result.get("tasks", [])
    db_tasks = []
    for t in task_dicts:
        effort_str = t.get("effort", "MEDIUM")
        try:
            effort = EffortLevel(effort_str)
        except ValueError:
            effort = EffortLevel.MEDIUM

        task = FSTaskDB(
            fs_id=doc_id,
            task_id=t.get("task_id", ""),
            title=t.get("title", ""),
            description=t.get("description", ""),
            section_index=t.get("section_index", 0),
            section_heading=t.get("section_heading", ""),
            depends_on=t.get("depends_on", []),
            acceptance_criteria=t.get("acceptance_criteria", []),
            effort=effort,
            tags=t.get("tags", []),
            order=t.get("order", 0),
            can_parallel=t.get("can_parallel", False),
        )
        db.add(task)
        db_tasks.append(task)

    # ── Persist traceability matrix (L5) ──
    trace_dicts = pipeline_result.get("traceability_matrix", [])
    db_traces = []
    for tr in trace_dicts:
        entry = TraceabilityEntryDB(
            fs_id=doc_id,
            task_id=tr.get("task_id", ""),
            task_title=tr.get("task_title", ""),
            section_index=tr.get("section_index", 0),
            section_heading=tr.get("section_heading", ""),
        )
        db.add(entry)
        db_traces.append(entry)

    # Update document status
    doc.status = FSDocumentStatus.COMPLETE
    doc.analysis_stale = False

    # ── Persist debate results (L6) ──
    debate_dicts = pipeline_result.get("debate_results", [])
    db_debates = []
    for dr in debate_dicts:
        debate = DebateResultDB(
            fs_id=doc_id,
            section_index=dr.get("section_index", 0),
            section_heading=dr.get("section_heading", ""),
            flagged_text=dr.get("flagged_text", ""),
            original_reason=dr.get("original_reason", ""),
            verdict=dr.get("verdict", "AMBIGUOUS"),
            red_argument=dr.get("red_argument", ""),
            blue_argument=dr.get("blue_argument", ""),
            arbiter_reasoning=dr.get("arbiter_reasoning", ""),
            confidence=dr.get("confidence", 50),
        )
        db.add(debate)
        db_debates.append(debate)

    # ── Persist duplicate flags (L9) ──
    duplicate_dicts = pipeline_result.get("duplicates", [])
    db_duplicates = []
    for dup in duplicate_dicts:
        similar_fs_id_str = dup.get("similar_fs_id", "")
        try:
            import uuid as uuid_mod

            similar_uuid = uuid_mod.UUID(similar_fs_id_str) if similar_fs_id_str else None
        except (ValueError, AttributeError):
            similar_uuid = None

        if similar_uuid:
            dup_flag = DuplicateFlagDB(
                fs_id=doc_id,
                section_index=dup.get("section_index", 0),
                section_heading=dup.get("section_heading", ""),
                similar_fs_id=similar_uuid,
                similar_section_heading=dup.get("similar_section_heading", ""),
                similarity_score=dup.get("similarity_score", 0.0),
                flagged_text=dup.get("flagged_text", ""),
                similar_text=dup.get("similar_text", ""),
            )
            db.add(dup_flag)
            db_duplicates.append(dup_flag)

    # ── Persist test cases (L10) ──
    testcase_dicts = pipeline_result.get("test_cases", [])
    db_testcases = []
    for tc in testcase_dicts:
        test_type_str = tc.get("test_type", "UNIT")
        try:
            test_type = TestType(test_type_str)
        except ValueError:
            test_type = TestType.UNIT

        testcase = TestCaseDB(
            fs_id=doc_id,
            task_id=tc.get("task_id", ""),
            title=tc.get("title", ""),
            preconditions=tc.get("preconditions", ""),
            steps=tc.get("steps", []),
            expected_result=tc.get("expected_result", ""),
            test_type=test_type,
            section_index=tc.get("section_index", 0),
            section_heading=tc.get("section_heading", ""),
        )
        db.add(testcase)
        db_testcases.append(testcase)

    # ── Log audit events (L9) ──
    from app.db.audit import log_audit_event

    await log_audit_event(
        db,
        doc_id,
        AuditEventType.ANALYZED,
        payload={
            "ambiguities": len(db_flags),
            "contradictions": len(db_contradictions),
            "edge_cases": len(db_edge_cases),
            "tasks": len(db_tasks),
            "duplicates": len(db_duplicates),
            "test_cases": len(db_testcases),
        },
    )
    if db_tasks:
        await log_audit_event(
            db,
            doc_id,
            AuditEventType.TASKS_GENERATED,
            payload={"tasks_count": len(db_tasks)},
        )

    await db.commit()

    # Refresh all to get IDs
    for item in (
        db_flags
        + db_contradictions
        + db_edge_cases
        + db_compliance
        + db_tasks
        + db_traces
        + db_debates
        + db_duplicates
        + db_testcases
    ):
        await db.refresh(item)

    # Build response
    flag_schemas = [
        AmbiguityFlagSchema(
            id=f.id,
            section_index=f.section_index,
            section_heading=f.section_heading,
            flagged_text=f.flagged_text,
            reason=f.reason,
            severity=f.severity.value,
            clarification_question=f.clarification_question,
            resolved=f.resolved,
        )
        for f in db_flags
    ]

    high_count = sum(1 for f in db_flags if f.severity == AmbiguitySeverity.HIGH)
    medium_count = sum(1 for f in db_flags if f.severity == AmbiguitySeverity.MEDIUM)
    low_count = sum(1 for f in db_flags if f.severity == AmbiguitySeverity.LOW)

    # Build quality score schema
    quality_dict = pipeline_result.get("quality_score", {})
    quality_schema = (
        QualityScoreSchema(
            completeness=quality_dict.get("completeness", 0.0),
            clarity=quality_dict.get("clarity", 0.0),
            consistency=quality_dict.get("consistency", 0.0),
            overall=quality_dict.get("overall", 0.0),
        )
        if quality_dict
        else None
    )

    return APIResponse(
        data=AnalysisResponse(
            id=doc.id,
            filename=doc.filename,
            status=doc.status.value,
            ambiguities_count=len(db_flags),
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            ambiguities=flag_schemas,
            contradictions_count=len(db_contradictions),
            edge_cases_count=len(db_edge_cases),
            tasks_count=len(db_tasks),
            quality_score=quality_schema,
        ),
    )


@router.post("/{doc_id}/cancel-analysis", response_model=APIResponse[dict])
async def cancel_analysis(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Cancel a running analysis for a document."""
    evt = _cancel_events.get(doc_id)
    if not evt:
        return APIResponse(
            data={
                "cancelled": False,
                "reason": "No active analysis found for this document",
            },
        )

    evt.set()

    await asyncio.sleep(1)

    result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc and doc.status == FSDocumentStatus.ANALYZING:
        doc.status = FSDocumentStatus.PARSED
        from app.db.audit import log_audit_event

        await log_audit_event(db, doc_id, AuditEventType.ANALYSIS_CANCELLED)
        await db.commit()

    return APIResponse(data={"cancelled": True, "document_id": str(doc_id)})


@router.post("/{doc_id}/refine", response_model=APIResponse)
async def refine_document(
    doc_id: uuid.UUID,
    mode: str = Query("auto", description="Refinement mode: auto, targeted, full"),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Run refinement pipeline and return refined FS candidate.

    mode=auto: targeted if <= 5 issues, full otherwise.
    mode=targeted: only fix affected paragraphs (fast, fewer tokens).
    mode=full: rewrite entire document (thorough).

    When ``llm_provider == "cursor"``, we branch to a CursorTask so the
    user pastes the refine prompt into Cursor and the MCP ``submit_refine``
    tool pushes the refined markdown back without burning any Direct-API
    tokens.
    """
    from app.orchestration.config_resolver import get_configured_llm_provider_name

    provider = (await get_configured_llm_provider_name()) or "api"
    if provider == "cursor":
        from app.db.models import (
            AmbiguityFlagDB,
            CursorTaskDB,
            CursorTaskKind,
            CursorTaskStatus,
        )
        from app.orchestration.cursor_prompts import (
            build_mcp_snippet,
            build_refine_prompt,
        )

        doc_row = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
        doc = doc_row.scalar_one_or_none()
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        fs_text = doc.parsed_text or doc.original_text or ""
        if not fs_text.strip():
            raise HTTPException(
                status_code=400,
                detail="FS document has no parsed text yet; upload / parse it first.",
            )
        flag_rows = (
            (
                await db.execute(
                    select(AmbiguityFlagDB).where(
                        AmbiguityFlagDB.fs_id == doc_id,
                        AmbiguityFlagDB.resolved.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        accepted_flags = [
            {
                "section_index": f.section_index,
                "section_heading": f.section_heading,
                "flagged_text": f.flagged_text,
                "clarification_question": f.clarification_question,
                "resolution_text": f.resolution_text or "",
            }
            for f in flag_rows
        ]
        task_id = uuid.uuid4()
        prompt = build_refine_prompt(
            task_id=task_id,
            fs_text=fs_text,
            accepted_flags=accepted_flags,
        )
        task = CursorTaskDB(
            id=task_id,
            kind=CursorTaskKind.REFINE,
            status=CursorTaskStatus.PENDING,
            related_id=doc.id,
            input_payload={"doc_id": str(doc.id), "mode": mode},
            prompt_text=prompt,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        logger.info("Refine route branched to Cursor paste-per-action task %s", task.id)
        return APIResponse(
            data={
                "mode": "cursor_task",
                "task_id": str(task.id),
                "kind": "refine",
                "prompt": task.prompt_text,
                "mcp_snippet": build_mcp_snippet(),
                "status": task.status.value.lower(),
            }
        )

    from app.pipeline.refinement_graph import run_refinement_pipeline

    result = await run_refinement_pipeline(str(doc_id), db, mode=mode)
    if result.get("errors"):
        raise HTTPException(status_code=400, detail="; ".join(result["errors"]))

    suggestions = [
        RefinementSuggestionSchema(
            issue=str(s.get("issue") or s.get("issue_type") or "issue"),
            original=str(s.get("original_text") or ""),
            refined=str(s.get("suggested_fix") or ""),
        )
        for s in result.get("suggestions", [])
    ]
    diff = [RefinementDiffLineSchema(line=str(d.get("line", ""))) for d in result.get("diff", [])]

    return APIResponse(
        data=RefinementResponse(
            original_score=float(result.get("original_score", 0.0)),
            refined_score=float(result.get("refined_score", result.get("original_score", 0.0))),
            changes_made=int(result.get("changes_made", 0)),
            refined_text=str(result.get("refined_text", result.get("original_text", ""))),
            diff=diff,
            suggestions=suggestions,
        )
    )


@router.post("/{doc_id}/refine/accept")
async def accept_refined_document(
    doc_id: uuid.UUID,
    body: AcceptRefinementRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Persist refined text as latest version. Returns immediately; the frontend
    triggers re-analysis separately via the analyze endpoint so the progress
    stepper works correctly."""
    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    refined_text = (body.refined_text or "").strip()
    if not refined_text:
        raise HTTPException(status_code=400, detail="refined_text is required")

    version = await _persist_refined_version(doc, refined_text, db)
    await db.commit()

    return APIResponse(
        data={
            "accepted": True,
            "version_id": str(version.id),
            "version_number": version.version_number,
        }
    )


@router.get("/{doc_id}/ambiguities", response_model=APIResponse[list[AmbiguityFlagSchema]])
async def list_ambiguities(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[AmbiguityFlagSchema]]:
    """List all ambiguity flags for a document."""
    result = await db.execute(
        select(AmbiguityFlagDB)
        .where(AmbiguityFlagDB.fs_id == doc_id)
        .order_by(AmbiguityFlagDB.section_index, AmbiguityFlagDB.created_at)
    )
    flags = result.scalars().all()

    schemas = [
        AmbiguityFlagSchema(
            id=f.id,
            section_index=f.section_index,
            section_heading=f.section_heading,
            flagged_text=f.flagged_text,
            reason=f.reason,
            severity=f.severity.value,
            clarification_question=f.clarification_question,
            resolved=f.resolved,
            resolution_text=f.resolution_text,
            resolved_at=f.resolved_at,
        )
        for f in flags
    ]

    return APIResponse(data=schemas)


@router.patch("/{doc_id}/ambiguities/{flag_id}")
async def resolve_ambiguity(
    doc_id: uuid.UUID,
    flag_id: uuid.UUID,
    body: AmbiguityResolveRequest | None = Body(None),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AmbiguityFlagSchema]:
    """Mark an ambiguity flag as resolved, optionally with a resolution note."""
    result = await db.execute(
        select(AmbiguityFlagDB).where(
            AmbiguityFlagDB.id == flag_id,
            AmbiguityFlagDB.fs_id == doc_id,
        )
    )
    flag = result.scalar_one_or_none()

    if not flag:
        raise HTTPException(status_code=404, detail="Ambiguity flag not found")

    resolution_text: str | None = None
    target_resolved = True
    if body is not None:
        resolution_text = (body.resolution_text or "").strip() or None
        target_resolved = bool(body.resolved)

    flag.resolved = target_resolved
    if target_resolved:
        flag.resolution_text = resolution_text
        flag.resolved_at = datetime.now(UTC)
    else:
        flag.resolved_at = None
    if target_resolved:
        await _safe_audit(
            db,
            doc_id,
            AuditEventType.AMBIGUITY_RESOLVED,
            payload={
                "flag_id": str(flag_id),
                "section_heading": flag.section_heading,
                "severity": flag.severity.value if hasattr(flag.severity, "value") else str(flag.severity),
                "has_resolution_text": bool(resolution_text),
            },
        )
    await db.commit()
    await db.refresh(flag)
    await _refresh_quality_score_internal(doc_id, db)

    return APIResponse(
        data=AmbiguityFlagSchema(
            id=flag.id,
            section_index=flag.section_index,
            section_heading=flag.section_heading,
            flagged_text=flag.flagged_text,
            reason=flag.reason,
            severity=flag.severity.value,
            clarification_question=flag.clarification_question,
            resolved=flag.resolved,
            resolution_text=flag.resolution_text,
            resolved_at=flag.resolved_at,
        ),
    )


@router.get("/{doc_id}/quality-score/refresh")
async def refresh_quality_score(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Recompute quality score from current DB state without rerunning full pipeline."""
    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    refreshed = await _refresh_quality_score_internal(doc_id, db)
    return APIResponse(data=refreshed)


# ── L4 Endpoints ───────────────────────────────────────


@router.get("/{doc_id}/contradictions", response_model=APIResponse[list[ContradictionSchema]])
async def list_contradictions(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[ContradictionSchema]]:
    """List all contradictions detected in a document."""
    result = await db.execute(
        select(ContradictionDB)
        .where(ContradictionDB.fs_id == doc_id)
        .order_by(ContradictionDB.section_a_index, ContradictionDB.created_at)
    )
    rows = result.scalars().all()

    schemas = [
        ContradictionSchema(
            id=r.id,
            section_a_index=r.section_a_index,
            section_a_heading=r.section_a_heading,
            section_b_index=r.section_b_index,
            section_b_heading=r.section_b_heading,
            description=r.description,
            severity=r.severity.value,
            suggested_resolution=r.suggested_resolution,
            resolved=r.resolved,
        )
        for r in rows
    ]

    return APIResponse(data=schemas)


@router.patch("/{doc_id}/contradictions/{contradiction_id}")
async def resolve_contradiction(
    doc_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ContradictionSchema]:
    """Mark a contradiction as resolved."""
    result = await db.execute(
        select(ContradictionDB).where(
            ContradictionDB.id == contradiction_id,
            ContradictionDB.fs_id == doc_id,
        )
    )
    row = result.scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Contradiction not found")

    row.resolved = True
    await _safe_audit(
        db,
        doc_id,
        AuditEventType.CONTRADICTION_ACCEPTED,
        payload={
            "contradiction_id": str(contradiction_id),
            "section_a_heading": row.section_a_heading,
            "section_b_heading": row.section_b_heading,
            "mode": "manual_resolve",
        },
    )
    await db.commit()
    await db.refresh(row)

    return APIResponse(
        data=ContradictionSchema(
            id=row.id,
            section_a_index=row.section_a_index,
            section_a_heading=row.section_a_heading,
            section_b_index=row.section_b_index,
            section_b_heading=row.section_b_heading,
            description=row.description,
            severity=row.severity.value,
            suggested_resolution=row.suggested_resolution,
            resolved=row.resolved,
        ),
    )


@router.get("/{doc_id}/edge-cases", response_model=APIResponse[list[EdgeCaseGapSchema]])
async def list_edge_cases(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[EdgeCaseGapSchema]]:
    """List all edge case gaps detected in a document."""
    result = await db.execute(
        select(EdgeCaseGapDB)
        .where(EdgeCaseGapDB.fs_id == doc_id)
        .order_by(EdgeCaseGapDB.section_index, EdgeCaseGapDB.created_at)
    )
    rows = result.scalars().all()

    schemas = [
        EdgeCaseGapSchema(
            id=r.id,
            section_index=r.section_index,
            section_heading=r.section_heading,
            scenario_description=r.scenario_description,
            impact=r.impact.value,
            suggested_addition=r.suggested_addition,
            resolved=r.resolved,
        )
        for r in rows
    ]

    return APIResponse(data=schemas)


@router.patch("/{doc_id}/edge-cases/{edge_case_id}")
async def resolve_edge_case(
    doc_id: uuid.UUID,
    edge_case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[EdgeCaseGapSchema]:
    """Mark an edge case gap as resolved."""
    result = await db.execute(
        select(EdgeCaseGapDB).where(
            EdgeCaseGapDB.id == edge_case_id,
            EdgeCaseGapDB.fs_id == doc_id,
        )
    )
    row = result.scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Edge case gap not found")

    row.resolved = True
    await _safe_audit(
        db,
        doc_id,
        AuditEventType.EDGE_CASE_ACCEPTED,
        payload={
            "edge_case_id": str(edge_case_id),
            "section_heading": row.section_heading,
            "mode": "manual_resolve",
        },
    )
    await db.commit()
    await db.refresh(row)

    return APIResponse(
        data=EdgeCaseGapSchema(
            id=row.id,
            section_index=row.section_index,
            section_heading=row.section_heading,
            scenario_description=row.scenario_description,
            impact=row.impact.value,
            suggested_addition=row.suggested_addition,
            resolved=row.resolved,
        ),
    )


@router.post("/{doc_id}/edge-cases/{edge_case_id}/accept")
async def accept_edge_case_suggestion(
    doc_id: uuid.UUID,
    edge_case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[EdgeCaseGapSchema]:
    """Accept an edge case suggestion: merge suggested_addition into the FS
    document text at the relevant section, mark the edge case as resolved,
    and create a new version snapshot."""
    ec_result = await db.execute(
        select(EdgeCaseGapDB).where(
            EdgeCaseGapDB.id == edge_case_id,
            EdgeCaseGapDB.fs_id == doc_id,
        )
    )
    row = ec_result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Edge case gap not found")
    if row.resolved:
        raise HTTPException(status_code=400, detail="Edge case already resolved")
    if not row.suggested_addition:
        raise HTTPException(status_code=400, detail="No suggested addition to apply")

    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    text = doc.parsed_text or doc.original_text or ""
    text = _append_to_section(text, row.section_index, row.suggested_addition.strip())

    await _persist_refined_version(doc, text, db, trigger="edge_case_accepted")
    row.resolved = True
    await _safe_audit(
        db,
        doc_id,
        AuditEventType.EDGE_CASE_ACCEPTED,
        payload={
            "edge_case_id": str(edge_case_id),
            "section_heading": row.section_heading,
            "impact": row.impact.value if hasattr(row.impact, "value") else str(row.impact),
        },
    )
    await db.commit()
    await db.refresh(row)

    return APIResponse(
        data=EdgeCaseGapSchema(
            id=row.id,
            section_index=row.section_index,
            section_heading=row.section_heading,
            scenario_description=row.scenario_description,
            impact=row.impact.value,
            suggested_addition=row.suggested_addition,
            resolved=row.resolved,
        ),
    )


def _append_to_section(text: str, section_index: int, addition: str) -> str:
    """Append text at the end of a specific section in the document."""
    from app.parsers.section_extractor import extract_sections_from_text

    sections = extract_sections_from_text(text)
    target = None
    for s in sections:
        if s.section_index == section_index:
            target = s
            break
    if target and target.content:
        last_line = target.content.rstrip().split("\n")[-1]
        pos = text.rfind(last_line)
        if pos >= 0:
            end = pos + len(last_line)
            return text[:end] + "\n" + addition + text[end:]
    return text.rstrip() + "\n\n" + addition


@router.post("/{doc_id}/contradictions/{contradiction_id}/accept")
async def accept_contradiction_suggestion(
    doc_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ContradictionSchema]:
    """Accept a contradiction resolution: merge suggested_resolution into the FS
    document at section A, mark resolved, create a version snapshot."""
    c_result = await db.execute(
        select(ContradictionDB).where(
            ContradictionDB.id == contradiction_id,
            ContradictionDB.fs_id == doc_id,
        )
    )
    row = c_result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Contradiction not found")
    if row.resolved:
        raise HTTPException(status_code=400, detail="Contradiction already resolved")
    if not row.suggested_resolution:
        raise HTTPException(status_code=400, detail="No suggested resolution to apply")

    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    text = doc.parsed_text or doc.original_text or ""
    text = _append_to_section(text, row.section_a_index, row.suggested_resolution.strip())

    await _persist_refined_version(doc, text, db, trigger="contradiction_accepted")
    row.resolved = True
    await _safe_audit(
        db,
        doc_id,
        AuditEventType.CONTRADICTION_ACCEPTED,
        payload={
            "contradiction_id": str(contradiction_id),
            "section_a_heading": row.section_a_heading,
            "section_b_heading": row.section_b_heading,
            "severity": row.severity.value if hasattr(row.severity, "value") else str(row.severity),
        },
    )
    await db.commit()
    await db.refresh(row)

    return APIResponse(
        data=ContradictionSchema(
            id=row.id,
            section_a_index=row.section_a_index,
            section_a_heading=row.section_a_heading,
            section_b_index=row.section_b_index,
            section_b_heading=row.section_b_heading,
            description=row.description,
            severity=row.severity.value,
            suggested_resolution=row.suggested_resolution,
            resolved=row.resolved,
        ),
    )


# ── Bulk Operations ────────────────────────────────────


@router.post("/{doc_id}/edge-cases/bulk-accept")
async def bulk_accept_edge_cases(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Accept all unresolved edge case suggestions, merging each into the document."""
    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    rows_result = await db.execute(
        select(EdgeCaseGapDB)
        .where(
            EdgeCaseGapDB.fs_id == doc_id,
            EdgeCaseGapDB.resolved.is_(False),
        )
        .order_by(EdgeCaseGapDB.section_index)
    )
    rows = rows_result.scalars().all()

    text = doc.parsed_text or doc.original_text or ""
    accepted = 0
    for row in rows:
        if row.suggested_addition:
            text = _append_to_section(text, row.section_index, row.suggested_addition.strip())
            accepted += 1
        row.resolved = True

    if accepted > 0:
        await _persist_refined_version(doc, text, db, trigger="edge_case_bulk_accept")
        await _safe_audit(
            db,
            doc_id,
            AuditEventType.EDGE_CASE_ACCEPTED,
            payload={"mode": "bulk_accept", "accepted": accepted},
        )
    await db.commit()
    return APIResponse(data={"accepted": accepted, "resolved": len(rows)})


@router.post("/{doc_id}/edge-cases/bulk-resolve")
async def bulk_resolve_edge_cases(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Mark all unresolved edge cases as resolved without merging text."""
    rows_result = await db.execute(
        select(EdgeCaseGapDB).where(
            EdgeCaseGapDB.fs_id == doc_id,
            EdgeCaseGapDB.resolved.is_(False),
        )
    )
    rows = rows_result.scalars().all()
    for row in rows:
        row.resolved = True
    await db.commit()
    return APIResponse(data={"resolved": len(rows)})


@router.post("/{doc_id}/contradictions/bulk-accept")
async def bulk_accept_contradictions(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Accept all unresolved contradiction resolutions, merging each into the document."""
    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    rows_result = await db.execute(
        select(ContradictionDB)
        .where(
            ContradictionDB.fs_id == doc_id,
            ContradictionDB.resolved.is_(False),
        )
        .order_by(ContradictionDB.section_a_index)
    )
    rows = rows_result.scalars().all()

    text = doc.parsed_text or doc.original_text or ""
    accepted = 0
    for row in rows:
        if row.suggested_resolution:
            text = _append_to_section(text, row.section_a_index, row.suggested_resolution.strip())
            accepted += 1
        row.resolved = True

    if accepted > 0:
        await _persist_refined_version(doc, text, db, trigger="contradiction_bulk_accept")
        await _safe_audit(
            db,
            doc_id,
            AuditEventType.CONTRADICTION_ACCEPTED,
            payload={"mode": "bulk_accept", "accepted": accepted},
        )
    await db.commit()
    return APIResponse(data={"accepted": accepted, "resolved": len(rows)})


@router.post("/{doc_id}/contradictions/bulk-resolve")
async def bulk_resolve_contradictions(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Mark all unresolved contradictions as resolved without merging text."""
    rows_result = await db.execute(
        select(ContradictionDB).where(
            ContradictionDB.fs_id == doc_id,
            ContradictionDB.resolved.is_(False),
        )
    )
    rows = rows_result.scalars().all()
    for row in rows:
        row.resolved = True
    await db.commit()
    return APIResponse(data={"resolved": len(rows)})


@router.post("/{doc_id}/ambiguities/bulk-resolve")
async def bulk_resolve_ambiguities(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Mark all unresolved ambiguities as resolved."""
    rows_result = await db.execute(
        select(AmbiguityFlagDB).where(
            AmbiguityFlagDB.fs_id == doc_id,
            AmbiguityFlagDB.resolved.is_(False),
        )
    )
    rows = rows_result.scalars().all()
    for row in rows:
        row.resolved = True
    await db.commit()
    return APIResponse(data={"resolved": len(rows)})


@router.get("/{doc_id}/quality-score", response_model=APIResponse[QualityDashboardResponse])
async def get_quality_dashboard(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[QualityDashboardResponse]:
    """Get full quality dashboard data for a document.

    Returns quality score, contradictions, edge cases, and compliance tags.
    """
    # Verify document exists
    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Load only unresolved issues for quality score (matches build endpoint behavior)
    ambiguities_result = await db.execute(
        select(AmbiguityFlagDB).where(
            AmbiguityFlagDB.fs_id == doc_id,
            AmbiguityFlagDB.resolved.is_(False),
        )
    )
    ambiguities = ambiguities_result.scalars().all()

    contradictions_result = await db.execute(
        select(ContradictionDB)
        .where(
            ContradictionDB.fs_id == doc_id,
            ContradictionDB.resolved.is_(False),
        )
        .order_by(ContradictionDB.section_a_index)
    )
    contradictions = contradictions_result.scalars().all()

    edge_cases_result = await db.execute(
        select(EdgeCaseGapDB)
        .where(
            EdgeCaseGapDB.fs_id == doc_id,
            EdgeCaseGapDB.resolved.is_(False),
        )
        .order_by(EdgeCaseGapDB.section_index)
    )
    edge_cases = edge_cases_result.scalars().all()

    compliance_result = await db.execute(
        select(ComplianceTagDB).where(ComplianceTagDB.fs_id == doc_id).order_by(ComplianceTagDB.section_index)
    )
    compliance_tags = compliance_result.scalars().all()

    # Recompute quality score from persisted data
    from app.parsers.section_extractor import extract_sections_from_text
    from app.pipeline.nodes.quality_node import compute_quality_score

    text = (doc.parsed_text or doc.original_text or "").strip()
    try:
        total_sections = len(extract_sections_from_text(text)) if text else 1
    except Exception:
        total_sections = 1
    total_sections = max(total_sections, 1)

    quality = compute_quality_score(
        total_sections=total_sections,
        ambiguities=[{"section_index": a.section_index} for a in ambiguities],
        contradictions=[{"section_a_index": c.section_a_index} for c in contradictions],
        edge_cases=[{"section_index": e.section_index} for e in edge_cases],
    )

    return APIResponse(
        data=QualityDashboardResponse(
            id=doc.id,
            filename=doc.filename,
            quality_score=QualityScoreSchema(
                completeness=quality.completeness,
                clarity=quality.clarity,
                consistency=quality.consistency,
                overall=quality.overall,
            ),
            contradictions=[
                ContradictionSchema(
                    id=c.id,
                    section_a_index=c.section_a_index,
                    section_a_heading=c.section_a_heading,
                    section_b_index=c.section_b_index,
                    section_b_heading=c.section_b_heading,
                    description=c.description,
                    severity=c.severity.value,
                    suggested_resolution=c.suggested_resolution,
                    resolved=c.resolved,
                )
                for c in contradictions
            ],
            edge_cases=[
                EdgeCaseGapSchema(
                    id=e.id,
                    section_index=e.section_index,
                    section_heading=e.section_heading,
                    scenario_description=e.scenario_description,
                    impact=e.impact.value,
                    suggested_addition=e.suggested_addition,
                    resolved=e.resolved,
                )
                for e in edge_cases
            ],
            compliance_tags=[
                ComplianceTagSchema(
                    id=ct.id,
                    section_index=ct.section_index,
                    section_heading=ct.section_heading,
                    tag=ct.tag,
                    reason=ct.reason,
                )
                for ct in compliance_tags
            ],
        ),
    )


# ── L6 Endpoints ───────────────────────────────────────


@router.get("/{doc_id}/debate-results", response_model=APIResponse[DebateResultsResponse])
async def get_debate_results(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[DebateResultsResponse]:
    """Get all adversarial debate results for a document.

    Returns debate transcripts for HIGH severity ambiguity flags
    that were challenged by the Red vs Blue agent debate (L6).
    """
    # Verify document exists
    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Load debate results
    result = await db.execute(
        select(DebateResultDB)
        .where(DebateResultDB.fs_id == doc_id)
        .order_by(DebateResultDB.section_index, DebateResultDB.created_at)
    )
    debates = result.scalars().all()

    schemas = [
        DebateResultSchema(
            id=d.id,
            section_index=d.section_index,
            section_heading=d.section_heading,
            flagged_text=d.flagged_text,
            original_reason=d.original_reason,
            verdict=d.verdict,
            red_argument=d.red_argument,
            blue_argument=d.blue_argument,
            arbiter_reasoning=d.arbiter_reasoning,
            confidence=d.confidence,
        )
        for d in debates
    ]

    confirmed = sum(1 for d in debates if d.verdict == "AMBIGUOUS")
    cleared = sum(1 for d in debates if d.verdict == "CLEAR")

    return APIResponse(
        data=DebateResultsResponse(
            results=schemas,
            total_debated=len(debates),
            confirmed_ambiguous=confirmed,
            cleared=cleared,
        ),
    )
