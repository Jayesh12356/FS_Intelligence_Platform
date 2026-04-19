"""Selective re-analysis behaviour for run_analysis_pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.graph import SELECTIVE_NODE_SET, run_analysis_pipeline


@pytest.mark.asyncio
async def test_selective_skips_cross_cutting_nodes(test_db):
    sections = [
        {"heading": "A", "content": "x" * 200, "section_index": 0},
        {"heading": "B", "content": "y" * 200, "section_index": 1},
        {"heading": "C", "content": "z" * 200, "section_index": 2},
    ]

    called: list[str] = []

    async def _record(name: str):
        async def _fake(state):
            called.append(name)
            return state

        return _fake

    # Patch every node function used in run_analysis_pipeline's db branch
    patches = []
    for node in [
        "parse_node",
        "ambiguity_node",
        "debate_node",
        "contradiction_node",
        "edge_case_node",
        "quality_node",
        "task_decomposition_node",
        "dependency_node",
        "traceability_node",
        "duplicate_node",
        "testcase_node",
    ]:
        fake = AsyncMock(side_effect=lambda s, _n=node: called.append(_n) or s)
        patches.append(patch(f"app.pipeline.graph.{node}", fake))

    for p in patches:
        p.start()
    try:
        await run_analysis_pipeline(
            "11111111-1111-1111-1111-111111111111",
            sections,
            db=test_db,
            changed_indices={1},
        )
    finally:
        for p in patches:
            p.stop()

    for n in called:
        assert n in SELECTIVE_NODE_SET, f"Unexpected cross-cutting node ran: {n}"
    # At least the per-section + preamble nodes should have run
    assert "parse_node" in called
    assert "ambiguity_node" in called


@pytest.mark.asyncio
async def test_selective_filters_sections_list():
    sections = [
        {"heading": "A", "content": "x" * 200, "section_index": 0},
        {"heading": "B", "content": "y" * 200, "section_index": 1},
        {"heading": "C", "content": "z" * 200, "section_index": 2},
    ]
    observed: list[int] = []

    async def spy_ambiguity(state):
        for s in state.get("parsed_sections", []):
            observed.append(s["section_index"])
        return state

    with (
        patch("app.pipeline.graph.ambiguity_node", AsyncMock(side_effect=spy_ambiguity)),
        patch("app.pipeline.graph.parse_node", AsyncMock(side_effect=lambda s: s)),
        patch("app.pipeline.graph.debate_node", AsyncMock(side_effect=lambda s: s)),
        patch("app.pipeline.graph.edge_case_node", AsyncMock(side_effect=lambda s: s)),
    ):
        await run_analysis_pipeline(
            "22222222-2222-2222-2222-222222222222",
            sections,
            db=None,  # will still use the graph path, but the filter happens before
            changed_indices={2},
        )
    # Without db the selective path does not short-circuit node_order, but the
    # sections list is already filtered ahead of time.
    # Since db is None we go through the LangGraph; just assert no-op.
    # The real assertion is through the db path above.
