"""Tests for Build Engine endpoints — state, file registry, pre/post checks, snapshots, cache."""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FSDocument, FSDocumentStatus, FSTaskDB, TaskStatus

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def seeded_doc(test_db: AsyncSession) -> str:
    """Insert a minimal document + tasks so build endpoints work."""
    doc_id = uuid.uuid4()
    doc = FSDocument(
        id=doc_id,
        filename="test_build.txt",
        original_text="1. Auth\nUsers must log in.\n2. Dashboard\nShow stats.",
        parsed_text="1. Auth\nUsers must log in.\n2. Dashboard\nShow stats.",
        status=FSDocumentStatus.COMPLETE,
    )
    test_db.add(doc)
    for i, title in enumerate(["Auth login", "Dashboard stats"]):
        test_db.add(
            FSTaskDB(
                fs_id=doc_id,
                task_id=f"TASK-{i + 1}",
                title=title,
                description=f"Implement {title}",
                section_index=i,
                section_heading=f"Section {i}",
                depends_on=[],
                acceptance_criteria=["Done when tested"],
                effort="MEDIUM",
                tags=["backend"],
                order=i,
                status=TaskStatus.PENDING,
            )
        )
    await test_db.commit()
    return str(doc_id)


# ── Build State CRUD ──────────────────────────────────


async def test_create_build_state(client: AsyncClient, seeded_doc: str):
    r = await client.post(f"/api/fs/{seeded_doc}/build-state")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "PENDING"
    assert data["total_tasks"] == 2


async def test_get_build_state_empty(client: AsyncClient, seeded_doc: str):
    r = await client.get(f"/api/fs/{seeded_doc}/build-state")
    assert r.status_code == 200
    assert r.json()["data"] is None


