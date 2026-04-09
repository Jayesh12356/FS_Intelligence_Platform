"""FS Vector Store — embeds and stores parsed document chunks in Qdrant.

Supports multiple embedding providers via EMBEDDING_PROVIDER setting:
  - openai     → OpenAI API (text-embedding-3-small, 1536 dims)
  - groq       → Groq API (OpenAI-compatible)
  - openrouter → OpenRouter API (OpenAI-compatible)

Upserts chunks into the fs_requirements collection with metadata payload.
"""

import logging
import uuid
from typing import List

from openai import OpenAI

from app.config import get_settings
from app.parsers.base import FSChunk
from app.vector import get_qdrant_manager
from qdrant_client.http import models as qdrant_models

logger = logging.getLogger(__name__)

# Max texts per embedding batch
_EMBED_BATCH_SIZE = 100

# Provider base URLs (OpenAI uses default, so not listed)
_EMBED_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

# Default embedding models per provider
_DEFAULT_EMBED_MODELS = {
    "openai": "text-embedding-3-small",
    "groq": "text-embedding-3-small",         # Groq supports OpenAI models
    "openrouter": "openai/text-embedding-3-small",
}


def _get_embedding_client() -> OpenAI:
    """Create an embedding client for the configured provider.

    All supported providers (OpenAI, Groq, OpenRouter) use the
    OpenAI SDK — just with different base_urls and API keys.
    """
    settings = get_settings()
    provider = getattr(settings, "EMBEDDING_PROVIDER", "openai").lower().strip()

    # Resolve API key
    key_map = {
        "openai": settings.OPENAI_API_KEY,
        "groq": getattr(settings, "GROQ_API_KEY", ""),
        "openrouter": getattr(settings, "OPENROUTER_API_KEY", ""),
    }
    api_key = key_map.get(provider, settings.OPENAI_API_KEY)

    if not api_key:
        raise ValueError(
            f"No API key for embedding provider '{provider}'. "
            f"Set the corresponding env var (e.g. OPENAI_API_KEY, GROQ_API_KEY)."
        )

    kwargs = {"api_key": api_key}
    if provider in _EMBED_BASE_URLS:
        kwargs["base_url"] = _EMBED_BASE_URLS[provider]

    logger.debug("Embedding client → provider=%s", provider)
    return OpenAI(**kwargs)


