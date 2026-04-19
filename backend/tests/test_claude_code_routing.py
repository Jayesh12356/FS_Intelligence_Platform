"""Claude Code provider must own every pipeline call — no Direct API.

Acts as a guard around the orchestration bridge: when the configured
``llm_provider`` is ``claude_code``, every ``pipeline_call_llm`` /
``pipeline_call_llm_json`` call must land on
:meth:`ClaudeCodeProvider.call_llm` and *never* on the Direct-API client.

The provider itself is isolated by mocking ``_run_cli`` so we don't hit
a real Anthropic subscription during tests.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import AsyncMock, patch

import pytest


def _make_cli_payload(result_text: str) -> bytes:
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": result_text,
            "modelUsage": {"claude-haiku-4-5": {"inputTokens": 1, "outputTokens": 1}},
        }
    ).encode()


@pytest.fixture
def orchestration_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRATION_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def no_misroute():
    """Skip the Anthropic pre-flight env check in unit tests."""
    with patch(
        "app.orchestration.providers.claude_code_provider._detect_non_anthropic_routing",
        return_value=None,
    ):
        yield


@pytest.fixture
def boom_direct_api(monkeypatch: pytest.MonkeyPatch):
    async def _boom(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError(
            "LLMClient.call_llm was invoked when provider=claude_code; that would leak OpenRouter tokens."
        )

    from app.llm.client import LLMClient

    monkeypatch.setattr(LLMClient, "call_llm", _boom)
    yield


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        "primary",
        "generate_fs",
        "analyze",
        "refine",
        "reverse_fs",
        "impact",
        "dependency",
        "testcase",
    ],
)
async def test_pipeline_call_llm_routes_to_claude_cli(orchestration_on, no_misroute, boom_direct_api, role):
    """``pipeline_call_llm`` must call the Claude CLI for every pipeline role."""
    from app.orchestration.pipeline_llm import pipeline_call_llm

    good_payload = "A" * 200  # above the provider's minimum-content threshold
    mock_result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=_make_cli_payload(good_payload),
        stderr=b"",
    )

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="claude_code"),
        ),
        patch(
            "app.orchestration.providers.claude_code_provider._run_cli",
            return_value=mock_result,
        ) as mock_cli,
    ):
        out = await pipeline_call_llm("hello", role=role)

    assert out == good_payload
    assert mock_cli.called, f"CLI should have been invoked for role={role}"


@pytest.mark.asyncio
async def test_pipeline_call_llm_json_routes_to_claude_cli(orchestration_on, no_misroute, boom_direct_api):
    """JSON helper must also go through the Claude CLI when claude_code is selected."""
    from app.orchestration.pipeline_llm import pipeline_call_llm_json

    padded_json = '{"ok": true, "notes": "%s"}' % ("x" * 200)
    mock_result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=_make_cli_payload(padded_json),
        stderr=b"",
    )

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="claude_code"),
        ),
        patch(
            "app.orchestration.providers.claude_code_provider._run_cli",
            return_value=mock_result,
        ) as mock_cli,
    ):
        out = await pipeline_call_llm_json("hello", role="analyze")

    assert out == {"ok": True, "notes": "x" * 200}
    assert mock_cli.called


@pytest.mark.asyncio
async def test_claude_code_cli_failure_bubbles_up_no_fallback(orchestration_on, no_misroute, boom_direct_api):
    """CLI non-zero exit must surface as :class:`LLMError`, never hit Direct API."""
    from app.llm.client import LLMError
    from app.orchestration.pipeline_llm import pipeline_call_llm

    mock_result = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout=b"",
        stderr=b"boom",
    )

    with (
        patch(
            "app.orchestration.config_resolver.get_configured_llm_provider_name",
            new=AsyncMock(return_value="claude_code"),
        ),
        patch(
            "app.orchestration.providers.claude_code_provider._run_cli",
            return_value=mock_result,
        ),
    ):
        with pytest.raises(LLMError):
            await pipeline_call_llm("hello")
