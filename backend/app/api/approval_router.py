"""Approval workflow API — submit, approve, reject FS documents (L9)."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.audit import log_audit_event
from app.db.base import get_db
from app.db.models import (
    ApprovalStatus,
    AuditEventType,
    FSApprovalDB,
    FSDocument,
    FSDocumentStatus,
)
from app.models.schemas import (
    APIResponse,
    ApprovalActionRequest,
    ApprovalStatusResponse,
    FSApprovalSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fs", tags=["approval"])


@router.post("/{doc_id}/submit-for-approval", response_model=APIResponse[FSApprovalSchema])
async def submit_for_approval(
    doc_id: uuid.UUID,
    body: ApprovalActionRequest = ApprovalActionRequest(),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSApprovalSchema]:
    """Submit an FS document for approval review.

    Document must be in COMPLETE status (analysis done) to submit.
    Creates a PENDING approval record.
    """
    # Verify document exists and is analysed
    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status not in (FSDocumentStatus.COMPLETE, FSDocumentStatus.PARSED):
        raise HTTPException(
            status_code=400,
            detail=f"Document must be analysed before approval submission. Status: {doc.status.value}",
        )

    # Check if already pending
    existing = await db.execute(
        select(FSApprovalDB).where(FSApprovalDB.fs_id == doc_id, FSApprovalDB.status == ApprovalStatus.PENDING)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Document already has a pending approval")

    # Create pending approval
    approval = FSApprovalDB(
        fs_id=doc_id,
        approver_id=body.approver_id,
        status=ApprovalStatus.PENDING,
        comment=body.comment,
    )
    db.add(approval)

    # Log audit event
    await log_audit_event(
        db,
        doc_id,
        AuditEventType.SUBMITTED_FOR_APPROVAL,
        user_id=body.approver_id,
        payload={"comment": body.comment},
    )

    await db.flush()
    await db.refresh(approval)

    return APIResponse(
        data=FSApprovalSchema(
            id=approval.id,
            fs_id=approval.fs_id,
            approver_id=approval.approver_id,
            status=approval.status.value,
            comment=approval.comment,
            created_at=approval.created_at,
        ),
    )


@router.post("/{doc_id}/approve", response_model=APIResponse[FSApprovalSchema])
async def approve_document(
    doc_id: uuid.UUID,
    body: ApprovalActionRequest = ApprovalActionRequest(),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSApprovalSchema]:
    """Approve an FS document.

    Updates the latest PENDING approval to APPROVED.
    Also adds approved sections to the requirement library.
    """
    # Find pending approval
    result = await db.execute(
        select(FSApprovalDB)
        .where(FSApprovalDB.fs_id == doc_id, FSApprovalDB.status == ApprovalStatus.PENDING)
        .order_by(FSApprovalDB.created_at.desc())
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise HTTPException(status_code=400, detail="No pending approval found for this document")

    approval.status = ApprovalStatus.APPROVED
    approval.approver_id = body.approver_id
    approval.comment = body.comment or approval.comment

    # Log audit event
    await log_audit_event(
        db,
        doc_id,
        AuditEventType.APPROVED,
        user_id=body.approver_id,
        payload={"comment": body.comment, "approval_id": str(approval.id)},
    )

    await db.flush()
    await db.refresh(approval)

    # Auto-add sections to requirement library
    try:
        doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
        doc = doc_result.scalar_one_or_none()
        if doc and doc.status == FSDocumentStatus.COMPLETE:
            from app.parsers.router import parse_document as do_parse

            parsed = await do_parse(str(doc.id), db)
            from app.vector.fs_store import store_library_item

            for section in parsed.sections:
                heading = section.heading if hasattr(section, "heading") else section.get("heading", "")
                content = section.content if hasattr(section, "content") else section.get("content", "")
                idx = section.section_index if hasattr(section, "section_index") else section.get("section_index", 0)
                try:
                    store_library_item(
                        fs_id=str(doc_id),
                        section_index=idx,
                        heading=heading,
                        text=content,
                    )
                except Exception as exc:
                    logger.warning("Failed to store library item for section %d: %s", idx, exc)
            logger.info("Added %d sections to requirement library for fs_id=%s", len(parsed.sections), doc_id)
    except Exception as exc:
        logger.warning("Failed to populate requirement library on approval: %s", exc)

    return APIResponse(
        data=FSApprovalSchema(
            id=approval.id,
            fs_id=approval.fs_id,
            approver_id=approval.approver_id,
            status=approval.status.value,
            comment=approval.comment,
            created_at=approval.created_at,
        ),
    )


@router.post("/{doc_id}/reject", response_model=APIResponse[FSApprovalSchema])
async def reject_document(
    doc_id: uuid.UUID,
    body: ApprovalActionRequest = ApprovalActionRequest(),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSApprovalSchema]:
    """Reject an FS document.

    Updates the latest PENDING approval to REJECTED.
    """
    # Find pending approval
    result = await db.execute(
        select(FSApprovalDB)
        .where(FSApprovalDB.fs_id == doc_id, FSApprovalDB.status == ApprovalStatus.PENDING)
        .order_by(FSApprovalDB.created_at.desc())
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise HTTPException(status_code=400, detail="No pending approval found for this document")

    approval.status = ApprovalStatus.REJECTED
    approval.approver_id = body.approver_id
    approval.comment = body.comment or approval.comment

    # Log audit event
    await log_audit_event(
        db,
        doc_id,
        AuditEventType.REJECTED,
        user_id=body.approver_id,
        payload={"comment": body.comment, "approval_id": str(approval.id)},
    )

    await db.flush()
    await db.refresh(approval)

    return APIResponse(
        data=FSApprovalSchema(
            id=approval.id,
            fs_id=approval.fs_id,
            approver_id=approval.approver_id,
            status=approval.status.value,
            comment=approval.comment,
            created_at=approval.created_at,
        ),
    )


@router.get("/{doc_id}/approval-status", response_model=APIResponse[ApprovalStatusResponse])
async def get_approval_status(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ApprovalStatusResponse]:
    """Get the current approval status and full history for a document."""
    # Verify document exists
    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Load all approval records
    result = await db.execute(
        select(FSApprovalDB).where(FSApprovalDB.fs_id == doc_id).order_by(FSApprovalDB.created_at.desc())
    )
    approvals = result.scalars().all()

    # Determine current status
    current_status = "NONE"
    if approvals:
        current_status = approvals[0].status.value

    schemas = [
        FSApprovalSchema(
            id=a.id,
            fs_id=a.fs_id,
            approver_id=a.approver_id,
            status=a.status.value,
            comment=a.comment,
            created_at=a.created_at,
        )
        for a in approvals
    ]

    return APIResponse(
        data=ApprovalStatusResponse(
            fs_id=doc_id,
            current_status=current_status,
            history=schemas,
            total=len(schemas),
        ),
    )
