"""Regression: Claude Code provider must honour LLM_TIMEOUT_S and raise typed LLMError on timeout.

Before this fix, ``claude_code_provider.call_llm`` hard-coded ``timeout=180``
which surfaced long analyze/refine prompts as a bare ``subprocess.TimeoutExpired``
in the error trail (see ``reports/e2e-final.md`` — ``Claude analyze ReadTimeout``).
These tests lock the new behavior.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from app.llm.client import LLMError
from app.orchestration.providers import claude_code_provider as prov
from app.orchestration.providers.claude_code_provider import ClaudeCodeProvider


@pytest.mark.asyncio
async def test_timeout_honours_llm_timeout_s_and_raises_llm_error(monkeypatch):
    """call_llm must raise LLMError (never raw TimeoutExpired) and cite the timeout in the message."""
    # Neutralise the pre-flight guard so the test exercises the CLI call path.
    monkeypatch.setattr(prov, "_detect_non_anthropic_routing", lambda: None)

    # Simulate a CLI invocation that blows past the configured timeout.
    def _raise_timeout(args, timeout=120, cwd=None):
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    provider = ClaudeCodeProvider()

    with patch.object(prov, "_run_cli", side_effect=_raise_timeout):
        with pytest.raises(LLMError) as excinfo:
            await provider.call_llm(prompt="hello", system="")

    msg = str(excinfo.value)
    assert "timed out" in msg.lower()
    # The fix threads LLM_TIMEOUT_S through — the message must reference it
    # so users know which knob to tune.
    assert "LLM_TIMEOUT_S" in msg


@pytest.mark.asyncio
async def test_timeout_value_scales_with_setting(monkeypatch):
    """The subprocess timeout passed to _run_cli must track LLM_TIMEOUT_S (not be a hard-coded 180)."""
    monkeypatch.setattr(prov, "_detect_non_anthropic_routing", lambda: None)

    captured: dict = {}

    def _capture(args, timeout=120, cwd=None):
        captured["timeout"] = timeout

        # Emulate a clean CLI response shape so call_llm returns normally.
        class _CP:
            returncode = 0
            stdout = b'{"result": "OK acknowledged and tested", "modelUsage": {"claude-sonnet": {}}}'
            stderr = b""

        return _CP()

    # Override the setting via direct monkeypatch of get_settings().
    from app.config import get_settings

    settings = get_settings()
    old = settings.LLM_TIMEOUT_S
    settings.LLM_TIMEOUT_S = 400.0
    try:
        provider = ClaudeCodeProvider()
        with patch.object(prov, "_run_cli", side_effect=_capture):
            text = await provider.call_llm(prompt="ping", system="")
        assert "OK acknowledged and tested" in text
        # 400s * 1.5 = 600s expected; provider floors to 30s minimum.
        assert captured["timeout"] >= 400
    finally:
        settings.LLM_TIMEOUT_S = old
