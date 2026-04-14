"""Build Engine API — state persistence, file registry, pre/post checks, snapshots, cache."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import (
    AmbiguityFlagDB,
    AmbiguitySeverity,
    BuildSnapshotDB,
    BuildStateDB,
    BuildStatus,
    ContradictionDB,
    EdgeCaseGapDB,
    FileRegistryDB,
    FSDocument,
    FSTaskDB,
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
    existing = (await db.execute(
        select(BuildStateDB).where(BuildStateDB.document_id == doc_id)
    )).scalar_one_or_none()
    if existing:
        existing.status = BuildStatus.PENDING
        existing.current_phase = 0
        existing.current_task_index = 0
        existing.completed_task_ids = []
        existing.failed_task_ids = []
        existing.started_at = None
        existing.last_updated = datetime.now(timezone.utc)
    else:
        tasks_count = (await db.execute(
            select(func.count(FSTaskDB.id)).where(FSTaskDB.fs_id == doc_id)
        )).scalar() or 0
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
    row = (await db.execute(
        select(BuildStateDB).where(BuildStateDB.document_id == doc_id)
    )).scalar_one_or_none()
    if not row:
        return {"data": None}
    return {"data": _build_state_dict(row)}


@router.patch("/{doc_id}/build-state")
async def update_build_state(
    doc_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(BuildStateDB).where(BuildStateDB.document_id == doc_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "No build state found — call POST first")
    if "current_phase" in body:
        row.current_phase = int(body["current_phase"])
    if "current_task_index" in body:
        row.current_task_index = int(body["current_task_index"])
    if "status" in body:
        row.status = BuildStatus(body["status"])
    if body.get("completed_task_id"):
        done = list(row.completed_task_ids or [])
        tid = str(body["completed_task_id"])
        if tid not in done:
            done.append(tid)
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
        row.started_at = datetime.now(timezone.utc)
    row.last_updated = datetime.now(timezone.utc)
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
    task = (await db.execute(
        select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.task_id == task_id)
    )).scalar_one_or_none()
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

    test_cases = (await db.execute(
        select(TestCaseDB).where(TestCaseDB.fs_id == doc_id, TestCaseDB.task_id == task_id)
    )).scalars().all()

    dep_tasks = []
    for dep_id in (task.depends_on or []):
        dep = (await db.execute(
            select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.task_id == dep_id)
        )).scalar_one_or_none()
        if dep:
            dep_tasks.append({
                "task_id": dep.task_id,
                "title": dep.title,
                "status": dep.status.value if dep.status else "PENDING",
            })

    files = (await db.execute(
        select(FileRegistryDB).where(
            FileRegistryDB.document_id == doc_id,
            FileRegistryDB.task_id == task_id,
        )
    )).scalars().all()

    build = (await db.execute(
        select(BuildStateDB).where(BuildStateDB.document_id == doc_id)
    )).scalar_one_or_none()

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
    task = (await db.execute(
        select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.task_id == task_id)
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    checks: list[dict] = []

    files = (await db.execute(
        select(FileRegistryDB).where(
            FileRegistryDB.document_id == doc_id,
            FileRegistryDB.task_id == task_id,
        )
    )).scalars().all()
    checks.append({
        "criterion": "At least one file registered",
        "pass": len(files) > 0,
        "detail": f"{len(files)} files registered",
    })

    test_count = (await db.execute(
        select(func.count(TestCaseDB.id)).where(
            TestCaseDB.fs_id == doc_id, TestCaseDB.task_id == task_id,
        )
    )).scalar() or 0
    has_test_file = any(f.file_type == "test" for f in files)
    checks.append({
        "criterion": "Test coverage exists",
        "pass": test_count > 0 or has_test_file,
        "detail": f"{test_count} test cases, {sum(1 for f in files if f.file_type == 'test')} test files",
    })

    for dep_id in (task.depends_on or []):
        dep = (await db.execute(
            select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.task_id == dep_id)
        )).scalar_one_or_none()
        dep_complete = dep and dep.status and dep.status.value == "COMPLETE"
        checks.append({
            "criterion": f"Dependency {dep_id} is COMPLETE",
            "pass": dep_complete,
            "detail": f"Status: {dep.status.value if dep and dep.status else 'MISSING'}",
        })

    for idx, criterion in enumerate(task.acceptance_criteria or []):
        checks.append({
            "criterion": f"Acceptance: {criterion[:80]}",
            "pass": len(files) > 0,
            "detail": "Files exist (manual verification recommended)",
        })

    all_pass = all(c["pass"] for c in checks)
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

    affected_tasks_result = (await db.execute(
        select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.section_index == section_idx)
    )).scalars().all()
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

    from app.pipeline.nodes.quality_node import compute_quality_score
    from app.parsers.chunker import chunk_text_into_sections

    text = (doc.parsed_text or doc.original_text or "").strip()
    try:
        total_sections = max(len(chunk_text_into_sections(text)), 1) if text else 1
    except Exception:
        total_sections = 1

    amb_rows = (await db.execute(
        select(AmbiguityFlagDB).where(AmbiguityFlagDB.fs_id == doc_id, AmbiguityFlagDB.resolved.is_(False))
    )).scalars().all()
    con_rows = (await db.execute(
        select(ContradictionDB).where(ContradictionDB.fs_id == doc_id, ContradictionDB.resolved.is_(False))
    )).scalars().all()
    edge_rows = (await db.execute(
        select(EdgeCaseGapDB).where(EdgeCaseGapDB.fs_id == doc_id, EdgeCaseGapDB.resolved.is_(False))
    )).scalars().all()

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

    tasks = (await db.execute(
        select(FSTaskDB).where(FSTaskDB.fs_id == doc_id)
    )).scalars().all()
    files = (await db.execute(
        select(FileRegistryDB).where(FileRegistryDB.document_id == doc_id)
    )).scalars().all()

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
    test_cases = (await db.execute(
        select(func.count(TestCaseDB.id)).where(TestCaseDB.fs_id == doc_id)
    )).scalar() or 0
    test_ok = len(test_files) > 0 or test_cases > 0
    if not test_ok:
        gaps.append("No test files or test cases registered")

    orphaned = [f.file_path for f in files if f.task_id and f.task_id not in {t.task_id for t in tasks}]
    if orphaned:
        gaps.append(f"{len(orphaned)} orphaned files (task deleted)")

    from app.pipeline.nodes.quality_node import compute_quality_score
    amb_count = (await db.execute(
        select(func.count(AmbiguityFlagDB.id)).where(
            AmbiguityFlagDB.fs_id == doc_id, AmbiguityFlagDB.resolved.is_(False)
        )
    )).scalar() or 0
    con_count = (await db.execute(
        select(func.count(ContradictionDB.id)).where(
            ContradictionDB.fs_id == doc_id, ContradictionDB.resolved.is_(False)
        )
    )).scalar() or 0
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
    files = (await db.execute(
        select(FileRegistryDB).where(FileRegistryDB.document_id == doc_id)
    )).scalars().all()
    tasks = (await db.execute(
        select(FSTaskDB).where(FSTaskDB.fs_id == doc_id)
    )).scalars().all()

    from app.pipeline.nodes.quality_node import compute_quality_score
    doc = (await db.execute(select(FSDocument).where(FSDocument.id == doc_id))).scalar_one_or_none()
    text = (doc.parsed_text or doc.original_text or "").strip() if doc else ""
    try:
        from app.parsers.chunker import chunk_text_into_sections
        ts = max(len(chunk_text_into_sections(text)), 1) if text else 1
    except Exception:
        ts = 1
    amb_count = (await db.execute(
        select(func.count(AmbiguityFlagDB.id)).where(
            AmbiguityFlagDB.fs_id == doc_id, AmbiguityFlagDB.resolved.is_(False)
        )
    )).scalar() or 0
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
            {"task_id": t.task_id, "status": t.status.value if t.status else "PENDING"}
            for t in tasks
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
    snap = (await db.execute(
        select(BuildSnapshotDB).where(
            BuildSnapshotDB.id == snapshot_id,
            BuildSnapshotDB.document_id == doc_id,
        )
    )).scalar_one_or_none()
    if not snap:
        raise HTTPException(404, "Snapshot not found")

    for ts in (snap.task_states_snapshot or []):
        task_row = (await db.execute(
            select(FSTaskDB).where(FSTaskDB.fs_id == doc_id, FSTaskDB.task_id == ts.get("task_id"))
        )).scalar_one_or_none()
        if task_row:
            try:
                task_row.status = TaskStatus(ts.get("status", "PENDING"))
            except ValueError:
                task_row.status = TaskStatus.PENDING

    await db.execute(delete(FileRegistryDB).where(FileRegistryDB.document_id == doc_id))
    for fsnap in (snap.file_registry_snapshot or []):
        db.add(FileRegistryDB(
            document_id=doc_id,
            task_id=fsnap.get("task_id", ""),
            section_id=fsnap.get("section_id", ""),
            file_path=fsnap.get("file_path", ""),
            file_type=fsnap.get("file_type", "unknown"),
            status=fsnap.get("status", "CREATED"),
        ))

    await db.commit()
    return {"data": {"rolled_back": True, "snapshot_id": str(snapshot_id), "quality_at_snapshot": snap.quality_score_at_snapshot}}


# ── Addition 7: Pipeline Cache ─────────────────────────


@router.get("/{doc_id}/pipeline-cache")
async def list_pipeline_cache(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(PipelineCacheDB).where(PipelineCacheDB.document_id == doc_id)
    )).scalars().all()
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
    result = await db.execute(
        delete(PipelineCacheDB).where(PipelineCacheDB.document_id == doc_id)
    )
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
    doc = (await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    tasks = (await db.execute(
        select(FSTaskDB).where(FSTaskDB.fs_id == doc_id)
    )).scalars().all()

    from app.parsers.section_extractor import extract_sections_from_text
    text = (doc.parsed_text or doc.original_text or "").strip()
    try:
        section_count = len(extract_sections_from_text(text)) if text else 0
    except Exception:
        section_count = 0

    from app.pipeline.nodes.quality_node import compute_quality_score
    amb_rows = (await db.execute(
        select(AmbiguityFlagDB).where(
            AmbiguityFlagDB.fs_id == doc_id,
            AmbiguityFlagDB.resolved.is_(False),
        )
    )).scalars().all()
    con_rows = (await db.execute(
        select(ContradictionDB).where(
            ContradictionDB.fs_id == doc_id,
            ContradictionDB.resolved.is_(False),
        )
    )).scalars().all()
    edge_rows = (await db.execute(
        select(EdgeCaseGapDB).where(
            EdgeCaseGapDB.fs_id == doc_id,
            EdgeCaseGapDB.resolved.is_(False),
        )
    )).scalars().all()

    score = compute_quality_score(
        total_sections=max(section_count, 1),
        ambiguities=[{"section_index": a.section_index} for a in amb_rows],
        contradictions=[{"section_a_index": c.section_a_index} for c in con_rows],
        edge_cases=[{"section_index": e.section_index} for e in edge_rows],
    )
    high_amb = sum(1 for a in amb_rows if a.severity == AmbiguitySeverity.HIGH)
    task_count = len(tasks)

    prompt = (
        f"You are connected to the FS Intelligence Platform via MCP. Your mission: "
        f"build the complete product defined in document {doc_id} with zero human intervention.\n"
        f"\n"
        f"STEP 1: Call the `start_build_loop` prompt with these exact parameters:\n"
        f'  document_id = "{doc_id}"\n'
        f'  stack = "{stack}"\n'
        f'  output_folder = "{output_folder}"\n'
        f'  auto_proceed = "true"\n'
        f"\n"
        f"STEP 2: Follow EVERY phase the prompt returns — PRE-FLIGHT through EXPORT.\n"
        f"Do NOT skip phases. Do NOT mark tasks complete without calling verify_task_completion.\n"
        f"\n"
        f"KEY TOOLS (use these in every task implementation cycle):\n"
        f"  get_task_context → Full FS section, acceptance criteria, test cases, dependencies\n"
        f"  verify_task_completion → Must pass BEFORE marking any task COMPLETE\n"
        f"  check_library_for_reuse → Check for reusable patterns before writing new code\n"
        f"  register_file → Register EVERY file created (required for traceability)\n"
        f"\n"
        f"DOCUMENT STATUS:\n"
        f"  Quality Score: {score.overall}/100\n"
        f"  Total Tasks: {task_count}\n"
        f"  FS Sections: {section_count}\n"
        f"  Open HIGH Ambiguities: {high_amb} {'(must resolve before building)' if high_amb > 0 else '(clear — ready to build)'}\n"
        f"  Contradictions: {len(con_rows)} | Edge Case Gaps: {len(edge_rows)}\n"
        f"\n"
        f"Build all code in the output folder. Report progress after each phase."
    )

    mcp_config = {
        "mcpServers": {
            "fs-intelligence-platform": {
                "command": "python",
                "args": ["mcp-server/server.py"],
                "env": {
                    "BACKEND_URL": "http://localhost:8000"
                }
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
            }
        }
    }
