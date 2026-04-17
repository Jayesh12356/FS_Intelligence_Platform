"""Tests for app.pipeline.refinement_graph.

Exercises suggestion_node / rewriter_node / validation_node plus run_refinement_pipeline
with mocked LLM calls so the graph can be validated deterministically.
"""

from __future__ import annotations

import uuid

import pytest

from app.llm.client import LLMError
from app.pipeline import refinement_graph as rg


def _issue(kind: str = "ambiguity") -> dict:
    return {
        "issue_id": str(uuid.uuid4()),
        "issue_type": kind,
        "issue": "uses the word 'fast' without a measurable threshold",
        "original_text": "The system shall respond fast to user input.",
        "section_heading": "Performance",
    }


@pytest.mark.asyncio
async def test_suggestion_node_returns_llm_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_json(**_kw):
        return {"suggested_fix": "The system shall respond within 200ms."}

    monkeypatch.setattr(rg, "pipeline_call_llm_json", fake_json)
    state = {"issues": [_issue()]}
    result = await rg.suggestion_node(state)
    assert result["suggestions"][0]["suggested_fix"] == "The system shall respond within 200ms."


@pytest.mark.asyncio
async def test_suggestion_node_recovers_on_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def bad_json(**_kw):
        raise ValueError("could not parse")

    monkeypatch.setattr(rg, "pipeline_call_llm_json", bad_json)
    state = {"issues": [_issue()]}
    result = await rg.suggestion_node(state)
    # Falls back to original text marked [REFINED].
    assert result["suggestions"][0]["suggested_fix"].endswith("[REFINED]")


@pytest.mark.asyncio
async def test_suggestion_node_propagates_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def llm_fail(**_kw):
        raise LLMError("provider unreachable")

    monkeypatch.setattr(rg, "pipeline_call_llm_json", llm_fail)
    with pytest.raises(LLMError):
        await rg.suggestion_node({"issues": [_issue()]})


@pytest.mark.asyncio
async def test_rewriter_node_applies_llm_rewrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_rewrite(**_kw):
        return "The system shall respond within 200ms. [REFINED]\n"

    monkeypatch.setattr(rg, "pipeline_call_llm", fake_rewrite)

    state = {
        "original_text": "The system shall respond fast to user input.",
        "suggestions": [
            {
                **_issue(),
                "suggested_fix": "The system shall respond within 200ms.",
            }
        ],
    }
    result = await rg.rewriter_node(state)
    assert "[REFINED]" in result["refined_text"]
    assert result["changes_made"] >= 1


@pytest.mark.asyncio
async def test_rewriter_node_deterministic_fallback_when_llm_misses_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def lazy_llm(**_kw):
        # LLM returns original text without the [REFINED] token — fallback should fire.
        return "The system shall respond fast to user input."

    monkeypatch.setattr(rg, "pipeline_call_llm", lazy_llm)

    state = {
        "original_text": "The system shall respond fast to user input.",
        "suggestions": [
            {
                **_issue(),
                "suggested_fix": "The system shall respond within 200ms.",
            }
        ],
    }
    result = await rg.rewriter_node(state)
    assert "[REFINED]" in result["refined_text"]
    assert "within 200ms" in result["refined_text"]


@pytest.mark.asyncio
async def test_rewriter_node_handles_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def empty_llm(**_kw):
        return ""

    monkeypatch.setattr(rg, "pipeline_call_llm", empty_llm)

    state = {
        "original_text": "Original text remains.",
        "suggestions": [
            {
                **_issue(),
                "suggested_fix": "Does-not-match replacement.",
            }
        ],
    }
    result = await rg.rewriter_node(state)
    # With no matching fragment, the refined text stays equal to original.
    assert result["refined_text"] == "Original text remains."


@pytest.mark.asyncio
async def test_rewriter_node_noop_without_suggestions() -> None:
    state = {
        "original_text": "Some text.",
        "suggestions": [],
    }
    result = await rg.rewriter_node(state)
    assert result["refined_text"] == "Some text."
    assert result["changes_made"] == 0
    assert result["diff"] == []


@pytest.mark.asyncio
async def test_validation_node_accepts_when_refined_better() -> None:
    state = {
        "original_text": "The system shall respond fast to user input.",
        "refined_text": "The system shall respond within 200ms. [REFINED]",
        "original_score": 70.0,
        "suggestions": [
            {
                **_issue(),
                "suggested_fix": "The system shall respond within 200ms.",
            }
        ],
    }
    result = await rg.validation_node(state)
    assert result["accepted"] is True
    assert result["refined_score"] >= 70.0


@pytest.mark.asyncio
async def test_validation_node_rejects_when_refinement_empty() -> None:
    state = {
        "original_text": "Original.",
        "refined_text": "",
        "original_score": 75.0,
        "suggestions": [],
    }
    result = await rg.validation_node(state)
    assert result["accepted"] is False
    assert result["refined_score"] == 75.0
    assert result["refined_text"] == "Original."


@pytest.mark.asyncio
async def test_validation_node_rejects_when_no_issues_resolved() -> None:
    state = {
        "original_text": "The system shall respond fast to user input.",
        # Simulated bad rewrite — refined still contains original issue text.
        "refined_text": "The system shall respond fast to user input.",
        "original_score": 80.0,
        "suggestions": [
            {
                **_issue(),
                "suggested_fix": "The system shall respond within 200ms.",
            }
        ],
    }
    result = await rg.validation_node(state)
    # Score cannot improve when 100% of suggestions remain unresolved, so uplift = 0.
    assert result["refined_score"] == 80.0


@pytest.mark.asyncio
async def test_targeted_rewriter_applies_fuzzy_replacements() -> None:
    issue = _issue()
    state = {
        "original_text": "The system shall respond fast to user input.\nThe system shall handle failures.",
        "suggestions": [
            {
                **issue,
                "suggested_fix": "The system shall respond within 200ms.",
            }
        ],
    }
    result = await rg.targeted_rewriter_node(state)
    assert "within 200ms" in result["refined_text"]
    assert result["changes_made"] == 1
