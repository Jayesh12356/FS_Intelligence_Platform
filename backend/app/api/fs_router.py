"""FS Document API — upload, list, get, delete, parse, reset, section edit."""

import hashlib
import logging
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_db
from app.db.models import FSDocument, FSDocumentStatus, FSVersion, AuditEventType
from app.db.audit import log_audit_event
from app.parsers.section_extractor import extract_sections_from_text, rebuild_text_from_sections
from app.parsers.base import FSSection
from app.models.schemas import (
    APIResponse,
    FSDocumentDetail,
    FSDocumentListResponse,
    FSDocumentResponse,
    FSSectionSchema,
    ParseResponse,
    SectionAddRequest,
    SectionEditRequest,
    UploadResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fs", tags=["FS Documents"])

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _validate_file(file: UploadFile) -> None:
    """Validate file type and extension."""
    settings = get_settings()

    # Check extension
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{ext}' not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS)}",
            )

    # Check content type (lenient — some clients don't send correct MIME)
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        # Only warn, don't block — rely on extension check
        logger.warning("Unexpected content type: %s for file %s", file.content_type, file.filename)


async def _save_file(file: UploadFile, doc_id: uuid.UUID) -> tuple[str, int]:
    """Save uploaded file to disk. Returns (file_path, file_size)."""
    settings = get_settings()
    ext = Path(file.filename).suffix.lower() if file.filename else ".bin"
    save_dir = settings.upload_path / str(doc_id)
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"original{ext}"

    size = 0
    with open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 64):  # 64KB chunks
            size += len(chunk)
            if size > settings.max_upload_bytes:
                # Clean up partial file
                f.close()
                shutil.rmtree(save_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB}MB",
                )
            f.write(chunk)

    return str(file_path), size


