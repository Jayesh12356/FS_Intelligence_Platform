"""Duplicate detection node — finds cross-document duplicate requirements via Qdrant (L9).

For each parsed section, embeds the text and searches the fs_requirements
Qdrant collection for cosine similarity > threshold. If a match is found
from a DIFFERENT FS document, it is flagged as a potential duplicate.
"""

import logging
from typing import Any, Dict, List

from app.pipeline.state import FSAnalysisState

logger = logging.getLogger(__name__)

# Minimum cosine similarity to flag as potential duplicate
DUPLICATE_THRESHOLD = 0.88


async def duplicate_node(state: FSAnalysisState) -> FSAnalysisState:
    """Detect cross-document duplicate requirements via Qdrant similarity search.

    For each section in the document, embeds the content and searches
    fs_requirements for similar sections from OTHER documents.

    Args:
        state: Pipeline state with fs_id and parsed_sections.

    Returns:
        Updated state with duplicates list populated.
    """
    fs_id = state.get("fs_id", "")
    sections = state.get("parsed_sections", [])
    errors = list(state.get("errors", []))
    duplicates: List[Dict[str, Any]] = []

    if not sections:
        logger.warning("duplicate_node: no sections for fs_id=%s", fs_id)
        return {**state, "duplicates": duplicates}

    try:
        from app.vector.fs_store import search_similar_sections

        for section in sections:
            content = section.get("content", "")
            heading = section.get("heading", "")
            section_index = section.get("section_index", 0)

            if not content or len(content.strip()) < 20:
                continue

            try:
                matches = search_similar_sections(
                    text=content,
                    collection="fs_requirements",
                    threshold=DUPLICATE_THRESHOLD,
                    exclude_fs_id=fs_id,
                    limit=3,
                )

                for match in matches:
                    duplicate = {
                        "section_index": section_index,
                        "section_heading": heading,
                        "similar_fs_id": match.get("fs_id", ""),
                        "similar_section_heading": match.get("section_heading", ""),
                        "similarity_score": match.get("score", 0.0),
                        "flagged_text": content[:500],
                        "similar_text": match.get("text", "")[:500],
                    }
                    duplicates.append(duplicate)

            except Exception as exc:
                logger.warning(
                    "duplicate_node: search failed for section %d: %s",
                    section_index, exc,
                )
                continue

    except ImportError as exc:
        logger.error("duplicate_node: vector store not available: %s", exc)
        errors.append(f"Duplicate detection unavailable: {exc}")
    except Exception as exc:
        logger.error("duplicate_node: unexpected error: %s", exc)
        errors.append(f"Duplicate detection error: {exc}")

    logger.info(
        "duplicate_node: found %d potential duplicates for fs_id=%s",
        len(duplicates), fs_id,
    )

    return {
        **state,
        "duplicates": duplicates,
        "errors": errors,
    }
