"""Coverage test: every lifecycle audit event we wired actually fires.

We keep the activity-log narrative in sync with the platform by directly
exercising the routers that emit each new ``AuditEventType``. Failures
here surface as silent gaps in the per-document Lifecycle timeline and
the global /monitoring activity tab — precisely the bug the user
reported ("activity logs only show uploaded but we did everything
analyse to build").
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.db.audit import log_audit_event
from app.db.models import (
    AuditEventDB,
    AuditEventType,
    BuildStateDB,
    BuildStatus,
    FileRegistryDB,
    FSDocument,
    FSDocumentStatus,
)


# ---------------------------------------------------------------------------
# Smallest possible smoke — every new enum value can be persisted with
# ``log_audit_event`` and round-tripped through the ORM.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_new_audit_event_type_is_persistable(test_db) -> None:
    fs = FSDocument(filename="cov.md", status=FSDocumentStatus.UPLOADED)
    test_db.add(fs)
    await test_db.commit()
    await test_db.refresh(fs)

    new_types = (
        AuditEventType.ANALYSIS_REFINED,
        AuditEventType.AMBIGUITY_RESOLVED,
        AuditEventType.CONTRADICTION_ACCEPTED,
        AuditEventType.EDGE_CASE_ACCEPTED,
        AuditEventType.VERSION_REVERTED,
        AuditEventType.BUILD_STARTED,
        AuditEventType.BUILD_PHASE_CHANGED,
        AuditEventType.BUILD_TASK_COMPLETED,
        AuditEventType.FILE_REGISTERED,
        AuditEventType.BUILD_COMPLETED,
        AuditEventType.BUILD_FAILED,
    )
    for t in new_types:
        await log_audit_event(
            test_db, fs.id, t, user_id="test", payload={"probe": t.value}
        )
    await test_db.commit()

    rows = (
        await test_db.execute(
            select(AuditEventDB).where(AuditEventDB.fs_id == fs.id)
        )
    ).scalars().all()
    seen = {r.event_type for r in rows}
    missing = [t for t in new_types if t not in seen]
    assert not missing, f"Audit events failed to persist: {missing}"


# ---------------------------------------------------------------------------
# Build router — register_file should emit FILE_REGISTERED, and
# update_build_state should emit BUILD_PHASE_CHANGED on phase change.
# ---------------------------------------------------------------------------


async def _seed_doc_with_build_state(
    test_db, *, status: BuildStatus = BuildStatus.RUNNING
) -> uuid.UUID:
    fs = FSDocument(filename="b.md", status=FSDocumentStatus.COMPLETE)
    test_db.add(fs)
    await test_db.commit()
    await test_db.refresh(fs)

    bs = BuildStateDB(
        document_id=fs.id,
        status=status,
        current_phase=1,
        total_tasks=3,
    )
    test_db.add(bs)
    await test_db.commit()
    return fs.id


async def _events_of(test_db, fs_id: uuid.UUID, t: AuditEventType) -> list[Any]:
    rows = (
        await test_db.execute(
            select(AuditEventDB).where(
                AuditEventDB.fs_id == fs_id,
                AuditEventDB.event_type == t,
            )
        )
    ).scalars().all()
    return list(rows)


@pytest.mark.asyncio
async def test_register_file_emits_file_registered_audit(client, test_db) -> None:
    fs_id = await _seed_doc_with_build_state(test_db)

    resp = await client.post(
        f"/api/fs/{fs_id}/file-registry",
        json={
            "task_id": str(uuid.uuid4()),
            "section_id": str(uuid.uuid4()),
            "file_path": "src/foo.py",
            "file_type": "code",
        },
    )
    assert resp.status_code == 200, resp.text

    events = await _events_of(test_db, fs_id, AuditEventType.FILE_REGISTERED)
    assert events, "FILE_REGISTERED must be emitted on successful register-file"

    file_rows = (
        await test_db.execute(
            select(FileRegistryDB).where(FileRegistryDB.document_id == fs_id)
        )
    ).scalars().all()
    assert len(file_rows) == 1


@pytest.mark.asyncio
async def test_update_build_state_emits_phase_change(client, test_db) -> None:
    fs_id = await _seed_doc_with_build_state(test_db)

    resp = await client.patch(
        f"/api/fs/{fs_id}/build-state",
        json={"current_phase": 4, "current_task_index": 0},
    )
    assert resp.status_code == 200, resp.text

    events = await _events_of(test_db, fs_id, AuditEventType.BUILD_PHASE_CHANGED)
    assert events, "BUILD_PHASE_CHANGED must fire when current_phase changes"


@pytest.mark.asyncio
async def test_update_build_state_emits_terminal_event(client, test_db) -> None:
    fs_id = await _seed_doc_with_build_state(test_db)

    resp = await client.patch(
        f"/api/fs/{fs_id}/build-state",
        json={"status": "COMPLETE"},
    )
    assert resp.status_code == 200, resp.text

    completed = await _events_of(test_db, fs_id, AuditEventType.BUILD_COMPLETED)
    assert completed, "BUILD_COMPLETED must fire when status flips to COMPLETE"


# ---------------------------------------------------------------------------
# Activity-log endpoint — fs_id and include_payload params must filter
# correctly and surface the new fields.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activity_log_supports_fs_id_and_payload_params(client, test_db) -> None:
    fs = FSDocument(filename="x.md", status=FSDocumentStatus.COMPLETE)
    test_db.add(fs)
    await test_db.commit()
    await test_db.refresh(fs)

    await log_audit_event(
        test_db,
        fs.id,
        AuditEventType.BUILD_STARTED,
        user_id="test",
        payload={"why": "smoke"},
    )
    await test_db.commit()

    resp = await client.get(
        "/api/activity-log",
        params={"fs_id": str(fs.id), "include_payload": "true"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data") or body
    entries = data.get("events") or data.get("entries") or []
    assert entries, "activity log should return the seeded event"
    types = {e["event_type"] for e in entries}
    assert "BUILD_STARTED" in types
    sample = next(e for e in entries if e["event_type"] == "BUILD_STARTED")
    assert sample.get("category") == "build"
    assert "payload" in sample and sample["payload"] == {"why": "smoke"}
