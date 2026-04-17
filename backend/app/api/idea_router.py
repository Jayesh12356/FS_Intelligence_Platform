"""Idea-to-FS generation API — convert product ideas into professional FS documents."""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import FSDocument, FSDocumentStatus, IdeaSessionDB
from app.models.schemas import APIResponse
from app.pipeline.nodes.idea_node import (
    generate_fs_quick,
    generate_guided_questions,
    generate_fs_guided,
)
from app.parsers.section_extractor import extract_sections_from_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/idea", tags=["idea"])


class QuickGenerateRequest(BaseModel):
    idea: str = Field(..., min_length=10, description="Product idea description")
    industry: Optional[str] = Field(None, description="Target industry")
    complexity: Optional[str] = Field(None, description="simple | moderate | enterprise")


class GuidedStepRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="Session ID for continuing a guided flow")
    idea: str = Field("", description="Product idea (required for step 0)")
    step: int = Field(0, description="Current step number")
    answers: Optional[dict] = Field(None, description="Answers to previous step's questions")
    industry: Optional[str] = None
    complexity: Optional[str] = None


class IdeaGenerateResponse(BaseModel):
    document_id: str
    filename: str
    fs_text: str
    section_count: int


class GuidedQuestionsResponse(BaseModel):
    session_id: str
    step: int
    questions: list[dict]


@router.post("/generate", response_model=APIResponse[IdeaGenerateResponse])
async def generate_fs_from_idea(
    req: QuickGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[IdeaGenerateResponse]:
    """Quick mode: generate a full FS document from a product idea."""
    try:
        fs_text = await generate_fs_quick(
            idea=req.idea,
            industry=req.industry,
            complexity=req.complexity,
        )
    except Exception as exc:
        logger.exception("FS generation failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}") from exc

    title_fragment = req.idea[:60].strip().replace(" ", "_")
    filename = f"idea_{title_fragment}.txt"

    sections = extract_sections_from_text(fs_text)

    doc = FSDocument(
        id=uuid.uuid4(),
        filename=filename,
        original_text=req.idea,
        parsed_text=fs_text,
        status=FSDocumentStatus.PARSED,
        file_size=len(fs_text.encode()),
        content_type="text/plain",
    )
    db.add(doc)

    session = IdeaSessionDB(
        id=uuid.uuid4(),
        idea_text=req.idea,
        industry=req.industry or "",
        complexity=req.complexity or "",
        mode="quick",
        generated_fs_id=doc.id,
    )
    db.add(session)
    await db.commit()

    logger.info("Generated FS document %s from idea (quick mode)", doc.id)

    return APIResponse(
        data=IdeaGenerateResponse(
            document_id=str(doc.id),
            filename=filename,
            fs_text=fs_text,
            section_count=len(sections),
        )
    )


@router.post("/guided", response_model=APIResponse)
async def guided_step(
    req: GuidedStepRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Guided mode: multi-step wizard for FS generation."""

    if req.step == 0:
        if not req.idea or len(req.idea.strip()) < 10:
            raise HTTPException(status_code=400, detail="Idea must be at least 10 characters")

        try:
            questions = await generate_guided_questions(req.idea)
        except Exception as exc:
            logger.exception("Guided question generation failed")
            raise HTTPException(status_code=500, detail=f"Question generation failed: {exc}") from exc

        session = IdeaSessionDB(
            id=uuid.uuid4(),
            idea_text=req.idea,
            industry=req.industry or "",
            complexity=req.complexity or "",
            mode="guided",
            conversation_state={"step": 0, "questions": questions, "answers": {}},
        )
        db.add(session)
        await db.commit()

        return APIResponse(
            data=GuidedQuestionsResponse(
                session_id=str(session.id),
                step=0,
                questions=questions,
            ).model_dump()
        )

    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id required for step > 0")

    result = await db.execute(
        select(IdeaSessionDB).where(IdeaSessionDB.id == uuid.UUID(req.session_id))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.conversation_state or {}
    if req.answers:
        existing_answers = state.get("answers", {})
        existing_answers.update(req.answers)
        state["answers"] = existing_answers

    if req.step >= 1 and state.get("answers"):
        try:
            fs_text = await generate_fs_guided(
                idea=session.idea_text,
                answers=state["answers"],
                industry=session.industry or None,
                complexity=session.complexity or None,
            )
        except Exception as exc:
            logger.exception("Guided FS generation failed")
            raise HTTPException(status_code=500, detail=f"Generation failed: {exc}") from exc

        title_fragment = session.idea_text[:60].strip().replace(" ", "_")
        filename = f"idea_{title_fragment}.txt"
        sections = extract_sections_from_text(fs_text)

        doc = FSDocument(
            id=uuid.uuid4(),
            filename=filename,
            original_text=session.idea_text,
            parsed_text=fs_text,
            status=FSDocumentStatus.PARSED,
            file_size=len(fs_text.encode()),
            content_type="text/plain",
        )
        db.add(doc)

        session.generated_fs_id = doc.id
        state["step"] = req.step
        state["completed"] = True
        session.conversation_state = state
        await db.commit()

        return APIResponse(
            data=IdeaGenerateResponse(
                document_id=str(doc.id),
                filename=filename,
                fs_text=fs_text,
                section_count=len(sections),
            ).model_dump()
        )

    state["step"] = req.step
    session.conversation_state = state
    await db.commit()

    return APIResponse(data={"session_id": str(session.id), "step": req.step, "status": "awaiting_answers"})
