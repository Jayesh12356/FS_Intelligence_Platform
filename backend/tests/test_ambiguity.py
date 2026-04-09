"""Tests for L3 ambiguity detection pipeline.

Tests:
- Pipeline state and models
- Ambiguity node (mocked LLM)
- LangGraph pipeline flow
- Analysis API endpoint
- Ambiguity list and resolve endpoints
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.state import (
    AmbiguityFlag,
    FSAnalysisState,
    Severity,
    SectionInput,
)


# ── Unit Tests: State & Models ──────────────────────────


class TestPipelineState:
    """Test pipeline state models."""

    def test_ambiguity_flag_creation(self):
        flag = AmbiguityFlag(
            section_index=0,
            section_heading="Requirements",
            flagged_text="The system should respond quickly",
            reason="No measurable threshold",
            severity=Severity.HIGH,
            clarification_question="What is the max response time?",
        )
        assert flag.severity == Severity.HIGH
        assert flag.section_index == 0
        assert "quickly" in flag.flagged_text

    def test_severity_enum(self):
        assert Severity.HIGH.value == "HIGH"
        assert Severity.MEDIUM.value == "MEDIUM"
        assert Severity.LOW.value == "LOW"

    def test_section_input(self):
        section = SectionInput(
            heading="Introduction",
            content="This is the introduction.",
            section_index=0,
        )
        assert section.heading == "Introduction"

    def test_analysis_state_structure(self):
        state: FSAnalysisState = {
            "fs_id": "test-123",
            "parsed_sections": [],
            "ambiguities": [],
            "contradictions": [],
            "quality_score": 0.0,
            "tasks": [],
            "errors": [],
        }
        assert state["fs_id"] == "test-123"
        assert isinstance(state["ambiguities"], list)


# ── Unit Tests: Ambiguity Node (mocked LLM) ────────────


class TestAmbiguityNode:
    """Test ambiguity detection with mocked LLM."""

    @pytest.mark.asyncio
    async def test_detect_ambiguities_returns_flags(self):
        """Mocked LLM returns ambiguity flags."""
        mock_response = [
            {
                "flagged_text": "The system should respond quickly",
                "reason": "No measurable threshold",
                "severity": "HIGH",
                "clarification_question": "What is the max response time?",
            },
            {
                "flagged_text": "and other relevant data",
                "reason": "Undefined scope",
                "severity": "MEDIUM",
                "clarification_question": "List all data fields.",
            },
        ]

        with patch("app.pipeline.nodes.ambiguity_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            from app.pipeline.nodes.ambiguity_node import detect_ambiguities_in_section

            flags = await detect_ambiguities_in_section(
                heading="Requirements",
                content="The system should respond quickly and include other relevant data for the user.",
                section_index=0,
            )

            assert len(flags) == 2
            assert flags[0].severity == Severity.HIGH
            assert flags[1].severity == Severity.MEDIUM
            assert "quickly" in flags[0].flagged_text

    @pytest.mark.asyncio
    async def test_detect_empty_section_skipped(self):
        """Short sections should be skipped."""
        from app.pipeline.nodes.ambiguity_node import detect_ambiguities_in_section

        flags = await detect_ambiguities_in_section(
            heading="Empty",
            content="Short.",
            section_index=0,
        )
        assert len(flags) == 0

    @pytest.mark.asyncio
    async def test_ambiguity_node_full_flow(self):
        """Run ambiguity node on mocked state."""
        mock_response = [
            {
                "flagged_text": "should be fast",
                "reason": "Vague",
                "severity": "MEDIUM",
                "clarification_question": "Define fast.",
            },
        ]

        with patch("app.pipeline.nodes.ambiguity_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            from app.pipeline.nodes.ambiguity_node import ambiguity_node

            state: FSAnalysisState = {
                "fs_id": "test-1",
                "parsed_sections": [
                    {
                        "heading": "Requirements",
                        "content": "The system should be fast and handle relevant cases.",
                        "section_index": 0,
                    },
                ],
                "ambiguities": [],
                "errors": [],
            }

            result = await ambiguity_node(state)

            assert len(result["ambiguities"]) == 1
            assert result["ambiguities"][0]["severity"] == "MEDIUM"

    @pytest.mark.asyncio
    async def test_ambiguity_node_handles_llm_error(self):
        """LLM failure should not crash the node — just add error."""
        with patch("app.pipeline.nodes.ambiguity_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(side_effect=Exception("LLM down"))
            mock_get.return_value = mock_client

            from app.pipeline.nodes.ambiguity_node import ambiguity_node

            state: FSAnalysisState = {
                "fs_id": "test-err",
                "parsed_sections": [
                    {
                        "heading": "Reqs",
                        "content": "The system should be fast and reliable under load.",
                        "section_index": 0,
                    },
                ],
                "ambiguities": [],
                "errors": [],
            }

            result = await ambiguity_node(state)
            # Should not crash — ambiguities empty, no errors added since detection returns []
            assert len(result["ambiguities"]) == 0


# ── Unit Tests: Pipeline Graph ──────────────────────────


class TestPipelineGraph:
    """Test the LangGraph pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_runs_with_mocked_llm(self):
        """Full pipeline should complete with mocked LLM."""
        mock_response = [
            {
                "flagged_text": "appropriate measures",
                "reason": "Undefined measures",
                "severity": "LOW",
                "clarification_question": "Specify the exact measures.",
            },
        ]

        with patch("app.pipeline.nodes.ambiguity_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            # Reset compiled graph to pick up mocks
            import app.pipeline.graph as graph_mod
            graph_mod._compiled_graph = None

            from app.pipeline.graph import run_analysis_pipeline

            result = await run_analysis_pipeline(
                fs_id="test-pipeline",
                sections=[
                    {
                        "heading": "Security",
                        "content": "The system shall implement appropriate measures to protect user data.",
                        "section_index": 0,
                    },
                ],
            )

            assert "ambiguities" in result
            assert len(result["ambiguities"]) == 1
            assert result["ambiguities"][0]["severity"] == "LOW"

            # Clean up
            graph_mod._compiled_graph = None


# ── Integration Tests: Analysis API ─────────────────────


class TestAnalysisAPI:
    """Test analysis endpoints via HTTP client."""

    @pytest.mark.asyncio
    async def test_analyze_requires_parsed_status(self, client):
        """Cannot analyze a document that hasn't been parsed."""
        # Upload a file
        content = b"Some test content."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("test.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]

        # Try to analyze without parsing
        response = await client.post(f"/api/fs/{doc_id}/analyze")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_ambiguities_empty(self, client):
        """List ambiguities for a document with none."""
        content = b"Some content for test."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("test2.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]

        response = await client.get(f"/api/fs/{doc_id}/ambiguities")
        assert response.status_code == 200
        assert response.json()["data"] == []

    @pytest.mark.asyncio
    async def test_full_analyze_flow_mocked(self, client):
        """Upload → parse → analyze (mocked LLM) → list ambiguities → resolve."""
        mock_response = [
            {
                "flagged_text": "should be reliable",
                "reason": "No reliability metric",
                "severity": "HIGH",
                "clarification_question": "What uptime percentage is required?",
            },
        ]

        # Upload
        content = b"""1. REQUIREMENTS
The system should be reliable and handle user requests efficiently.
"""
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("spec.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]

        # Parse
        await client.post(f"/api/fs/{doc_id}/parse")

        # Analyze with mocked LLM
        with patch("app.pipeline.nodes.ambiguity_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            import app.pipeline.graph as graph_mod
            graph_mod._compiled_graph = None

            response = await client.post(f"/api/fs/{doc_id}/analyze")
            assert response.status_code == 200

            data = response.json()["data"]
            assert data["status"] == "COMPLETE"
            assert data["ambiguities_count"] >= 1
            assert data["high_count"] >= 1

            graph_mod._compiled_graph = None

        # List ambiguities
        response = await client.get(f"/api/fs/{doc_id}/ambiguities")
        assert response.status_code == 200
        flags = response.json()["data"]
        assert len(flags) >= 1

        flag_id = flags[0]["id"]

        # Resolve one
        response = await client.patch(f"/api/fs/{doc_id}/ambiguities/{flag_id}")
        assert response.status_code == 200
        assert response.json()["data"]["resolved"] is True

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_flag(self, client):
        """Resolving a non-existent flag should 404."""
        fake_doc = "00000000-0000-0000-0000-000000000001"
        fake_flag = "00000000-0000-0000-0000-000000000002"
        response = await client.patch(f"/api/fs/{fake_doc}/ambiguities/{fake_flag}")
        assert response.status_code == 404
