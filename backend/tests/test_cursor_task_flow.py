"""End-to-end coverage for the Cursor paste-per-action task lifecycle."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.db.models import (
    CodeUploadDB,
    CodeUploadStatus,
    FSDocument,
    FSDocumentStatus,
    FSVersion,
)

# ── generate_fs ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_fs_full_lifecycle(client: AsyncClient, test_db):
    resp = await client.post(
        "/api/cursor-tasks/generate-fs",
        json={"idea": "A tiny todo list"},
    )
    assert resp.status_code == 200, resp.text
    env = resp.json()["data"]
    task_id = env["task_id"]
    assert env["mode"] == "cursor_task"
    assert env["kind"] == "generate_fs"
    assert env["status"] == "pending"
    assert env["prompt"].strip()

    claim = await client.post(f"/api/cursor-tasks/{task_id}/claim")
    assert claim.status_code == 200, claim.text
    assert claim.json()["data"]["status"] == "claimed"

    fs_markdown = "# Todo FS\n\n## Goals\nBuild a tiny todo list for one user."
    submit = await client.post(
        f"/api/cursor-tasks/{task_id}/submit/generate-fs",
        json={"fs_markdown": fs_markdown},
    )
    assert submit.status_code == 200, submit.text
    poll = submit.json()["data"]
    assert poll["status"] == "done"
    assert poll["result_ref"], "result_ref should point to the new FSDocument"

    # FSDocument should exist in PARSED state
    from sqlalchemy import select

    row = await test_db.execute(select(FSDocument).where(FSDocument.id == uuid.UUID(poll["result_ref"])))
    doc = row.scalar_one_or_none()
    assert doc is not None
    assert doc.status == FSDocumentStatus.PARSED
    assert doc.parsed_text == fs_markdown

    # Poll endpoint returns the final state
    final = await client.get(f"/api/cursor-tasks/{task_id}")
    assert final.json()["data"]["status"] == "done"


# ── analyze ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_full_lifecycle(client: AsyncClient, test_db):
    doc = FSDocument(
        id=uuid.uuid4(),
        filename="spec.md",
        original_text="# Spec\nBuild a todo app.",
        parsed_text="# Spec\nBuild a todo app.",
        status=FSDocumentStatus.PARSED,
        file_size=30,
        content_type="text/markdown",
    )
    test_db.add(doc)
    await test_db.commit()

    resp = await client.post(f"/api/cursor-tasks/analyze/{doc.id}")
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["data"]["task_id"]

    await client.post(f"/api/cursor-tasks/{task_id}/claim")

    payload = {
        "quality_score": {
            "overall": 85,
            "clarity": 80,
            "completeness": 90,
            "consistency": 85,
            "risks": [],
        },
        "ambiguities": [
            {
                "section_index": 0,
                "section_heading": "Spec",
                "flagged_text": "build",
                "reason": "vague",
                "severity": "LOW",
                "clarification_question": "Which platforms?",
            }
        ],
        "contradictions": [],
        "edge_cases": [],
        "tasks": [
            {
                "title": "Implement CRUD",
                "description": "Build todo CRUD endpoints.",
                "section_index": 0,
                "section_heading": "Spec",
                "depends_on": [],
                "acceptance_criteria": ["Can create", "Can delete"],
                "effort": "MEDIUM",
                "tags": ["backend"],
                "can_parallel": False,
            }
        ],
    }
    submit = await client.post(
        f"/api/cursor-tasks/{task_id}/submit/analyze",
        json={"payload": payload},
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["data"]["status"] == "done"

    # Verify the ambiguity/ task landed on the document
    from sqlalchemy import select

    from app.db.models import AmbiguityFlagDB, FSTaskDB

    amb_rows = await test_db.execute(select(AmbiguityFlagDB).where(AmbiguityFlagDB.fs_id == doc.id))
    assert len(amb_rows.scalars().all()) == 1
    task_rows = await test_db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc.id))
    assert len(task_rows.scalars().all()) == 1


# ── reverse_fs ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reverse_fs_full_lifecycle(client: AsyncClient, test_db):
    upload = CodeUploadDB(
        id=uuid.uuid4(),
        filename="repo.zip",
        zip_path="/tmp/repo.zip",
        status=CodeUploadStatus.PARSED,
        file_size=2048,
        primary_language="python",
        total_files=2,
        total_lines=40,
        languages={"python": 2},
        snapshot_data={
            "files": [
                {"path": "a.py", "language": "python", "content": "print('a')"},
                {"path": "b.py", "language": "python", "content": "print('b')"},
            ]
        },
    )
    test_db.add(upload)
    await test_db.commit()

    resp = await client.post(f"/api/cursor-tasks/reverse-fs/{upload.id}")
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["data"]["task_id"]

    await client.post(f"/api/cursor-tasks/{task_id}/claim")

    body = {
        "fs_markdown": "# Reverse FS\n\n## Summary\nTwo python files printing characters.",
        "report": {
            "coverage": 0.9,
            "confidence": 0.8,
            "primary_language": "python",
            "modules": [{"name": "a", "purpose": "prints"}],
            "user_flows": [],
            "gaps": [],
            "notes": "ok",
        },
    }
    submit = await client.post(
        f"/api/cursor-tasks/{task_id}/submit/reverse-fs",
        json=body,
    )
    assert submit.status_code == 200, submit.text
    poll = submit.json()["data"]
    assert poll["status"] == "done"
    assert poll["result_ref"]

    # CodeUpload should be GENERATED and linked to the new FSDocument
    await test_db.refresh(upload)
    assert upload.status == CodeUploadStatus.GENERATED
    assert upload.generated_fs_id is not None


# ── refine ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refine_full_lifecycle(client: AsyncClient, test_db):
    doc = FSDocument(
        id=uuid.uuid4(),
        filename="spec.md",
        original_text="# Spec\nBuild a vague thing.",
        parsed_text="# Spec\nBuild a vague thing.",
        status=FSDocumentStatus.PARSED,
        file_size=40,
        content_type="text/markdown",
    )
    test_db.add(doc)
    await test_db.commit()

    resp = await client.post(f"/api/cursor-tasks/refine/{doc.id}")
    assert resp.status_code == 200, resp.text
    env = resp.json()["data"]
    assert env["kind"] == "refine"
    task_id = env["task_id"]

    await client.post(f"/api/cursor-tasks/{task_id}/claim")

    refined = "# Spec (refined)\n\n## Goals\nA todo app that supports create, list, and delete tasks.\n"
    submit = await client.post(
        f"/api/cursor-tasks/{task_id}/submit/refine",
        json={
            "refined_markdown": refined,
            "summary": "Clarified goals and scope.",
            "changed_sections": ["Goals"],
        },
    )
    assert submit.status_code == 200, submit.text
    poll = submit.json()["data"]
    assert poll["status"] == "done"
    assert poll["result_ref"]

    from sqlalchemy import select

    row = await test_db.execute(select(FSDocument).where(FSDocument.id == uuid.UUID(poll["result_ref"])))
    new_doc = row.scalar_one_or_none()
    assert new_doc is not None
    assert new_doc.status == FSDocumentStatus.PARSED
    assert new_doc.parsed_text == refined


# ── impact ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_impact_full_lifecycle(client: AsyncClient, test_db):
    doc = FSDocument(
        id=uuid.uuid4(),
        filename="spec.md",
        original_text="# Spec\n## Goals\nOld goals.",
        parsed_text="# Spec\n## Goals\nOld goals.",
        status=FSDocumentStatus.PARSED,
        file_size=40,
        content_type="text/markdown",
    )
    test_db.add(doc)
    await test_db.commit()
    version = FSVersion(
        id=uuid.uuid4(),
        fs_id=doc.id,
        version_number=2,
        parsed_text="# Spec\n## Goals\nNew goals with more detail.",
    )
    test_db.add(version)
    await test_db.commit()

    resp = await client.post(f"/api/cursor-tasks/impact/{version.id}")
    assert resp.status_code == 200, resp.text
    env = resp.json()["data"]
    assert env["kind"] == "impact"
    task_id = env["task_id"]

    await client.post(f"/api/cursor-tasks/{task_id}/claim")

    payload = {
        "fs_changes": [
            {
                "change_type": "MODIFIED",
                "section_id": "goals",
                "section_heading": "Goals",
                "section_index": 1,
                "old_text": "Old goals.",
                "new_text": "New goals with more detail.",
            }
        ],
        "task_impacts": [
            {
                "task_id": "T1",
                "task_title": "Implement goals",
                "impact_type": "REQUIRES_REVIEW",
                "reason": "Goals clarified.",
                "change_section": "Goals",
            }
        ],
        "rework_estimate": {
            "invalidated_count": 0,
            "review_count": 1,
            "unaffected_count": 0,
            "total_rework_days": 0.5,
            "affected_sections": ["Goals"],
            "changes_summary": "Goals section rewritten.",
        },
    }
    submit = await client.post(
        f"/api/cursor-tasks/{task_id}/submit/impact",
        json={"payload": payload},
    )
    assert submit.status_code == 200, submit.text
    poll = submit.json()["data"]
    assert poll["status"] == "done"
    assert poll["result_ref"] == str(version.id)

    from sqlalchemy import select

    from app.db.models import FSChangeDB, ReworkEstimateDB, TaskImpactDB

    ch = await test_db.execute(select(FSChangeDB).where(FSChangeDB.version_id == version.id))
    assert len(ch.scalars().all()) == 1
    ti = await test_db.execute(select(TaskImpactDB).where(TaskImpactDB.version_id == version.id))
    assert len(ti.scalars().all()) == 1
    rw = await test_db.execute(select(ReworkEstimateDB).where(ReworkEstimateDB.version_id == version.id))
    assert len(rw.scalars().all()) == 1


# ── failures + TTL ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fail_cursor_task_marks_failed(client: AsyncClient):
    resp = await client.post(
        "/api/cursor-tasks/generate-fs",
        json={"idea": "Something tiny"},
    )
    task_id = resp.json()["data"]["task_id"]

    fail = await client.post(
        f"/api/cursor-tasks/{task_id}/fail",
        json={"error": "Cursor could not complete"},
    )
    assert fail.status_code == 200, fail.text
    data = fail.json()["data"]
    assert data["status"] == "failed"
    assert "could not complete" in (data["error"] or "")


@pytest.mark.asyncio
async def test_cancel_marks_task_expired(client: AsyncClient):
    """User-triggered cancel is the UI path equivalent to a TTL expiration."""
    resp = await client.post(
        "/api/cursor-tasks/generate-fs",
        json={"idea": "A tiny thing"},
    )
    task_id = resp.json()["data"]["task_id"]

    cancel = await client.post(f"/api/cursor-tasks/{task_id}/cancel")
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["data"]["status"] == "expired"


@pytest.mark.asyncio
async def test_submit_wrong_kind_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/cursor-tasks/generate-fs",
        json={"idea": "Something tiny"},
    )
    task_id = resp.json()["data"]["task_id"]

    # Attempt to submit an analyze payload to a generate_fs task
    bad = await client.post(
        f"/api/cursor-tasks/{task_id}/submit/analyze",
        json={
            "payload": {"quality_score": {"overall": 1, "clarity": 1, "completeness": 1, "consistency": 1, "risks": []}}
        },
    )
    assert bad.status_code == 400, bad.text
