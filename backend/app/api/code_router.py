"""Code Upload & Reverse FS Generation API (L8).

Endpoints:
  POST /api/code/upload         — upload zip of codebase
  POST /api/code/{id}/generate-fs — trigger reverse FS generation
  GET  /api/code/{id}/generated-fs — get generated FS document
  GET  /api/code/{id}/report     — coverage + gaps report
  GET  /api/code/uploads         — list all code uploads
  GET  /api/code/{id}            — get code upload details
"""

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_db
from app.db.models import (
    CodeUploadDB,
    CodeUploadStatus,
    FSDocument,
    FSDocumentStatus,
)
from app.models.schemas import (
    APIResponse,
    CodeReportSchema,
    CodeUploadDetailResponse,
    CodeUploadListResponse,
    CodeUploadResponse,
    FSSectionSchema,
    GeneratedFSResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/code", tags=["code"])


# ── Upload ──────────────────────────────────────────────


@router.post("/upload", response_model=APIResponse[CodeUploadResponse])
async def upload_codebase(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CodeUploadResponse]:
    """Upload a zip archive of a codebase for reverse FS generation."""
    settings = get_settings()

    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext != ".zip":
        raise HTTPException(
            status_code=400,
            detail=f"Only .zip files are accepted (got '{ext}')",
        )

    # Save zip file — sanitize filename to avoid path-traversal on disk write
    upload_id = uuid.uuid4()
    save_dir = settings.upload_path / "code" / str(upload_id)
    save_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name or f"upload_{upload_id}.zip"
    if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    zip_path = save_dir / safe_name

    file_size = 0
    with open(zip_path, "wb") as f:
        while chunk := await file.read(1024 * 64):
            file_size += len(chunk)
            if file_size > settings.max_upload_bytes:
                # Hybrid mode: permit larger archives for reverse FS when enabled,
                # with a stricter dedicated upper bound.
                if settings.REVERSE_LARGE_UPLOAD_ENABLED and file_size <= settings.reverse_max_archive_bytes:
                    pass
                else:
                    f.close()
                    shutil.rmtree(save_dir, ignore_errors=True)
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB}MB "
                            f"(or {settings.REVERSE_MAX_ARCHIVE_SIZE_MB}MB in reverse large-upload mode)"
                        ),
                    )
            if file_size > settings.reverse_max_archive_bytes and settings.REVERSE_LARGE_UPLOAD_ENABLED:
                f.close()
                shutil.rmtree(save_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds reverse archive cap of {settings.REVERSE_MAX_ARCHIVE_SIZE_MB}MB",
                )
            f.write(chunk)

    # Create DB record
    code_upload = CodeUploadDB(
        id=upload_id,
        filename=file.filename,
        zip_path=str(zip_path),
        file_size=file_size,
        status=CodeUploadStatus.UPLOADED,
    )
    db.add(code_upload)
    await db.commit()
    await db.refresh(code_upload)

    # Parse codebase immediately
    import anyio
    from app.parsers.code_parser import parse_codebase

    try:
        code_upload.status = CodeUploadStatus.PARSING
        await db.flush()

        snapshot = await anyio.to_thread.run_sync(parse_codebase, str(zip_path))
        snapshot_dict = snapshot.model_dump()

        # Remove content from snapshot_data to save DB space
        snapshot_for_db = snapshot.model_dump()
        for f_entry in snapshot_for_db.get("files", []):
            f_entry.pop("content", None)

        code_upload.status = CodeUploadStatus.PARSED
        code_upload.primary_language = snapshot.primary_language
        code_upload.total_files = snapshot.total_files
        code_upload.total_lines = snapshot.total_lines
        code_upload.languages = snapshot.languages
        code_upload.snapshot_data = snapshot_for_db
        await db.commit()
        await db.refresh(code_upload)

        logger.info(
            "Codebase parsed: %s — %d files, %d lines, primary: %s",
            file.filename, snapshot.total_files, snapshot.total_lines, snapshot.primary_language,
        )

    except Exception as exc:
        code_upload.status = CodeUploadStatus.ERROR
        await db.commit()
        logger.error("Codebase parsing failed for %s: %s", upload_id, exc)
        raise HTTPException(status_code=400, detail=f"Failed to parse codebase: {exc}")

    return APIResponse(
        data=CodeUploadResponse.model_validate(code_upload),
        meta={
            "total_files": snapshot.total_files,
            "total_lines": snapshot.total_lines,
            "primary_language": snapshot.primary_language,
            "parser_stats": snapshot_dict.get("parser_stats", {}),
        },
    )


