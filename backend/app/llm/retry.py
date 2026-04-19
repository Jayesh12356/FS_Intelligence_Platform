"""Lightweight LLM retry helper.

Implements exponential backoff + jitter without a tenacity dependency. Used by
``pipeline_call_llm`` and the direct LLM client to transparently recover from
transient failures (network hiccups, 5xx, brief rate-limit spikes).
"""

from __future__ import annotations

import asyncio
import logging
import random
from functools import wraps
from typing import Any, Awaitable, Callable, Tuple, Type, TypeVar

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


TRANSIENT_EXC_DEFAULTS: Tuple[Type[BaseException], ...] = (
    TimeoutError,
    asyncio.TimeoutError,
    ConnectionError,
)


def _should_retry(exc: BaseException, transient: Tuple[Type[BaseException], ...]) -> bool:
    if isinstance(exc, transient):
        return True
    msg = str(exc).lower()
    return any(tok in msg for tok in ("timeout", "rate limit", "temporarily", "unavailable", "502", "503", "504"))


async def llm_retry[T](
    coro_factory: Callable[[], Awaitable[T]],
    *,
    attempts: int | None = None,
    base_delay: float = 0.6,
    max_delay: float = 8.0,
    transient: Tuple[Type[BaseException], ...] = TRANSIENT_EXC_DEFAULTS,
    label: str = "llm_call",
) -> T:
    """Invoke ``coro_factory()`` with exponential-backoff retry.

    ``coro_factory`` must be a zero-arg callable returning a coroutine, so
    each retry creates a fresh awaitable.
    """
    settings = get_settings()
    max_attempts = attempts if attempts is not None else int(getattr(settings, "LLM_RETRY_ATTEMPTS", 3))
    max_attempts = max(1, max_attempts)

    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except BaseException as exc:  # noqa: BLE001 — we inspect via _should_retry
            last_exc = exc
            if attempt >= max_attempts or not _should_retry(exc, transient):
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay = delay * (0.7 + 0.6 * random.random())  # 0.7x–1.3x jitter
            logger.warning(
                "%s attempt %d/%d failed: %s — retrying in %.2fs",
                label,
                attempt,
                max_attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    assert last_exc is not None
    raise last_exc


def with_llm_retry(label: str = "llm_call"):
    """Decorator form of :func:`llm_retry` for async functions."""

    def _wrap(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def _inner(*args: Any, **kwargs: Any) -> T:
            async def _factory() -> T:
                return await fn(*args, **kwargs)

            return await llm_retry(_factory, label=label)

        return _inner

    return _wrap
