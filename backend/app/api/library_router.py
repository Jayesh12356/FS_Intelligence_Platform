"""Requirement library API — semantic search in reusable requirement library (L9)."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import FSDocument, FSDocumentStatus
from app.models.schemas import (
    APIResponse,
    LibraryItemSchema,
    LibrarySearchResponse,
    SuggestionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["library"])


@router.get("/api/library/search", response_model=APIResponse[LibrarySearchResponse])
async def search_library_endpoint(
    q: str = Query(..., min_length=3, description="Search query text"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
) -> APIResponse[LibrarySearchResponse]:
    """Semantic search in the reusable requirement library.

    Searches the fs_library Qdrant collection for requirements
    similar to the query text.
    """
    try:
        from app.vector.fs_store import search_library

        results = search_library(query_text=q, limit=limit)
    except Exception as exc:
        logger.error("Library search failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Library search failed: {exc}")

    items = [
        LibraryItemSchema(
            id=r["id"],
            fs_id=r["fs_id"],
            section_index=r["section_index"],
            section_heading=r["section_heading"],
            text=r["text"],
            score=r.get("score"),
        )
        for r in results
    ]

    return APIResponse(
        data=LibrarySearchResponse(
            results=items,
            total=len(items),
            query=q,
        ),
    )


@router.get("/api/library/{item_id}", response_model=APIResponse[LibraryItemSchema])
async def get_library_item(
    item_id: str,
) -> APIResponse[LibraryItemSchema]:
    """Get a specific requirement from the library by its Qdrant point ID."""
    try:
        from app.vector import get_qdrant_manager

        qdrant = get_qdrant_manager()
        results = qdrant.client.retrieve(
            collection_name="fs_library",
            ids=[item_id],
            with_payload=True,
        )

        if not results:
            raise HTTPException(status_code=404, detail="Library item not found")

        point = results[0]
        payload = point.payload or {}

        item = LibraryItemSchema(
            id=str(point.id),
            fs_id=payload.get("fs_id", ""),
            section_index=payload.get("section_index", 0),
            section_heading=payload.get("section_heading", ""),
            text=payload.get("text", ""),
        )

        return APIResponse(data=item)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get library item %s: %s", item_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to get library item: {exc}")


@router.post("/api/fs/{doc_id}/suggestions", response_model=APIResponse[SuggestionResponse])
async def suggest_requirements(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[SuggestionResponse]:
    """Suggest similar requirements from the library for a document.

    Searches the fs_library collection for requirements similar to
    each section in the document.
    """
    # Verify document exists and is parsed
    doc_result = await db.execute(
        select(FSDocument).where(FSDocument.id == doc_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status not in (FSDocumentStatus.PARSED, FSDocumentStatus.COMPLETE, FSDocumentStatus.ANALYZING):
        raise HTTPException(
            status_code=400,
            detail=f"Document must be parsed first. Current status: {doc.status.value}",
        )

    # Load parsed sections
    try:
        from app.parsers.router import parse_document as do_parse
        parsed = await do_parse(str(doc.id), db)
        sections = parsed.sections
    except Exception as exc:
        logger.error("Failed to load sections for %s: %s", doc_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to load sections: {exc}")

    import anyio

    all_suggestions: list[LibraryItemSchema] = []
    seen_ids: set[str] = set()
    failed_sections: list[dict] = []

    from app.vector.fs_store import search_library

    def _search(content: str) -> list[dict]:
        return search_library(query_text=content, limit=3, threshold=0.75)

    sem = anyio.Semaphore(4)

    async def _worker(idx: int, content: str, heading: str) -> tuple[int, list[dict] | None, str | None]:
        async with sem:
            try:
                res = await anyio.to_thread.run_sync(_search, content)
                return (idx, res, None)
            except Exception as exc:
                logger.warning("Library search failed for section %d (%s): %s", idx, heading, exc)
                return (idx, None, str(exc))

    tasks: list[tuple[int, str, str]] = []
    for idx, section in enumerate(sections):
        content = section.content if hasattr(section, "content") else section.get("content", "")
        heading = section.heading if hasattr(section, "heading") else section.get("heading", "")
        if not content or len(content.strip()) < 20:
            continue
        tasks.append((idx, content, heading))

    collected: list = []

    async def _run(t):
        out = await _worker(*t)
        collected.append(out)

    async with anyio.create_task_group() as tg:
        for t in tasks:
            tg.start_soon(_run, t)

    for idx, res, err in collected:
        if res is None:
            failed_sections.append({"section_index": idx, "error": err})
            continue
        for r in res:
            if r["fs_id"] == str(doc_id) or r["id"] in seen_ids:
                continue
            seen_ids.add(r["id"])
            all_suggestions.append(
                LibraryItemSchema(
                    id=r["id"],
                    fs_id=r["fs_id"],
                    section_index=r["section_index"],
                    section_heading=r["section_heading"],
                    text=r["text"],
                    score=r.get("score"),
                )
            )

    all_suggestions.sort(key=lambda s: s.score or 0, reverse=True)

    return APIResponse(
        data=SuggestionResponse(
            suggestions=all_suggestions[:20],
            total=len(all_suggestions[:20]),
        ),
        meta={
            "diagnostics": {
                "total_sections": len(tasks),
                "failed_sections": failed_sections,
            }
        },
    )
