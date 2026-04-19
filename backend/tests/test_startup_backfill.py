"""Smoke test for the ANALYZED back-fill.

Guards two contracts:
  1. A COMPLETE document with no ANALYZED event gets exactly one
     synthetic event inserted with ``user_id='backfill'``.
  2. Running the back-fill a second time is a no-op (idempotent).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.db.audit import log_audit_event
from app.db.models import (
    AuditEventDB,
    AuditEventType,
    FSDocument,
    FSDocumentStatus,
)


@pytest.mark.asyncio
async def test_backfill_inserts_one_analyzed_event(test_db, monkeypatch) -> None:
    fs_old = FSDocument(filename="old.md", status=FSDocumentStatus.COMPLETE)
    fs_already = FSDocument(filename="already.md", status=FSDocumentStatus.COMPLETE)
    fs_uploaded = FSDocument(filename="up.md", status=FSDocumentStatus.UPLOADED)
    test_db.add_all([fs_old, fs_already, fs_uploaded])
    await test_db.commit()
    await test_db.refresh(fs_already)

    # Mark `fs_already` as already-analysed via a real audit event.
    await log_audit_event(
        test_db,
        fs_already.id,
        AuditEventType.ANALYZED,
        user_id="cursor",
        payload={"tasks": 5},
    )
    await test_db.commit()

    @asynccontextmanager
    async def _fake_session_factory():
        yield test_db

    monkeypatch.setattr(
        "app.db.base.async_session_factory", _fake_session_factory
    )

    from app.startup.backfill import backfill_analyzed_events

    inserted = await backfill_analyzed_events()
    assert inserted == 1, "Only the old COMPLETE doc should be back-filled"

    # Re-running is a no-op — the back-fill is idempotent.
    inserted_again = await backfill_analyzed_events()
    assert inserted_again == 0

    rows = (
        await test_db.execute(
            select(AuditEventDB).where(
                AuditEventDB.event_type == AuditEventType.ANALYZED
            )
        )
    ).scalars().all()
    fs_by_id = {r.fs_id: r for r in rows}
    assert fs_old.id in fs_by_id
    assert fs_by_id[fs_old.id].user_id == "backfill"
    assert fs_already.id in fs_by_id
    assert fs_by_id[fs_already.id].user_id == "cursor"
    assert fs_uploaded.id not in fs_by_id, (
        "Documents not in COMPLETE status must never be back-filled"
    )
