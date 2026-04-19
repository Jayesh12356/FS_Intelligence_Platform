"""Build Engine API — state persistence, file registry, pre/post checks, snapshots, cache."""

import asyncio
import json
import logging
import os
import tempfile
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.audit import log_audit_event
from app.db.base import get_db
from app.db.models import (
    AmbiguityFlagDB,
    AmbiguitySeverity,
    AuditEventType,
    BuildSnapshotDB,
    BuildStateDB,
    BuildStatus,
    ContradictionDB,
    EdgeCaseGapDB,
    FileRegistryDB,
    FSDocument,
    FSTaskDB,
    MCPSessionDB,
    MCPSessionEventDB,
    PipelineCacheDB,
    TaskStatus,
    TestCaseDB,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fs", tags=["build-engine"])


# ── Addition 1: Build State ────────────────────────────


@router.post("/{doc_id}/build-state")
async def create_or_reset_build_state(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(select(BuildStateDB).where(BuildStateDB.document_id == doc_id))).scalar_one_or_none()
    if existing:
        existing.status = BuildStatus.PENDING
        existing.current_phase = 0
        existing.current_task_index = 0
        existing.completed_task_ids = []
        existing.failed_task_ids = []
        existing.started_at = None
        existing.last_updated = datetime.now(UTC)
    else:
        tasks_count = (await db.execute(select(func.count(FSTaskDB.id)).where(FSTaskDB.fs_id == doc_id))).scalar() or 0
        existing = BuildStateDB(
            document_id=doc_id,
            total_tasks=tasks_count,
        )
        db.add(existing)
    await db.commit()
    await db.refresh(existing)
    return {"data": _build_state_dict(existing)}


@router.get("/{doc_id}/build-state")
async def get_build_state(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(BuildStateDB).where(BuildStateDB.document_id == doc_id))).scalar_one_or_none()
    if not row:
        return {"data": None}
    return {"data": _build_state_dict(row)}


