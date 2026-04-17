"""Load ToolConfigDB for orchestration (LLM / build / frontend provider names)."""

import logging
import time
from typing import List, Optional

from sqlalchemy import select

from app.config import get_settings
from app.db.base import async_session_factory
from app.db.models import ToolConfigDB

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 5.0
_cached_llm_provider: Optional[str] = None
_cached_fallback_chain: Optional[List[str]] = None
_cache_at: float = 0.0


async def _load_config() -> ToolConfigDB | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ToolConfigDB).where(ToolConfigDB.user_id == "default").limit(1)
        )
        return result.scalar_one_or_none()


async def _ensure_cache() -> None:
    global _cached_llm_provider, _cached_fallback_chain, _cache_at
    now = time.monotonic()
    if _cached_llm_provider is not None and (now - _cache_at) < _CACHE_TTL_SEC:
        return

    row = await _load_config()
    raw = (row.llm_provider if row else None) or "api"
    name = raw.strip().lower().replace("-", "_") if raw else "api"
    if not name:
        name = "api"

    _cached_llm_provider = name

    settings = get_settings()
    chain = (row.fallback_chain if row else None) or ["api"]
    # In strict mode we do NOT silently append "api" as a last-resort provider —
    # the user asked for a specific provider and wants failures to surface
    # rather than be papered over by direct API calls.
    if not settings.ORCHESTRATION_STRICT_LLM and "api" not in chain:
        chain = chain + ["api"]
    _cached_fallback_chain = chain
    _cache_at = now
    logger.debug("Resolved orchestration llm_provider=%s, fallback_chain=%s", _cached_llm_provider, _cached_fallback_chain)


async def get_configured_llm_provider_name() -> str:
    """Return `llm_provider` from ToolConfigDB for user_id=default."""
    await _ensure_cache()
    return _cached_llm_provider  # type: ignore[return-value]


async def get_configured_fallback_chain() -> List[str]:
    """Return the fallback_chain from ToolConfigDB."""
    await _ensure_cache()
    return _cached_fallback_chain or ["api"]


def invalidate_orchestration_config_cache() -> None:
    """Call after PUT /api/orchestration/config so next LLM call sees new value."""
    global _cached_llm_provider, _cached_fallback_chain, _cache_at
    _cached_llm_provider = None
    _cached_fallback_chain = None
    _cache_at = 0.0
