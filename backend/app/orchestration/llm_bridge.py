"""Bridge between the orchestration layer and the existing LLM client.

When ORCHESTRATION_ENABLED is true, routes LLM calls through the user-preferred
provider from ToolConfigDB, respecting the configured fallback_chain.
When false, delegates directly to the existing call_llm (Phase 1 behavior).
"""

import logging
from typing import Any, List

from app.config import get_settings
from app.llm import get_llm_client
from app.llm.client import LLMError

logger = logging.getLogger(__name__)


async def _call_via_direct_api(
    prompt: str, system: str, max_tokens: int, temperature: float, role: str, **kwargs: Any
) -> str:
    client = get_llm_client()
    return await client.call_llm(
        prompt=prompt, system=system, max_tokens=max_tokens,
        temperature=temperature, role=role, **kwargs,
    )


async def _call_via_provider(
    provider: Any, prompt: str, system: str, max_tokens: int, temperature: float, **kwargs: Any
) -> str:
    if provider.name == "api":
        return await _call_via_direct_api(prompt, system, max_tokens, temperature, "primary", **kwargs)
    return await provider.call_llm(
        prompt=prompt, system=system, max_tokens=max_tokens, temperature=temperature, **kwargs,
    )


async def orchestrated_call_llm(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.0,
    role: str = "primary",
    **kwargs: Any,
) -> str:
    """Drop-in replacement for call_llm that routes through the tool registry."""
    settings = get_settings()

    if not settings.ORCHESTRATION_ENABLED:
        return await _call_via_direct_api(prompt, system, max_tokens, temperature, role, **kwargs)

    from app.orchestration import get_tool_registry
    from app.orchestration.config_resolver import get_configured_llm_provider_name, get_configured_fallback_chain

    registry = get_tool_registry()
    strict = settings.ORCHESTRATION_STRICT_LLM
    preferred = await get_configured_llm_provider_name()
    fallback_chain: List[str] = await get_configured_fallback_chain()

    try:
        provider = registry.get_provider_for("llm", preferred, strict_preferred=strict)
    except ValueError as exc:
        if strict and not fallback_chain:
            raise LLMError(
                f"Orchestration LLM routing failed: {exc}",
                provider=preferred or "", model="",
            ) from exc
        logger.warning("Primary provider %s failed to resolve: %s", preferred, exc)
        provider = None

    if provider is not None:
        try:
            logger.info("Routing LLM call through provider: %s", provider.name)
            return await _call_via_provider(provider, prompt, system, max_tokens, temperature, **kwargs)
        except Exception as exc:
            logger.warning("Provider %s call failed: %s", provider.name, exc)
            if strict and not fallback_chain:
                raise LLMError(
                    f"Provider {provider.name!r} failed: {exc}",
                    provider=provider.name, model="",
                ) from exc

    for chain_name in fallback_chain:
        if chain_name == preferred:
            continue
        try:
            chain_provider = registry.get_provider_for("llm", chain_name, strict_preferred=False)
        except ValueError:
            logger.warning("Fallback provider %s not found, skipping", chain_name)
            continue
        try:
            logger.info("Trying fallback provider: %s", chain_provider.name)
            return await _call_via_provider(chain_provider, prompt, system, max_tokens, temperature, **kwargs)
        except Exception as exc:
            logger.warning("Fallback provider %s failed: %s", chain_provider.name, exc)
            continue

    if strict:
        raise LLMError(
            f"All providers exhausted (preferred={preferred!r}, chain={fallback_chain})",
            provider=preferred or "", model="",
        )

    logger.warning("All configured providers failed; final fallback to Direct API")
    return await _call_via_direct_api(prompt, system, max_tokens, temperature, role, **kwargs)
