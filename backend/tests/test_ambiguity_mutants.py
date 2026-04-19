"""Mutation-targeted tests for app/pipeline/nodes/ambiguity_node.

Each test here exists to kill a specific mutmut survivor from the
``app/pipeline/nodes/ambiguity_node.py`` mutation run recorded in
``reports/perfection/mutmut_baseline.md``:

* M5  — ``len(content.strip()) < 20`` → ``<= 20`` (off-by-one boundary)
* M12 — ``temperature=0.0`` → ``temperature=1.0`` (determinism guard)
* M13 — ``max_tokens=2048`` → ``max_tokens=2049`` (prompt budget guard)

These assertions pin the exact arguments the LLM is called with and the
exact boundary at which a section is considered "too short to audit",
closing three real behavioural gaps that the existing end-to-end tests
miss because they never inspect the LLM call kwargs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.nodes.ambiguity_node import detect_ambiguities_in_section


@pytest.mark.asyncio
async def test_boundary_twenty_chars_triggers_llm_call():
    """Content of exactly 20 chars (stripped) must be audited, not skipped.

    Kills mutant M5 where ``<`` was flipped to ``<=``.
    """
    content = "a" * 20
    with patch(
        "app.pipeline.nodes.ambiguity_node.pipeline_call_llm_json",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = []
        await detect_ambiguities_in_section("H", content, 0)
    assert mock_llm.await_count == 1, "20-char content must still be audited; the boundary must be strictly '< 20'"


@pytest.mark.asyncio
async def test_short_content_skips_llm_call():
    """Content with <20 non-whitespace chars must NOT call the LLM."""
    with patch(
        "app.pipeline.nodes.ambiguity_node.pipeline_call_llm_json",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = []
        flags = await detect_ambiguities_in_section("H", "short", 0)
    assert flags == []
    assert mock_llm.await_count == 0


@pytest.mark.asyncio
async def test_llm_invoked_with_deterministic_temperature_and_fixed_budget():
    """Kills M12 (temperature) and M13 (max_tokens).

    Ambiguity detection must be deterministic (temperature==0) and use
    the fixed 2048-token budget the prompt was tuned against. A drift
    on either value silently changes output shape and is a real bug.
    """
    content = "The system shall respond quickly." * 5
    with patch(
        "app.pipeline.nodes.ambiguity_node.pipeline_call_llm_json",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = []
        await detect_ambiguities_in_section("Requirements", content, 0)

    mock_llm.assert_awaited_once()
    _, kwargs = mock_llm.await_args
    assert kwargs["temperature"] == 0.0, "ambiguity detection must stay deterministic"
    assert kwargs["max_tokens"] == 2048, "ambiguity prompt budget must stay at 2048"
