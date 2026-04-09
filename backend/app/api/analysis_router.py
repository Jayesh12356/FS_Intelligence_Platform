"""Analysis API — trigger analysis, list/resolve ambiguities, L4+L5 endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
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
    TestCaseDB,
    TestType,
    TraceabilityEntryDB,
)
from app.models.schemas import (
    AmbiguityFlagSchema,
    AnalysisResponse,
    APIResponse,
    ComplianceTagSchema,
    ContradictionSchema,
    DebateResultSchema,
    DebateResultsResponse,
    EdgeCaseGapSchema,
    QualityDashboardResponse,
    QualityScoreSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fs", tags=["analysis"])


@router.post("/{doc_id}/analyze", response_model=APIResponse[AnalysisResponse])
async def analyze_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AnalysisResponse]:
    """Trigger LangGraph analysis pipeline on a parsed document.

    Pipeline (L4): parse_node → ambiguity_node → contradiction_node
                   → edge_case_node → quality_node → END
    Persists all results to PostgreSQL.
    Updates document status: PARSED → ANALYZING → COMPLETE (or ERROR).
    """
    from app.pipeline.graph import run_analysis_pipeline

    # Load document
    result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status not in (FSDocumentStatus.PARSED, FSDocumentStatus.COMPLETE, FSDocumentStatus.ANALYZING):
        raise HTTPException(
            status_code=400,
            detail=f"Document must be parsed before analysis. Current status: {doc.status.value}",
        )

    # Update status to ANALYZING
    doc.status = FSDocumentStatus.ANALYZING
    await db.commit()

    # Load parsed sections from the parse result
    from app.parsers.router import parse_document as do_parse
    parsed = await do_parse(str(doc.id), db)

    sections = [
        {
            "heading": s.heading,
            "content": s.content,
            "section_index": s.section_index,
        }
        for s in parsed.sections
    ]

    # Run the LangGraph pipeline
    try:
        pipeline_result = await run_analysis_pipeline(str(doc.id), sections)
    except Exception as exc:
        doc.status = FSDocumentStatus.ERROR
        await db.commit()
        logger.error("Analysis pipeline failed for %s: %s", doc_id, exc)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

    # ── Delete existing results for this document (re-analysis) ──
    for model_class in [AmbiguityFlagDB, ContradictionDB, EdgeCaseGapDB, ComplianceTagDB, FSTaskDB, TraceabilityEntryDB, DebateResultDB, DuplicateFlagDB, TestCaseDB]:
        existing = await db.execute(
            select(model_class).where(model_class.fs_id == doc_id)
        )
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
        db, doc_id, AuditEventType.ANALYZED,
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
            db, doc_id, AuditEventType.TASKS_GENERATED,
            payload={"tasks_count": len(db_tasks)},
        )

    await db.commit()

    # Refresh all to get IDs
    for item in db_flags + db_contradictions + db_edge_cases + db_compliance + db_tasks + db_traces + db_debates + db_duplicates + db_testcases:
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
    quality_schema = QualityScoreSchema(
        completeness=quality_dict.get("completeness", 0.0),
        clarity=quality_dict.get("clarity", 0.0),
        consistency=quality_dict.get("consistency", 0.0),
        overall=quality_dict.get("overall", 0.0),
    ) if quality_dict else None

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
        )
        for f in flags
    ]

    return APIResponse(data=schemas)


@router.patch("/{doc_id}/ambiguities/{flag_id}")
async def resolve_ambiguity(
    doc_id: uuid.UUID,
    flag_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AmbiguityFlagSchema]:
    """Mark an ambiguity flag as resolved."""
    result = await db.execute(
        select(AmbiguityFlagDB).where(
            AmbiguityFlagDB.id == flag_id,
            AmbiguityFlagDB.fs_id == doc_id,
        )
    )
    flag = result.scalar_one_or_none()

    if not flag:
        raise HTTPException(status_code=404, detail="Ambiguity flag not found")

    flag.resolved = True
    await db.commit()
    await db.refresh(flag)

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
        ),
    )


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


@router.get("/{doc_id}/quality-score", response_model=APIResponse[QualityDashboardResponse])
async def get_quality_dashboard(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[QualityDashboardResponse]:
    """Get full quality dashboard data for a document.

    Returns quality score, contradictions, edge cases, and compliance tags.
    """
    # Verify document exists
    doc_result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Load all analysis results
    ambiguities_result = await db.execute(
        select(AmbiguityFlagDB).where(AmbiguityFlagDB.fs_id == doc_id)
    )
    ambiguities = ambiguities_result.scalars().all()

    contradictions_result = await db.execute(
        select(ContradictionDB)
        .where(ContradictionDB.fs_id == doc_id)
        .order_by(ContradictionDB.section_a_index)
    )
    contradictions = contradictions_result.scalars().all()

    edge_cases_result = await db.execute(
        select(EdgeCaseGapDB)
        .where(EdgeCaseGapDB.fs_id == doc_id)
        .order_by(EdgeCaseGapDB.section_index)
    )
    edge_cases = edge_cases_result.scalars().all()

    compliance_result = await db.execute(
        select(ComplianceTagDB)
        .where(ComplianceTagDB.fs_id == doc_id)
        .order_by(ComplianceTagDB.section_index)
    )
    compliance_tags = compliance_result.scalars().all()

    # Recompute quality score from persisted data
    from app.pipeline.nodes.quality_node import compute_quality_score

    # Get section count from analysis result or parse
    from app.parsers.router import parse_document as do_parse
    try:
        parsed = await do_parse(str(doc.id), db)
        total_sections = len(parsed.sections)
    except Exception:
        # Fallback: estimate from ambiguity section indices
        all_indices = set()
        for a in ambiguities:
            all_indices.add(a.section_index)
        for e in edge_cases:
            all_indices.add(e.section_index)
        total_sections = max(len(all_indices), 1)

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
    doc_result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
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
