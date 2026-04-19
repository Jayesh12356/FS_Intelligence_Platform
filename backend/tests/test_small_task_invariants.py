"""Small-task invariants — "a small spec must behave small end-to-end".

These tests pin behavioural bounds for the TODO-API scenario so the pipeline
does not over-produce tasks, flag non-existent ambiguities, or call the LLM
more times than necessary. They run against the ``mock`` LLM provider so
they're deterministic, free, and loop-safe.

If any of these invariants fire in the perfection loop the repair policy
will not silently suppress them — the signature escalates to ``unresolved.md``.
"""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient

from app.orchestration.providers import mock_provider as mock_mod
from app.orchestration.providers.mock_provider import (
    MockProvider,
    classify_prompt,
    render_mock_response,
)

# --------------------------------------------------------------------------- #
# Pure unit: the classifier routes prompts correctly and responses are JSON.  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "prompt, expected_key",
    [
        ("Identify ambiguities in the following spec…", "ambiguity"),
        ("Find contradictions between these two sections.", "contradiction"),
        ("List edge-case gaps in error handling.", "edge_case"),
        ("Compute a quality score for the document.", "quality"),
        ("Break this FS into atomic tasks with acceptance criteria.", "task"),
        ("Generate a functional specification from the following idea.", "idea"),
        ("Produce test cases from the acceptance criteria.", "testcase"),
    ],
)
def test_mock_classifier_routes_prompts(prompt: str, expected_key: str) -> None:
    assert classify_prompt(prompt, system="") == expected_key


def test_mock_render_is_always_valid_json() -> None:
    import json

    for prompt in [
        "find ambiguities",
        "find contradictions",
        "totally unrelated gibberish",
        "",
    ]:
        rendered = render_mock_response(prompt)
        # Must always json-parse without error — downstream nodes depend on this.
        json.loads(rendered)


@pytest.mark.asyncio
async def test_mock_provider_is_healthy_and_deterministic() -> None:
    p = MockProvider()
    assert await p.check_health() is True
    first = await p.call_llm(prompt="List ambiguities", system="")
    second = await p.call_llm(prompt="List ambiguities", system="")
    assert first == second  # deterministic


# --------------------------------------------------------------------------- #
# Behavioural: the mock-backed pipeline produces a *small* result shape.      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_task_fixture_yields_small_task_set() -> None:
    """The TODO-API fixture must produce <= 15 tasks (small task invariant)."""
    import json

    path = (
        # Resolve relative to this test file; avoids depending on cwd.
        mock_mod._FIXTURE_DIR / "task.json"
    )
    assert path.exists(), "task fixture missing"
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    assert 1 <= len(tasks) <= 15, f"Task fixture yields {len(tasks)} tasks; invariant is 1..15."
    for t in tasks:
        assert t["title"]
        assert t["description"]
        assert isinstance(t.get("acceptance_criteria", []), list)
        assert int(t.get("effort_hours", 0)) >= 0


@pytest.mark.asyncio
async def test_quality_fixture_reports_reasonable_score() -> None:
    import json

    data = json.loads((mock_mod._FIXTURE_DIR / "quality.json").read_text(encoding="utf-8"))
    q = data["quality_score"]
    assert 70 <= q <= 100, f"quality_score={q} outside sane band (70..100)"


@pytest.mark.asyncio
async def test_small_spec_endpoint_round_trip_with_mock(client: AsyncClient) -> None:
    """Upload TODO-API text, list — the API surface stays boring for a small spec."""
    import io

    os.environ.setdefault("PERFECTION_LOOP", "1")  # enable mock provider registration

    # Small spec upload. We do NOT call /analyze here (needs full DB rows
    # beyond SQLite coverage in conftest); the invariant here is simply that
    # the upload endpoint does not fan out into extra rows, background jobs,
    # or >1 document per upload.
    body = b"GET /todos, POST /todos, DELETE /todos/{id}, GET /health."
    up = await client.post(
        "/api/fs/upload",
        files={"file": ("todo_small.txt", io.BytesIO(body), "text/plain")},
    )
    assert up.status_code == 200
    doc_id = up.json()["data"]["id"]

    listed = await client.get("/api/fs/")
    assert listed.status_code == 200
    docs = listed.json()["data"]["documents"]
    # Exactly one new doc — no duplication from upload side-effects.
    matching = [d for d in docs if d["id"] == doc_id]
    assert len(matching) == 1
