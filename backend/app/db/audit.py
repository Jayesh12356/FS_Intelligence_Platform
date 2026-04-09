"""Audit event logging helper — centralised audit trail for all state changes (L9).

Usage:
    from app.db.audit import log_audit_event
    await log_audit_event(db, fs_id, AuditEventType.UPLOADED, user_id="system", payload={"filename": "spec.pdf"})
"""

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEventDB, AuditEventType

logger = logging.getLogger(__name__)


async def log_audit_event(
    db: AsyncSession,
    fs_id: UUID,
    event_type: AuditEventType,
    user_id: str = "system",
    payload: Optional[Dict[str, Any]] = None,
) -> AuditEventDB:
    """Log an audit event for an FS document.

    Args:
        db: Async database session.
        fs_id: FS document UUID.
        event_type: Type of event from AuditEventType enum.
        user_id: The user who triggered the event.
        payload: Optional JSON payload with event details.

    Returns:
        The created AuditEventDB record.
    """
    event = AuditEventDB(
        fs_id=fs_id,
        user_id=user_id,
        event_type=event_type,
        payload_json=payload,
    )
    db.add(event)

    logger.info(
        "Audit event logged: type=%s fs_id=%s user=%s",
        event_type.value, fs_id, user_id,
    )

    return event
