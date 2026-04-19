"""Activity Log API — global audit event timeline for the monitoring dashboard.

This endpoint backs both the global ``/monitoring`` Activity tab and the
per-document ``DocumentLifecycle`` strip on the doc detail page. Events
are sourced from ``audit_events`` and rendered into user-friendly
sentences — never raw runtime traces.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import AuditEventDB, FSDocument
from app.models.schemas import ActivityLogEntry, ActivityLogResponse, APIResponse

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
    # Lifecycle additions
    "ANALYSIS_REFINED": "Spec refined",
    "AMBIGUITY_RESOLVED": "Ambiguity resolved",
    "CONTRADICTION_ACCEPTED": "Contradiction resolved",
    "EDGE_CASE_ACCEPTED": "Edge case accepted",
    "VERSION_REVERTED": "Reverted to earlier version",
    # Build telemetry
    "BUILD_STARTED": "Autonomous build started",
    "BUILD_PHASE_CHANGED": "Build phase advanced",
    "BUILD_TASK_COMPLETED": "Task verified complete",
    "FILE_REGISTERED": "File registered",
    "BUILD_COMPLETED": "Build completed",
    "BUILD_FAILED": "Build failed",
}


# Bucket events into 4 user-facing categories so the UI can color the
# chips. Anything not listed defaults to ``document``.
_EVENT_CATEGORIES = {
    "UPLOADED": "document",
    "PARSED": "document",
    "VERSION_ADDED": "document",
    "VERSION_REVERTED": "document",
    "EXPORTED": "document",
    "SECTION_EDITED": "document",
    "SECTION_ADDED": "document",
    "ANALYZED": "analysis",
    "ANALYSIS_CANCELLED": "analysis",
    "TASKS_GENERATED": "analysis",
    "ANALYSIS_REFINED": "analysis",
    "AMBIGUITY_RESOLVED": "analysis",
    "CONTRADICTION_ACCEPTED": "analysis",
    "EDGE_CASE_ACCEPTED": "analysis",
    "BUILD_STARTED": "build",
    "BUILD_PHASE_CHANGED": "build",
    "BUILD_TASK_COMPLETED": "build",
    "FILE_REGISTERED": "build",
    "BUILD_COMPLETED": "build",
    "BUILD_FAILED": "build",
    "APPROVED": "collab",
    "REJECTED": "collab",
    "SUBMITTED_FOR_APPROVAL": "collab",
    "COMMENT_ADDED": "collab",
    "COMMENT_RESOLVED": "collab",
}


def _build_detail(event_type: str, payload: dict | None) -> str:
    """Build a human-readable single-line detail from the event payload.

    Keep these strings short — the UI shows them as a subtitle next to
    the event label, not as a runtime log dump.
    """
    if not payload:
        return ""
    parts: list[str] = []
    if event_type == "ANALYZED":
        for key in ("ambiguities", "contradictions", "edge_cases", "tasks"):
            if key in payload:
                parts.append(f"{payload[key]} {key.replace('_', ' ')}")
        if payload.get("source") == "cursor_paste":
            parts.append("via Cursor")
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
    elif event_type == "ANALYSIS_REFINED":
        trigger = payload.get("trigger")
        if trigger:
            pretty = trigger.replace("_", " ")
            parts.append(f"Trigger: {pretty}")
        if "version_number" in payload:
            parts.append(f"v{payload['version_number']}")
    elif event_type == "AMBIGUITY_RESOLVED":
        sev = payload.get("severity")
        head = payload.get("section_heading") or payload.get("flag_id")
        if sev:
            parts.append(f"{sev} severity")
        if head:
            parts.append(str(head)[:80])
    elif event_type == "CONTRADICTION_ACCEPTED":
        mode = payload.get("mode")
        sa = payload.get("section_a_heading")
        sb = payload.get("section_b_heading")
        if sa and sb:
            parts.append(f"{sa} vs {sb}")
        elif mode == "bulk_accept":
            parts.append(f"{payload.get('accepted', 0)} merged")
    elif event_type == "EDGE_CASE_ACCEPTED":
        mode = payload.get("mode")
        head = payload.get("section_heading")
        if head:
            parts.append(str(head)[:80])
        elif mode == "bulk_accept":
            parts.append(f"{payload.get('accepted', 0)} merged")
    elif event_type == "VERSION_REVERTED":
        if "to_version" in payload:
            parts.append(f"to v{payload['to_version']}")
    elif event_type == "BUILD_STARTED":
        provider = payload.get("provider", "agent")
        stack = payload.get("stack", "")
        out = payload.get("output_folder", "")
        parts.append(provider)
        if stack:
            parts.append(stack)
        if out:
            parts.append(out)
    elif event_type == "BUILD_PHASE_CHANGED":
        from_p = payload.get("from_phase")
        to_p = payload.get("to_phase")
        if from_p is not None and to_p is not None:
            parts.append(f"phase {from_p} → {to_p}")
        if "current_task_index" in payload and "total_tasks" in payload:
            parts.append(f"task {payload['current_task_index']}/{payload['total_tasks']}")
    elif event_type == "BUILD_TASK_COMPLETED":
        if payload.get("task_title"):
            parts.append(str(payload["task_title"])[:80])
        elif payload.get("task_id"):
            parts.append(str(payload["task_id"]))
        if "completed_count" in payload and "total_tasks" in payload:
            parts.append(f"{payload['completed_count']}/{payload['total_tasks']} done")
    elif event_type == "FILE_REGISTERED":
        if payload.get("file_path"):
            parts.append(payload["file_path"])
        if payload.get("file_type") and payload["file_type"] != "unknown":
            parts.append(f"({payload['file_type']})")
    elif event_type in ("BUILD_COMPLETED", "BUILD_FAILED"):
        ct = payload.get("completed_tasks")
        tt = payload.get("total_tasks")
        dur = payload.get("duration_ms")
        if ct is not None and tt:
            parts.append(f"{ct}/{tt} tasks")
        if dur:
            secs = max(1, int(dur / 1000))
            parts.append(f"{secs}s")
        if event_type == "BUILD_FAILED" and payload.get("returncode") not in (None, 0):
            parts.append(f"rc={payload['returncode']}")
    if parts:
        return " · ".join(str(p) for p in parts if p)
    return ""


@router.get("", response_model=APIResponse[ActivityLogResponse])
async def get_activity_log(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0, le=2**31 - 1),
    event_type: str | None = Query(None, description="Filter by event type"),
    document_name: str | None = Query(None, description="Filter by document name (substring)"),
    fs_id: uuid.UUID | None = Query(None, description="Filter by document UUID"),
    category: str | None = Query(
        None,
        description="Filter by event category: document | analysis | build | collab",
    ),
    include_payload: bool = Query(
        False,
        description="When true, include the raw event payload (used by the per-doc Lifecycle timeline tooltip).",
    ),
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

    if fs_id is not None:
        query = query.where(AuditEventDB.fs_id == fs_id)
        count_query = count_query.where(AuditEventDB.fs_id == fs_id)

    if document_name:
        escaped = document_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_pattern = f"%{escaped}%"
        query = query.where(FSDocument.filename.ilike(like_pattern, escape="\\"))
        count_query = count_query.join(FSDocument, AuditEventDB.fs_id == FSDocument.id).where(
            FSDocument.filename.ilike(like_pattern, escape="\\")
        )

    if category:
        # Postgres supports ANY(array); simpler portable approach is IN().
        wanted = [k for k, v in _EVENT_CATEGORIES.items() if v == category]
        if wanted:
            query = query.where(AuditEventDB.event_type.in_(wanted))
            count_query = count_query.where(AuditEventDB.event_type.in_(wanted))

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
        entries.append(
            ActivityLogEntry(
                id=event.id,
                fs_id=event.fs_id,
                document_name=filename,
                event_type=evt_type,
                event_label=_EVENT_LABELS.get(evt_type, evt_type.replace("_", " ").title()),
                detail=_build_detail(evt_type, event.payload_json),
                category=_EVENT_CATEGORIES.get(evt_type, "document"),
                payload=(event.payload_json if include_payload else None),
                user_id=event.user_id,
                created_at=event.created_at,
            )
        )

    return APIResponse(data=ActivityLogResponse(events=entries, total=total))
