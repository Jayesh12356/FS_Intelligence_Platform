"""Idea-to-FS generation API — convert product ideas into professional FS documents."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import (
    CursorTaskDB,
    CursorTaskKind,
    CursorTaskStatus,
    FSDocument,
    FSDocumentStatus,
    IdeaSessionDB,
)
from app.llm.client import LLMError
from app.models.schemas import APIResponse
from app.orchestration.config_resolver import get_configured_llm_provider_name
from app.orchestration.cursor_prompts import (
    build_generate_fs_prompt,
    build_mcp_snippet,
)
from app.parsers.section_extractor import extract_sections_from_text
from app.pipeline.nodes.idea_node import (
    generate_fs_guided,
    generate_fs_quick,
    generate_guided_questions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/idea", tags=["idea"])


class QuickGenerateRequest(BaseModel):
    idea: str = Field(..., min_length=10, description="Product idea description")
    industry: str | None = Field(None, description="Target industry")
    complexity: str | None = Field(None, description="simple | moderate | enterprise")


class GuidedStepRequest(BaseModel):
    session_id: str | None = Field(None, description="Session ID for continuing a guided flow")
    idea: str = Field("", description="Product idea (required for step 0)")
    step: int = Field(0, description="Current step number")
    answers: dict | None = Field(None, description="Answers to previous step's questions")
    industry: str | None = None
    complexity: str | None = None


class IdeaGenerateResponse(BaseModel):
    document_id: str
    filename: str
    fs_text: str
    section_count: int


class GuidedQuestionsResponse(BaseModel):
    session_id: str
    step: int
    questions: list[dict]


class CursorTaskEnvelope(BaseModel):
    mode: str = "cursor_task"
    task_id: str
    kind: str
    prompt: str
    mcp_snippet: str
    status: str


async def _mint_cursor_generate_fs_task(
    db: AsyncSession,
    *,
    idea: str,
    industry: str | None,
    complexity: str | None,
) -> CursorTaskEnvelope:
    """Mint a Cursor paste-per-action task and return the envelope.

    The Generate FS UI calls this path when ``llm_provider == "cursor"``
    so no pipeline LLM calls are made. The user pastes the resulting
    prompt into Cursor; Cursor submits the FS via the MCP tool.
    """
    task_id = uuid.uuid4()
    prompt = build_generate_fs_prompt(
        task_id=task_id,
        idea=idea,
        industry=industry or "",
        complexity=complexity or "",
    )
    task = CursorTaskDB(
        id=task_id,
        kind=CursorTaskKind.GENERATE_FS,
        status=CursorTaskStatus.PENDING,
        input_payload={
            "idea": idea,
            "industry": industry or "",
            "complexity": complexity or "",
        },
        prompt_text=prompt,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    logger.info("Idea route branched to Cursor paste-per-action task %s", task.id)
    return CursorTaskEnvelope(
        task_id=str(task.id),
        kind="generate_fs",
        prompt=task.prompt_text,
        mcp_snippet=build_mcp_snippet(),
        status=task.status.value.lower(),
    )


@router.post("/generate", response_model=APIResponse)
async def generate_fs_from_idea(
    req: QuickGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Quick mode: generate a full FS document from a product idea.

    Branches on ``llm_provider``: Cursor returns a paste-per-action
    task envelope; api and claude_code run the synchronous pipeline.
    """
    provider = (await get_configured_llm_provider_name()) or "api"
    if provider == "cursor":
        envelope = await _mint_cursor_generate_fs_task(
            db,
            idea=req.idea,
            industry=req.industry,
            complexity=req.complexity,
        )
        return APIResponse(data=envelope.model_dump())

    try:
        fs_text = await generate_fs_quick(
            idea=req.idea,
            industry=req.industry,
            complexity=req.complexity,
        )
    except LLMError:
        # Let the global handler surface the typed LLMError (e.g.
        # claude_cli_unavailable as 503) instead of wrapping it as 500.
        raise
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

    provider = (await get_configured_llm_provider_name()) or "api"

    if req.step == 0:
        if not req.idea or len(req.idea.strip()) < 10:
            raise HTTPException(status_code=400, detail="Idea must be at least 10 characters")

        # Cursor does not do an interactive guided flow — there is one
        # paste that produces the full FS in one shot. Route the user
        # straight to the paste modal with a generate_fs task envelope
        # so Settings and Create stay consistent.
        if provider == "cursor":
            envelope = await _mint_cursor_generate_fs_task(
                db,
                idea=req.idea,
                industry=req.industry,
                complexity=req.complexity,
            )
            return APIResponse(data=envelope.model_dump())

        try:
            questions = await generate_guided_questions(req.idea)
        except LLMError:
            raise
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

    try:
        session_uuid = uuid.UUID(req.session_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"session_id must be a valid UUID, got: {req.session_id!r}",
        ) from exc

    result = await db.execute(select(IdeaSessionDB).where(IdeaSessionDB.id == session_uuid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.conversation_state or {}
    if req.answers:
        existing_answers = state.get("answers", {})
        existing_answers.update(req.answers)
        state["answers"] = existing_answers

    if req.step >= 1 and state.get("answers"):
        if provider == "cursor":
            # Guided answers should enrich the idea, but Cursor only
            # wants one paste. Collapse everything into a single
            # generate_fs task prompt.
            enriched_idea = session.idea_text
            answers = state.get("answers") or {}
            if answers:
                lines = [session.idea_text, "", "Additional context:"]
                for key, value in answers.items():
                    lines.append(f"- {key}: {value}")
                enriched_idea = "\n".join(lines)
            envelope = await _mint_cursor_generate_fs_task(
                db,
                idea=enriched_idea,
                industry=session.industry or None,
                complexity=session.complexity or None,
            )
            state["step"] = req.step
            state["cursor_task_id"] = envelope.task_id
            session.conversation_state = state
            await db.commit()
            return APIResponse(data=envelope.model_dump())

        try:
            fs_text = await generate_fs_guided(
                idea=session.idea_text,
                answers=state["answers"],
                industry=session.industry or None,
                complexity=session.complexity or None,
            )
        except LLMError:
            raise
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
