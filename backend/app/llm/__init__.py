"""LLM client singleton accessor."""

from functools import lru_cache

from app.llm.client import LLMClient, LLMError  # noqa: F401


@lru_cache
def get_llm_client() -> LLMClient:
    """Return a cached LLMClient singleton."""
    return LLMClient()
