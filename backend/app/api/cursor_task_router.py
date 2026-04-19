"""Cursor paste-per-action task router (0.4.0).

Each endpoint under ``/api/cursor-tasks`` represents one user action
that the platform hands off to the Cursor IDE via a single paste. The
lifecycle for a task is:

* ``POST /api/cursor-tasks/{kind}`` — mints a :class:`CursorTaskDB`
  row, returns ``{mode: "cursor_task", task_id, prompt, mcp_snippet,
  status}``. The frontend shows the prompt in a modal.
* ``POST /api/cursor-tasks/{task_id}/claim`` — Cursor's MCP tool tells
  the backend it is handling this task. Status goes PENDING → CLAIMED.
* ``POST /api/cursor-tasks/{task_id}/submit`` — Cursor's MCP submit
  tool posts the agent's output. The backend persists it (FSDocument,
  ambiguities, etc.) and marks the task DONE with ``result_ref``.
* ``POST /api/cursor-tasks/{task_id}/fail`` — MCP fail tool; status
  FAILED with ``error`` set.
* ``GET /api/cursor-tasks/{task_id}`` — UI polling.
* ``POST /api/cursor-tasks/{task_id}/cancel`` — user cancels from UI.

A background TTL sweeper marks PENDING rows older than ``ttl_sec`` as
EXPIRED so the UI stops polling forever.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.audit import log_audit_event
from app.db.base import async_session_factory, get_db
from app.db.models import (
    AmbiguityFlagDB,
    AmbiguitySeverity,
    AuditEventType,
    CodeUploadDB,
    CodeUploadStatus,
    ContradictionDB,
    CursorTaskDB,
    CursorTaskKind,
    CursorTaskStatus,
    EdgeCaseGapDB,
    EffortLevel,
    FSChangeDB,
    FSDocument,
    FSDocumentStatus,
    FSTaskDB,
    FSVersion,
    ReworkEstimateDB,
    TaskImpactDB,
    TaskStatus,
    TraceabilityEntryDB,
)
from app.db.models import (
    ChangeType as ChangeTypeDB,
)
from app.db.models import (
    ImpactType as ImpactTypeDB,
)
from app.models.schemas import APIResponse
from app.orchestration.cursor_prompts import (
    build_analyze_prompt,
    build_generate_fs_prompt,
    build_impact_prompt,
    build_mcp_snippet,
    build_refine_prompt,
    build_reverse_fs_prompt,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cursor-tasks", tags=["cursor-tasks"])


# ── Schemas ──────────────────────────────────────────────────────────


class GenerateFSBody(BaseModel):
    idea: str = Field(..., min_length=3)
    industry: str = ""
    complexity: str = ""


class TaskEnvelope(BaseModel):
    mode: str = "cursor_task"
    task_id: str
    kind: str
    prompt: str
    mcp_snippet: str
    status: str


class TaskPoll(BaseModel):
    id: str
    kind: str
    status: str
    result_ref: str | None = None
    error: str | None = None
    created_at: str
    claimed_at: str | None = None
    completed_at: str | None = None


class ClaimResponse(BaseModel):
    task_id: str
    kind: str
    status: str
    input_payload: dict[str, Any]


class SubmitGenerateFSBody(BaseModel):
    fs_markdown: str = Field(..., min_length=20)


class AnalysisPayload(BaseModel):
    quality_score: dict[str, Any]
    ambiguities: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    edge_cases: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)


class SubmitAnalyzeBody(BaseModel):
    payload: AnalysisPayload


class ReverseReport(BaseModel):
    coverage: float = 0.0
    confidence: float = 0.0
    primary_language: str = ""
    modules: list[dict[str, Any]] = Field(default_factory=list)
    user_flows: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    notes: str = ""


class SubmitReverseFSBody(BaseModel):
    fs_markdown: str = Field(..., min_length=20)
    report: ReverseReport


class SubmitRefineBody(BaseModel):
    refined_markdown: str = Field(..., min_length=20)
    summary: str = Field(default="", description="Short rationale for the refinement")
    changed_sections: list[str] = Field(default_factory=list)


class ImpactChange(BaseModel):
    change_type: str = "MODIFIED"
    section_id: str = ""
    section_heading: str = ""
    section_index: int = 0
    old_text: str | None = None
    new_text: str | None = None


class ImpactTaskEntry(BaseModel):
    task_id: str
    task_title: str = ""
    impact_type: str = "UNAFFECTED"
    reason: str = ""
    change_section: str = ""


class ImpactReworkEstimate(BaseModel):
    invalidated_count: int = 0
    review_count: int = 0
    unaffected_count: int = 0
    total_rework_days: float = 0.0
    affected_sections: list[str] = Field(default_factory=list)
    changes_summary: str = ""


class ImpactPayload(BaseModel):
    fs_changes: list[ImpactChange] = Field(default_factory=list)
    task_impacts: list[ImpactTaskEntry] = Field(default_factory=list)
    rework_estimate: ImpactReworkEstimate = Field(default_factory=ImpactReworkEstimate)


class SubmitImpactBody(BaseModel):
    payload: ImpactPayload


class FailBody(BaseModel):
    error: str = Field(..., min_length=1)


def _change_type(value: Any, fallback: ChangeTypeDB = ChangeTypeDB.MODIFIED) -> ChangeTypeDB:
    try:
        return ChangeTypeDB(str(value).upper())
    except Exception:  # noqa: BLE001
        return fallback


def _impact_type(value: Any, fallback: ImpactTypeDB = ImpactTypeDB.UNAFFECTED) -> ImpactTypeDB:
    try:
        return ImpactTypeDB(str(value).upper())
    except Exception:  # noqa: BLE001
        return fallback


# ── Helpers ──────────────────────────────────────────────────────────


def _envelope(task: CursorTaskDB) -> TaskEnvelope:
    return TaskEnvelope(
        task_id=str(task.id),
        kind=task.kind.value.lower(),
        prompt=task.prompt_text,
        mcp_snippet=build_mcp_snippet(),
        status=task.status.value.lower(),
    )


def _poll(task: CursorTaskDB) -> TaskPoll:
    return TaskPoll(
        id=str(task.id),
        kind=task.kind.value.lower(),
        status=task.status.value.lower(),
        result_ref=str(task.result_ref) if task.result_ref else None,
        error=task.error,
        created_at=task.created_at.isoformat() if task.created_at else "",
        claimed_at=task.claimed_at.isoformat() if task.claimed_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


def _severity(value: Any, fallback: AmbiguitySeverity = AmbiguitySeverity.MEDIUM) -> AmbiguitySeverity:
    try:
        return AmbiguitySeverity(str(value).upper())
    except Exception:  # noqa: BLE001
        return fallback


def _effort(value: Any, fallback: EffortLevel = EffortLevel.MEDIUM) -> EffortLevel:
    try:
        return EffortLevel(str(value).upper())
    except Exception:  # noqa: BLE001
        return fallback


async def _load_task(db: AsyncSession, task_id: uuid.UUID) -> CursorTaskDB:
    row = await db.execute(select(CursorTaskDB).where(CursorTaskDB.id == task_id))
    task = row.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Cursor task {task_id} not found")
    return task


# ── Create endpoints ─────────────────────────────────────────────────


@router.post("/generate-fs", response_model=APIResponse[TaskEnvelope])
async def create_generate_fs_task(
    body: GenerateFSBody,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskEnvelope]:
    """Mint a Cursor task for Generate FS and return its prompt."""
    task_id = uuid.uuid4()
    prompt = build_generate_fs_prompt(
        task_id=task_id,
        idea=body.idea,
        industry=body.industry,
        complexity=body.complexity,
    )
    task = CursorTaskDB(
        id=task_id,
        kind=CursorTaskKind.GENERATE_FS,
        status=CursorTaskStatus.PENDING,
        input_payload={
            "idea": body.idea,
            "industry": body.industry,
            "complexity": body.complexity,
        },
        prompt_text=prompt,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    logger.info("Created Cursor task generate_fs id=%s", task.id)
    return APIResponse(data=_envelope(task))


@router.post("/analyze/{doc_id}", response_model=APIResponse[TaskEnvelope])
async def create_analyze_task(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskEnvelope]:
    """Mint a Cursor task for Analyze on an existing FS document."""
    doc_row = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_row.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail=f"FS document {doc_id} not found")
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
    logger.info("Created Cursor task analyze id=%s doc=%s", task.id, doc.id)
    return APIResponse(data=_envelope(task))


@router.post("/reverse-fs/{upload_id}", response_model=APIResponse[TaskEnvelope])
async def create_reverse_fs_task(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskEnvelope]:
    """Mint a Cursor task for Reverse FS on a parsed CodeUpload."""
    up_row = await db.execute(select(CodeUploadDB).where(CodeUploadDB.id == upload_id))
    upload = up_row.scalar_one_or_none()
    if upload is None:
        raise HTTPException(status_code=404, detail=f"Code upload {upload_id} not found")
    if upload.status not in (CodeUploadStatus.PARSED, CodeUploadStatus.GENERATED):
        raise HTTPException(
            status_code=400,
            detail=(f"Code upload is {upload.status}; wait for PARSED before reverse FS generation."),
        )

    manifest = {
        "primary_language": upload.primary_language,
        "total_files": upload.total_files,
        "total_lines": upload.total_lines,
        "languages": upload.languages or {},
    }
    # Pick a few representative file excerpts from the snapshot.
    file_excerpts: list[dict[str, Any]] = []
    snap = upload.snapshot_data or {}
    for entry in (snap.get("files") or [])[:20]:
        file_excerpts.append(
            {
                "path": entry.get("path", ""),
                "language": entry.get("language", ""),
                "excerpt": (entry.get("summary") or entry.get("content") or "")[:1200],
            }
        )

    task_id = uuid.uuid4()
    prompt = build_reverse_fs_prompt(
        task_id=task_id,
        code_manifest=manifest,
        file_excerpts=file_excerpts,
    )
    task = CursorTaskDB(
        id=task_id,
        kind=CursorTaskKind.REVERSE_FS,
        status=CursorTaskStatus.PENDING,
        related_id=upload.id,
        input_payload={
            "upload_id": str(upload.id),
            "manifest": manifest,
        },
        prompt_text=prompt,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    logger.info("Created Cursor task reverse_fs id=%s upload=%s", task.id, upload.id)
    return APIResponse(data=_envelope(task))


@router.post("/refine/{doc_id}", response_model=APIResponse[TaskEnvelope])
async def create_refine_task(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskEnvelope]:
    """Mint a Cursor task for Refine on an analyzed FS document."""
    doc_row = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_row.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail=f"FS document {doc_id} not found")
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
        input_payload={"doc_id": str(doc.id)},
        prompt_text=prompt,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    logger.info("Created Cursor task refine id=%s doc=%s", task.id, doc.id)
    return APIResponse(data=_envelope(task))


@router.post("/impact/{version_id}", response_model=APIResponse[TaskEnvelope])
async def create_impact_task(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskEnvelope]:
    """Mint a Cursor task for Impact analysis on an uploaded FS version.

    The caller must pass the *new* ``FSVersion.id``; the document's
    current ``parsed_text`` is treated as the "old" FS, and the version
    row's ``parsed_text`` is the "new" FS.
    """
    ver_row = await db.execute(select(FSVersion).where(FSVersion.id == version_id))
    version = ver_row.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail=f"FS version {version_id} not found")
    doc_row = await db.execute(select(FSDocument).where(FSDocument.id == version.fs_id))
    doc = doc_row.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Parent FS document not found")

    old_text = doc.parsed_text or doc.original_text or ""
    new_text = version.parsed_text or ""
    if not new_text.strip():
        raise HTTPException(
            status_code=400,
            detail="New FS version has no parsed text yet; parse it first.",
        )

    task_id = uuid.uuid4()
    prompt = build_impact_prompt(
        task_id=task_id,
        old_fs_text=old_text,
        new_fs_text=new_text,
    )
    task = CursorTaskDB(
        id=task_id,
        kind=CursorTaskKind.IMPACT,
        status=CursorTaskStatus.PENDING,
        related_id=doc.id,
        input_payload={
            "doc_id": str(doc.id),
            "version_id": str(version.id),
            "version_number": version.version_number,
        },
        prompt_text=prompt,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    logger.info(
        "Created Cursor task impact id=%s version=%s doc=%s",
        task.id,
        version.id,
        doc.id,
    )
    return APIResponse(data=_envelope(task))


# ── Poll / cancel ────────────────────────────────────────────────────


@router.get("/{task_id}", response_model=APIResponse[TaskPoll])
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskPoll]:
    task = await _load_task(db, task_id)
    return APIResponse(data=_poll(task))


@router.post("/{task_id}/cancel", response_model=APIResponse[TaskPoll])
async def cancel_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskPoll]:
    task = await _load_task(db, task_id)
    if task.status in (CursorTaskStatus.DONE, CursorTaskStatus.FAILED, CursorTaskStatus.EXPIRED):
        return APIResponse(data=_poll(task))
    task.status = CursorTaskStatus.EXPIRED
    task.error = task.error or "Cancelled by user"
    task.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(task)
    return APIResponse(data=_poll(task))


# ── MCP-facing lifecycle ─────────────────────────────────────────────


@router.post("/{task_id}/claim", response_model=APIResponse[ClaimResponse])
async def claim_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ClaimResponse]:
    task = await _load_task(db, task_id)
    if task.status not in (CursorTaskStatus.PENDING, CursorTaskStatus.CLAIMED):
        raise HTTPException(
            status_code=409,
            detail=f"Task is {task.status.value}; cannot claim.",
        )
    if task.status == CursorTaskStatus.PENDING:
        task.status = CursorTaskStatus.CLAIMED
        task.claimed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(task)
    return APIResponse(
        data=ClaimResponse(
            task_id=str(task.id),
            kind=task.kind.value.lower(),
            status=task.status.value.lower(),
            input_payload=task.input_payload or {},
        )
    )


@router.post("/{task_id}/submit/generate-fs", response_model=APIResponse[TaskPoll])
async def submit_generate_fs(
    task_id: uuid.UUID,
    body: SubmitGenerateFSBody,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskPoll]:
    task = await _load_task(db, task_id)
    if task.kind != CursorTaskKind.GENERATE_FS:
        raise HTTPException(status_code=400, detail=f"Task {task_id} is not generate_fs")
    if task.status in (CursorTaskStatus.DONE, CursorTaskStatus.FAILED, CursorTaskStatus.EXPIRED):
        raise HTTPException(status_code=409, detail=f"Task already {task.status.value}")

    fs_doc = FSDocument(
        id=uuid.uuid4(),
        filename=f"cursor-generate-{task.id}.md",
        original_text=body.fs_markdown,
        parsed_text=body.fs_markdown,
        status=FSDocumentStatus.PARSED,
        file_size=len(body.fs_markdown.encode("utf-8")),
        content_type="text/markdown",
    )
    db.add(fs_doc)

    task.status = CursorTaskStatus.DONE
    task.output_payload = {"fs_markdown_len": len(body.fs_markdown)}
    task.result_ref = fs_doc.id
    task.completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(task)
    logger.info("Cursor task %s generate_fs DONE -> FSDocument %s", task.id, fs_doc.id)
    return APIResponse(data=_poll(task))


@router.post("/{task_id}/submit/analyze", response_model=APIResponse[TaskPoll])
async def submit_analyze(
    task_id: uuid.UUID,
    body: SubmitAnalyzeBody,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskPoll]:
    task = await _load_task(db, task_id)
    if task.kind != CursorTaskKind.ANALYZE:
        raise HTTPException(status_code=400, detail=f"Task {task_id} is not analyze")
    if task.status in (CursorTaskStatus.DONE, CursorTaskStatus.FAILED, CursorTaskStatus.EXPIRED):
        raise HTTPException(status_code=409, detail=f"Task already {task.status.value}")
    if task.related_id is None:
        raise HTTPException(status_code=500, detail="Analyze task missing related doc_id")

    payload = body.payload

    for amb in payload.ambiguities:
        db.add(
            AmbiguityFlagDB(
                fs_id=task.related_id,
                section_index=int(amb.get("section_index", 0)),
                section_heading=str(amb.get("section_heading", "")),
                flagged_text=str(amb.get("flagged_text", "")),
                reason=str(amb.get("reason", "")),
                severity=_severity(amb.get("severity")),
                clarification_question=str(amb.get("clarification_question", "")),
            )
        )

    for ctr in payload.contradictions:
        db.add(
            ContradictionDB(
                fs_id=task.related_id,
                section_a_index=int(ctr.get("section_a_index", 0)),
                section_a_heading=str(ctr.get("section_a_heading", "")),
                section_b_index=int(ctr.get("section_b_index", 0)),
                section_b_heading=str(ctr.get("section_b_heading", "")),
                description=str(ctr.get("description", "")),
                severity=_severity(ctr.get("severity")),
                suggested_resolution=str(ctr.get("suggested_resolution", "")),
            )
        )

    for eg in payload.edge_cases:
        db.add(
            EdgeCaseGapDB(
                fs_id=task.related_id,
                section_index=int(eg.get("section_index", 0)),
                section_heading=str(eg.get("section_heading", "")),
                scenario_description=str(eg.get("scenario_description", "")),
                impact=_severity(eg.get("impact")),
                suggested_addition=str(eg.get("suggested_addition", "")),
            )
        )

    for idx, tk in enumerate(payload.tasks):
        tid = str(tk.get("task_id") or uuid.uuid4())
        db.add(
            FSTaskDB(
                fs_id=task.related_id,
                task_id=tid,
                title=str(tk.get("title", ""))[:512],
                description=str(tk.get("description", "")),
                section_index=int(tk.get("section_index", 0)),
                section_heading=str(tk.get("section_heading", "")),
                depends_on=list(tk.get("depends_on", [])),
                acceptance_criteria=list(tk.get("acceptance_criteria", [])),
                effort=_effort(tk.get("effort")),
                tags=list(tk.get("tags", [])),
                status=TaskStatus.PENDING,
                order=idx,
                can_parallel=bool(tk.get("can_parallel", False)),
            )
        )
        db.add(
            TraceabilityEntryDB(
                fs_id=task.related_id,
                task_id=tid,
                task_title=str(tk.get("title", ""))[:512],
                section_index=int(tk.get("section_index", 0)),
                section_heading=str(tk.get("section_heading", "")),
            )
        )

    # Mark the source document as COMPLETE so the Build CTA appears on
    # the detail page. Mirrors ``analysis_router.analyze_document`` which
    # sets ``doc.status = FSDocumentStatus.COMPLETE`` once the synchronous
    # pipeline succeeds. Without this the Cursor LLM path would always
    # leave the doc stuck in PARSED even though every analysis artefact
    # is now persisted.
    doc_row = await db.execute(select(FSDocument).where(FSDocument.id == task.related_id))
    doc = doc_row.scalar_one_or_none()
    if doc is not None:
        doc.status = FSDocumentStatus.COMPLETE
        doc.analysis_stale = False

    task.status = CursorTaskStatus.DONE
    task.output_payload = payload.model_dump()
    task.result_ref = task.related_id
    task.completed_at = datetime.now(UTC)

    # Lifecycle telemetry: this is the Cursor paste-per-action analyze
    # path. Without these audit rows the activity log + per-doc Lifecycle
    # timeline only ever show "Uploaded" for any doc analyzed via Cursor.
    try:
        await log_audit_event(
            db,
            task.related_id,
            AuditEventType.ANALYZED,
            user_id="cursor",
            payload={
                "ambiguities": len(payload.ambiguities),
                "contradictions": len(payload.contradictions),
                "edge_cases": len(payload.edge_cases),
                "tasks": len(payload.tasks),
                "source": "cursor_paste",
            },
        )
        if payload.tasks:
            await log_audit_event(
                db,
                task.related_id,
                AuditEventType.TASKS_GENERATED,
                user_id="cursor",
                payload={"tasks_count": len(payload.tasks), "source": "cursor_paste"},
            )
    except Exception:
        logger.exception("audit emit failed for cursor submit_analyze task=%s", task.id)

    await db.commit()
    await db.refresh(task)
    logger.info(
        "Cursor task %s analyze DONE (ambiguities=%d contradictions=%d edge_cases=%d tasks=%d)",
        task.id,
        len(payload.ambiguities),
        len(payload.contradictions),
        len(payload.edge_cases),
        len(payload.tasks),
    )
    return APIResponse(data=_poll(task))


@router.post("/{task_id}/submit/reverse-fs", response_model=APIResponse[TaskPoll])
async def submit_reverse_fs(
    task_id: uuid.UUID,
    body: SubmitReverseFSBody,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskPoll]:
    task = await _load_task(db, task_id)
    if task.kind != CursorTaskKind.REVERSE_FS:
        raise HTTPException(status_code=400, detail=f"Task {task_id} is not reverse_fs")
    if task.status in (CursorTaskStatus.DONE, CursorTaskStatus.FAILED, CursorTaskStatus.EXPIRED):
        raise HTTPException(status_code=409, detail=f"Task already {task.status.value}")
    if task.related_id is None:
        raise HTTPException(status_code=500, detail="Reverse task missing related upload_id")

    up_row = await db.execute(select(CodeUploadDB).where(CodeUploadDB.id == task.related_id))
    upload = up_row.scalar_one_or_none()
    if upload is None:
        raise HTTPException(status_code=404, detail="CodeUpload for this task disappeared")

    fs_doc = FSDocument(
        id=uuid.uuid4(),
        filename=f"cursor-reverse-{task.id}.md",
        original_text=body.fs_markdown,
        parsed_text=body.fs_markdown,
        status=FSDocumentStatus.PARSED,
        file_size=len(body.fs_markdown.encode("utf-8")),
        content_type="text/markdown",
    )
    db.add(fs_doc)

    upload.generated_fs_id = fs_doc.id
    upload.generated_fs_text = body.fs_markdown
    upload.coverage = body.report.coverage
    upload.confidence = body.report.confidence
    upload.report_data = body.report.model_dump()
    upload.status = CodeUploadStatus.GENERATED

    task.status = CursorTaskStatus.DONE
    task.output_payload = {
        "fs_markdown_len": len(body.fs_markdown),
        "report": body.report.model_dump(),
    }
    task.result_ref = fs_doc.id
    task.completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(task)
    logger.info(
        "Cursor task %s reverse_fs DONE -> FSDocument %s (upload=%s)",
        task.id,
        fs_doc.id,
        upload.id,
    )
    return APIResponse(data=_poll(task))


@router.post("/{task_id}/submit/refine", response_model=APIResponse[TaskPoll])
async def submit_refine(
    task_id: uuid.UUID,
    body: SubmitRefineBody,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskPoll]:
    """Persist a Cursor-generated refined FS as a new FSDocument."""
    task = await _load_task(db, task_id)
    if task.kind != CursorTaskKind.REFINE:
        raise HTTPException(status_code=400, detail=f"Task {task_id} is not refine")
    if task.status in (CursorTaskStatus.DONE, CursorTaskStatus.FAILED, CursorTaskStatus.EXPIRED):
        raise HTTPException(status_code=409, detail=f"Task already {task.status.value}")
    if task.related_id is None:
        raise HTTPException(status_code=500, detail="Refine task missing related doc_id")

    refined_doc = FSDocument(
        id=uuid.uuid4(),
        filename=f"cursor-refined-{task.id}.md",
        original_text=body.refined_markdown,
        parsed_text=body.refined_markdown,
        status=FSDocumentStatus.PARSED,
        file_size=len(body.refined_markdown.encode("utf-8")),
        content_type="text/markdown",
    )
    db.add(refined_doc)

    task.status = CursorTaskStatus.DONE
    task.output_payload = {
        "refined_len": len(body.refined_markdown),
        "summary": body.summary,
        "changed_sections": list(body.changed_sections),
    }
    task.result_ref = refined_doc.id
    task.completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(task)
    logger.info(
        "Cursor task %s refine DONE (source=%s -> refined=%s)",
        task.id,
        task.related_id,
        refined_doc.id,
    )
    return APIResponse(data=_poll(task))


@router.post("/{task_id}/submit/impact", response_model=APIResponse[TaskPoll])
async def submit_impact(
    task_id: uuid.UUID,
    body: SubmitImpactBody,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskPoll]:
    """Persist a Cursor-generated impact analysis against its FSVersion."""
    task = await _load_task(db, task_id)
    if task.kind != CursorTaskKind.IMPACT:
        raise HTTPException(status_code=400, detail=f"Task {task_id} is not impact")
    if task.status in (CursorTaskStatus.DONE, CursorTaskStatus.FAILED, CursorTaskStatus.EXPIRED):
        raise HTTPException(status_code=409, detail=f"Task already {task.status.value}")
    if task.related_id is None:
        raise HTTPException(status_code=500, detail="Impact task missing related doc_id")

    payload_dict = task.input_payload or {}
    version_id_str = payload_dict.get("version_id")
    if not version_id_str:
        raise HTTPException(status_code=500, detail="Impact task missing version_id")
    try:
        version_id = uuid.UUID(str(version_id_str))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid version_id: {exc}") from exc

    ver_row = await db.execute(select(FSVersion).where(FSVersion.id == version_id))
    version = ver_row.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail=f"FS version {version_id} disappeared")

    payload = body.payload
    for ch in payload.fs_changes:
        db.add(
            FSChangeDB(
                fs_id=task.related_id,
                version_id=version.id,
                change_type=_change_type(ch.change_type),
                section_id=ch.section_id[:256],
                section_heading=ch.section_heading[:512],
                section_index=int(ch.section_index),
                old_text=ch.old_text,
                new_text=ch.new_text,
            )
        )
    for ti in payload.task_impacts:
        db.add(
            TaskImpactDB(
                fs_id=task.related_id,
                version_id=version.id,
                task_id=ti.task_id[:64],
                task_title=ti.task_title[:512],
                impact_type=_impact_type(ti.impact_type),
                reason=ti.reason,
                change_section=ti.change_section[:512],
            )
        )
    est = payload.rework_estimate
    db.add(
        ReworkEstimateDB(
            fs_id=task.related_id,
            version_id=version.id,
            invalidated_count=int(est.invalidated_count),
            review_count=int(est.review_count),
            unaffected_count=int(est.unaffected_count),
            total_rework_days=float(est.total_rework_days),
            affected_sections=list(est.affected_sections),
            changes_summary=est.changes_summary,
        )
    )

    task.status = CursorTaskStatus.DONE
    task.output_payload = payload.model_dump()
    task.result_ref = version.id
    task.completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(task)
    logger.info(
        "Cursor task %s impact DONE (version=%s changes=%d impacts=%d)",
        task.id,
        version.id,
        len(payload.fs_changes),
        len(payload.task_impacts),
    )
    return APIResponse(data=_poll(task))


@router.post("/{task_id}/fail", response_model=APIResponse[TaskPoll])
async def fail_task(
    task_id: uuid.UUID,
    body: FailBody,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskPoll]:
    task = await _load_task(db, task_id)
    if task.status in (CursorTaskStatus.DONE, CursorTaskStatus.EXPIRED):
        raise HTTPException(status_code=409, detail=f"Task already {task.status.value}")
    task.status = CursorTaskStatus.FAILED
    task.error = body.error.strip()
    task.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(task)
    logger.info("Cursor task %s FAILED: %s", task.id, task.error)
    return APIResponse(data=_poll(task))


# ── TTL sweeper ──────────────────────────────────────────────────────


_SWEEPER_INTERVAL_SEC = 60.0
_sweeper_task: asyncio.Task | None = None


async def _sweep_once() -> int:
    now = datetime.now(UTC)
    expired_count = 0
    async with async_session_factory() as session:
        result = await session.execute(
            select(CursorTaskDB).where(CursorTaskDB.status.in_([CursorTaskStatus.PENDING, CursorTaskStatus.CLAIMED]))
        )
        for task in result.scalars().all():
            ttl = int(task.ttl_sec or 900)
            if task.created_at is None:
                continue
            created = task.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if now - created > timedelta(seconds=ttl):
                task.status = CursorTaskStatus.EXPIRED
                task.error = task.error or "Task expired without a Cursor submission"
                task.completed_at = now
                expired_count += 1
        if expired_count:
            await session.commit()
    return expired_count


async def _sweeper_loop() -> None:
    while True:
        try:
            n = await _sweep_once()
            if n:
                logger.info("Cursor task sweeper expired %d row(s)", n)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Cursor task sweeper error: %s", exc)
        await asyncio.sleep(_SWEEPER_INTERVAL_SEC)


def start_sweeper() -> None:
    global _sweeper_task
    if _sweeper_task is not None and not _sweeper_task.done():
        return
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    _sweeper_task = loop.create_task(_sweeper_loop())
