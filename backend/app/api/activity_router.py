"""Activity Log API — global audit event timeline for the monitoring dashboard."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import AuditEventDB, FSDocument
from app.models.schemas import APIResponse, ActivityLogEntry, ActivityLogResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/activity-log", tags=["Activity Log"])

_EVENT_LABELS = {
    "UPLOADED": "Document uploaded",
    "PARSED": "Document parsed",
    "ANALYZED": "Analysis completed",
    "APPROVED": "Document approved",
    "REJECTED": "Document rejected",
    "VERSION_ADDED": "New version added",
    "TASKS_GENERATED": "Tasks generated",
    "EXPORTED": "Document exported",
    "COMMENT_ADDED": "Comment added",
    "COMMENT_RESOLVED": "Comment resolved",
    "SUBMITTED_FOR_APPROVAL": "Submitted for approval",
    "SECTION_EDITED": "Section edited",
    "SECTION_ADDED": "Section added",
    "ANALYSIS_CANCELLED": "Analysis cancelled",
}


def _build_detail(event_type: str, payload: dict | None) -> str:
    """Build a human-readable detail string from event payload."""
    if not payload:
        return ""
    parts = []
    if event_type == "ANALYZED":
        for key in ("ambiguities", "contradictions", "edge_cases", "tasks"):
            if key in payload:
                parts.append(f"{payload[key]} {key.replace('_', ' ')}")
    elif event_type == "PARSED":
        if "sections_count" in payload:
            parts.append(f"{payload['sections_count']} sections")
        if "chunks_stored" in payload:
            parts.append(f"{payload['chunks_stored']} chunks stored")
    elif event_type == "UPLOADED":
        if "filename" in payload:
            parts.append(payload["filename"])
    elif event_type == "TASKS_GENERATED":
        if "tasks_count" in payload:
            parts.append(f"{payload['tasks_count']} tasks")
    elif event_type == "SECTION_EDITED":
        if "section_heading" in payload:
            parts.append(f"Section: {payload['section_heading']}")
    elif event_type == "SECTION_ADDED":
        if "heading" in payload:
            parts.append(f"New section: {payload['heading']}")
    if parts:
        return " · ".join(parts)
    return ""


@router.get("", response_model=APIResponse[ActivityLogResponse])
async def get_activity_log(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    document_name: Optional[str] = Query(None, description="Filter by document name (substring)"),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ActivityLogResponse]:
    """Get the global activity log — unified timeline of all audit events."""
    query = (
        select(AuditEventDB, FSDocument.filename)
        .outerjoin(FSDocument, AuditEventDB.fs_id == FSDocument.id)
        .order_by(AuditEventDB.created_at.desc())
    )

    count_query = select(func.count(AuditEventDB.id))

    if event_type:
        query = query.where(AuditEventDB.event_type == event_type)
        count_query = count_query.where(AuditEventDB.event_type == event_type)

    if document_name:
        escaped = (
            document_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        like_pattern = f"%{escaped}%"
        query = query.where(FSDocument.filename.ilike(like_pattern, escape="\\"))
        count_query = count_query.join(
            FSDocument, AuditEventDB.fs_id == FSDocument.id
        ).where(FSDocument.filename.ilike(like_pattern, escape="\\"))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    entries = []
    for row in rows:
        event = row[0]
        filename = row[1] or "Unknown document"
        evt_type = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
        entries.append(ActivityLogEntry(
            id=event.id,
            fs_id=event.fs_id,
            document_name=filename,
            event_type=evt_type,
            event_label=_EVENT_LABELS.get(evt_type, evt_type.replace("_", " ").title()),
            detail=_build_detail(evt_type, event.payload_json),
            user_id=event.user_id,
            created_at=event.created_at,
        ))

    return APIResponse(data=ActivityLogResponse(events=entries, total=total))
