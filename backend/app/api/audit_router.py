"""Audit trail API — full event timeline for FS documents (L9)."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import AuditEventDB, FSDocument
from app.models.schemas import (
    APIResponse,
    AuditEventSchema,
    AuditLogResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fs", tags=["audit"])


@router.get("/{doc_id}/audit-log", response_model=APIResponse[AuditLogResponse])
async def get_audit_log(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AuditLogResponse]:
    """Get the full audit event timeline for a document.

    Returns all state changes in chronological order:
    UPLOADED, PARSED, ANALYZED, APPROVED, REJECTED,
    VERSION_ADDED, TASKS_GENERATED, EXPORTED, COMMENT_ADDED, etc.
    """
    # Verify document exists
    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Load all audit events
    result = await db.execute(
        select(AuditEventDB).where(AuditEventDB.fs_id == doc_id).order_by(AuditEventDB.created_at.asc())
    )
    events = result.scalars().all()

    schemas = [
        AuditEventSchema(
            id=e.id,
            fs_id=e.fs_id,
            user_id=e.user_id,
            event_type=e.event_type.value,
            payload_json=e.payload_json,
            created_at=e.created_at,
        )
        for e in events
    ]

    return APIResponse(
        data=AuditLogResponse(
            events=schemas,
            total=len(schemas),
        ),
    )
