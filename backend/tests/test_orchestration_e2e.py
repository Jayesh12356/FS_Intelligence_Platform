"""End-to-end orchestration tests using a stub CLI provider.

These tests cover behaviour that the registry-level tests in
`test_orchestration_routing.py` don't exercise:

* A custom provider subclass can be registered at runtime and picked up by
  the capability-aware registry.
* Strict mode prevents silent fallback to the direct API when the preferred
  provider raises.
* Capability routing returns the first provider that supports a capability
  when no preferred provider is supplied.
* Non-LLM capabilities (e.g. ``build``) are routed to the appropriate
  provider rather than the generic ``api`` one.
"""

from __future__ import annotations

from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.orchestration.base import BuildResult, ExecutionProvider
from app.orchestration.registry import ToolRegistry


class StubCLIProvider(ExecutionProvider):
    """Minimal provider that records calls for assertions."""

    def __init__(
        self,
        name: str = "stub_cli",
        *,
        capabilities: list[str] | None = None,
        healthy: bool = True,
        response: str = "from-stub",
        build_ok: bool = True,
    ) -> None:
        self.name = name
        self.display_name = f"Stub {name}"
        self.capabilities = capabilities if capabilities is not None else ["llm", "build"]
        self._healthy = healthy
        self._response = response
        self._build_ok = build_ok
        self.call_log: list[tuple[str, dict[str, Any]]] = []

    async def call_llm(
        self, prompt: str, system: str = "", max_tokens: int = 4096,
        temperature: float = 0.0, **kwargs: Any,
    ) -> str:
        self.call_log.append(("call_llm", {"prompt": prompt, "system": system}))
        return self._response

    async def build_task(
        self, task_context: dict, output_folder: str, **kwargs: Any,
    ) -> BuildResult:
        self.call_log.append(("build_task", {"task": task_context, "out": output_folder}))
        return BuildResult(success=self._build_ok, output="built")

    async def check_health(self) -> bool:
        return self._healthy


@pytest.fixture
def stub_registry() -> Iterator[tuple[ToolRegistry, StubCLIProvider]]:
    reg = ToolRegistry()
    stub = StubCLIProvider()
    reg.register(stub)
    yield reg, stub


def test_registry_routes_by_capability_to_stub(
    stub_registry: tuple[ToolRegistry, StubCLIProvider],
) -> None:
    reg, stub = stub_registry
    picked = reg.get_provider_for("llm", stub.name, strict_preferred=True)
    assert picked.name == stub.name


def test_registry_rejects_unsupported_capability_for_provider(
    stub_registry: tuple[ToolRegistry, StubCLIProvider],
) -> None:
    """An explicit provider that lacks the requested capability must error out
    in strict mode — the registry must not silently pick a different provider."""
    reg = stub_registry[0]
    reg.register(StubCLIProvider(name="llm_only", capabilities=["llm"]))
    with pytest.raises(ValueError, match="does not support"):
        reg.get_provider_for("build", "llm_only", strict_preferred=True)


def test_registry_builds_capability_catalog(
    stub_registry: tuple[ToolRegistry, StubCLIProvider],
) -> None:
    reg = stub_registry[0]
    listing = reg.list_providers()
    # Every provider listed must expose its capabilities list as-is.
    for row in listing:
        assert isinstance(row["capabilities"], list)
        assert row["name"]
    # Stub is present with its declared capabilities.
    stub_entry = next(r for r in listing if r["name"] == "stub_cli")
    assert "llm" in stub_entry["capabilities"]
    assert "build" in stub_entry["capabilities"]


@pytest.mark.asyncio
async def test_registry_health_check_collects_all(
    stub_registry: tuple[ToolRegistry, StubCLIProvider],
) -> None:
    reg, stub = stub_registry
    # Force built-in providers to report False deterministically so the dict is complete.
    with (
        patch.object(reg.get("api"), "check_health", new=AsyncMock(return_value=True)),
        patch.object(reg.get("claude_code"), "check_health", new=AsyncMock(return_value=False)),
        patch.object(reg.get("cursor"), "check_health", new=AsyncMock(return_value=False)),
    ):
        health = await reg.health_check_all()
    assert health["api"] is True
    assert health["claude_code"] is False
    assert health["cursor"] is False
    assert health[stub.name] is True


@pytest.mark.asyncio
async def test_strict_mode_blocks_fallback_to_direct_api_when_stub_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORCHESTRATION_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_STRICT_LLM", "true")

    from app.config import get_settings
    from app.llm.client import LLMError
    from app.orchestration import get_tool_registry
    from app.orchestration.llm_bridge import orchestrated_call_llm

    get_settings.cache_clear()
    try:
        assert get_settings().ORCHESTRATION_STRICT_LLM is True

        registry = get_tool_registry()
        stub = StubCLIProvider(name="stub_strict")
        registry.register(stub)

        direct_api_mock = MagicMock()
        direct_api_mock.call_llm = AsyncMock(return_value="should-not-be-used")

        with (
            patch(
                "app.orchestration.config_resolver.get_configured_llm_provider_name",
                new=AsyncMock(return_value="stub_strict"),
            ),
            patch(
                "app.orchestration.config_resolver.get_configured_fallback_chain",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(stub, "call_llm", new=AsyncMock(side_effect=RuntimeError("stub down"))),
            patch(
                "app.orchestration.llm_bridge.get_llm_client",
                return_value=direct_api_mock,
            ),
        ):
            with pytest.raises(LLMError):
                await orchestrated_call_llm("hello")
            direct_api_mock.call_llm.assert_not_called()
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_loose_mode_uses_stub_response_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORCHESTRATION_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_STRICT_LLM", "false")

    from app.config import get_settings
    from app.orchestration import get_tool_registry
    from app.orchestration.llm_bridge import orchestrated_call_llm

    get_settings.cache_clear()
    try:
        registry = get_tool_registry()
        stub = StubCLIProvider(name="stub_loose", response="stub-answer")
        registry.register(stub)

        with (
            patch(
                "app.orchestration.config_resolver.get_configured_llm_provider_name",
                new=AsyncMock(return_value="stub_loose"),
            ),
            patch(
                "app.orchestration.config_resolver.get_configured_fallback_chain",
                new=AsyncMock(return_value=["api"]),
            ),
        ):
            out = await orchestrated_call_llm("hi")
        assert out == "stub-answer"
        assert stub.call_log and stub.call_log[0][0] == "call_llm"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_strict_mode_exhausts_fallback_chain_before_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even in strict mode, a fallback chain should be tried before raising."""
    monkeypatch.setenv("ORCHESTRATION_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_STRICT_LLM", "true")

    from app.config import get_settings
    from app.orchestration import get_tool_registry
    from app.orchestration.llm_bridge import orchestrated_call_llm

    get_settings.cache_clear()
    try:
        registry = get_tool_registry()
        primary = StubCLIProvider(name="stub_primary")
        secondary = StubCLIProvider(name="stub_secondary", response="from-secondary")
        registry.register(primary)
        registry.register(secondary)

        with (
            patch(
                "app.orchestration.config_resolver.get_configured_llm_provider_name",
                new=AsyncMock(return_value="stub_primary"),
            ),
            patch(
                "app.orchestration.config_resolver.get_configured_fallback_chain",
                new=AsyncMock(return_value=["stub_secondary"]),
            ),
            patch.object(primary, "call_llm", new=AsyncMock(side_effect=RuntimeError("down"))),
        ):
            out = await orchestrated_call_llm("hi")
        assert out == "from-secondary"
    finally:
        get_settings.cache_clear()
