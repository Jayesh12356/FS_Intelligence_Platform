"""Impact Analysis API — version management, diff views, impact analysis, rework estimates (L7)."""

import hashlib
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_db
from app.db.models import (
    AuditEventType,
    ChangeType as ChangeTypeDB,
    FSChangeDB,
    FSDocument,
    FSDocumentStatus,
    FSTaskDB,
    FSVersion,
    ImpactType as ImpactTypeDB,
    ReworkEstimateDB,
    TaskImpactDB,
)
from app.db.audit import log_audit_event
from app.models.schemas import (
    APIResponse,
    DiffResponse,
    FSChangeSchema,
    FSVersionListResponse,
    FSVersionSchema,
    ImpactAnalysisResponse,
    ReworkEstimateSchema,
    ReworkResponse,
    TaskImpactSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fs", tags=["impact"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


# ── Version Upload ──────────────────────────────────────


@router.post("/{doc_id}/version", response_model=APIResponse[FSVersionSchema])
async def upload_version(
    doc_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSVersionSchema]:
    """Upload a new version of an existing FS document.

    Stores as new FSVersion row, runs parser on new version,
    then triggers the impact analysis pipeline (diff → impact → rework).
    """
    from app.parsers.router import parse_document as do_parse
    from app.pipeline.graph import run_impact_pipeline

    # Validate document exists
    result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status not in (FSDocumentStatus.PARSED, FSDocumentStatus.COMPLETE):
        raise HTTPException(
            status_code=400,
            detail=f"Document must be parsed/analyzed before uploading a new version. Current status: {doc.status.value}",
        )

    # Validate file extension
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{ext}' not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS)}",
            )

    # Determine version number
    versions_result = await db.execute(
        select(FSVersion)
        .where(FSVersion.fs_id == doc_id)
        .order_by(FSVersion.version_number.desc())
    )
    existing_versions = versions_result.scalars().all()
    new_version_number = (existing_versions[0].version_number + 1) if existing_versions else 2

    # If this is the first version upload, create a v1 record from the current document state
    if not existing_versions:
        v1 = FSVersion(
            fs_id=doc_id,
            version_number=1,
            parsed_text=doc.parsed_text,
            file_path=doc.file_path,
            file_size=doc.file_size,
            content_type=doc.content_type,
            content_hash=hashlib.sha256((doc.parsed_text or "").encode()).hexdigest()[:32],
        )
        db.add(v1)
        await db.flush()

    # Save the new version file
    settings = get_settings()
    ext = Path(file.filename).suffix.lower() if file.filename else ".bin"
    save_dir = settings.upload_path / str(doc_id) / f"v{new_version_number}"
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"original{ext}"

    file_size = 0
    with open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 64):
            file_size += len(chunk)
            if file_size > settings.max_upload_bytes:
                f.close()
                shutil.rmtree(save_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB}MB",
                )
            f.write(chunk)

    # Update the main document's file_path to the new version
    old_file_path = doc.file_path
    doc.file_path = str(file_path)
    doc.file_size = file_size
    doc.content_type = file.content_type
    await db.flush()

    # Parse the new version
    try:
        parsed_new = await do_parse(str(doc_id), db)
    except Exception as exc:
        logger.error("Failed to parse new version for %s: %s", doc_id, exc)
        # Restore old file path on failure
        doc.file_path = old_file_path
        await db.flush()
        raise HTTPException(status_code=500, detail=f"Failed to parse new version: {exc}")

    new_parsed_text = parsed_new.raw_text
    content_hash = hashlib.sha256(new_parsed_text.encode()).hexdigest()[:32]

    # Create the version record
    version = FSVersion(
        fs_id=doc_id,
        version_number=new_version_number,
        parsed_text=new_parsed_text,
        file_path=str(file_path),
        file_size=file_size,
        content_type=file.content_type,
        content_hash=content_hash,
    )
    db.add(version)
    await db.flush()
    await db.refresh(version)

    # Get old sections (from previous version or original document)
    old_parsed_text = doc.original_text or ""
    if existing_versions:
        # Use the latest existing version's parsed text
        latest_version = existing_versions[0]
        old_parsed_text = latest_version.parsed_text or doc.original_text or ""

    # Parse old sections from text (re-parse old file)
    # We need to get the structured sections, not just text
    # Use the stored parsed_text to re-chunk
    from app.parsers.chunker import chunk_text_into_sections
    old_sections = chunk_text_into_sections(old_parsed_text)
    new_sections = [
        {
            "heading": s.heading,
            "content": s.content,
            "section_index": s.section_index,
        }
        for s in parsed_new.sections
    ]

    # Load existing tasks for impact analysis
    tasks_result = await db.execute(
        select(FSTaskDB)
        .where(FSTaskDB.fs_id == doc_id)
        .order_by(FSTaskDB.order)
    )
    existing_tasks = tasks_result.scalars().all()
    task_dicts = [
        {
            "task_id": t.task_id,
            "title": t.title,
            "description": t.description,
            "section_index": t.section_index,
            "section_heading": t.section_heading,
            "effort": t.effort.value if t.effort else "MEDIUM",
            "tags": t.tags or [],
        }
        for t in existing_tasks
    ]

    # Run impact pipeline
    try:
        impact_result = await run_impact_pipeline(
            fs_id=str(doc_id),
            version_id=str(version.id),
            old_sections=old_sections,
            new_sections=new_sections,
            tasks=task_dicts,
        )
    except Exception as exc:
        logger.error("Impact pipeline failed for %s v%d: %s", doc_id, new_version_number, exc)
        # Non-fatal — version is still saved
        impact_result = {"fs_changes": [], "task_impacts": [], "rework_estimate": {}, "errors": [str(exc)]}

    # Persist impact results
    # Delete existing impact data for this version
    for model_class in [FSChangeDB, TaskImpactDB, ReworkEstimateDB]:
        existing = await db.execute(
            select(model_class).where(model_class.version_id == version.id)
        )
        for row in existing.scalars().all():
            await db.delete(row)

    # Persist changes
    changes = impact_result.get("fs_changes", [])
    for c in changes:
        change_type_str = c.get("change_type", "MODIFIED")
        try:
            change_type = ChangeTypeDB(change_type_str)
        except ValueError:
            change_type = ChangeTypeDB.MODIFIED

        change_db = FSChangeDB(
            fs_id=doc_id,
            version_id=version.id,
            change_type=change_type,
            section_id=c.get("section_id", ""),
            section_heading=c.get("section_heading", ""),
            section_index=c.get("section_index", 0),
            old_text=c.get("old_text"),
            new_text=c.get("new_text"),
        )
        db.add(change_db)

    # Generate diff summary
    from app.pipeline.nodes.version_node import generate_diff_summary, FSChange as FSChangeModel
    change_models = []
    for c in changes:
        try:
            change_models.append(FSChangeModel(**c))
        except Exception:
            pass
    version.diff_summary = generate_diff_summary(change_models)

    # Persist task impacts
    task_impacts = impact_result.get("task_impacts", [])
    for ti in task_impacts:
        impact_type_str = ti.get("impact_type", "UNAFFECTED")
        try:
            impact_type = ImpactTypeDB(impact_type_str)
        except ValueError:
            impact_type = ImpactTypeDB.UNAFFECTED

        impact_db = TaskImpactDB(
            fs_id=doc_id,
            version_id=version.id,
            task_id=ti.get("task_id", ""),
            task_title=ti.get("task_title", ""),
            impact_type=impact_type,
            reason=ti.get("reason", ""),
            change_section=ti.get("change_section", ""),
        )
        db.add(impact_db)

    # Persist rework estimate
    rework = impact_result.get("rework_estimate", {})
    if rework:
        rework_db = ReworkEstimateDB(
            fs_id=doc_id,
            version_id=version.id,
            invalidated_count=rework.get("invalidated_count", 0),
            review_count=rework.get("review_count", 0),
            unaffected_count=rework.get("unaffected_count", 0),
            total_rework_days=rework.get("total_rework_days", 0.0),
            affected_sections=rework.get("affected_sections", []),
            changes_summary=rework.get("changes_summary", ""),
        )
        db.add(rework_db)

    await db.commit()
    await db.refresh(version)

    # Log audit event (L9)
    await log_audit_event(
        db, doc_id, AuditEventType.VERSION_ADDED,
        payload={
            "version_number": new_version_number,
            "changes_count": len(changes),
            "impacts_count": len(task_impacts),
        },
    )

    logger.info(
        "Version %d uploaded for document %s: %d changes, %d impacts",
        new_version_number, doc_id, len(changes), len(task_impacts),
    )

    return APIResponse(
        data=FSVersionSchema.model_validate(version),
        meta={
            "changes_count": len(changes),
            "impacts_count": len(task_impacts),
        },
    )


