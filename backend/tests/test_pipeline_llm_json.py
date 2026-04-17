"""Tests for pipeline_call_llm_json parsing + retry path."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.orchestration.pipeline_llm import (
    LLMJSONParseError,
    _extract_first_json_blob,
    _try_parse_json,
    pipeline_call_llm_json,
)


def test_try_parse_json_plain_object():
    assert _try_parse_json('{"a": 1}') == {"a": 1}


def test_try_parse_json_with_fences():
    raw = """```json
{"x": [1, 2, 3]}
```"""
    assert _try_parse_json(raw) == {"x": [1, 2, 3]}


def test_try_parse_json_blob_extraction():
    raw = "Sure, here is your JSON: {\"ok\": true}. Hope that helps!"
    assert _try_parse_json(raw) == {"ok": True}


def test_try_parse_json_array_blob():
    raw = "prose before [1,2,3] prose after"
    assert _try_parse_json(raw) == [1, 2, 3]


def test_try_parse_json_returns_none_on_garbage():
    assert _try_parse_json("utterly not json") is None


def test_extract_first_json_blob_handles_strings():
    raw = 'chat {"msg": "has } inside"} tail'
    assert _extract_first_json_blob(raw) == '{"msg": "has } inside"}'


@pytest.mark.asyncio
async def test_pipeline_call_llm_json_retries_on_bad_output(monkeypatch):
    calls: list[str] = []

    async def fake_call(*, prompt: str, system: str, **_kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            return "I think the answer is... {not json}"
        return '{"retry": "ok"}'

    class _FakeSettings:
        ORCHESTRATION_ENABLED = True

    with patch("app.orchestration.pipeline_llm.get_settings", return_value=_FakeSettings()), \
         patch("app.orchestration.llm_bridge.orchestrated_call_llm", fake_call):
        result = await pipeline_call_llm_json(prompt="Give me JSON", system="system")

    assert result == {"retry": "ok"}
    assert len(calls) == 2
    assert "ONLY" in calls[1]  # strict retry prompt mentions ONLY


@pytest.mark.asyncio
async def test_pipeline_call_llm_json_raises_after_retry(monkeypatch):
    async def fake_call(*, prompt: str, system: str, **_kwargs):
        return "no json anywhere at all"

    class _FakeSettings:
        ORCHESTRATION_ENABLED = True

    with patch("app.orchestration.pipeline_llm.get_settings", return_value=_FakeSettings()), \
         patch("app.orchestration.llm_bridge.orchestrated_call_llm", fake_call):
        with pytest.raises(LLMJSONParseError):
            await pipeline_call_llm_json(prompt="x", system="y")
