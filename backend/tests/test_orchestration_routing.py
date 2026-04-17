"""Tests for subscription-first LLM routing (registry + orchestrated_call_llm)."""

import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.orchestration.registry import ToolRegistry


def test_registry_respects_preferred_claude_code():
    reg = ToolRegistry()
    p = reg.get_provider_for("llm", "claude_code", strict_preferred=True)
    assert p.name == "claude_code"


def test_registry_strict_unknown_provider_raises():
    reg = ToolRegistry()
    with pytest.raises(ValueError, match="Unknown provider"):
        reg.get_provider_for("llm", "not_a_real_provider", strict_preferred=True)


def test_registry_respects_preferred_cursor():
    reg = ToolRegistry()
    p = reg.get_provider_for("llm", "cursor", strict_preferred=True)
    assert p.name == "cursor"


def test_list_providers_llm_selectable_flags():
    reg = ToolRegistry()
    by_name = {p["name"]: p for p in reg.list_providers()}
    assert by_name["api"]["llm_selectable"] is True
    assert by_name["claude_code"]["llm_selectable"] is True
    assert by_name["cursor"]["llm_selectable"] is True
    assert len(by_name) == 3
    for name in ("api", "claude_code", "cursor"):
        assert "llm" in by_name[name]["capabilities"]


@pytest.fixture
def orchestration_strict_env(monkeypatch):
    monkeypatch.setenv("ORCHESTRATION_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_STRICT_LLM", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def orchestration_loose_env(monkeypatch):
    monkeypatch.setenv("ORCHESTRATION_ENABLED", "true")
    monkeypatch.setenv("ORCHESTRATION_STRICT_LLM", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_orchestrated_strict_raises_without_api_fallback(orchestration_strict_env):
    from app.config import get_settings
    from app.llm.client import LLMError
    from app.orchestration import get_tool_registry
    from app.orchestration.llm_bridge import orchestrated_call_llm

    assert get_settings().ORCHESTRATION_STRICT_LLM is True
    reg = get_tool_registry()
    prov = reg.get("claude_code")
    assert prov is not None

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="claude_code"),
        ),
        patch(
            "app.orchestration.config_resolver.get_configured_fallback_chain",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(prov, "call_llm", new=AsyncMock(side_effect=RuntimeError("cli down"))),
        patch("app.orchestration.llm_bridge.get_llm_client") as mock_get_client,
    ):
        with pytest.raises(LLMError):
            await orchestrated_call_llm("ping")
        mock_get_client.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrated_non_strict_falls_back_to_direct_api(orchestration_loose_env):
    from app.config import get_settings
    from app.orchestration import get_tool_registry
    from app.orchestration.llm_bridge import orchestrated_call_llm

    assert get_settings().ORCHESTRATION_STRICT_LLM is False
    reg = get_tool_registry()
    prov = reg.get("claude_code")
    assert prov is not None

    mock_client = MagicMock()
    mock_client.call_llm = AsyncMock(return_value="from-api")

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="claude_code"),
        ),
        patch.object(prov, "call_llm", new=AsyncMock(side_effect=RuntimeError("cli down"))),
        patch("app.orchestration.llm_bridge.get_llm_client", return_value=mock_client),
    ):
        out = await orchestrated_call_llm("ping")
        assert out == "from-api"
        mock_client.call_llm.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_chain_is_respected(orchestration_strict_env):
    """When primary fails and fallback_chain includes api, it should try api."""
    from app.orchestration import get_tool_registry
    from app.orchestration.llm_bridge import orchestrated_call_llm

    reg = get_tool_registry()
    prov = reg.get("claude_code")
    assert prov is not None

    mock_client = MagicMock()
    mock_client.call_llm = AsyncMock(return_value="from-fallback-api")

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="claude_code"),
        ),
        patch(
            "app.orchestration.config_resolver.get_configured_fallback_chain",
            new=AsyncMock(return_value=["api"]),
        ),
        patch.object(prov, "call_llm", new=AsyncMock(side_effect=RuntimeError("cli down"))),
        patch("app.orchestration.llm_bridge.get_llm_client", return_value=mock_client),
    ):
        out = await orchestrated_call_llm("ping")
        assert out == "from-fallback-api"
        mock_client.call_llm.assert_called_once()