# ── Version List ────────────────────────────────────────


@router.get("/{doc_id}/versions", response_model=APIResponse[FSVersionListResponse])
async def list_versions(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSVersionListResponse]:
    """List all versions for a document."""
    # Verify document exists
    doc_result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(FSVersion)
        .where(FSVersion.fs_id == doc_id)
        .order_by(FSVersion.version_number.asc())
    )
    versions = result.scalars().all()

    schemas = [FSVersionSchema.model_validate(v) for v in versions]

    return APIResponse(
        data=FSVersionListResponse(versions=schemas, total=len(schemas)),
    )


@router.get("/{doc_id}/versions/{version_id}/text")
async def get_version_text(
    doc_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the full text of a specific version."""
    result = await db.execute(
        select(FSVersion).where(FSVersion.id == version_id, FSVersion.fs_id == doc_id)
    )
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"data": {"id": str(version.id), "version_number": version.version_number, "parsed_text": version.parsed_text or ""}}


@router.post("/{doc_id}/versions/{version_id}/revert")
async def revert_to_version(
    doc_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Revert document text to a specific version."""
    ver_result = await db.execute(
        select(FSVersion).where(FSVersion.id == version_id, FSVersion.fs_id == doc_id)
    )
    version = ver_result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.parsed_text = version.parsed_text
    doc.status = FSDocumentStatus.PARSED
    await db.commit()
    return {"data": {"reverted": True, "version_number": version.version_number}}


# ── Version Diff ────────────────────────────────────────


@router.get("/{doc_id}/versions/{version_id}/diff", response_model=APIResponse[DiffResponse])
async def get_version_diff(
    doc_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[DiffResponse]:
    """Get diff between a version and its predecessor."""
    # Verify document and version
    version_result = await db.execute(
        select(FSVersion).where(
            FSVersion.id == version_id,
            FSVersion.fs_id == doc_id,
        )
    )
    version = version_result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    # Load changes for this version
    changes_result = await db.execute(
        select(FSChangeDB)
        .where(FSChangeDB.version_id == version_id)
        .order_by(FSChangeDB.section_index)
    )
    changes = changes_result.scalars().all()

    change_schemas = [
        FSChangeSchema(
            id=c.id,
            change_type=c.change_type.value,
            section_id=c.section_id,
            section_heading=c.section_heading,
            section_index=c.section_index,
            old_text=c.old_text,
            new_text=c.new_text,
        )
        for c in changes
    ]

    added = sum(1 for c in changes if c.change_type == ChangeTypeDB.ADDED)
    modified = sum(1 for c in changes if c.change_type == ChangeTypeDB.MODIFIED)
    deleted = sum(1 for c in changes if c.change_type == ChangeTypeDB.DELETED)

    return APIResponse(
        data=DiffResponse(
            version_id=version.id,
            version_number=version.version_number,
            previous_version=version.version_number - 1 if version.version_number > 1 else None,
            changes=change_schemas,
            total_changes=len(change_schemas),
            added=added,
            modified=modified,
            deleted=deleted,
        ),
    )


# ── Impact Analysis ─────────────────────────────────────


@router.get("/{doc_id}/impact/{version_id}", response_model=APIResponse[ImpactAnalysisResponse])
async def get_impact_analysis(
    doc_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ImpactAnalysisResponse]:
    """Get full impact analysis for a version change."""
    # Verify version
    version_result = await db.execute(
        select(FSVersion).where(
            FSVersion.id == version_id,
            FSVersion.fs_id == doc_id,
        )
    )
    version = version_result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    # Load changes
    changes_result = await db.execute(
        select(FSChangeDB)
        .where(FSChangeDB.version_id == version_id)
        .order_by(FSChangeDB.section_index)
    )
    changes = changes_result.scalars().all()

    # Load task impacts
    impacts_result = await db.execute(
        select(TaskImpactDB)
        .where(TaskImpactDB.version_id == version_id)
        .order_by(TaskImpactDB.created_at)
    )
    impacts = impacts_result.scalars().all()

    # Load rework estimate
    rework_result = await db.execute(
        select(ReworkEstimateDB).where(ReworkEstimateDB.version_id == version_id)
    )
    rework = rework_result.scalar_one_or_none()

    change_schemas = [
        FSChangeSchema(
            id=c.id,
            change_type=c.change_type.value,
            section_id=c.section_id,
            section_heading=c.section_heading,
            section_index=c.section_index,
            old_text=c.old_text,
            new_text=c.new_text,
        )
        for c in changes
    ]

    impact_schemas = [
        TaskImpactSchema(
            id=i.id,
            task_id=i.task_id,
            task_title=i.task_title,
            impact_type=i.impact_type.value,
            reason=i.reason,
            change_section=i.change_section,
        )
        for i in impacts
    ]

    rework_schema = ReworkEstimateSchema(
        invalidated_count=rework.invalidated_count if rework else 0,
        review_count=rework.review_count if rework else 0,
        unaffected_count=rework.unaffected_count if rework else 0,
        total_rework_days=rework.total_rework_days if rework else 0.0,
        affected_sections=rework.affected_sections if rework else [],
        changes_summary=rework.changes_summary if rework else "",
    )

    invalidated = sum(1 for i in impacts if i.impact_type == ImpactTypeDB.INVALIDATED)
    review = sum(1 for i in impacts if i.impact_type == ImpactTypeDB.REQUIRES_REVIEW)
    unaffected = sum(1 for i in impacts if i.impact_type == ImpactTypeDB.UNAFFECTED)

    return APIResponse(
        data=ImpactAnalysisResponse(
            fs_id=doc_id,
            version_id=version.id,
            version_number=version.version_number,
            changes=change_schemas,
            task_impacts=impact_schemas,
            rework_estimate=rework_schema,
            invalidated_count=invalidated,
            review_count=review,
            unaffected_count=unaffected,
        ),
    )


# ── Rework Estimate ─────────────────────────────────────


@router.get("/{doc_id}/impact/{version_id}/rework", response_model=APIResponse[ReworkResponse])
async def get_rework_estimate(
    doc_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ReworkResponse]:
    """Get rework cost estimate for a version change."""
    # Verify version
    version_result = await db.execute(
        select(FSVersion).where(
            FSVersion.id == version_id,
            FSVersion.fs_id == doc_id,
        )
    )
    version = version_result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    # Load rework estimate
    rework_result = await db.execute(
        select(ReworkEstimateDB).where(ReworkEstimateDB.version_id == version_id)
    )
    rework = rework_result.scalar_one_or_none()

    rework_schema = ReworkEstimateSchema(
        invalidated_count=rework.invalidated_count if rework else 0,
        review_count=rework.review_count if rework else 0,
        unaffected_count=rework.unaffected_count if rework else 0,
        total_rework_days=rework.total_rework_days if rework else 0.0,
        affected_sections=rework.affected_sections if rework else [],
        changes_summary=rework.changes_summary if rework else "",
    )

    return APIResponse(
        data=ReworkResponse(
            fs_id=doc_id,
            version_id=version.id,
            version_number=version.version_number,
            rework_estimate=rework_schema,
        ),
    )
