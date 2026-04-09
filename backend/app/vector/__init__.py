"""Qdrant manager singleton accessor."""

from functools import lru_cache

from app.vector.client import QdrantManager  # noqa: F401


@lru_cache
def get_qdrant_manager() -> QdrantManager:
    """Return a cached QdrantManager singleton."""
    return QdrantManager()