@router.patch("/{doc_id}/build-state")
async def update_build_state(
    doc_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(BuildStateDB).where(BuildStateDB.document_id == doc_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "No build state found — call POST first")
    prev_phase = row.current_phase
    prev_status = row.status
    if "current_phase" in body:
        row.current_phase = int(body["current_phase"])
    if "current_task_index" in body:
        row.current_task_index = int(body["current_task_index"])
    if "status" in body:
        row.status = BuildStatus(body["status"])
    completed_added = None
    if body.get("completed_task_id"):
        done = list(row.completed_task_ids or [])
        tid = str(body["completed_task_id"])
        if tid not in done:
            done.append(tid)
            completed_added = tid
        row.completed_task_ids = done
    if body.get("failed_task_id"):
        failed = list(row.failed_task_ids or [])
        tid = str(body["failed_task_id"])
        if tid not in failed:
            failed.append(tid)
        row.failed_task_ids = failed
    if "stack" in body:
        row.stack = body["stack"]
    if "output_folder" in body:
        row.output_folder = body["output_folder"]
    if "total_tasks" in body:
        row.total_tasks = int(body["total_tasks"])
    if row.status == BuildStatus.RUNNING and not row.started_at:
        row.started_at = datetime.now(UTC)
    row.last_updated = datetime.now(UTC)

    if row.current_phase != prev_phase:
        try:
            await log_audit_event(
                db,
                doc_id,
                AuditEventType.BUILD_PHASE_CHANGED,
                user_id="agent",
                payload={
                    "from_phase": prev_phase,
                    "to_phase": row.current_phase,
                    "current_task_index": row.current_task_index,
                    "total_tasks": row.total_tasks,
                },
            )
        except Exception:
            logger.exception("audit emit failed for BUILD_PHASE_CHANGED doc=%s", doc_id)
    if completed_added:
        try:
            task = (
                await db.execute(
                    select(FSTaskDB).where(
                        FSTaskDB.fs_id == doc_id,
                        FSTaskDB.task_id == completed_added,
                    )
                )
            ).scalar_one_or_none()
            await log_audit_event(
                db,
                doc_id,
                AuditEventType.BUILD_TASK_COMPLETED,
                user_id="agent",
                payload={
                    "task_id": completed_added,
                    "task_title": (task.title if task else "")[:200],
                    "completed_count": len(row.completed_task_ids or []),
                    "total_tasks": row.total_tasks,
                },
            )
        except Exception:
            logger.exception("audit emit failed for BUILD_TASK_COMPLETED doc=%s", doc_id)
    if prev_status != row.status and row.status in (BuildStatus.COMPLETE, BuildStatus.FAILED):
        evt = (
            AuditEventType.BUILD_COMPLETED
            if row.status == BuildStatus.COMPLETE
            else AuditEventType.BUILD_FAILED
        )
        try:
            await log_audit_event(
                db,
                doc_id,
                evt,
                user_id="agent",
                payload={
                    "completed_tasks": len(row.completed_task_ids or []),
                    "failed_tasks": len(row.failed_task_ids or []),
                    "total_tasks": row.total_tasks,
                    "stack": row.stack or "",
                    "output_folder": row.output_folder or "",
                    "source": "agent_update",
                },
            )
        except Exception:
            logger.exception("audit emit failed for build finalize doc=%s", doc_id)

    await db.commit()
    await db.refresh(row)
    return {"data": _build_state_dict(row)}


def _build_state_dict(row: BuildStateDB) -> dict:
    return {
        "id": str(row.id),
        "document_id": str(row.document_id),
        "status": row.status.value if row.status else "PENDING",
        "current_phase": row.current_phase,
        "current_task_index": row.current_task_index,
        "completed_task_ids": row.completed_task_ids or [],
        "failed_task_ids": row.failed_task_ids or [],
        "total_tasks": row.total_tasks,
        "stack": row.stack,
        "output_folder": row.output_folder,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "last_updated": row.last_updated.isoformat() if row.last_updated else None,
    }


# ── Addition 2: File Registry ──────────────────────────


@router.post("/{doc_id}/file-registry")
async def register_file(
    doc_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    entry = FileRegistryDB(
        document_id=doc_id,
        task_id=body.get("task_id", ""),
        section_id=body.get("section_id", ""),
        file_path=body.get("file_path", ""),
        file_type=body.get("file_type", "unknown"),
        status="CREATED",
    )
    db.add(entry)
    try:
        await log_audit_event(
            db,
            doc_id,
            AuditEventType.FILE_REGISTERED,
            user_id="agent",
            payload={
                "file_path": entry.file_path,
                "file_type": entry.file_type,
                "task_id": entry.task_id,
                "section_id": entry.section_id,
            },
        )
    except Exception:
        logger.exception("audit emit failed for FILE_REGISTERED doc=%s", doc_id)
    await db.commit()
    await db.refresh(entry)
    return {"data": _file_dict(entry)}


@router.get("/{doc_id}/file-registry")
async def list_file_registry(
    doc_id: uuid.UUID,
    task_id: str = Query(None),
    section_id: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(FileRegistryDB).where(FileRegistryDB.document_id == doc_id)
    if task_id:
        q = q.where(FileRegistryDB.task_id == task_id)
    if section_id:
        q = q.where(FileRegistryDB.section_id == section_id)
    rows = (await db.execute(q.order_by(FileRegistryDB.created_at))).scalars().all()
    return {"data": {"files": [_file_dict(r) for r in rows], "total": len(rows)}}


def _file_dict(row: FileRegistryDB) -> dict:
    return {
        "id": str(row.id),
        "document_id": str(row.document_id),
        "task_id": row.task_id,
        "section_id": row.section_id,
        "file_path": row.file_path,
        "file_type": row.file_type,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ── Task Context (rich single-call payload) ────────────


@router.get("/{doc_id}/tasks/{task_id}/context")
async def get_task_context(
    doc_id: uuid.UUID,
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    task = (
        await db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.task_id == task_id))
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    doc = (await db.execute(select(FSDocument).where(FSDocument.id == doc_id))).scalar_one_or_none()
    text = (doc.parsed_text or doc.original_text or "") if doc else ""

    section_text = ""
    try:
        from app.parsers.chunker import chunk_text_into_sections

        for s in chunk_text_into_sections(text):
            if s.get("section_index") == task.section_index:
                section_text = s.get("content", "")
                break
    except Exception:
        pass

    test_cases = (
        (await db.execute(select(TestCaseDB).where(TestCaseDB.fs_id == doc_id, TestCaseDB.task_id == task_id)))
        .scalars()
        .all()
    )

    dep_tasks = []
    for dep_id in task.depends_on or []:
        dep = (
            await db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.task_id == dep_id))
        ).scalar_one_or_none()
        if dep:
            dep_tasks.append(
                {
                    "task_id": dep.task_id,
                    "title": dep.title,
                    "status": dep.status.value if dep.status else "PENDING",
                }
            )

    files = (
        (
            await db.execute(
                select(FileRegistryDB).where(
                    FileRegistryDB.document_id == doc_id,
                    FileRegistryDB.task_id == task_id,
                )
            )
        )
        .scalars()
        .all()
    )

    build = (await db.execute(select(BuildStateDB).where(BuildStateDB.document_id == doc_id))).scalar_one_or_none()

    return {
        "data": {
            "task": {
                "task_id": task.task_id,
                "title": task.title,
                "description": task.description,
                "section_index": task.section_index,
                "section_heading": task.section_heading,
                "effort": task.effort.value if task.effort else "UNKNOWN",
                "tags": task.tags or [],
                "acceptance_criteria": task.acceptance_criteria or [],
                "depends_on": task.depends_on or [],
                "status": task.status.value if task.status else "PENDING",
            },
            "fs_section": {
                "heading": task.section_heading,
                "section_index": task.section_index,
                "content": section_text,
            },
            "test_cases": [
                {
                    "title": tc.title,
                    "steps": tc.steps or [],
                    "expected_result": tc.expected_result,
                    "test_type": tc.test_type.value if tc.test_type else "UNIT",
                }
                for tc in test_cases
            ],
            "dependencies": dep_tasks,
            "existing_files": [_file_dict(f) for f in files],
            "stack": build.stack if build else "",
        }
    }


# ── Task Completion Verification ───────────────────────


@router.get("/{doc_id}/tasks/{task_id}/verify")
async def verify_task_completion(
    doc_id: uuid.UUID,
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    task = (
        await db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.task_id == task_id))
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    checks: list[dict] = []

    files = (
        (
            await db.execute(
                select(FileRegistryDB).where(
                    FileRegistryDB.document_id == doc_id,
                    FileRegistryDB.task_id == task_id,
                )
            )
        )
        .scalars()
        .all()
    )
    checks.append(
        {
            "criterion": "At least one file registered",
            "pass": len(files) > 0,
            "detail": f"{len(files)} files registered",
        }
    )

    test_count = (
        await db.execute(
            select(func.count(TestCaseDB.id)).where(
                TestCaseDB.fs_id == doc_id,
                TestCaseDB.task_id == task_id,
            )
        )
    ).scalar() or 0
    has_test_file = any(f.file_type == "test" for f in files)
    checks.append(
        {
            "criterion": "Test coverage exists",
            "pass": test_count > 0 or has_test_file,
            "detail": f"{test_count} test cases, {sum(1 for f in files if f.file_type == 'test')} test files",
        }
    )

    for dep_id in task.depends_on or []:
        dep = (
            await db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.task_id == dep_id))
        ).scalar_one_or_none()
        dep_complete = dep and dep.status and dep.status.value == "COMPLETE"
        checks.append(
            {
                "criterion": f"Dependency {dep_id} is COMPLETE",
                "pass": dep_complete,
                "detail": f"Status: {dep.status.value if dep and dep.status else 'MISSING'}",
            }
        )

    for _idx, criterion in enumerate(task.acceptance_criteria or []):
        checks.append(
            {
                "criterion": f"Acceptance: {criterion[:80]}",
                "pass": len(files) > 0,
                "detail": "Files exist (manual verification recommended)",
            }
        )

    all_pass = all(c["pass"] for c in checks)
    if all_pass:
        try:
            await log_audit_event(
                db,
                doc_id,
                AuditEventType.BUILD_TASK_COMPLETED,
                user_id="agent",
                payload={
                    "task_id": task_id,
                    "task_title": (task.title or "")[:200],
                    "verdict": "GO",
                    "passed_checks": len(checks),
                    "source": "verify",
                },
            )
            await db.commit()
        except Exception:
            logger.exception("audit emit failed for verify_task_completion doc=%s", doc_id)
    return {
        "data": {
            "task_id": task_id,
            "ready_for_complete": all_pass,
            "checks": checks,
            "total_checks": len(checks),
            "passed_checks": sum(1 for c in checks if c["pass"]),
        }
    }


