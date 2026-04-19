"""Tool Registry — manages available providers and user preferences."""

import logging

from app.orchestration.base import ExecutionProvider

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry of all execution providers."""

    def __init__(self) -> None:
        self._providers: dict[str, ExecutionProvider] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        from app.orchestration.providers.api_provider import APIProvider
        from app.orchestration.providers.claude_code_provider import ClaudeCodeProvider
        from app.orchestration.providers.cursor_provider import CursorProvider

        for cls in [APIProvider, ClaudeCodeProvider, CursorProvider]:
            provider = cls()
            self._providers[provider.name] = provider
            logger.debug("Registered provider: %s (%s)", provider.name, provider.capabilities)

        # Opt-in: the deterministic mock provider is only registered when the
        # env flag is set. This keeps production behaviour identical.
        from app.orchestration.providers.mock_provider import (
            MockProvider,
            mock_provider_enabled,
        )

        if mock_provider_enabled():
            prov = MockProvider()
            self._providers[prov.name] = prov
            logger.info("Registered mock LLM provider (PERFECTION_LOOP/LLM_PROVIDER=mock).")

    def register(self, provider: ExecutionProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> ExecutionProvider | None:
        return self._providers.get(name)

    def get_provider_for(
        self,
        capability: str,
        preferred: str | None = None,
        *,
        strict_preferred: bool = False,
    ) -> ExecutionProvider:
        """Return the best provider for a given capability.

        If `preferred` is set and that provider supports the capability, return it.
        If `strict_preferred` is True and `preferred` is unknown or unsupported, raise.
        Otherwise fall back to the first registered provider that supports the capability.
        """
        if preferred:
            p = self._providers.get(preferred)
            if p is None:
                if strict_preferred:
                    raise ValueError(f"Unknown provider: {preferred!r}")
            elif not p.supports(capability):
                if strict_preferred:
                    raise ValueError(f"Provider {preferred!r} does not support capability {capability!r}")
            else:
                return p

        for prov in self._providers.values():
            if prov.supports(capability):
                return prov

        raise ValueError(f"No provider available for capability: {capability}")

    def list_providers(self) -> list[dict]:
        return [
            {
                "name": p.name,
                "display_name": p.display_name,
                "capabilities": p.capabilities,
                "llm_selectable": getattr(p, "llm_selectable", True),
                "health_note": getattr(p, "health_note", "") or "",
            }
            for p in self._providers.values()
        ]

    async def health_check_all(self) -> dict[str, bool]:
        results = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.check_health()
            except Exception:
                results[name] = False
        return results