def _generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts.

    Uses the provider configured via EMBEDDING_PROVIDER.
    Batches requests to stay within API limits.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors.
    """
    settings = get_settings()
    client = _get_embedding_client()
    model = settings.EMBEDDING_MODEL or _DEFAULT_EMBED_MODELS.get(
        getattr(settings, "EMBEDDING_PROVIDER", "openai"), "text-embedding-3-small"
    )
    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), _EMBED_BATCH_SIZE):
        batch = texts[i : i + _EMBED_BATCH_SIZE]
        try:
            response = client.embeddings.create(
                model=model,
                input=batch,
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
        except Exception as exc:
            logger.error("Embedding generation failed for batch %d: %s", i, exc)
            raise

    return all_embeddings


async def store_fs_chunks(fs_id: str, chunks: List[FSChunk]) -> int:
    """Embed and store chunks in Qdrant fs_requirements collection.

    Args:
        fs_id: UUID of the source FS document.
        chunks: List of FSChunk instances from the chunker.

    Returns:
        Number of chunks stored.

    Raises:
        ValueError: If no chunks provided or API key missing.
        RuntimeError: If embedding or upsert fails.
    """
    if not chunks:
        logger.warning("No chunks to store for document %s", fs_id)
        return 0

    texts = [chunk.text for chunk in chunks]

    # Generate embeddings
    try:
        embeddings = _generate_embeddings(texts)
    except Exception as exc:
        logger.error("Failed to generate embeddings for document %s: %s", fs_id, exc)
        raise RuntimeError(f"Embedding generation failed: {exc}") from exc

    # Build Qdrant points
    points: List[qdrant_models.PointStruct] = []
    for chunk, embedding in zip(chunks, embeddings):
        point_id = str(uuid.uuid4())
        points.append(qdrant_models.PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "fs_id": str(fs_id),
                "section_heading": chunk.section_heading,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
            },
        ))

    # Upsert into Qdrant
    qdrant = get_qdrant_manager()
    try:
        qdrant.client.upsert(
            collection_name="fs_requirements",
            points=points,
        )
    except Exception as exc:
        logger.error("Qdrant upsert failed for document %s: %s", fs_id, exc)
        raise RuntimeError(f"Qdrant upsert failed: {exc}") from exc

    logger.info(
        "Stored %d chunks for document %s in Qdrant (collection: fs_requirements)",
        len(points),
        fs_id,
    )

    return len(points)


# ── L9: Semantic Search & Library Operations ───────────


def search_similar_sections(
    text: str,
    collection: str = "fs_requirements",
    threshold: float = 0.88,
    exclude_fs_id: str = "",
    limit: int = 5,
) -> list[dict]:
    """Search Qdrant for sections similar to the given text.

    Args:
        text: The text to search for similar content.
        collection: Qdrant collection to search.
        threshold: Minimum cosine similarity score.
        exclude_fs_id: FS document ID to exclude from results (for cross-doc detection).
        limit: Maximum number of results to return.

    Returns:
        List of dicts with: fs_id, section_heading, text, score.
    """
    if not text or len(text.strip()) < 10:
        return []

    # Generate embedding for the query text
    embeddings = _generate_embeddings([text])
    if not embeddings:
        return []

    query_vector = embeddings[0]

    # Search Qdrant
    qdrant = get_qdrant_manager()
    try:
        results = qdrant.client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit + 10,  # fetch extra to account for filtering
            score_threshold=threshold,
        )
    except Exception as exc:
        logger.error("Qdrant search failed: %s", exc)
        return []

    matches = []
    for hit in results:
        payload = hit.payload or {}
        hit_fs_id = payload.get("fs_id", "")

        # Exclude results from the same document
        if exclude_fs_id and hit_fs_id == str(exclude_fs_id):
            continue

        matches.append({
            "fs_id": hit_fs_id,
            "section_heading": payload.get("section_heading", ""),
            "text": payload.get("text", ""),
            "score": hit.score,
            "point_id": str(hit.id),
        })

        if len(matches) >= limit:
            break

    return matches


def store_library_item(
    fs_id: str,
    section_index: int,
    heading: str,
    text: str,
) -> str:
    """Store a requirement in the fs_library Qdrant collection.

    Args:
        fs_id: Source FS document ID.
        section_index: Section index in the source document.
        heading: Section heading.
        text: Full section text.

    Returns:
        The Qdrant point ID created.
    """
    if not text or len(text.strip()) < 10:
        logger.warning("Skipping library store: text too short for fs_id=%s section=%d", fs_id, section_index)
        return ""

    embeddings = _generate_embeddings([text])
    if not embeddings:
        raise RuntimeError("Failed to generate embedding for library item")

    point_id = str(uuid.uuid4())
    point = qdrant_models.PointStruct(
        id=point_id,
        vector=embeddings[0],
        payload={
            "fs_id": str(fs_id),
            "section_index": section_index,
            "section_heading": heading,
            "text": text,
        },
    )

    qdrant = get_qdrant_manager()
    try:
        qdrant.client.upsert(
            collection_name="fs_library",
            points=[point],
        )
    except Exception as exc:
        logger.error("Failed to store library item: %s", exc)
        raise RuntimeError(f"Library upsert failed: {exc}") from exc

    logger.info("Stored library item %s for fs_id=%s section=%d", point_id, fs_id, section_index)
    return point_id


def search_library(
    query_text: str,
    limit: int = 10,
    threshold: float = 0.7,
) -> list[dict]:
    """Search the reusable requirement library for similar requirements.

    Args:
        query_text: The search query text.
        limit: Maximum number of results.
        threshold: Minimum similarity score.

    Returns:
        List of dicts with: id, fs_id, section_index, section_heading, text, score.
    """
    if not query_text or len(query_text.strip()) < 5:
        return []

    embeddings = _generate_embeddings([query_text])
    if not embeddings:
        return []

    qdrant = get_qdrant_manager()
    try:
        results = qdrant.client.search(
            collection_name="fs_library",
            query_vector=embeddings[0],
            limit=limit,
            score_threshold=threshold,
        )
    except Exception as exc:
        logger.error("Library search failed: %s", exc)
        return []

    items = []
    for hit in results:
        payload = hit.payload or {}
        items.append({
            "id": str(hit.id),
            "fs_id": payload.get("fs_id", ""),
            "section_index": payload.get("section_index", 0),
            "section_heading": payload.get("section_heading", ""),
            "text": payload.get("text", ""),
            "score": hit.score,
        })

    return items

