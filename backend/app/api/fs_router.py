"""FS Document API — upload, list, get, delete, parse."""

import logging
import shutil
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_db
from app.db.models import FSDocument, FSDocumentStatus, AuditEventType
from app.db.audit import log_audit_event
from app.models.schemas import (
    APIResponse,
    FSDocumentDetail,
    FSDocumentListResponse,
    FSDocumentResponse,
    FSSectionSchema,
    ParseResponse,
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

    doc = FSDocument(
        id=doc_id,
        filename=file.filename or "unknown",
        status=FSDocumentStatus.UPLOADED,
        file_path=file_path,
        file_size=file_size,
        content_type=file.content_type,
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
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSDocumentListResponse]:
    """List all non-deleted documents."""
    result = await db.execute(
        select(FSDocument)
        .where(FSDocument.status != FSDocumentStatus.DELETED)
        .order_by(FSDocument.created_at.desc())
    )
    documents = result.scalars().all()

    doc_list = [
        FSDocumentResponse.model_validate(doc)
        for doc in documents
    ]

    return APIResponse(
        data=FSDocumentListResponse(documents=doc_list, total=len(doc_list)),
    )


@router.get("/{doc_id}", response_model=APIResponse[FSDocumentDetail])
async def get_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSDocumentDetail]:
    """Get a single document by ID."""
    result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()

    if doc is None or doc.status == FSDocumentStatus.DELETED:
        raise HTTPException(status_code=404, detail="Document not found")

    return APIResponse(
        data=FSDocumentDetail.model_validate(doc),
    )


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
