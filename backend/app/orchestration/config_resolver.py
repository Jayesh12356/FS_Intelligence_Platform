"""Load ToolConfigDB for orchestration (LLM / build / frontend provider names)."""

import logging
import time
from typing import List

from sqlalchemy import select

from app.db.base import async_session_factory
from app.db.models import ToolConfigDB

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 5.0
_cached_llm_provider: str | None = None
_cached_fallback_chain: List[str] | None = None
_cache_at: float = 0.0


async def _load_config() -> ToolConfigDB | None:
    async with async_session_factory() as session:
        result = await session.execute(select(ToolConfigDB).where(ToolConfigDB.user_id == "default").limit(1))
        return result.scalar_one_or_none()


# Document-LLM providers that the orchestration layer is allowed to
# resolve to. Must stay in sync with ``ALLOWED_LLM_PROVIDERS`` in
# ``app.api.orchestration_router`` — cursor is included here because
# the queue-bridge worker handoff lets it serve Generate FS / Analyze
# / Reverse FS like any synchronous provider would.
_VALID_LLM_PROVIDERS = {"api", "claude_code", "cursor", "mock"}

# Subscription-backed providers must NEVER be silently downgraded to
# Direct API: doing so would charge OpenRouter / Anthropic credits the
# user did not authorise. If the user picked one of these, we honour it
# even when the rest of the cache invalidates around it.
_NO_FALLBACK_PROVIDERS = {"cursor", "claude_code"}


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

    # Unknown providers fall back to Direct API. Cursor and Claude Code
    # are first-class Document LLMs, so they pass through untouched.
    if name not in _VALID_LLM_PROVIDERS:
        logger.warning(
            "Configured llm_provider=%r is unknown; routing to 'api'.",
            name,
        )
        name = "api"

    _cached_llm_provider = name

    # 0.4.0: strict single-provider routing. The bridge no longer walks
    # a fallback chain, so we publish the chain as exactly the chosen
    # provider. Legacy callers that read the chain see a one-element
    # list.
    _cached_fallback_chain = [name]
    _cache_at = now
    logger.debug(
        "Resolved orchestration llm_provider=%s (strict, no fallback)",
        _cached_llm_provider,
    )


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
