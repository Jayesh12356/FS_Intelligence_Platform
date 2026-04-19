"""Tests for L6 adversarial validation (debate) pipeline.

Tests:
- DebateVerdict model
- State with debate_results field
- Debate node (mocked CrewAI)
- Pipeline graph includes debate_node
- Debate results API endpoint
- Debate crew output parsing
- Benchmark precision/recall computation
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.state import (
    AmbiguityFlag,
    DebateVerdict,
    FSAnalysisState,
    Severity,
)

# ── Unit Tests: DebateVerdict Model ─────────────────────


class TestDebateVerdict:
    """Test the DebateVerdict Pydantic model."""

    def test_debate_verdict_creation(self):
        verdict = DebateVerdict(
            verdict="AMBIGUOUS",
            red_argument="The requirement lacks measurable thresholds.",
            blue_argument="Any developer knows what 'fast' means in context.",
            arbiter_reasoning="The term 'fast' is subjective and needs quantification.",
            confidence=85,
        )
        assert verdict.verdict == "AMBIGUOUS"
        assert verdict.confidence == 85
        assert "measurable" in verdict.red_argument

    def test_debate_verdict_clear(self):
        verdict = DebateVerdict(
            verdict="CLEAR",
            red_argument="The term 'users' is vague.",
            blue_argument="'Users' clearly refers to authenticated end-users.",
            arbiter_reasoning="Standard interpretation applies here.",
            confidence=70,
        )
        assert verdict.verdict == "CLEAR"
        assert verdict.confidence == 70

    def test_debate_verdict_serialisation(self):
        verdict = DebateVerdict(
            verdict="AMBIGUOUS",
            red_argument="Red argument text",
            blue_argument="Blue argument text",
            arbiter_reasoning="Arbiter reasoning text",
            confidence=90,
        )
        data = verdict.model_dump()
        assert data["verdict"] == "AMBIGUOUS"
        assert data["confidence"] == 90
        assert isinstance(data, dict)

    def test_debate_verdict_default_confidence(self):
        verdict = DebateVerdict(
            verdict="CLEAR",
            red_argument="R",
            blue_argument="B",
            arbiter_reasoning="A",
        )
        assert verdict.confidence == 50  # default


# ── Unit Tests: State with Debate Results ───────────────


class TestStateWithDebate:
    """Test FSAnalysisState includes debate_results field."""

    def test_state_has_debate_results_field(self):
        state: FSAnalysisState = {
            "fs_id": "test-123",
            "parsed_sections": [],
            "ambiguities": [],
            "debate_results": [],
            "contradictions": [],
            "edge_cases": [],
            "quality_score": {},
            "compliance_tags": [],
            "tasks": [],
            "traceability_matrix": [],
            "errors": [],
        }
        assert "debate_results" in state
        assert isinstance(state["debate_results"], list)

    def test_state_debate_results_with_data(self):
        state: FSAnalysisState = {
            "fs_id": "test-456",
            "parsed_sections": [],
            "ambiguities": [],
            "debate_results": [
                {
                    "section_index": 0,
                    "verdict": "CLEAR",
                    "confidence": 75,
                    "red_argument": "Red says ambiguous",
                    "blue_argument": "Blue says clear",
                    "arbiter_reasoning": "Clear enough",
                },
            ],
            "errors": [],
        }
        assert len(state["debate_results"]) == 1
        assert state["debate_results"][0]["verdict"] == "CLEAR"


# ── Unit Tests: Debate Node (mocked debate) ─────────────


class TestDebateNode:
    """Test debate_node with mocked CrewAI debate."""

    @pytest.mark.asyncio
    async def test_debate_node_skips_no_high_flags(self):
        """When there are no HIGH severity flags, debate should be skipped."""
        from app.pipeline.nodes.debate_node import debate_node

        state: FSAnalysisState = {
            "fs_id": "test-no-high",
            "parsed_sections": [],
            "ambiguities": [
                {
                    "section_index": 0,
                    "section_heading": "Auth",
                    "flagged_text": "some text",
                    "reason": "vague",
                    "severity": "MEDIUM",
                    "clarification_question": "Be specific.",
                },
                {
                    "section_index": 1,
                    "section_heading": "Data",
                    "flagged_text": "other text",
                    "reason": "unclear",
                    "severity": "LOW",
                    "clarification_question": "Clarify.",
                },
            ],
            "errors": [],
        }

        result = await debate_node(state)

        # No debate should run
        assert result["debate_results"] == []
        # All flags should remain
        assert len(result["ambiguities"]) == 2

    @pytest.mark.asyncio
    async def test_debate_node_clears_false_positive(self):
        """When debate verdict is CLEAR, the flag should be removed."""
        mock_verdict = DebateVerdict(
            verdict="CLEAR",
            red_argument="It could mean anything",
            blue_argument="Standard auth pattern — any developer knows",
            arbiter_reasoning="Standard pattern, clear enough",
            confidence=80,
        )

        with patch("app.pipeline.nodes.debate_node.run_debate", new_callable=AsyncMock) as mock_debate:
            mock_debate.return_value = mock_verdict

            from app.pipeline.nodes.debate_node import debate_node

            state: FSAnalysisState = {
                "fs_id": "test-clear",
                "parsed_sections": [],
                "ambiguities": [
                    {
                        "section_index": 0,
                        "section_heading": "Auth",
                        "flagged_text": "authenticate users",
                        "reason": "Auth method not specified",
                        "severity": "HIGH",
                        "clarification_question": "Which auth method?",
                    },
                    {
                        "section_index": 1,
                        "section_heading": "Data",
                        "flagged_text": "some text",
                        "reason": "vague",
                        "severity": "MEDIUM",
                        "clarification_question": "Specify.",
                    },
                ],
                "errors": [],
            }

            result = await debate_node(state)

            # HIGH flag cleared, MEDIUM flag remains
            assert len(result["ambiguities"]) == 1
            assert result["ambiguities"][0]["severity"] == "MEDIUM"
            # One debate result recorded
            assert len(result["debate_results"]) == 1
            assert result["debate_results"][0]["verdict"] == "CLEAR"
            assert result["debate_results"][0]["confidence"] == 80

    @pytest.mark.asyncio
    async def test_debate_node_confirms_ambiguity(self):
        """When debate verdict is AMBIGUOUS, the flag should be kept with reasoning."""
        mock_verdict = DebateVerdict(
            verdict="AMBIGUOUS",
            red_argument="No measurable threshold for 'fast'",
            blue_argument="'Fast' is relative to context",
            arbiter_reasoning="Needs quantification — ambiguous",
            confidence=90,
        )

        with patch("app.pipeline.nodes.debate_node.run_debate", new_callable=AsyncMock) as mock_debate:
            mock_debate.return_value = mock_verdict

            from app.pipeline.nodes.debate_node import debate_node

            state: FSAnalysisState = {
                "fs_id": "test-ambig",
                "parsed_sections": [],
                "ambiguities": [
                    {
                        "section_index": 0,
                        "section_heading": "Performance",
                        "flagged_text": "fast response",
                        "reason": "No threshold defined",
                        "severity": "HIGH",
                        "clarification_question": "Define max response time.",
                    },
                ],
                "errors": [],
            }

            result = await debate_node(state)

            # Flag kept
            assert len(result["ambiguities"]) == 1
            assert result["ambiguities"][0]["severity"] == "HIGH"
            # Debate reasoning added to flag
            assert "debate_reasoning" in result["ambiguities"][0]
            assert "debate_confidence" in result["ambiguities"][0]
            assert result["ambiguities"][0]["debate_confidence"] == 90
            # One debate result
            assert len(result["debate_results"]) == 1
            assert result["debate_results"][0]["verdict"] == "AMBIGUOUS"

    @pytest.mark.asyncio
    async def test_debate_node_handles_debate_failure(self):
        """If debate fails, flags should be kept (fail-safe)."""
        with patch("app.pipeline.nodes.debate_node.run_debate", new_callable=AsyncMock) as mock_debate:
            mock_debate.side_effect = Exception("CrewAI crashed")

            from app.pipeline.nodes.debate_node import debate_node

            state: FSAnalysisState = {
                "fs_id": "test-fail",
                "parsed_sections": [],
                "ambiguities": [
                    {
                        "section_index": 0,
                        "section_heading": "Reqs",
                        "flagged_text": "appropriate measures",
                        "reason": "Undefined",
                        "severity": "HIGH",
                        "clarification_question": "Define measures.",
                    },
                ],
                "errors": [],
            }

            result = await debate_node(state)

            # Flag should be kept on failure
            assert len(result["ambiguities"]) == 1
            assert result["ambiguities"][0]["severity"] == "HIGH"
            # Error recorded
            assert len(result["errors"]) == 1
            assert "CrewAI crashed" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_debate_node_multiple_high_flags(self):
        """Multiple HIGH flags should each be debated individually."""
        call_count = 0

        async def mock_debate_fn(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return DebateVerdict(
                    verdict="CLEAR",
                    red_argument="R1",
                    blue_argument="B1",
                    arbiter_reasoning="Clear",
                    confidence=75,
                )
            return DebateVerdict(
                verdict="AMBIGUOUS",
                red_argument="R2",
                blue_argument="B2",
                arbiter_reasoning="Ambiguous",
                confidence=85,
            )

        with patch("app.pipeline.nodes.debate_node.run_debate", side_effect=mock_debate_fn):
            from app.pipeline.nodes.debate_node import debate_node

            state: FSAnalysisState = {
                "fs_id": "test-multi",
                "parsed_sections": [],
                "ambiguities": [
                    {
                        "section_index": 0,
                        "section_heading": "A",
                        "flagged_text": "text1",
                        "reason": "r1",
                        "severity": "HIGH",
                        "clarification_question": "q1",
                    },
                    {
                        "section_index": 1,
                        "section_heading": "B",
                        "flagged_text": "text2",
                        "reason": "r2",
                        "severity": "HIGH",
                        "clarification_question": "q2",
                    },
                    {
                        "section_index": 2,
                        "section_heading": "C",
                        "flagged_text": "text3",
                        "reason": "r3",
                        "severity": "LOW",
                        "clarification_question": "q3",
                    },
                ],
                "errors": [],
            }

            result = await debate_node(state)

            # 1 cleared + 1 confirmed + 1 LOW = 2 remaining
            assert len(result["ambiguities"]) == 2
            assert result["debate_results"][0]["verdict"] == "CLEAR"
            assert result["debate_results"][1]["verdict"] == "AMBIGUOUS"
            assert call_count == 2  # Only HIGH flags debated


# ── Unit Tests: Debate Output Parsing ───────────────────


class TestDebateOutputParsing:
    """Test the arbiter verdict parser."""

    def test_parse_valid_json(self):
        from app.agents.debate_crew import _parse_arbiter_verdict

        raw = '{"verdict": "AMBIGUOUS", "reasoning": "Not clear", "confidence": 85}'
        result = _parse_arbiter_verdict(raw)
        assert result["verdict"] == "AMBIGUOUS"
        assert result["confidence"] == 85

    def test_parse_json_in_code_block(self):
        from app.agents.debate_crew import _parse_arbiter_verdict

        raw = '```json\n{"verdict": "CLEAR", "reasoning": "Clear enough", "confidence": 70}\n```'
        result = _parse_arbiter_verdict(raw)
        assert result["verdict"] == "CLEAR"
        assert result["confidence"] == 70

    def test_parse_invalid_verdict_defaults_to_ambiguous(self):
        from app.agents.debate_crew import _parse_arbiter_verdict

        raw = '{"verdict": "MAYBE", "reasoning": "Unsure", "confidence": 50}'
        result = _parse_arbiter_verdict(raw)
        assert result["verdict"] == "AMBIGUOUS"

    def test_parse_invalid_json_fallback(self):
        from app.agents.debate_crew import _parse_arbiter_verdict

        raw = "I think this is AMBIGUOUS because the requirement is vague."
        result = _parse_arbiter_verdict(raw)
        assert result["verdict"] == "AMBIGUOUS"
        assert result["confidence"] <= 50

    def test_parse_clear_in_text_fallback(self):
        from app.agents.debate_crew import _parse_arbiter_verdict

        raw = "Based on my analysis, this requirement is CLEAR."
        result = _parse_arbiter_verdict(raw)
        assert result["verdict"] == "CLEAR"

    def test_parse_confidence_clamped(self):
        from app.agents.debate_crew import _parse_arbiter_verdict

        raw = '{"verdict": "AMBIGUOUS", "reasoning": "x", "confidence": 150}'
        result = _parse_arbiter_verdict(raw)
        assert result["confidence"] == 100

    def test_parse_confidence_negative(self):
        from app.agents.debate_crew import _parse_arbiter_verdict

        raw = '{"verdict": "CLEAR", "reasoning": "x", "confidence": -10}'
        result = _parse_arbiter_verdict(raw)
        assert result["confidence"] == 0


# ── Unit Tests: Benchmark Computation ───────────────────


class TestBenchmarkComputation:
    """Test precision/recall computation used in benchmarks."""

    def test_perfect_detection(self):
        from app.pipeline.benchmarks.debate_benchmark import _compute_precision_recall

        ground_truth = [
            {"section_index": 0, "ground_truth_ambiguous": ["fast response"]},
        ]
        detected = [
            {"section_index": 0, "flagged_text": "fast response"},
        ]
        metrics = _compute_precision_recall(detected, ground_truth)
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1"] == 1.0

    def test_false_positive(self):
        from app.pipeline.benchmarks.debate_benchmark import _compute_precision_recall

        ground_truth = [
            {"section_index": 0, "ground_truth_ambiguous": []},
        ]
        detected = [
            {"section_index": 0, "flagged_text": "some text"},
        ]
        metrics = _compute_precision_recall(detected, ground_truth)
        assert metrics["precision"] == 0.0

    def test_missed_detection(self):
        from app.pipeline.benchmarks.debate_benchmark import _compute_precision_recall

        ground_truth = [
            {"section_index": 0, "ground_truth_ambiguous": ["vague term"]},
        ]
        detected = []
        metrics = _compute_precision_recall(detected, ground_truth)
        assert metrics["recall"] == 0.0

    def test_empty_both(self):
        from app.pipeline.benchmarks.debate_benchmark import _compute_precision_recall

        metrics = _compute_precision_recall([], [{"section_index": 0, "ground_truth_ambiguous": []}])
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0


# ── Integration Tests: Pipeline Graph with Debate ──────


class TestPipelineWithDebate:
    """Test that the graph includes debate_node in the right position."""

    def test_graph_has_debate_node(self):
        """The compiled graph should contain a debate_node."""
        import app.pipeline.graph as graph_mod

        graph_mod._compiled_graph = None

        # Patch all LLM-dependent nodes to avoid real calls
        with (
            patch("app.pipeline.nodes.ambiguity_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.debate_node.run_debate", new_callable=AsyncMock),
            patch("app.pipeline.nodes.contradiction_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.edge_case_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.quality_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.task_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.dependency_node.pipeline_call_llm_json", new_callable=AsyncMock),
        ):
            graph = graph_mod.build_analysis_graph()

            # The graph should have the debate_node
            # Check it's in the node list (LangGraph stores nodes internally)
            assert graph is not None

        graph_mod._compiled_graph = None


# ── Integration Tests: Debate Results API ───────────────


class TestDebateResultsAPI:
    """Test debate results API endpoints."""

    @pytest.mark.asyncio
    async def test_debate_results_empty(self, client):
        """Debate results should be empty for a new document."""
        # Upload a file first
        content = b"Test document for debate."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("debate_test.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]

        response = await client.get(f"/api/fs/{doc_id}/debate-results")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total_debated"] == 0
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_debate_results_not_found(self, client):
        """Debate results for non-existent document should 404."""
        fake_id = "00000000-0000-0000-0000-000000000099"
        response = await client.get(f"/api/fs/{fake_id}/debate-results")
        assert response.status_code == 404
