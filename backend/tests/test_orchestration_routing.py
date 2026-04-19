"""Tests for strict single-provider LLM routing (0.4.0).

The bridge no longer walks a fallback chain. Each ``llm_provider`` is
tried exactly once; failures raise :class:`LLMError`. For subscription-
backed providers (``cursor`` / ``claude_code``) the Direct-API client is
*never* consulted — this is the token-leak guard.
"""

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
    """All three providers are user-selectable Document LLMs."""
    reg = ToolRegistry()
    by_name = {p["name"]: p for p in reg.list_providers()}
    assert by_name["api"]["llm_selectable"] is True
    assert by_name["claude_code"]["llm_selectable"] is True
    assert by_name["cursor"]["llm_selectable"] is True
    assert len(by_name) == 3
    for name in ("api", "claude_code", "cursor"):
        assert "llm" in by_name[name]["capabilities"]
    assert "build" in by_name["cursor"]["capabilities"]
    assert "build" in by_name["claude_code"]["capabilities"]


@pytest.fixture
def orchestration_env(monkeypatch):
    monkeypatch.setenv("ORCHESTRATION_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_claude_code_failure_never_reaches_direct_api(orchestration_env):
    """Claude Code CLI failures must raise, never fall back to Direct API."""
    from app.llm.client import LLMError
    from app.orchestration import get_tool_registry
    from app.orchestration.llm_bridge import orchestrated_call_llm

    reg = get_tool_registry()
    prov = reg.get("claude_code")
    assert prov is not None

    mock_client = MagicMock()
    mock_client.call_llm = AsyncMock(return_value="should-not-be-called")

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="claude_code"),
        ),
        patch.object(prov, "call_llm", new=AsyncMock(side_effect=RuntimeError("cli down"))),
        patch("app.orchestration.llm_bridge.get_llm_client", return_value=mock_client),
    ):
        with pytest.raises(LLMError):
            await orchestrated_call_llm("ping")
        mock_client.call_llm.assert_not_called()


@pytest.mark.asyncio
async def test_cursor_call_llm_raises_never_hits_direct_api(orchestration_env):
    """Cursor provider.call_llm raises CursorLLMUnsupported under the
    paste-per-action model. The bridge must surface that as LLMError
    without ever invoking the Direct-API client."""
    from app.llm.client import LLMError
    from app.orchestration.llm_bridge import orchestrated_call_llm

    mock_direct_client = MagicMock()
    mock_direct_client.call_llm = AsyncMock(return_value="should-not-be-called")

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="cursor"),
        ),
        patch("app.orchestration.llm_bridge.get_llm_client", return_value=mock_direct_client),
    ):
        with pytest.raises(LLMError):
            await orchestrated_call_llm("ping")
        mock_direct_client.call_llm.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    ["generate_fs", "analyze", "refine", "reverse_fs", "impact", "testcase", "dependency", "primary"],
)
@pytest.mark.parametrize("provider_name", ["claude_code", "cursor"])
async def test_no_direct_api_for_any_pipeline_role(orchestration_env, role, provider_name):
    """For every pipeline role, a provider failure (cursor or claude) must
    raise an LLMError, never reach the Direct-API client."""
    from app.llm.client import LLMError
    from app.orchestration import get_tool_registry
    from app.orchestration.llm_bridge import orchestrated_call_llm

    reg = get_tool_registry()
    prov = reg.get(provider_name)
    assert prov is not None

    mock_direct_client = MagicMock()
    mock_direct_client.call_llm = AsyncMock(return_value="must-never-run")

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value=provider_name),
        ),
        patch.object(prov, "call_llm", new=AsyncMock(side_effect=RuntimeError("provider down"))),
        patch("app.orchestration.llm_bridge.get_llm_client", return_value=mock_direct_client),
    ):
        with pytest.raises(LLMError):
            await orchestrated_call_llm("ping", role=role)
        mock_direct_client.call_llm.assert_not_called()


# ── Claude Code CLI-first behaviour ───────────────────────────────────


