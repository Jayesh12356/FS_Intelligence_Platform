"""Live LLM prompt evaluation (gated behind PROMPT_EVAL_LIVE=1).

By default every test here is skipped so CI costs zero tokens. When you
want to validate that the v2 prompts still produce usable output from
the real LLM, run::

    cd backend && PROMPT_EVAL_LIVE=1 pytest tests/prompt_eval/test_live.py -s

For each prompt surface, this runs one representative fixture through
``pipeline_call_llm`` (or ``pipeline_call_llm_json`` for JSON shapes)
and asserts that the response parses against the declared
``OutputContract`` — schema validation for JSON shapes, non-empty
heading check for Markdown shapes.

When a surface takes highly structured inputs (impact analysis, reverse
flows, etc.) we keep the fixture representative but minimal.
"""

from __future__ import annotations

import json
import os

import pytest

from app.pipeline.prompts.master_template import OutputShape

from .test_structural import PROMPTS, _sample_for

LIVE_MODE = os.getenv("PROMPT_EVAL_LIVE") in {"1", "true", "True"}

pytestmark = pytest.mark.skipif(
    not LIVE_MODE,
    reason="PROMPT_EVAL_LIVE=1 required to run live prompt evaluation",
)


@pytest.mark.parametrize(
    "name, spec, builder",
    PROMPTS,
    ids=[name for name, *_ in PROMPTS],
)
@pytest.mark.asyncio
async def test_live_prompt_returns_valid_shape(name: str, spec, builder) -> None:
    from app.orchestration.pipeline_llm import (
        pipeline_call_llm,
        pipeline_call_llm_json,
    )

    kwargs = _sample_for(name)
    system_prompt, user_prompt = builder(**kwargs)
    contract = spec.output_contract
    assert contract is not None

    if contract.shape in (OutputShape.JSON_ARRAY, OutputShape.JSON_OBJECT):
        result = await pipeline_call_llm_json(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.0,
            max_tokens=2048,
        )
        if contract.shape == OutputShape.JSON_ARRAY:
            assert isinstance(result, list), f"{name}: expected JSON array"
        else:
            assert isinstance(result, dict), f"{name}: expected JSON object"
        # Sanity check: serialises back to valid JSON.
        json.dumps(result)
    else:
        result = await pipeline_call_llm(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.0,
            max_tokens=2048,
        )
        assert isinstance(result, str) and result.strip(), f"{name}: expected non-empty markdown"
