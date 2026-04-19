"""Bridge between the orchestration layer and the LLM client.

Every LLM call made by the backend goes through :func:`orchestrated_call_llm`.
The provider configured in ``ToolConfigDB`` (``api`` | ``claude_code`` |
``cursor``) is resolved from the registry and called exactly once. There
is no feature flag and there is no fallback chain.

Token-protection rule (0.4.0+)
------------------------------

Subscription-backed providers (``cursor``, ``claude_code``) must **never**
silently fall back to a different provider — least of all the Direct
API — because that would charge the user's OpenRouter / Anthropic
credits instead of the subscription they asked to use.

Concretely, if the configured ``llm_provider`` is:

* ``cursor``      — the calling route should have branched to the
                    paste-per-action flow and never called this
                    function. If it does, :class:`CursorLLMUnsupported`
                    is raised and surfaced as a loud :class:`LLMError`
                    so the bug is visible.
* ``claude_code`` — the Claude Code CLI provider is tried exactly once.
                    On any failure we raise :class:`LLMError`. No
                    fallback chain is ever consulted.
* ``api``         — the Direct-API client is the only path.

There is no silent fallback path to the Direct API anywhere in this
module. If this rule is ever weakened, add a matching assertion to
``backend/tests/test_no_direct_api_fallback.py`` first.
"""

import logging
from typing import Any

from app.llm import get_llm_client
from app.llm.client import LLMError

logger = logging.getLogger(__name__)

# Providers that MUST NOT fall back to any other provider. These are
# subscription-backed (user's Cursor Pro / Anthropic Claude Code plan)
# and any fallback would leak tokens to server-side credits.
NO_FALLBACK_PROVIDERS = {"cursor", "claude_code"}


async def _call_via_direct_api(
    prompt: str, system: str, max_tokens: int, temperature: float, role: str, **kwargs: Any
) -> str:
    client = get_llm_client()
    return await client.call_llm(
        prompt=prompt,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
        role=role,
        **kwargs,
    )


async def _call_via_provider(
    provider: Any, prompt: str, system: str, max_tokens: int, temperature: float, role: str, **kwargs: Any
) -> str:
    if provider.name == "api":
        return await _call_via_direct_api(prompt, system, max_tokens, temperature, role, **kwargs)
    return await provider.call_llm(
        prompt=prompt,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
        **kwargs,
    )


async def orchestrated_call_llm(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.0,
    role: str = "primary",
    **kwargs: Any,
) -> str:
    """Drop-in replacement for call_llm that routes through the tool registry.

    Strict provider isolation: ``cursor`` and ``claude_code`` are tried
    exactly once and any failure is raised; only ``api`` (Direct API)
    ever executes the built-in ``_call_via_direct_api`` path.
    """
    from app.orchestration import get_tool_registry
    from app.orchestration.config_resolver import get_configured_llm_provider_name

    registry = get_tool_registry()
    preferred = (await get_configured_llm_provider_name()) or "api"

    # Resolve the single provider we will use. No fallback ever.
    try:
        provider = registry.get_provider_for("llm", preferred, strict_preferred=True)
    except ValueError as exc:
        raise LLMError(
            f"Configured LLM provider {preferred!r} is not available: {exc}",
            provider=preferred,
            model="",
        ) from exc

    logger.info("Routing LLM call through provider: %s (strict, no fallback)", provider.name)
    try:
        return await _call_via_provider(provider, prompt, system, max_tokens, temperature, role, **kwargs)
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001 — wrap everything as LLMError for the handler
        from app.orchestration.providers.cursor_provider import CursorLLMUnsupported

        if isinstance(exc, CursorLLMUnsupported):
            raise LLMError(
                str(exc),
                provider=provider.name,
                model="",
            ) from exc
        if provider.name in NO_FALLBACK_PROVIDERS:
            logger.error(
                "Subscription-backed provider %s failed; refusing fallback: %s",
                provider.name,
                exc,
            )
            raise LLMError(
                f"Provider {provider.name!r} failed and fallback is disabled (subscription-backed): {exc}",
                provider=provider.name,
                model="",
            ) from exc
        raise LLMError(
            f"Provider {provider.name!r} failed: {exc}",
            provider=provider.name,
            model="",
        ) from exc