async def test_update_build_state(client: AsyncClient, seeded_doc: str):
    await client.post(f"/api/fs/{seeded_doc}/build-state")
    r = await client.patch(
        f"/api/fs/{seeded_doc}/build-state",
        json={"status": "RUNNING", "current_phase": 4, "current_task_index": 1, "completed_task_id": "TASK-1"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "RUNNING"
    assert data["current_phase"] == 4
    assert "TASK-1" in data["completed_task_ids"]


async def test_build_state_reset(client: AsyncClient, seeded_doc: str):
    await client.post(f"/api/fs/{seeded_doc}/build-state")
    await client.patch(
        f"/api/fs/{seeded_doc}/build-state",
        json={"status": "RUNNING", "completed_task_id": "TASK-1"},
    )
    r = await client.post(f"/api/fs/{seeded_doc}/build-state")
    data = r.json()["data"]
    assert data["status"] == "PENDING"
    assert data["completed_task_ids"] == []


# ── File Registry CRUD ────────────────────────────────


async def test_register_file(client: AsyncClient, seeded_doc: str):
    r = await client.post(
        f"/api/fs/{seeded_doc}/file-registry",
        json={"task_id": "TASK-1", "section_id": "0", "file_path": "src/auth.py", "file_type": "api"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["file_path"] == "src/auth.py"


async def test_list_file_registry(client: AsyncClient, seeded_doc: str):
    await client.post(
        f"/api/fs/{seeded_doc}/file-registry",
        json={"task_id": "TASK-1", "section_id": "0", "file_path": "src/auth.py", "file_type": "api"},
    )
    await client.post(
        f"/api/fs/{seeded_doc}/file-registry",
        json={"task_id": "TASK-2", "section_id": "1", "file_path": "src/dash.py", "file_type": "component"},
    )
    r = await client.get(f"/api/fs/{seeded_doc}/file-registry")
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 2


async def test_filter_files_by_task(client: AsyncClient, seeded_doc: str):
    await client.post(
        f"/api/fs/{seeded_doc}/file-registry",
        json={"task_id": "TASK-1", "section_id": "0", "file_path": "src/auth.py", "file_type": "api"},
    )
    await client.post(
        f"/api/fs/{seeded_doc}/file-registry",
        json={"task_id": "TASK-2", "section_id": "1", "file_path": "src/dash.py", "file_type": "component"},
    )
    r = await client.get(f"/api/fs/{seeded_doc}/file-registry", params={"task_id": "TASK-1"})
    assert r.json()["data"]["total"] == 1
    assert r.json()["data"]["files"][0]["file_path"] == "src/auth.py"


# ── Pre-Build Check ───────────────────────────────────


async def test_pre_build_check(client: AsyncClient, seeded_doc: str):
    r = await client.get(f"/api/fs/{seeded_doc}/pre-build-check")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "go" in data
    assert "checks" in data
    assert "blockers" in data


# ── Post-Build Check ──────────────────────────────────


async def test_post_build_check_no_go(client: AsyncClient, seeded_doc: str):
    r = await client.get(f"/api/fs/{seeded_doc}/post-build-check")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["verdict"] == "NO-GO"
    assert len(data["gaps"]) > 0


# ── Snapshots + Rollback ──────────────────────────────


async def test_snapshot_and_rollback(client: AsyncClient, seeded_doc: str, test_db: AsyncSession):
    snap_r = await client.post(
        f"/api/fs/{seeded_doc}/snapshots",
        json={"reason": "pre-change test"},
    )
    assert snap_r.status_code == 200
    snap_id = snap_r.json()["data"]["snapshot_id"]

    await client.post(
        f"/api/fs/{seeded_doc}/file-registry",
        json={"task_id": "TASK-1", "section_id": "0", "file_path": "src/extra.py", "file_type": "util"},
    )
    files_r = await client.get(f"/api/fs/{seeded_doc}/file-registry")
    assert files_r.json()["data"]["total"] == 1

    rollback_r = await client.post(f"/api/fs/{seeded_doc}/snapshots/{snap_id}/rollback")
    assert rollback_r.status_code == 200
    assert rollback_r.json()["data"]["rolled_back"] is True

    files_after = await client.get(f"/api/fs/{seeded_doc}/file-registry")
    assert files_after.json()["data"]["total"] == 0


# ── Pipeline Cache ────────────────────────────────────


async def test_pipeline_cache_empty(client: AsyncClient, seeded_doc: str):
    r = await client.get(f"/api/fs/{seeded_doc}/pipeline-cache")
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 0


async def test_clear_pipeline_cache(client: AsyncClient, seeded_doc: str):
    r = await client.delete(f"/api/fs/{seeded_doc}/pipeline-cache")
    assert r.status_code == 200
    assert r.json()["data"]["cleared"] is True


# ── Task Context ──────────────────────────────────────


async def test_get_task_context(client: AsyncClient, seeded_doc: str):
    r = await client.get(f"/api/fs/{seeded_doc}/tasks/TASK-1/context")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["task"]["task_id"] == "TASK-1"
    assert data["task"]["acceptance_criteria"] == ["Done when tested"]
    assert "fs_section" in data
    assert "test_cases" in data
    assert "dependencies" in data
    assert "existing_files" in data


async def test_get_task_context_404(client: AsyncClient, seeded_doc: str):
    r = await client.get(f"/api/fs/{seeded_doc}/tasks/NONEXISTENT/context")
    assert r.status_code == 404


# ── Task Verification ─────────────────────────────────


async def test_verify_task_no_files(client: AsyncClient, seeded_doc: str):
    r = await client.get(f"/api/fs/{seeded_doc}/tasks/TASK-1/verify")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ready_for_complete"] is False
    assert data["passed_checks"] < data["total_checks"]


async def test_verify_task_with_files(client: AsyncClient, seeded_doc: str):
    await client.post(
        f"/api/fs/{seeded_doc}/file-registry",
        json={"task_id": "TASK-1", "section_id": "0", "file_path": "src/auth.py", "file_type": "api"},
    )
    await client.post(
        f"/api/fs/{seeded_doc}/file-registry",
        json={"task_id": "TASK-1", "section_id": "0", "file_path": "tests/test_auth.py", "file_type": "test"},
    )
    r = await client.get(f"/api/fs/{seeded_doc}/tasks/TASK-1/verify")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["passed_checks"] >= 2
