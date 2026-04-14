"""Project API — CRUD for FS projects and document assignment."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import FSDocument, FSDocumentStatus, FSProject
from app.models.schemas import (
    APIResponse,
    FSDocumentResponse,
    FSProjectCreateRequest,
    FSProjectDetailSchema,
    FSProjectListResponse,
    FSProjectSchema,
    FSProjectUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.post("", response_model=APIResponse[FSProjectSchema])
async def create_project(
    body: FSProjectCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSProjectSchema]:
    """Create a new project."""
    existing = await db.execute(
        select(FSProject).where(FSProject.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Project '{body.name}' already exists")

    project = FSProject(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)

    doc_count = (await db.execute(
        select(func.count(FSDocument.id)).where(FSDocument.project_id == project.id)
    )).scalar() or 0

    logger.info("Created project %s: %s", project.id, project.name)
    return APIResponse(data=FSProjectSchema(
        id=project.id,
        name=project.name,
        description=project.description,
        document_count=doc_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    ))


@router.get("", response_model=APIResponse[FSProjectListResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSProjectListResponse]:
    """List all projects."""
    result = await db.execute(
        select(FSProject).order_by(FSProject.updated_at.desc())
    )
    projects = result.scalars().all()

    schemas = []
    for p in projects:
        doc_count = (await db.execute(
            select(func.count(FSDocument.id)).where(
                FSDocument.project_id == p.id,
                FSDocument.status != FSDocumentStatus.DELETED,
            )
        )).scalar() or 0
        schemas.append(FSProjectSchema(
            id=p.id,
            name=p.name,
            description=p.description,
            document_count=doc_count,
            created_at=p.created_at,
            updated_at=p.updated_at,
        ))

    return APIResponse(data=FSProjectListResponse(projects=schemas, total=len(schemas)))


@router.get("/{project_id}", response_model=APIResponse[FSProjectDetailSchema])
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSProjectDetailSchema]:
    """Get project detail with its documents."""
    result = await db.execute(
        select(FSProject).where(FSProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    docs_result = await db.execute(
        select(FSDocument)
        .where(
            FSDocument.project_id == project_id,
            FSDocument.status != FSDocumentStatus.DELETED,
        )
        .order_by(FSDocument.order_in_project, FSDocument.created_at)
    )
    docs = docs_result.scalars().all()

    doc_schemas = [FSDocumentResponse.model_validate(d) for d in docs]

    return APIResponse(data=FSProjectDetailSchema(
        id=project.id,
        name=project.name,
        description=project.description,
        document_count=len(doc_schemas),
        documents=doc_schemas,
        created_at=project.created_at,
        updated_at=project.updated_at,
    ))


@router.patch("/{project_id}", response_model=APIResponse[FSProjectSchema])
async def update_project(
    project_id: uuid.UUID,
    body: FSProjectUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSProjectSchema]:
    """Update a project's name or description."""
    result = await db.execute(
        select(FSProject).where(FSProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.name is not None:
        dup = await db.execute(
            select(FSProject).where(FSProject.name == body.name, FSProject.id != project_id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Project name '{body.name}' already taken")
        project.name = body.name
    if body.description is not None:
        project.description = body.description

    await db.flush()
    await db.refresh(project)

    doc_count = (await db.execute(
        select(func.count(FSDocument.id)).where(
            FSDocument.project_id == project.id,
            FSDocument.status != FSDocumentStatus.DELETED,
        )
    )).scalar() or 0

    return APIResponse(data=FSProjectSchema(
        id=project.id,
        name=project.name,
        description=project.description,
        document_count=doc_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    ))


@router.delete("/{project_id}", response_model=APIResponse[dict])
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Delete a project. Documents are unlinked (not deleted)."""
    result = await db.execute(
        select(FSProject).where(FSProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    docs_result = await db.execute(
        select(FSDocument).where(FSDocument.project_id == project_id)
    )
    for doc in docs_result.scalars().all():
        doc.project_id = None
        doc.order_in_project = 0

    await db.delete(project)
    await db.flush()

    logger.info("Deleted project %s: %s", project_id, project.name)
    return APIResponse(data={"id": str(project_id), "deleted": True})


@router.post("/{project_id}/documents/{doc_id}", response_model=APIResponse[dict])
async def assign_document_to_project(
    project_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Assign an existing document to a project."""
    proj_result = await db.execute(
        select(FSProject).where(FSProject.id == project_id)
    )
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    doc_result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    max_order = (await db.execute(
        select(func.max(FSDocument.order_in_project)).where(FSDocument.project_id == project_id)
    )).scalar() or 0

    doc.project_id = project_id
    doc.order_in_project = max_order + 1
    await db.flush()

    logger.info("Assigned document %s to project %s (order=%d)", doc_id, project_id, doc.order_in_project)
    return APIResponse(data={
        "document_id": str(doc_id),
        "project_id": str(project_id),
        "order_in_project": doc.order_in_project,
    })
