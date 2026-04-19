"""Duplicate detection API — list cross-document duplicate requirement flags (L9)."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import DuplicateFlagDB, FSDocument
from app.models.schemas import (
    APIResponse,
    DuplicateFlagSchema,
    DuplicateListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fs", tags=["duplicates"])


@router.get("/{doc_id}/duplicates", response_model=APIResponse[DuplicateListResponse])
async def list_duplicates(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[DuplicateListResponse]:
    """List all cross-document duplicate flags for a document.

    Duplicates are detected during the analysis pipeline (duplicate_node)
    by searching Qdrant for cosine similarity > 0.88 across different documents.
    """
    # Verify document exists
    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Load duplicate flags
    result = await db.execute(
        select(DuplicateFlagDB).where(DuplicateFlagDB.fs_id == doc_id).order_by(DuplicateFlagDB.similarity_score.desc())
    )
    flags = result.scalars().all()

    schemas = [
        DuplicateFlagSchema(
            id=f.id,
            section_index=f.section_index,
            section_heading=f.section_heading,
            similar_fs_id=f.similar_fs_id,
            similar_section_heading=f.similar_section_heading,
            similarity_score=f.similarity_score,
            flagged_text=f.flagged_text,
            similar_text=f.similar_text,
        )
        for f in flags
    ]

    return APIResponse(
        data=DuplicateListResponse(
            duplicates=schemas,
            total=len(schemas),
        ),
    )