def _make_json_payload(
    result_text: str = "",
    *,
    is_error: bool = False,
    model_usage: dict | None = None,
    cost_usd: float | None = None,
) -> bytes:
    """Build fake ``--output-format json`` output (the single-blob format)."""
    blob: dict = {
        "type": "result",
        "subtype": "error" if is_error else "success",
        "is_error": is_error,
        "result": result_text,
        "modelUsage": model_usage or {"claude-haiku-4-5": {"inputTokens": 1, "outputTokens": 1}},
    }
    if cost_usd is not None:
        blob["total_cost_usd"] = cost_usd
    return json.dumps(blob).encode()


@pytest.fixture
def _no_misroute():
    """Force the pre-flight config check to always pass in unit tests."""
    with patch(
        "app.orchestration.providers.claude_code_provider._detect_non_anthropic_routing",
        return_value=None,
    ):
        yield


@pytest.mark.asyncio
async def test_claude_code_llm_tries_cli_first(_no_misroute):
    """When CLI returns good content, call_llm returns it without fallback."""
    from app.orchestration.providers.claude_code_provider import ClaudeCodeProvider

    good_text = "A" * 100
    mock_result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=_make_json_payload(result_text=good_text),
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
async def test_claude_code_llm_raises_on_empty_no_fallback(_no_misroute):
    """When the CLI returns insufficient content, call_llm surfaces LLMError."""
    from app.llm.client import LLMError
    from app.orchestration.providers.claude_code_provider import ClaudeCodeProvider

    mock_result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=_make_json_payload(result_text=""),
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
async def test_claude_code_llm_raises_on_cli_failure(_no_misroute):
    """When CLI exits non-zero, call_llm raises LLMError."""
    from app.llm.client import LLMError
    from app.orchestration.providers.claude_code_provider import ClaudeCodeProvider

    mock_result = subprocess.CompletedProcess(
        args=[],
        returncode=1,
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
async def test_claude_code_llm_preflight_refuses_misrouted_env(monkeypatch):
    """When env vars show non-Anthropic routing, call_llm must refuse before
    the CLI is invoked."""
    from app.llm.client import LLMError
    from app.orchestration.providers.claude_code_provider import ClaudeCodeProvider

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("ANTHROPIC_MODEL", "deepseek/deepseek-r1")
    with patch(
        "app.orchestration.providers.claude_code_provider._run_cli",
        side_effect=AssertionError("CLI must not be invoked when pre-flight fails"),
    ):
        with pytest.raises(LLMError) as excinfo:
            await ClaudeCodeProvider().call_llm("hi")
    msg = str(excinfo.value)
    assert "openrouter" in msg.lower() or "non-anthropic" in msg.lower()


# ── _parse_json_output unit tests ─────────────────────────────────────


def test_parse_json_output_happy_path():
    from app.orchestration.providers.claude_code_provider import _parse_json_output

    blob = _make_json_payload(result_text="hello world")
    parsed = _parse_json_output(blob)
    assert parsed["result"] == "hello world"
    assert parsed["is_error"] is False


def test_parse_json_output_skips_leading_warning_line():
    """The CLI sometimes prints a warning about stdin before the JSON blob."""
    from app.orchestration.providers.claude_code_provider import _parse_json_output

    warning = b"Warning: no stdin data received in 3s, proceeding without it.\n"
    blob = _make_json_payload(result_text="ok")
    parsed = _parse_json_output(warning + blob)
    assert parsed["result"] == "ok"


def test_parse_json_output_empty_and_garbage():
    from app.orchestration.providers.claude_code_provider import _parse_json_output

    assert _parse_json_output(b"") == {}
    assert _parse_json_output(b"not json at all") == {}


def test_clear_settings_cache():
    from app.config import clear_settings_cache, get_settings

    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    clear_settings_cache()
    s3 = get_settings()
    assert s3 is not s1


@pytest.mark.asyncio
async def test_claude_build_dispatch_validates_provider():
    """/build/run hard-rejects any provider != claude_code."""
    from fastapi import HTTPException

    from app.api.build_router import run_build

    fake_db = MagicMock()
    fake_bg = MagicMock()
    with pytest.raises(HTTPException) as excinfo:
        await run_build(
            doc_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            body={"provider": "cursor"},
            background_tasks=fake_bg,
            db=fake_db,
        )
    assert excinfo.value.status_code == 400
