"""Idempotent ANALYZED back-fill.

Why this exists:
  Before the lifecycle telemetry uplift, the platform never wrote an
  ``ANALYZED`` audit event from the Cursor-driven submit_analyze path.
  Documents that finished analysis under the old code therefore show
  only ``UPLOADED`` in the per-document Lifecycle strip and the global
  activity feed, even though their full analysis is intact.

What this back-fill does:
  Once per process boot, scans for ``FSDocument`` rows with
  ``status = COMPLETE`` that have NO ``ANALYZED`` event yet, and
  inserts a single synthetic event with ``user_id="backfill"`` so the
  UI catches up. The query is cheap (indexed on fs_id + event_type)
  and the inserts are guarded by an existence check, so running the
  back-fill more than once is safe and a no-op.

Bounds:
  Runs at most once per startup, processes at most ``LIMIT`` rows per
  invocation (default 500) so a very old, very large corpus does not
  block boot. Operators can re-run by restarting the service until the
  log line "ANALYZED back-fill: 0 documents updated" appears.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import and_, exists, select

from app.db.base import async_session_factory
from app.db.models import (
    AuditEventDB,
    AuditEventType,
    FSDocument,
    FSDocumentStatus,
)

logger = logging.getLogger(__name__)

LIMIT = 500


async def backfill_analyzed_events() -> int:
    """Insert a synthetic ANALYZED event for any COMPLETE doc missing one.

    Returns the number of rows inserted (0 means the corpus is already
    healed). Failures are logged but never propagated — telemetry must
    not block startup.
    """

    inserted = 0
    async with async_session_factory() as session:
        # Subquery: documents that already HAVE an ANALYZED event.
        analyzed_exists = (
            exists()
            .where(
                and_(
                    AuditEventDB.fs_id == FSDocument.id,
                    AuditEventDB.event_type == AuditEventType.ANALYZED,
                )
            )
            .correlate(FSDocument)
        )

        candidates = (
            await session.execute(
                select(FSDocument)
                .where(FSDocument.status == FSDocumentStatus.COMPLETE)
                .where(~analyzed_exists)
                .limit(LIMIT)
            )
        ).scalars().all()

        if not candidates:
            logger.info("ANALYZED back-fill: 0 documents updated")
            return 0

        now = datetime.now(UTC)
        for doc in candidates:
            session.add(
                AuditEventDB(
                    fs_id=doc.id,
                    user_id="backfill",
                    event_type=AuditEventType.ANALYZED,
                    payload_json={
                        "source": "startup_backfill",
                        "reason": (
                            "Document was COMPLETE before lifecycle "
                            "telemetry shipped; synthesising one event "
                            "so the timeline is accurate."
                        ),
                        "backfilled_at": now.isoformat(),
                    },
                )
            )
            inserted += 1

        await session.commit()

    logger.info("ANALYZED back-fill: %d documents updated", inserted)
    return inserted


__all__ = ["backfill_analyzed_events"]