@router.post("/upload", response_model=APIResponse[UploadResponse])
async def upload_file(
    file: UploadFile = File(...),
    project_id: Optional[str] = Query(None, description="Optional project ID to assign document to"),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[UploadResponse]:
    """Upload a PDF, DOCX, or TXT file."""
    _validate_file(file)

    doc_id = uuid.uuid4()

    try:
        file_path, file_size = await _save_file(file, doc_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to save file: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    parsed_project_id = None
    order_in_project = 0
    if project_id:
        try:
            parsed_project_id = uuid.UUID(project_id)
            from app.db.models import FSProject
            from sqlalchemy import func
            proj = (await db.execute(select(FSProject).where(FSProject.id == parsed_project_id))).scalar_one_or_none()
            if not proj:
                raise HTTPException(status_code=404, detail="Project not found")
            max_order = (await db.execute(
                select(func.max(FSDocument.order_in_project)).where(FSDocument.project_id == parsed_project_id)
            )).scalar() or 0
            order_in_project = max_order + 1
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid project_id format")

    doc = FSDocument(
        id=doc_id,
        filename=file.filename or "unknown",
        status=FSDocumentStatus.UPLOADED,
        file_path=file_path,
        file_size=file_size,
        content_type=file.content_type,
        project_id=parsed_project_id,
        order_in_project=order_in_project,
    )
    db.add(doc)
    await db.flush()

    logger.info("Uploaded document %s: %s (%d bytes)", doc_id, file.filename, file_size)

    # Log audit event (L9)
    await log_audit_event(
        db, doc_id, AuditEventType.UPLOADED,
        payload={"filename": file.filename or "unknown", "file_size": file_size},
    )

    return APIResponse(
        data=UploadResponse(
            id=doc.id,
            filename=doc.filename,
            status=doc.status.value,
        ),
        meta={"file_size": file_size},
    )


@router.get("/", response_model=APIResponse[FSDocumentListResponse])
async def list_documents(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSDocumentListResponse]:
    """List non-deleted documents with pagination.

    Query params: ``limit`` (1-500, default 50) and ``offset`` (default 0).
    """
    base_filter = FSDocument.status != FSDocumentStatus.DELETED

    total_result = await db.execute(
        select(func.count()).select_from(FSDocument).where(base_filter)
    )
    total = int(total_result.scalar_one() or 0)

    result = await db.execute(
        select(FSDocument)
        .where(base_filter)
        .order_by(FSDocument.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    documents = result.scalars().all()

    doc_list = [FSDocumentResponse.model_validate(doc) for doc in documents]

    return APIResponse(
        data=FSDocumentListResponse(documents=doc_list, total=total),
        meta={"limit": limit, "offset": offset, "count": len(doc_list)},
    )


@router.get("/{doc_id}", response_model=APIResponse[FSDocumentDetail])
async def get_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSDocumentDetail]:
    """Get a single document by ID, including reconstructed sections."""
    result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()

    if doc is None or doc.status == FSDocumentStatus.DELETED:
        raise HTTPException(status_code=404, detail="Document not found")

    detail = FSDocumentDetail.model_validate(doc)

    if doc.parsed_text:
        extracted = extract_sections_from_text(doc.parsed_text)
        logger.info("Extracted %d sections from parsed_text for doc %s", len(extracted), doc_id)
        detail.sections = [
            FSSectionSchema(
                heading=s.heading,
                content=s.content,
                section_index=s.section_index,
            )
            for s in extracted
        ]

    return APIResponse(data=detail)


@router.get("/{doc_id}/status")
async def get_document_status(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Get the processing status of a document."""
    result = await db.execute(
        select(FSDocument.status).where(FSDocument.id == doc_id)
    )
    status = result.scalar_one_or_none()

    if status is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return APIResponse(
        data={"id": str(doc_id), "status": status.value},
    )


@router.delete("/{doc_id}", response_model=APIResponse[dict])
async def delete_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Soft-delete a document (sets status to DELETED)."""
    result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()

    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = FSDocumentStatus.DELETED
    await db.flush()

    logger.info("Soft-deleted document %s", doc_id)

    return APIResponse(
        data={"id": str(doc_id), "deleted": True},
    )


@router.post("/{doc_id}/reset-status", response_model=APIResponse[dict])
async def reset_document_status(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Admin: reset a stuck document back to PARSED (or UPLOADED if never parsed)."""
    result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    old_status = doc.status.value if hasattr(doc.status, "value") else str(doc.status)
    if doc.parsed_text:
        doc.status = FSDocumentStatus.PARSED
    else:
        doc.status = FSDocumentStatus.UPLOADED
    await db.flush()

    new_status = doc.status.value if hasattr(doc.status, "value") else str(doc.status)
    logger.info("Reset document %s status: %s → %s", doc_id, old_status, new_status)
    return APIResponse(data={"id": str(doc_id), "old_status": old_status, "new_status": new_status})


@router.post("/{doc_id}/parse", response_model=APIResponse[ParseResponse])
async def parse_document_endpoint(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ParseResponse]:
    """Trigger parsing for an uploaded document.

    Pipeline: parse → chunk → embed → store in Qdrant.
    Updates document status: UPLOADED → PARSING → PARSED.
    """
    from app.parsers.router import parse_document
    from app.parsers.chunker import chunk_parsed_fs
    from app.vector.fs_store import store_fs_chunks

    # Parse the document
    try:
        parsed = await parse_document(str(doc_id), db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Chunk the parsed result
    chunks = chunk_parsed_fs(parsed)

    # Embed and store in Qdrant (non-fatal if API key not set)
    chunks_stored = 0
    try:
        chunks_stored = await store_fs_chunks(str(doc_id), chunks)
    except Exception as exc:
        logger.warning(
            "Embedding storage failed for document %s (non-fatal): %s",
            doc_id, exc,
        )

    # Reload document for response
    result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()

    sections = [
        FSSectionSchema(
            heading=s.heading,
            content=s.content,
            section_index=s.section_index,
        )
        for s in parsed.sections
    ]

    # Log audit event (L9)
    await log_audit_event(
        db, doc_id, AuditEventType.PARSED,
        payload={"sections_count": len(sections), "chunks_stored": chunks_stored},
    )

    return APIResponse(
        data=ParseResponse(
            id=doc.id,
            filename=doc.filename,
            status=doc.status.value,
            sections_count=len(sections),
            chunks_stored=chunks_stored,
            sections=sections,
        ),
        meta={
            "characters": len(parsed.raw_text),
            "chunks": len(chunks),
        },
    )


# ── Section Edit / Add Endpoints ───────────────────────


async def _create_version_snapshot(doc: FSDocument, db: AsyncSession, summary: str) -> FSVersion:
    """Create a version snapshot before editing."""
    versions_result = await db.execute(
        select(FSVersion)
        .where(FSVersion.fs_id == doc.id)
        .order_by(FSVersion.version_number.desc())
    )
    existing = versions_result.scalars().first()
    next_num = (existing.version_number + 1) if existing else 1

    version = FSVersion(
        fs_id=doc.id,
        version_number=next_num,
        parsed_text=doc.parsed_text or "",
        file_path=doc.file_path,
        file_size=doc.file_size,
        content_type=doc.content_type,
        content_hash=hashlib.sha256((doc.parsed_text or "").encode()).hexdigest()[:32],
        diff_summary=summary,
    )
    db.add(version)
    return version


@router.patch("/{doc_id}/sections/{section_index}", response_model=APIResponse[FSSectionSchema])
async def edit_section(
    doc_id: uuid.UUID,
    section_index: int,
    body: SectionEditRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSSectionSchema]:
    """Edit a section's heading or content in-place."""
    result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.parsed_text:
        raise HTTPException(status_code=400, detail="Document has no parsed text")

    sections = extract_sections_from_text(doc.parsed_text)
    if section_index < 0 or section_index >= len(sections):
        raise HTTPException(status_code=404, detail=f"Section index {section_index} out of range (0-{len(sections)-1})")

    old_heading = sections[section_index].heading
    if body.heading is not None:
        sections[section_index] = FSSection(
            heading=body.heading,
            content=sections[section_index].content,
            section_index=section_index,
        )
    if body.content is not None:
        sections[section_index] = FSSection(
            heading=sections[section_index].heading,
            content=body.content,
            section_index=section_index,
        )

    await _create_version_snapshot(doc, db, f"Section '{old_heading}' edited")
    doc.parsed_text = rebuild_text_from_sections(sections)
    await log_audit_event(db, doc_id, AuditEventType.SECTION_EDITED, payload={
        "section_index": section_index,
        "section_heading": sections[section_index].heading,
    })
    await db.flush()

    updated = sections[section_index]
    return APIResponse(data=FSSectionSchema(
        heading=updated.heading,
        content=updated.content,
        section_index=updated.section_index,
    ))


@router.post("/{doc_id}/sections", response_model=APIResponse[FSSectionSchema])
async def add_section(
    doc_id: uuid.UUID,
    body: SectionAddRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSSectionSchema]:
    """Add a new section to the document."""
    result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    sections = extract_sections_from_text(doc.parsed_text or "")

    insert_idx = len(sections)
    if body.insert_after is not None and 0 <= body.insert_after < len(sections):
        insert_idx = body.insert_after + 1

    new_section = FSSection(heading=body.heading, content=body.content, section_index=insert_idx)
    sections.insert(insert_idx, new_section)

    for i, s in enumerate(sections):
        sections[i] = FSSection(heading=s.heading, content=s.content, section_index=i)

    await _create_version_snapshot(doc, db, f"Section '{body.heading}' added")
    doc.parsed_text = rebuild_text_from_sections(sections)
    if doc.status == FSDocumentStatus.UPLOADED:
        doc.status = FSDocumentStatus.PARSED
    await log_audit_event(db, doc_id, AuditEventType.SECTION_ADDED, payload={
        "heading": body.heading,
        "insert_index": insert_idx,
    })
    await db.flush()

    return APIResponse(data=FSSectionSchema(
        heading=new_section.heading,
        content=new_section.content,
        section_index=insert_idx,
    ))
