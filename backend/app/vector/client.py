"""Qdrant vector store client — collection management and operations."""

import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.config import get_settings

logger = logging.getLogger(__name__)

# Collection definitions
COLLECTIONS = {
    "fs_requirements": {
        "size": 1536,
        "distance": qdrant_models.Distance.COSINE,
        "description": "Stores requirement embeddings from FS documents",
    },
    "fs_library": {
        "size": 1536,
        "distance": qdrant_models.Distance.COSINE,
        "description": "Stores reusable requirement patterns",
    },
}


class QdrantManager:
    """Manages Qdrant vector store connections and collections."""

    def __init__(self) -> None:
        settings = get_settings()
        self._url = settings.QDRANT_URL
        self._api_key = settings.QDRANT_API_KEY or None
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        """Lazy-initialised Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(url=self._url, api_key=self._api_key)
        return self._client

    async def create_collections(self) -> None:
        """Create all required collections (idempotent — safe on every startup)."""
        for name, config in COLLECTIONS.items():
            try:
                # Check if collection already exists
                existing = self.client.get_collections().collections
                existing_names = {c.name for c in existing}

                if name in existing_names:
                    logger.info("Qdrant collection '%s' already exists — skipping", name)
                    continue

                self.client.create_collection(
                    collection_name=name,
                    vectors_config=qdrant_models.VectorParams(
                        size=config["size"],
                        distance=config["distance"],
                    ),
                )
                logger.info("Created Qdrant collection '%s' (dim=%d)", name, config["size"])

            except UnexpectedResponse as exc:
                # Collection might already exist (race condition)
                if "already exists" in str(exc).lower():
                    logger.info("Qdrant collection '%s' already exists (race)", name)
                else:
                    logger.error("Failed to create collection '%s': %s", name, exc)
                    raise
            except Exception as exc:
                logger.error("Failed to create Qdrant collection '%s': %s", name, exc)
                raise

    async def check_health(self) -> bool:
        """Check if Qdrant is reachable."""
        try:
            self.client.get_collections()
            return True
        except Exception as exc:
            logger.warning("Qdrant health check failed: %s", exc)
            return False
