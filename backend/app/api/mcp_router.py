"""MCP session monitoring API."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_db
from app.db.models import MCPSessionDB, MCPSessionEventDB, MCPSessionStatus
from app.models.schemas import (
    APIResponse,
    MCPSessionCreateRequest,
    MCPSessionEventCreateRequest,
    MCPSessionEventListResponse,
    MCPSessionEventSchema,
    MCPSessionListResponse,
    MCPSessionSchema,
)

router = APIRouter(prefix="/api/mcp", tags=["mcp-monitoring"])


@router.post("/sessions", response_model=APIResponse[MCPSessionSchema])
async def create_session(
    body: MCPSessionCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[MCPSessionSchema]:
    settings = get_settings()
    if not settings.MCP_MONITORING_ENABLED:
        raise HTTPException(status_code=400, detail="MCP monitoring disabled")
    session = MCPSessionDB(
        fs_id=body.document_id,
        target_stack=body.target_stack,
        source=body.source,
        dry_run=body.dry_run,
        total_phases=body.total_phases,
        meta_json=body.meta,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return APIResponse(data=MCPSessionSchema.model_validate(session))


@router.get("/sessions", response_model=APIResponse[MCPSessionListResponse])
async def list_sessions(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[MCPSessionListResponse]:
    result = await db.execute(
        select(MCPSessionDB).order_by(MCPSessionDB.created_at.desc()).limit(max(1, min(limit, 200)))
    )
    rows = result.scalars().all()
    data = [MCPSessionSchema.model_validate(r) for r in rows]
    return APIResponse(data=MCPSessionListResponse(sessions=data, total=len(data)))


@router.get("/sessions/{session_id}", response_model=APIResponse[MCPSessionSchema])
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[MCPSessionSchema]:
    row = await db.get(MCPSessionDB, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return APIResponse(data=MCPSessionSchema.model_validate(row))


@router.post("/sessions/{session_id}/events", response_model=APIResponse[MCPSessionEventSchema])
async def append_event(
    session_id: uuid.UUID,
    body: MCPSessionEventCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[MCPSessionEventSchema]:
    session = await db.get(MCPSessionDB, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    evt = MCPSessionEventDB(
        session_id=session_id,
        event_type=body.event_type,
        phase=body.phase,
        status=body.status,
        message=body.message,
        payload_json=body.payload,
    )
    db.add(evt)

    session.phase = max(session.phase, body.phase)
    session.current_step = body.message or session.current_step
    if body.status.lower() in {"failed", "error"}:
        session.status = MCPSessionStatus.FAILED
        session.ended_at = datetime.now(UTC)
    elif body.event_type == "session_completed":
        session.status = MCPSessionStatus.PASSED
        session.ended_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(evt)
    return APIResponse(data=MCPSessionEventSchema.model_validate(evt))


@router.get("/sessions/{session_id}/events", response_model=APIResponse[MCPSessionEventListResponse])
async def list_events(
    session_id: uuid.UUID,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[MCPSessionEventListResponse]:
    session = await db.get(MCPSessionDB, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    result = await db.execute(
        select(MCPSessionEventDB)
        .where(MCPSessionEventDB.session_id == session_id)
        .order_by(MCPSessionEventDB.created_at.desc())
        .limit(max(1, min(limit, 1000)))
    )
    rows = result.scalars().all()
    data = [MCPSessionEventSchema.model_validate(r) for r in rows]
    return APIResponse(data=MCPSessionEventListResponse(events=data, total=len(data)))


@router.get("/sessions/{session_id}/events/stream")
async def stream_events(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(MCPSessionDB, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        last_seen = None
        while True:
            query = select(MCPSessionEventDB).where(MCPSessionEventDB.session_id == session_id)
            if last_seen is not None:
                query = query.where(MCPSessionEventDB.created_at > last_seen)
            query = query.order_by(MCPSessionEventDB.created_at.asc()).limit(100)
            result = await db.execute(query)
            rows = result.scalars().all()
            for row in rows:
                payload = MCPSessionEventSchema.model_validate(row).model_dump(mode="json")
                last_seen = row.created_at
                yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