# ── Generate FS ─────────────────────────────────────────


@router.post("/{upload_id}/generate-fs", response_model=APIResponse[GeneratedFSResponse])
async def generate_fs(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GeneratedFSResponse]:
    """Trigger reverse FS generation from a parsed codebase.

    Runs the reverse pipeline (reverse_fs_node → reverse_quality_node)
    and stores the result as an FSDocument.
    """
    from app.pipeline.graph import run_reverse_pipeline
    from app.parsers.code_parser import parse_codebase

    # Load code upload
    result = await db.execute(
        select(CodeUploadDB).where(CodeUploadDB.id == upload_id)
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Code upload not found")

    if upload.status not in (CodeUploadStatus.PARSED, CodeUploadStatus.GENERATED):
        raise HTTPException(
            status_code=400,
            detail=f"Codebase must be parsed before generating FS. Current status: {upload.status.value}",
        )

    # Set status to generating
    upload.status = CodeUploadStatus.GENERATING
    await db.flush()

    # Re-parse to get full snapshot with content (DB version has content stripped)
    import anyio
    try:
        snapshot = await anyio.to_thread.run_sync(parse_codebase, upload.zip_path)
        snapshot_dict = snapshot.model_dump()
    except Exception as exc:
        upload.status = CodeUploadStatus.ERROR
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to re-parse codebase: {exc}")

    # Run reverse pipeline
    try:
        pipeline_result = await run_reverse_pipeline(
            code_upload_id=str(upload_id),
            snapshot=snapshot_dict,
        )
    except Exception as exc:
        upload.status = CodeUploadStatus.ERROR
        await db.commit()
        logger.error("Reverse pipeline failed for %s: %s", upload_id, exc)
        raise HTTPException(status_code=500, detail=f"FS generation failed: {exc}")

    generated_sections = pipeline_result.get("generated_sections", [])
    raw_fs_text = pipeline_result.get("raw_fs_text", "")
    report = pipeline_result.get("report", {})

    # Create FSDocument from generated FS
    fs_doc = FSDocument(
        filename=f"[Generated] {upload.filename.replace('.zip', '')}.fs",
        parsed_text=raw_fs_text,
        original_text=raw_fs_text,
        status=FSDocumentStatus.PARSED,
        file_size=len(raw_fs_text.encode("utf-8")),
        content_type="text/plain",
    )
    db.add(fs_doc)
    await db.flush()
    await db.refresh(fs_doc)

    # Update code upload
    upload.status = CodeUploadStatus.GENERATED
    upload.generated_fs_id = fs_doc.id
    upload.generated_fs_text = raw_fs_text
    upload.generated_sections = generated_sections
    upload.coverage = report.get("coverage", 0.0)
    upload.confidence = report.get("confidence", 0.0)
    upload.gaps = report.get("gaps", [])
    upload.report_data = report
    await db.commit()
    await db.refresh(upload)

    logger.info(
        "FS generated for %s: %d sections, coverage=%.0f%%, confidence=%.0f%%",
        upload_id, len(generated_sections),
        (report.get("coverage", 0) * 100),
        (report.get("confidence", 0) * 100),
    )

    section_schemas = [
        FSSectionSchema(
            heading=s.get("heading", ""),
            content=s.get("content", ""),
            section_index=s.get("section_index", i),
        )
        for i, s in enumerate(generated_sections)
    ]

    report_schema = CodeReportSchema(
        coverage=report.get("coverage", 0.0),
        confidence=report.get("confidence", 0.0),
        gaps=report.get("gaps", []),
        total_entities=report.get("total_entities", 0),
        documented_entities=report.get("documented_entities", 0),
        undocumented_files=report.get("undocumented_files", []),
        confidence_reasons=report.get("confidence_reasons", []),
        generation_stats=report.get("generation_stats", {}),
    )

    return APIResponse(
        data=GeneratedFSResponse(
            code_upload_id=upload.id,
            generated_fs_id=fs_doc.id,
            status=upload.status.value,
            sections=section_schemas,
            raw_text=raw_fs_text,
            report=report_schema,
        ),
    )


# ── Get Generated FS ────────────────────────────────────


@router.get("/{upload_id}/generated-fs", response_model=APIResponse[GeneratedFSResponse])
async def get_generated_fs(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GeneratedFSResponse]:
    """Get the generated FS document for a code upload."""
    result = await db.execute(
        select(CodeUploadDB).where(CodeUploadDB.id == upload_id)
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Code upload not found")

    if upload.status != CodeUploadStatus.GENERATED:
        raise HTTPException(
            status_code=400,
            detail=f"FS not yet generated. Current status: {upload.status.value}",
        )

    sections = upload.generated_sections or []
    section_schemas = [
        FSSectionSchema(
            heading=s.get("heading", ""),
            content=s.get("content", ""),
            section_index=s.get("section_index", i),
        )
        for i, s in enumerate(sections)
    ]

    report = upload.report_data or {}
    report_schema = CodeReportSchema(
        coverage=report.get("coverage", 0.0),
        confidence=report.get("confidence", 0.0),
        gaps=report.get("gaps", []),
        total_entities=report.get("total_entities", 0),
        documented_entities=report.get("documented_entities", 0),
        undocumented_files=report.get("undocumented_files", []),
        confidence_reasons=report.get("confidence_reasons", []),
        generation_stats=report.get("generation_stats", {}),
    )

    return APIResponse(
        data=GeneratedFSResponse(
            code_upload_id=upload.id,
            generated_fs_id=upload.generated_fs_id,
            status=upload.status.value,
            sections=section_schemas,
            raw_text=upload.generated_fs_text or "",
            report=report_schema,
        ),
    )


# ── Quality Report ──────────────────────────────────────


@router.get("/{upload_id}/report", response_model=APIResponse[CodeReportSchema])
async def get_report(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CodeReportSchema]:
    """Get the quality report for a generated FS."""
    result = await db.execute(
        select(CodeUploadDB).where(CodeUploadDB.id == upload_id)
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Code upload not found")

    if not upload.report_data:
        raise HTTPException(
            status_code=400,
            detail=f"No report available. Current status: {upload.status.value}",
        )

    report = upload.report_data
    return APIResponse(
        data=CodeReportSchema(
            coverage=report.get("coverage", 0.0),
            confidence=report.get("confidence", 0.0),
            gaps=report.get("gaps", []),
            total_entities=report.get("total_entities", 0),
            documented_entities=report.get("documented_entities", 0),
            undocumented_files=report.get("undocumented_files", []),
            confidence_reasons=report.get("confidence_reasons", []),
            generation_stats=report.get("generation_stats", {}),
        ),
    )


# ── List Uploads ────────────────────────────────────────


@router.get("/uploads", response_model=APIResponse[CodeUploadListResponse])
async def list_uploads(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CodeUploadListResponse]:
    """List code uploads with pagination."""
    total_result = await db.execute(select(func.count()).select_from(CodeUploadDB))
    total = int(total_result.scalar_one() or 0)

    result = await db.execute(
        select(CodeUploadDB)
        .order_by(CodeUploadDB.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    uploads = result.scalars().all()

    schemas = [CodeUploadResponse.model_validate(u) for u in uploads]

    return APIResponse(
        data=CodeUploadListResponse(uploads=schemas, total=total),
        meta={"limit": limit, "offset": offset, "count": len(schemas)},
    )


# ── Upload Detail ───────────────────────────────────────


@router.get("/{upload_id}", response_model=APIResponse[CodeUploadDetailResponse])
async def get_upload_detail(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CodeUploadDetailResponse]:
    """Get detailed info about a code upload."""
    result = await db.execute(
        select(CodeUploadDB).where(CodeUploadDB.id == upload_id)
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Code upload not found")

    detail = CodeUploadDetailResponse.model_validate(upload)
    detail.parser_stats = (upload.snapshot_data or {}).get("parser_stats", {})
    detail.generation_stats = (upload.report_data or {}).get("generation_stats", {})

    return APIResponse(
        data=detail,
    )