@pytest.mark.asyncio
async def test_cursor_llm_delegates_to_direct_api(orchestration_strict_env):
    """When Cursor is the preferred LLM provider, calls delegate to Direct API."""
    from app.orchestration.llm_bridge import orchestrated_call_llm

    mock_client = MagicMock()
    mock_client.call_llm = AsyncMock(return_value="from-cursor-via-api")

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="cursor"),
        ),
        patch(
            "app.orchestration.config_resolver.get_configured_fallback_chain",
            new=AsyncMock(return_value=["api"]),
        ),
        patch("app.llm.get_llm_client", return_value=mock_client),
    ):
        out = await orchestrated_call_llm("ping")
        assert out == "from-cursor-via-api"
        mock_client.call_llm.assert_called_once()


# ── Claude Code CLI-first behaviour ───────────────────────────────────


def _make_stream_json(assistant_text: str = "", result_text: str = "") -> bytes:
    """Build fake ``--output-format stream-json`` output."""
    lines = []
    if assistant_text:
        lines.append(json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": assistant_text}],
            },
        }))
    if result_text:
        lines.append(json.dumps({"type": "result", "result": result_text}))
    return "\n".join(lines).encode()


@pytest.mark.asyncio
async def test_claude_code_llm_tries_cli_first():
    """When CLI returns good content, call_llm returns it without fallback."""
    from app.orchestration.providers.claude_code_provider import ClaudeCodeProvider

    good_text = "A" * 100
    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=_make_stream_json(assistant_text=good_text),
        stderr=b"",
    )

    provider = ClaudeCodeProvider()

    with patch(
        "app.orchestration.providers.claude_code_provider._run_cli",
        return_value=mock_result,
    ):
        out = await provider.call_llm("Say hello")
        assert out == good_text


@pytest.mark.asyncio
async def test_claude_code_llm_falls_back_on_empty():
    """When CLI returns insufficient content, call_llm raises LLMError for fallback."""
    from app.llm.client import LLMError
    from app.orchestration.providers.claude_code_provider import ClaudeCodeProvider

    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=_make_stream_json(assistant_text="", result_text=""),
        stderr=b"",
    )

    provider = ClaudeCodeProvider()

    with patch(
        "app.orchestration.providers.claude_code_provider._run_cli",
        return_value=mock_result,
    ):
        with pytest.raises(LLMError, match="insufficient content"):
            await provider.call_llm("Say hello")


@pytest.mark.asyncio
async def test_claude_code_llm_raises_on_cli_failure():
    """When CLI exits non-zero, call_llm raises LLMError."""
    from app.llm.client import LLMError
    from app.orchestration.providers.claude_code_provider import ClaudeCodeProvider

    mock_result = subprocess.CompletedProcess(
        args=[], returncode=1,
        stdout=b"",
        stderr=b"Something went wrong",
    )

    provider = ClaudeCodeProvider()

    with patch(
        "app.orchestration.providers.claude_code_provider._run_cli",
        return_value=mock_result,
    ):
        with pytest.raises(LLMError, match="Claude CLI failed"):
            await provider.call_llm("Say hello")


@pytest.mark.asyncio
async def test_claude_code_llm_prefers_longer_source():
    """Parser picks the longer text between assistant blocks and result."""
    from app.orchestration.providers.claude_code_provider import ClaudeCodeProvider

    short_assistant = "short"
    long_result = "B" * 200

    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=_make_stream_json(assistant_text=short_assistant, result_text=long_result),
        stderr=b"",
    )

    provider = ClaudeCodeProvider()

    with patch(
        "app.orchestration.providers.claude_code_provider._run_cli",
        return_value=mock_result,
    ):
        out = await provider.call_llm("ping")
        assert out == long_result


# ── _extract_text_from_stream unit tests ──────────────────────────────


def test_extract_text_from_stream_assistant_only():
    from app.orchestration.providers.claude_code_provider import _extract_text_from_stream

    payload = _make_stream_json(assistant_text="Hello world from assistant")
    assert _extract_text_from_stream(payload) == "Hello world from assistant"


def test_extract_text_from_stream_result_only():
    from app.orchestration.providers.claude_code_provider import _extract_text_from_stream

    payload = _make_stream_json(result_text="Hello from result field")
    assert _extract_text_from_stream(payload) == "Hello from result field"


def test_extract_text_from_stream_empty():
    from app.orchestration.providers.claude_code_provider import _extract_text_from_stream

    assert _extract_text_from_stream(b"") == ""
    assert _extract_text_from_stream(b"\n\n") == ""


def test_extract_text_from_stream_invalid_json_lines():
    from app.orchestration.providers.claude_code_provider import _extract_text_from_stream

    payload = b"not json\nalso not json\n"
    assert _extract_text_from_stream(payload) == ""


def test_clear_settings_cache():
    from app.config import get_settings, clear_settings_cache

    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    clear_settings_cache()
    s3 = get_settings()
    assert s3 is not s1
