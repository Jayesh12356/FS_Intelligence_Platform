"""Collaboration API — comments on FS document sections (L9)."""

import logging
import uuid
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.audit import log_audit_event
from app.db.models import (
    AuditEventType,
    FSCommentDB,
    FSDocument,
    FSMentionDB,
)
from app.models.schemas import (
    APIResponse,
    CommentCreateRequest,
    CommentListResponse,
    FSCommentSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fs", tags=["collaboration"])


def _extract_mentions(text: str) -> list[str]:
    """Extract @-mentions from comment text."""
    return re.findall(r"@(\w+)", text)


@router.post("/{doc_id}/sections/{section_index}/comments", response_model=APIResponse[FSCommentSchema])
async def add_comment(
    doc_id: uuid.UUID,
    section_index: int,
    body: CommentCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSCommentSchema]:
    """Add a comment to a specific section of an FS document."""
    # Verify document exists
    doc_result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="Comment text cannot be empty")

    # Create comment
    comment = FSCommentDB(
        fs_id=doc_id,
        section_index=section_index,
        user_id=body.user_id,
        text=body.text.strip(),
        resolved=False,
    )
    db.add(comment)
    await db.flush()

    # Extract and persist mentions
    mention_ids = body.mentions or _extract_mentions(body.text)
    mention_records = []
    for user_id in set(mention_ids):
        mention = FSMentionDB(
            comment_id=comment.id,
            mentioned_user_id=user_id,
        )
        db.add(mention)
        mention_records.append(mention)

    # Log audit event
    await log_audit_event(
        db, doc_id, AuditEventType.COMMENT_ADDED,
        user_id=body.user_id,
        payload={
            "section_index": section_index,
            "comment_id": str(comment.id),
            "mentions": [m.mentioned_user_id for m in mention_records],
        },
    )

    await db.flush()
    await db.refresh(comment)

    return APIResponse(
        data=FSCommentSchema(
            id=comment.id,
            fs_id=comment.fs_id,
            section_index=comment.section_index,
            user_id=comment.user_id,
            text=comment.text,
            resolved=comment.resolved,
            mentions=[m.mentioned_user_id for m in mention_records],
            created_at=comment.created_at,
        ),
    )


@router.get("/{doc_id}/comments", response_model=APIResponse[CommentListResponse])
async def list_comments(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CommentListResponse]:
    """List all comments for an FS document, ordered by section then date."""
    # Verify document exists
    doc_result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(FSCommentDB)
        .where(FSCommentDB.fs_id == doc_id)
        .order_by(FSCommentDB.section_index, FSCommentDB.created_at)
    )
    comments = result.scalars().all()

    # Load mentions for each comment
    schemas = []
    for c in comments:
        mentions_result = await db.execute(
            select(FSMentionDB).where(FSMentionDB.comment_id == c.id)
        )
        mentions = mentions_result.scalars().all()

        schemas.append(
            FSCommentSchema(
                id=c.id,
                fs_id=c.fs_id,
                section_index=c.section_index,
                user_id=c.user_id,
                text=c.text,
                resolved=c.resolved,
                mentions=[m.mentioned_user_id for m in mentions],
                created_at=c.created_at,
            )
        )

    resolved_count = sum(1 for c in comments if c.resolved)

    return APIResponse(
        data=CommentListResponse(
            comments=schemas,
            total=len(schemas),
            resolved_count=resolved_count,
        ),
    )


@router.patch("/{doc_id}/comments/{comment_id}/resolve", response_model=APIResponse[FSCommentSchema])
async def resolve_comment(
    doc_id: uuid.UUID,
    comment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[FSCommentSchema]:
    """Mark a comment as resolved."""
    result = await db.execute(
        select(FSCommentDB).where(
            FSCommentDB.id == comment_id,
            FSCommentDB.fs_id == doc_id,
        )
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    comment.resolved = True
    await db.flush()

    # Log audit event
    await log_audit_event(
        db, doc_id, AuditEventType.COMMENT_RESOLVED,
        user_id=comment.user_id,
        payload={"comment_id": str(comment.id), "section_index": comment.section_index},
    )

    await db.flush()
    await db.refresh(comment)

    # Load mentions
    mentions_result = await db.execute(
        select(FSMentionDB).where(FSMentionDB.comment_id == comment.id)
    )
    mentions = mentions_result.scalars().all()

    return APIResponse(
        data=FSCommentSchema(
            id=comment.id,
            fs_id=comment.fs_id,
            section_index=comment.section_index,
            user_id=comment.user_id,
            text=comment.text,
            resolved=comment.resolved,
            mentions=[m.mentioned_user_id for m in mentions],
            created_at=comment.created_at,
        ),
    )
