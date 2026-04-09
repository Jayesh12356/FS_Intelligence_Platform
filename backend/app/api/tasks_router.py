"""Tasks API — list/detail/update tasks, dependency graph, traceability."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import (
    FSDocument,
    FSTaskDB,
    TraceabilityEntryDB,
)
from app.models.schemas import (
    APIResponse,
    DependencyEdge,
    DependencyGraphResponse,
    FSTaskSchema,
    TaskListResponse,
    TraceabilityEntrySchema,
    TraceabilityResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fs", tags=["tasks"])


# ── Body schemas ───────────────────────────────────────


class TaskUpdateBody(BaseModel):
    """Body for PATCH task update (manual editing)."""
    title: str | None = None
    description: str | None = None
    effort: str | None = None
    tags: list[str] | None = None
    acceptance_criteria: list[str] | None = None


# ── Task Endpoints ─────────────────────────────────────


@router.get("/{doc_id}/tasks", response_model=APIResponse[TaskListResponse])
async def list_tasks(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TaskListResponse]:
    """List all tasks for a document, ordered by execution order."""
    result = await db.execute(
        select(FSTaskDB)
        .where(FSTaskDB.fs_id == doc_id)
        .order_by(FSTaskDB.order, FSTaskDB.section_index)
    )
    rows = result.scalars().all()

    schemas = [
        FSTaskSchema(
            id=r.id,
            task_id=r.task_id,
            title=r.title,
            description=r.description,
            section_index=r.section_index,
            section_heading=r.section_heading,
            depends_on=r.depends_on or [],
            acceptance_criteria=r.acceptance_criteria or [],
            effort=r.effort.value,
            tags=r.tags or [],
            order=r.order,
            can_parallel=r.can_parallel,
        )
        for r in rows
    ]

    return APIResponse(
        data=TaskListResponse(tasks=schemas, total=len(schemas))
    )


@router.get("/{doc_id}/tasks/dependency-graph", response_model=APIResponse[DependencyGraphResponse])
async def get_dependency_graph(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[DependencyGraphResponse]:
    """Get the dependency graph for a document's tasks as an adjacency list."""
    result = await db.execute(
        select(FSTaskDB)
        .where(FSTaskDB.fs_id == doc_id)
        .order_by(FSTaskDB.order)
    )
    rows = result.scalars().all()

    nodes = [r.task_id for r in rows]
    adjacency: dict[str, list[str]] = {}
    edges: list[DependencyEdge] = []

    valid_ids = set(nodes)

    for r in rows:
        deps = [d for d in (r.depends_on or []) if d in valid_ids]
        adjacency[r.task_id] = deps
        for dep in deps:
            edges.append(DependencyEdge(from_task=dep, to_task=r.task_id))

    return APIResponse(
        data=DependencyGraphResponse(
            nodes=nodes,
            edges=edges,
            adjacency=adjacency,
        )
    )


@router.get("/{doc_id}/tasks/{task_id}", response_model=APIResponse[FSTaskSchema])
async def get_task_detail(
    doc_id: uuid.UUID,
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSTaskSchema]:
    """Get a single task by its pipeline task_id."""
    result = await db.execute(
        select(FSTaskDB).where(
            FSTaskDB.fs_id == doc_id,
            FSTaskDB.task_id == task_id,
        )
    )
    row = result.scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    return APIResponse(
        data=FSTaskSchema(
            id=row.id,
            task_id=row.task_id,
            title=row.title,
            description=row.description,
            section_index=row.section_index,
            section_heading=row.section_heading,
            depends_on=row.depends_on or [],
            acceptance_criteria=row.acceptance_criteria or [],
            effort=row.effort.value,
            tags=row.tags or [],
            order=row.order,
            can_parallel=row.can_parallel,
        ),
    )


@router.patch("/{doc_id}/tasks/{task_id}", response_model=APIResponse[FSTaskSchema])
async def update_task(
    doc_id: uuid.UUID,
    task_id: str,
    body: TaskUpdateBody,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSTaskSchema]:
    """Update a task (manual edit — title, description, effort, tags, criteria)."""
    result = await db.execute(
        select(FSTaskDB).where(
            FSTaskDB.fs_id == doc_id,
            FSTaskDB.task_id == task_id,
        )
    )
    row = result.scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.title is not None:
        row.title = body.title
    if body.description is not None:
        row.description = body.description
    if body.effort is not None:
        from app.db.models import EffortLevel
        try:
            row.effort = EffortLevel(body.effort.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid effort: {body.effort}")
    if body.tags is not None:
        row.tags = body.tags
    if body.acceptance_criteria is not None:
        row.acceptance_criteria = body.acceptance_criteria

    await db.commit()
    await db.refresh(row)

    return APIResponse(
        data=FSTaskSchema(
            id=row.id,
            task_id=row.task_id,
            title=row.title,
            description=row.description,
            section_index=row.section_index,
            section_heading=row.section_heading,
            depends_on=row.depends_on or [],
            acceptance_criteria=row.acceptance_criteria or [],
            effort=row.effort.value,
            tags=row.tags or [],
            order=row.order,
            can_parallel=row.can_parallel,
        ),
    )


# ── Traceability Endpoint ──────────────────────────────


@router.get("/{doc_id}/traceability", response_model=APIResponse[TraceabilityResponse])
async def get_traceability(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TraceabilityResponse]:
    """Get full traceability matrix for a document."""
    # Verify document exists
    doc_result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(TraceabilityEntryDB)
        .where(TraceabilityEntryDB.fs_id == doc_id)
        .order_by(TraceabilityEntryDB.section_index)
    )
    rows = result.scalars().all()

    entries = [
        TraceabilityEntrySchema(
            task_id=r.task_id,
            task_title=r.task_title,
            section_index=r.section_index,
            section_heading=r.section_heading,
        )
        for r in rows
    ]

    # Count unique sections
    unique_sections = set(r.section_index for r in rows)

    return APIResponse(
        data=TraceabilityResponse(
            entries=entries,
            total_tasks=len(entries),
            total_sections=len(unique_sections),
        )
    )