# ── Addition 3: Smart FS Change Placement ──────────────


@router.post("/{doc_id}/place-requirement")
async def place_requirement(
    doc_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    new_requirement = (body.get("new_requirement") or "").strip()
    if not new_requirement:
        raise HTTPException(400, "new_requirement is required")

    doc = (await db.execute(select(FSDocument).where(FSDocument.id == doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    text = (doc.parsed_text or doc.original_text or "").strip()
    if not text:
        raise HTTPException(400, "Document has no parsed content")

    from app.parsers.chunker import chunk_text_into_sections

    sections = chunk_text_into_sections(text)

    best_section = None
    best_score = 0.0
    req_words = set(w.lower() for w in new_requirement.split() if len(w) > 2)

    for s in sections:
        section_words = set(w.lower() for w in (s.get("content") or "").split() if len(w) > 2)
        overlap = len(req_words & section_words)
        score = overlap / max(len(req_words), 1)
        if score > best_score:
            best_score = score
            best_section = {"section_index": s.get("section_index", 0), "heading": s.get("heading", "")}

    if not best_section and sections:
        last = sections[-1]
        best_section = {"section_index": last.get("section_index", 0), "heading": last.get("heading", "")}
        best_score = 0.1

    section_idx = best_section.get("section_index", 0) if best_section else 0

    affected_tasks_result = (
        (await db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.section_index == section_idx)))
        .scalars()
        .all()
    )
    affected = [{"task_id": t.task_id, "title": t.title} for t in affected_tasks_result]

    return {
        "data": {
            "best_section": best_section,
            "similarity_score": best_score,
            "affected_tasks": affected,
            "insertion_position": f"After section {section_idx}",
        }
    }


# ── Addition 4: Pre-Build Validator ────────────────────


@router.get("/{doc_id}/pre-build-check")
async def pre_build_check(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    doc = (await db.execute(select(FSDocument).where(FSDocument.id == doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    checks: dict = {}
    blockers: list[str] = []
    warnings: list[str] = []

    from app.parsers.chunker import chunk_text_into_sections
    from app.pipeline.nodes.quality_node import compute_quality_score

    text = (doc.parsed_text or doc.original_text or "").strip()
    try:
        total_sections = max(len(chunk_text_into_sections(text)), 1) if text else 1
    except Exception:
        total_sections = 1

    amb_rows = (
        (
            await db.execute(
                select(AmbiguityFlagDB).where(AmbiguityFlagDB.fs_id == doc_id, AmbiguityFlagDB.resolved.is_(False))
            )
        )
        .scalars()
        .all()
    )
    con_rows = (
        (
            await db.execute(
                select(ContradictionDB).where(ContradictionDB.fs_id == doc_id, ContradictionDB.resolved.is_(False))
            )
        )
        .scalars()
        .all()
    )
    edge_rows = (
        (
            await db.execute(
                select(EdgeCaseGapDB).where(EdgeCaseGapDB.fs_id == doc_id, EdgeCaseGapDB.resolved.is_(False))
            )
        )
        .scalars()
        .all()
    )

    score = compute_quality_score(
        total_sections=total_sections,
        ambiguities=[{"section_index": a.section_index} for a in amb_rows],
        contradictions=[{"section_a_index": c.section_a_index} for c in con_rows],
        edge_cases=[{"section_index": e.section_index} for e in edge_rows],
    )

    quality_pass = score.overall >= 90.0
    checks["quality"] = {"pass": quality_pass, "score": score.overall}
    if not quality_pass:
        blockers.append(f"Quality score {score.overall} < 90")

    high_open = [a for a in amb_rows if a.severity == AmbiguitySeverity.HIGH]
    checks["ambiguities"] = {"pass": len(high_open) == 0, "open_high_count": len(high_open)}
    if high_open:
        blockers.append(f"{len(high_open)} open HIGH ambiguities")

    checks["contradictions"] = {"pass": len(con_rows) == 0, "open_count": len(con_rows)}
    if con_rows:
        blockers.append(f"{len(con_rows)} open contradictions")

    tasks_result = (await db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc_id))).scalars().all()
    task_sections = {t.section_index for t in tasks_result}
    try:
        all_sections = chunk_text_into_sections(text) if text else []
    except Exception:
        all_sections = []
    uncovered = [
        s.get("heading", f"Section {s.get('section_index', '?')}")
        for s in all_sections
        if s.get("section_index") not in task_sections
    ]
    checks["section_coverage"] = {"pass": len(uncovered) == 0, "uncovered": uncovered}
    if uncovered:
        warnings.append(f"{len(uncovered)} sections have no tasks")

    deps = {}
    for t in tasks_result:
        deps[t.task_id] = t.depends_on or []

    has_cycle = False
    visited: set[str] = set()
    path: set[str] = set()

    def _dfs(node: str) -> bool:
        if node in path:
            return True
        if node in visited:
            return False
        visited.add(node)
        path.add(node)
        for dep in deps.get(node, []):
            if _dfs(dep):
                return True
        path.discard(node)
        return False

    for tid in deps:
        if _dfs(tid):
            has_cycle = True
            break
    checks["dependency_cycles"] = {"pass": not has_cycle}
    if has_cycle:
        blockers.append("Dependency graph has cycles")

    from app.llm import get_llm_client

    try:
        llm_ok = await get_llm_client().check_health()
    except Exception:
        llm_ok = False
    checks["llm_health"] = {"pass": llm_ok}
    if not llm_ok:
        blockers.append("LLM provider not responding")

    go = len(blockers) == 0
    return {"data": {"go": go, "checks": checks, "blockers": blockers, "warnings": warnings}}


# ── Addition 5: Post-Build Verifier ────────────────────


@router.get("/{doc_id}/post-build-check")
async def post_build_check(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    doc = (await db.execute(select(FSDocument).where(FSDocument.id == doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    gaps: list[str] = []

    tasks = (await db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc_id))).scalars().all()
    files = (await db.execute(select(FileRegistryDB).where(FileRegistryDB.document_id == doc_id))).scalars().all()

    from app.parsers.chunker import chunk_text_into_sections

    text = (doc.parsed_text or doc.original_text or "").strip()
    try:
        all_sections = chunk_text_into_sections(text) if text else []
        section_indices = {s.get("section_index", 0) for s in all_sections}
    except Exception:
        section_indices = {t.section_index for t in tasks}

    file_task_ids = {f.task_id for f in files}
    file_section_ids = {f.section_id for f in files}

    sections_with_files = sum(1 for si in section_indices if str(si) in file_section_ids)
    total_sections = len(section_indices)
    checks_sections = f"{sections_with_files}/{total_sections}"
    if sections_with_files < total_sections:
        gaps.append(f"{total_sections - sections_with_files} sections have no registered files")

    complete_tasks = sum(1 for t in tasks if t.status and t.status.value == "COMPLETE")
    total_tasks = len(tasks)
    checks_tasks = f"{complete_tasks}/{total_tasks}"
    if complete_tasks < total_tasks:
        gaps.append(f"{total_tasks - complete_tasks} tasks not COMPLETE")

    tasks_with_files = sum(1 for t in tasks if t.task_id in file_task_ids)
    if tasks_with_files < total_tasks:
        gaps.append(f"{total_tasks - tasks_with_files} tasks have no registered files")

    test_files = [f for f in files if f.file_type == "test"]
    test_cases = (await db.execute(select(func.count(TestCaseDB.id)).where(TestCaseDB.fs_id == doc_id))).scalar() or 0
    test_ok = len(test_files) > 0 or test_cases > 0
    if not test_ok:
        gaps.append("No test files or test cases registered")

    orphaned = [f.file_path for f in files if f.task_id and f.task_id not in {t.task_id for t in tasks}]
    if orphaned:
        gaps.append(f"{len(orphaned)} orphaned files (task deleted)")

    from app.pipeline.nodes.quality_node import compute_quality_score

    amb_count = (
        await db.execute(
            select(func.count(AmbiguityFlagDB.id)).where(
                AmbiguityFlagDB.fs_id == doc_id, AmbiguityFlagDB.resolved.is_(False)
            )
        )
    ).scalar() or 0
    con_count = (
        await db.execute(
            select(func.count(ContradictionDB.id)).where(
                ContradictionDB.fs_id == doc_id, ContradictionDB.resolved.is_(False)
            )
        )
    ).scalar() or 0
    q = compute_quality_score(
        total_sections=max(total_sections, 1),
        ambiguities=[{"section_index": 0}] * amb_count,
        contradictions=[{"section_a_index": 0}] * con_count,
        edge_cases=[],
    )
    if q.overall < 90.0:
        gaps.append(f"Quality regressed to {q.overall}")

    verdict = "GO" if not gaps else "NO-GO"
    return {
        "data": {
            "verdict": verdict,
            "score": q.overall,
            "coverage": {
                "sections_with_files": checks_sections,
                "tasks_complete": checks_tasks,
                "test_files_exist": test_ok,
                "orphaned_files": orphaned,
            },
            "gaps": gaps,
            "export_ready": verdict == "GO",
        }
    }


# ── Addition 6: Build Snapshots ────────────────────────


@router.post("/{doc_id}/snapshots")
async def create_snapshot(
    doc_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    files = (await db.execute(select(FileRegistryDB).where(FileRegistryDB.document_id == doc_id))).scalars().all()
    tasks = (await db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc_id))).scalars().all()

    from app.pipeline.nodes.quality_node import compute_quality_score

    doc = (await db.execute(select(FSDocument).where(FSDocument.id == doc_id))).scalar_one_or_none()
    text = (doc.parsed_text or doc.original_text or "").strip() if doc else ""
    try:
        from app.parsers.chunker import chunk_text_into_sections

        ts = max(len(chunk_text_into_sections(text)), 1) if text else 1
    except Exception:
        ts = 1
    amb_count = (
        await db.execute(
            select(func.count(AmbiguityFlagDB.id)).where(
                AmbiguityFlagDB.fs_id == doc_id, AmbiguityFlagDB.resolved.is_(False)
            )
        )
    ).scalar() or 0
    q = compute_quality_score(
        total_sections=ts,
        ambiguities=[{"section_index": 0}] * amb_count,
        contradictions=[],
        edge_cases=[],
    )

    snap = BuildSnapshotDB(
        document_id=doc_id,
        snapshot_reason=body.get("reason", "manual"),
        quality_score_at_snapshot=q.overall,
        file_registry_snapshot=[_file_dict(f) for f in files],
        task_states_snapshot=[
            {"task_id": t.task_id, "status": t.status.value if t.status else "PENDING"} for t in tasks
        ],
    )
    db.add(snap)
    await db.commit()
    await db.refresh(snap)
    return {"data": {"snapshot_id": str(snap.id), "quality_score": q.overall, "files_count": len(files)}}


@router.post("/{doc_id}/snapshots/{snapshot_id}/rollback")
async def rollback_to_snapshot(
    doc_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    snap = (
        await db.execute(
            select(BuildSnapshotDB).where(
                BuildSnapshotDB.id == snapshot_id,
                BuildSnapshotDB.document_id == doc_id,
            )
        )
    ).scalar_one_or_none()
    if not snap:
        raise HTTPException(404, "Snapshot not found")

    for ts in snap.task_states_snapshot or []:
        task_row = (
            await db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.task_id == ts.get("task_id")))
        ).scalar_one_or_none()
        if task_row:
            try:
                task_row.status = TaskStatus(ts.get("status", "PENDING"))
            except ValueError:
                task_row.status = TaskStatus.PENDING

    await db.execute(delete(FileRegistryDB).where(FileRegistryDB.document_id == doc_id))
    for fsnap in snap.file_registry_snapshot or []:
        db.add(
            FileRegistryDB(
                document_id=doc_id,
                task_id=fsnap.get("task_id", ""),
                section_id=fsnap.get("section_id", ""),
                file_path=fsnap.get("file_path", ""),
                file_type=fsnap.get("file_type", "unknown"),
                status=fsnap.get("status", "CREATED"),
            )
        )

    await db.commit()
    return {
        "data": {
            "rolled_back": True,
            "snapshot_id": str(snapshot_id),
            "quality_at_snapshot": snap.quality_score_at_snapshot,
        }
    }


# ── Addition 7: Pipeline Cache ─────────────────────────


@router.get("/{doc_id}/pipeline-cache")
async def list_pipeline_cache(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(PipelineCacheDB).where(PipelineCacheDB.document_id == doc_id))).scalars().all()
    return {
        "data": {
            "entries": [
                {
                    "node_name": r.node_name,
                    "input_hash": r.input_hash,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                }
                for r in rows
            ],
            "total": len(rows),
        }
    }


@router.delete("/{doc_id}/pipeline-cache")
async def clear_pipeline_cache(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(delete(PipelineCacheDB).where(PipelineCacheDB.document_id == doc_id))
    await db.commit()
    return {"data": {"cleared": True, "rows_deleted": result.rowcount}}


# ── Build Prompt Generator ─────────────────────────────


@router.get("/{doc_id}/build-prompt")
async def get_build_prompt(
    doc_id: uuid.UUID,
    stack: str = Query("Next.js + FastAPI"),
    output_folder: str = Query("./output"),
    db: AsyncSession = Depends(get_db),
):
    doc = (await db.execute(select(FSDocument).where(FSDocument.id == doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    tasks = (await db.execute(select(FSTaskDB).where(FSTaskDB.fs_id == doc_id))).scalars().all()

    from app.parsers.section_extractor import extract_sections_from_text

    text = (doc.parsed_text or doc.original_text or "").strip()
    try:
        section_count = len(extract_sections_from_text(text)) if text else 0
    except Exception:
        section_count = 0

    from app.pipeline.nodes.quality_node import compute_quality_score

    amb_rows = (
        (
            await db.execute(
                select(AmbiguityFlagDB).where(
                    AmbiguityFlagDB.fs_id == doc_id,
                    AmbiguityFlagDB.resolved.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    con_rows = (
        (
            await db.execute(
                select(ContradictionDB).where(
                    ContradictionDB.fs_id == doc_id,
                    ContradictionDB.resolved.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    edge_rows = (
        (
            await db.execute(
                select(EdgeCaseGapDB).where(
                    EdgeCaseGapDB.fs_id == doc_id,
                    EdgeCaseGapDB.resolved.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )

    score = compute_quality_score(
        total_sections=max(section_count, 1),
        ambiguities=[{"section_index": a.section_index} for a in amb_rows],
        contradictions=[{"section_a_index": c.section_a_index} for c in con_rows],
        edge_cases=[{"section_index": e.section_index} for e in edge_rows],
    )
    high_amb = sum(1 for a in amb_rows if a.severity == AmbiguitySeverity.HIGH)
    task_count = len(tasks)

    # Test-case footprint — kept lightweight (just a count) so the prompt
    # stays well below the model context budget while still telling the
    # agent that test_cases are first-class and will be validated.
    test_count = (
        await db.execute(
            select(func.count(TestCaseDB.id)).where(TestCaseDB.fs_id == doc_id)
        )
    ).scalar() or 0

    # Layer breakdown helps the agent pick a sensible execution order
    # (DB → API → Frontend) when the dependency graph is sparse.
    layer_counts: dict[str, int] = {
        "frontend": 0, "backend": 0, "db": 0, "api": 0, "auth": 0,
        "testing": 0, "devops": 0, "integration": 0, "ui": 0,
        "performance": 0, "security": 0,
    }
    sample_titles: list[str] = []
    for t in tasks:
        for tag in (t.tags or []):
            if tag in layer_counts:
                layer_counts[tag] += 1
        if t.title and len(sample_titles) < 12:
            sample_titles.append(f"- {t.title}")
    nonzero_layers = {k: v for k, v in layer_counts.items() if v > 0}
    layer_line = (
        ", ".join(f"{k}={v}" for k, v in sorted(nonzero_layers.items()))
        or "uncategorised"
    )

    # Top open blockers (capped) — high-severity ambiguities and any
    # unresolved contradictions are the agent's first reading list.
    blocker_lines: list[str] = []
    for a in amb_rows[:5]:
        if a.severity != AmbiguitySeverity.HIGH:
            continue
        snippet = (a.flagged_text or "").strip().replace("\n", " ")
        if len(snippet) > 140:
            snippet = snippet[:137] + "..."
        blocker_lines.append(f"  • [HIGH ambiguity] {snippet}")
    for c in con_rows[:5]:
        desc = (c.description or "").strip().replace("\n", " ")
        if len(desc) > 140:
            desc = desc[:137] + "..."
        blocker_lines.append(f"  • [contradiction] {desc}")
    blocker_block = "\n".join(blocker_lines) if blocker_lines else (
        "  (none — analysis is green, you may proceed at full speed)"
    )

    # GRAPHIFY block — every build run starts by capturing a fresh code-
    # graph of whatever scaffolding already exists in output_folder. This
    # gives the agent a structural prior so it doesn't accidentally
    # duplicate modules. We keep the block self-contained (no external
    # docs lookup needed) so the agent can replay it deterministically.
    graphify_block = (
        "GRAPHIFY (Phase 0 — runs ONCE before code is written):\n"
        "  1. If output_folder is non-empty, call `pre_build_check` to "
        "fail-fast on missing prerequisites.\n"
        "  2. Build a structural map of any existing scaffolding by "
        "listing files, identifying entry points, and recording exported "
        "symbols. Treat this map as the canonical 'reuse index'.\n"
        "  3. For every new task, ALWAYS call `check_library_for_reuse` "
        "first; only write fresh code when no reusable artefact exists.\n"
        "  4. Re-graph after each phase exit so the reuse index reflects "
        "what you just shipped — never reason from a stale graph."
    )

    sample_titles_block = "\n".join(sample_titles) if sample_titles else (
        "  (no tasks yet — the analysis pipeline must run first)"
    )

    prompt = (
        "<role>\n"
        "You are a principal full-stack engineer driving an autonomous "
        "build of a complete, production-ready product. You are connected "
        "to the FS Intelligence Platform over MCP and have full control "
        "of the build loop, file registry, telemetry, and verification "
        "tools. There is no human in the loop — your output IS the "
        "release.\n"
        "</role>\n"
        "\n"
        "<mission>\n"
        f"Implement document {doc_id} end-to-end in `{output_folder}` on "
        f"the `{stack}` stack. Ship a product that boots, passes its own "
        "test suite, and satisfies every accepted FS requirement on the "
        "first try. Treat the analysis snapshot below as the source of "
        "truth for scope, severity, and acceptance criteria.\n"
        "</mission>\n"
        "\n"
        "<context>\n"
        "DOCUMENT SNAPSHOT\n"
        f"  Document ID  : {doc_id}\n"
        f"  Status       : {doc.status.value if doc.status else 'UNKNOWN'}\n"
        f"  Quality      : {score.overall}/100 across {section_count} FS sections\n"
        f"  Tasks        : {task_count} total ({layer_line})\n"
        f"  Test cases   : {test_count} authored\n"
        f"  Open HIGH ambiguities : {high_amb} "
        f"{'(BLOCKERS — resolve in collaboration with platform before code)' if high_amb else '(clear)'}\n"
        f"  Open contradictions   : {len(con_rows)}\n"
        f"  Open edge-case gaps   : {len(edge_rows)}\n"
        "\n"
        "TOP BLOCKERS\n"
        f"{blocker_block}\n"
        "\n"
        "REPRESENTATIVE TASKS (first 12 — call `get_task_context` for the full list)\n"
        f"{sample_titles_block}\n"
        "</context>\n"
        "\n"
        "<instructions>\n"
        "STEP 1 — Open the build loop:\n"
        "  Call the `start_build_loop` prompt with EXACTLY:\n"
        f'    document_id   = "{doc_id}"\n'
        f'    stack         = "{stack}"\n'
        f'    output_folder = "{output_folder}"\n'
        '    auto_proceed  = "true"\n'
        "\n"
        "STEP 2 — Walk every phase the prompt returns (PRE-FLIGHT → "
        "EXPORT). Do NOT skip phases, do NOT mark tasks complete without "
        "`verify_task_completion`, and do NOT batch unrelated tasks "
        "into one commit.\n"
        "\n"
        "PER-TASK CYCLE (repeat until the loop reports DONE):\n"
        "  1. `get_task_context`            → load FS section, AC, "
        "tests, dependencies, related files.\n"
        "  2. `check_library_for_reuse`     → reuse > rewrite; only "
        "create new files when no candidate matches.\n"
        "  3. Implement the task. Stay strictly within the task's "
        "acceptance criteria — no scope creep, no stub TODOs.\n"
        "  4. `register_file` for EVERY file you create or materially "
        "change (path, language, lines, sha) — this is how traceability "
        "and the per-document Lifecycle timeline stay accurate.\n"
        "  5. `verify_task_completion`      → MUST return GO before "
        "advancing. On NO_GO, fix the cited gap and re-verify.\n"
        "  6. `update_build_state`          → mark the task complete and "
        "advance the loop.\n"
        "\n"
        f"{graphify_block}\n"
        "\n"
        "POST-BUILD SELF-HEAL LOOP (mandatory — do not stop here):\n"
        "  After EXPORT reports success, run the entire product end-to-"
        "end yourself before declaring done:\n"
        "    a. Boot the backend, run its full test suite, and confirm "
        "       every endpoint named in the FS responds with the expected "
        "       contract (status code, schema, side effects).\n"
        "    b. Build and start the frontend, walk every primary user "
        "       flow named in the FS, and confirm the UI matches the "
        "       acceptance criteria of the corresponding tasks.\n"
        "    c. Run any integration / E2E tests authored from the test "
        "       cases above.\n"
        "  If ANY step fails: locate the failing task, write a fix, "
        "  re-run `verify_task_completion`, register changed files, "
        "  and restart the post-build loop from (a). Repeat until ALL "
        "  three steps pass cleanly twice in a row. Only then call "
        "  `post_build_check` and finish.\n"
        "  Goal: when you stop, the user can open the project and use "
        "  it without ANY manual setup, fixes, or follow-up prompts.\n"
        "\n"
        "PROHIBITED:\n"
        "  - Skipping `verify_task_completion`.\n"
        "  - Marking tasks complete with TODOs, placeholders, or "
        "    `pass`-only function bodies.\n"
        "  - Inventing new requirements not in the FS.\n"
        "  - Touching files outside `output_folder`.\n"
        "</instructions>\n"
        "\n"
        "<thinking_protocol>\n"
        "Before each task, silently answer:\n"
        "  1. Which FS section and acceptance criteria does this satisfy?\n"
        "  2. What artefact already exists I can reuse (per the graphify map)?\n"
        "  3. What is the exact contract (inputs, outputs, side effects, "
        "errors) I must satisfy?\n"
        "  4. What is the smallest change that satisfies it without "
        "breaking neighbouring tasks?\n"
        "  5. How will `verify_task_completion` know I succeeded?\n"
        "Answer privately — only emit code, tool calls, and brief phase "
        "summaries.\n"
        "</thinking_protocol>\n"
        "\n"
        "<self_check>\n"
        "Before you call `update_build_state` to advance a task:\n"
        "  - Every acceptance criterion is observable in the registered "
        "files.\n"
        "  - No file you touched is unregistered.\n"
        "  - Tests added for the task pass locally.\n"
        "  - You did NOT introduce stubs, TODOs, or `raise NotImplementedError`.\n"
        "Before you finish the entire build:\n"
        "  - The post-build self-heal loop completed twice in a row "
        "without errors.\n"
        "  - `post_build_check` returns success.\n"
        "  - The product runs from a clean clone of `output_folder` "
        "with documented commands.\n"
        "</self_check>\n"
        "\n"
        "<refusal>\n"
        "If the platform reports unresolved HIGH ambiguities or "
        "contradictions, stop after PRE-FLIGHT and surface them via "
        "`update_build_state` with status=FAILED and a short reason "
        "naming the blocker. Do not guess intent on HIGH-severity gaps.\n"
        "</refusal>"
    )

    mcp_config = {
        "mcpServers": {
            "fs-intelligence-platform": {
                "command": "python",
                "args": ["mcp-server/server.py"],
                "env": {"BACKEND_URL": "http://localhost:8000"},
            }
        }
    }

    return {
        "data": {
            "prompt": prompt,
            "mcp_config": mcp_config,
            "summary": {
                "quality": score.overall,
                "tasks": task_count,
                "sections": section_count,
                "blockers": high_amb + len(con_rows),
                "high_ambiguities": high_amb,
                "contradictions": len(con_rows),
                "edge_cases": len(edge_rows),
                "status": doc.status.value if doc.status else "UNKNOWN",
            },
        }
    }


# ── Headless Build Runner (Claude Code) ────────────────
#
# One-click build kick-off when ``build_provider = claude_code``. The UI
# posts stack + output_folder; we create/reset the build state, capture
# the build prompt, and spawn the Claude CLI in the background with the
# MCP config wired in. Progress is then visible via the existing
# ``GET /{doc_id}/build-state`` endpoint — no new polling infrastructure
# is needed.


async def _run_claude_build(
    doc_id: uuid.UUID,
    prompt: str,
    mcp_config: dict,
    output_folder: str,
    *,
    stack: str = "",
) -> None:
    """Drive ``claude -p ...`` and reflect progress on build_state.

    Telemetry contract:
      * Inserts an ``MCPSessionDB`` row before spawn and exports its id
        as ``MCP_SESSION_ID`` to the subprocess. Every MCP tool call the
        agent makes will then emit ``MCPSessionEventDB`` rows that the
        existing "Build Sessions" tab in /monitoring renders live.
      * Emits ``BUILD_STARTED`` and ``BUILD_COMPLETED`` / ``BUILD_FAILED``
        audit events bracketing the CLI invocation so the activity log
        and per-document Lifecycle timeline always have build bookends.
    """

    from app.config import get_settings
    from app.db.base import async_session_factory
    from app.db.models import MCPSessionStatus
    from app.orchestration.providers.claude_code_provider import (
        _resolve_cli_invocation,
        _run_cli,
    )

    settings = get_settings()
    cli = (
        (settings.CLAUDE_CLI_PATH if hasattr(settings, "CLAUDE_CLI_PATH") else None)
        or os.environ.get("CLAUDE_CLI_PATH")
        or "claude"
    )
    cli_argv = _resolve_cli_invocation(cli)

    try:
        os.makedirs(output_folder, exist_ok=True)
    except Exception as exc:
        logger.warning("Could not create output_folder %r: %s", output_folder, exc)

    cfg_fd, cfg_path = tempfile.mkstemp(
        prefix="fsp-claude-mcp-",
        suffix=".json",
    )
    try:
        with os.fdopen(cfg_fd, "w", encoding="utf-8") as fh:
            json.dump(mcp_config, fh)
    except Exception:
        try:
            os.remove(cfg_path)
        except OSError:
            pass
        cfg_path = ""

    # Create the MCP session row BEFORE spawning so we can hand its id
    # to the subprocess via env. Without this every emit_session_event
    # call inside the MCP server tools no-ops and the Sessions tab stays
    # empty even after a successful build.
    session_id: str | None = None
    backend_url = (
        os.environ.get("PUBLIC_BACKEND_URL")
        or getattr(settings, "PUBLIC_BACKEND_URL", None)
        or "http://localhost:8000"
    )
    started_at = datetime.now(UTC)
    async with async_session_factory() as session:
        row = (
            await session.execute(select(BuildStateDB).where(BuildStateDB.document_id == doc_id))
        ).scalar_one_or_none()
        if row is not None:
            row.status = BuildStatus.RUNNING
            row.started_at = started_at
            row.last_updated = started_at
        try:
            mcp_session = MCPSessionDB(
                fs_id=doc_id,
                target_stack=stack or (row.stack if row else "") or "",
                source="headless_build",
                status=MCPSessionStatus.RUNNING,
                phase=0,
                current_step="Spawning Claude CLI",
                meta_json={
                    "output_folder": output_folder,
                    "cli": " ".join(cli_argv),
                    "started_at": started_at.isoformat(),
                },
            )
            session.add(mcp_session)
            await session.flush()
            session_id = str(mcp_session.id)
        except Exception:
            logger.exception("Failed to create MCPSessionDB for doc %s", doc_id)
            session_id = None
        try:
            await log_audit_event(
                session,
                doc_id,
                AuditEventType.BUILD_STARTED,
                user_id="agent",
                payload={
                    "provider": "claude_code",
                    "stack": stack or (row.stack if row else "") or "",
                    "output_folder": output_folder,
                    "mcp_session_id": session_id,
                },
            )
        except Exception:
            logger.exception("audit emit failed for BUILD_STARTED doc=%s", doc_id)
        await session.commit()

    args = [*cli_argv, "-p", prompt]
    if cfg_path:
        args.extend(["--mcp-config", cfg_path])
    args.extend(
        [
            "--allowedTools",
            "mcp__fs-intelligence-platform__*",
            "--output-format",
            "stream-json",
            "--verbose",
        ]
    )

    subprocess_env = dict(os.environ)
    subprocess_env["BACKEND_URL"] = backend_url
    if session_id:
        subprocess_env["MCP_SESSION_ID"] = session_id

    try:
        result = await asyncio.to_thread(
            _run_cli,
            args,
            timeout=60 * 60,  # 1h hard cap
            cwd=output_folder,
            env=subprocess_env,
        )
        ok = result.returncode == 0
        rc = result.returncode
        stderr = result.stderr.decode(errors="replace") if result.stderr else ""
        if not ok:
            logger.error(
                "Claude build for doc %s exited rc=%s: %s",
                doc_id,
                result.returncode,
                stderr[:400],
            )
    except TypeError:
        # Backwards-compat: older _run_cli without env support.
        result = await asyncio.to_thread(
            _run_cli,
            args,
            timeout=60 * 60,
            cwd=output_folder,
        )
        ok = result.returncode == 0
        rc = result.returncode
        stderr = result.stderr.decode(errors="replace") if result.stderr else ""
    except Exception as exc:
        logger.exception("Claude build for doc %s crashed: %s", doc_id, exc)
        ok = False
        rc = -1
        stderr = str(exc)

    finished_at = datetime.now(UTC)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    # Finalise build_state, MCP session, and emit BUILD_COMPLETED/FAILED.
    # The agent may have already marked the build COMPLETE/FAILED via MCP
    # tools (which now triggers audit events from update_build_state); in
    # that case we only finalise the MCP session row here.
    async with async_session_factory() as session:
        row = (
            await session.execute(select(BuildStateDB).where(BuildStateDB.document_id == doc_id))
        ).scalar_one_or_none()
        finalised_here = False
        if row is not None and row.status == BuildStatus.RUNNING:
            row.status = BuildStatus.COMPLETE if ok else BuildStatus.FAILED
            row.last_updated = finished_at
            finalised_here = True
        if session_id:
            mcp_row = (
                await session.execute(select(MCPSessionDB).where(MCPSessionDB.id == uuid.UUID(session_id)))
            ).scalar_one_or_none()
            if mcp_row is not None:
                mcp_row.status = (
                    MCPSessionStatus.PASSED if ok else MCPSessionStatus.FAILED
                )
                mcp_row.ended_at = finished_at
                mcp_row.current_step = "Build finished" if ok else "Build failed"
                meta = dict(mcp_row.meta_json or {})
                meta.update(
                    {
                        "ended_at": finished_at.isoformat(),
                        "duration_ms": duration_ms,
                        "returncode": rc,
                    }
                )
                mcp_row.meta_json = meta
                # Final session event so the timeline closes cleanly.
                session.add(
                    MCPSessionEventDB(
                        session_id=mcp_row.id,
                        event_type="build_finished" if ok else "build_failed",
                        phase=mcp_row.phase or 0,
                        status="ok" if ok else "error",
                        message=(
                            f"Build finished in {duration_ms} ms"
                            if ok
                            else f"Build failed (rc={rc}) after {duration_ms} ms"
                        ),
                        payload_json={
                            "returncode": rc,
                            "duration_ms": duration_ms,
                            "stderr_tail": (stderr or "")[-400:],
                        },
                    )
                )
        if finalised_here:
            evt = AuditEventType.BUILD_COMPLETED if ok else AuditEventType.BUILD_FAILED
            try:
                await log_audit_event(
                    session,
                    doc_id,
                    evt,
                    user_id="agent",
                    payload={
                        "returncode": rc,
                        "duration_ms": duration_ms,
                        "output_folder": output_folder,
                        "completed_tasks": len(row.completed_task_ids or []) if row else 0,
                        "failed_tasks": len(row.failed_task_ids or []) if row else 0,
                        "total_tasks": row.total_tasks if row else 0,
                        "source": "headless_build",
                    },
                )
            except Exception:
                logger.exception("audit emit failed for build finalize doc=%s", doc_id)
        await session.commit()

    try:
        if cfg_path:
            os.remove(cfg_path)
    except OSError:
        pass


@router.post("/{doc_id}/build/run")
async def run_build(
    doc_id: uuid.UUID,
    body: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Dispatch a headless Claude Code build for the given document.

    Expected body:
        {
          "stack": "Next.js + FastAPI",
          "output_folder": "./output",
          "provider": "claude_code"   # optional; only claude_code is supported today
        }

    Returns the ``build_state`` id so the UI can poll
    ``GET /{doc_id}/build-state`` for live progress.
    """
    provider = (body.get("provider") or "claude_code").strip().lower()
    if provider != "claude_code":
        raise HTTPException(
            status_code=400,
            detail=(
                f"provider={provider!r} is not supported for headless build. "
                f"Use provider=cursor via the copy-prompt flow instead."
            ),
        )

    stack = (body.get("stack") or "Next.js + FastAPI").strip() or "Next.js + FastAPI"
    output_folder = (body.get("output_folder") or "./output").strip() or "./output"

    # 1) Verify doc exists and build the agent prompt (reuse the same
    # endpoint-building code to avoid drift).
    prompt_res = await get_build_prompt(  # type: ignore[misc]
        doc_id=doc_id,
        stack=stack,
        output_folder=output_folder,
        db=db,
    )
    prompt = prompt_res["data"]["prompt"]
    mcp_config = prompt_res["data"]["mcp_config"]

    # 2) Create or reset the build state.
    state = (await db.execute(select(BuildStateDB).where(BuildStateDB.document_id == doc_id))).scalar_one_or_none()
    if state is None:
        tasks_count = (await db.execute(select(func.count(FSTaskDB.id)).where(FSTaskDB.fs_id == doc_id))).scalar() or 0
        state = BuildStateDB(
            document_id=doc_id,
            total_tasks=tasks_count,
            stack=stack,
            output_folder=output_folder,
            status=BuildStatus.PENDING,
        )
        db.add(state)
    else:
        state.status = BuildStatus.PENDING
        state.stack = stack
        state.output_folder = output_folder
        state.started_at = None
        state.completed_task_ids = []
        state.failed_task_ids = []
        state.last_updated = datetime.now(UTC)
    await db.commit()
    await db.refresh(state)

    # 3) Verify the Claude CLI is reachable before spawning. Surface a
    # clean 424 so the UI can guide the user to `claude login`.
    from app.orchestration import get_tool_registry

    registry = get_tool_registry()
    claude = registry.get("claude_code")
    healthy = False
    try:
        if claude is not None:
            healthy = await claude.check_health()
    except Exception:
        healthy = False
    if not healthy:
        raise HTTPException(
            status_code=424,
            detail=(
                "Claude CLI is not available. Install it with "
                "`npm install -g @anthropic-ai/claude-code`, then run "
                "`claude login` once to authenticate."
            ),
        )

    background_tasks.add_task(
        _run_claude_build,
        doc_id,
        prompt,
        mcp_config,
        output_folder,
        stack=stack,
    )

    return {
        "data": {
            "build_state_id": str(state.id),
            "document_id": str(doc_id),
            "status": state.status.value if state.status else "PENDING",
            "stack": stack,
            "output_folder": output_folder,
            "provider": provider,
        }
    }
