"""Tests for L4 deep FS analysis pipeline.

Tests:
- Pipeline state L4 models (Contradiction, EdgeCaseGap, ComplianceTag, FSQualityScore)
- Contradiction node (mocked LLM)
- Edge case node (mocked LLM)
- Quality node (score computation + compliance tagging)
- Full L4 pipeline flow
- L4 API endpoints (contradictions, edge-cases, quality-score)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.state import (
    Contradiction,
    ComplianceTag,
    EdgeCaseGap,
    FSAnalysisState,
    FSQualityScore,
    Severity,
)
from app.pipeline.nodes.quality_node import compute_quality_score


# ── Unit Tests: L4 State Models ─────────────────────────


class TestL4StateModels:
    """Test L4 pipeline state models."""

    def test_contradiction_creation(self):
        c = Contradiction(
            section_a_index=0,
            section_a_heading="Requirements",
            section_b_index=2,
            section_b_heading="Data Policy",
            description="Section A says retain 90 days, Section B says delete after 7 days.",
            severity=Severity.HIGH,
            suggested_resolution="Clarify with compliance team.",
        )
        assert c.severity == Severity.HIGH
        assert c.section_a_index == 0
        assert c.section_b_index == 2

    def test_edge_case_gap_creation(self):
        ec = EdgeCaseGap(
            section_index=1,
            section_heading="Payment Processing",
            scenario_description="No behavior defined for gateway timeout.",
            impact=Severity.HIGH,
            suggested_addition="Add retry logic with manual reconciliation.",
        )
        assert ec.impact == Severity.HIGH
        assert "timeout" in ec.scenario_description

    def test_compliance_tag_creation(self):
        ct = ComplianceTag(
            section_index=3,
            section_heading="User Registration",
            tag="pii",
            reason="Section references email addresses and phone numbers.",
        )
        assert ct.tag == "pii"

    def test_quality_score_creation(self):
        qs = FSQualityScore(
            completeness=80.0,
            clarity=90.0,
            consistency=100.0,
            overall=89.0,
        )
        assert qs.overall == 89.0
        assert qs.completeness == 80.0

    def test_analysis_state_l4_fields(self):
        state: FSAnalysisState = {
            "fs_id": "test-l4",
            "parsed_sections": [],
            "ambiguities": [],
            "contradictions": [],
            "edge_cases": [],
            "quality_score": {},
            "compliance_tags": [],
            "tasks": [],
            "errors": [],
        }
        assert "edge_cases" in state
        assert "compliance_tags" in state
        assert "quality_score" in state


# ── Unit Tests: Quality Score Computation ───────────────


class TestQualityScoreComputation:
    """Test quality score computation logic."""

    def test_perfect_score_no_issues(self):
        """No ambiguities, contradictions, or edge cases → 100%."""
        score = compute_quality_score(
            total_sections=5,
            ambiguities=[],
            contradictions=[],
            edge_cases=[],
        )
        assert score.completeness == 100.0
        assert score.clarity == 100.0
        assert score.consistency == 100.0
        assert score.overall == 100.0

    def test_clarity_drops_with_ambiguities(self):
        """Ambiguities reduce clarity score."""
        score = compute_quality_score(
            total_sections=4,
            ambiguities=[
                {"section_index": 0},
                {"section_index": 0},  # Same section — shouldn't double-count
                {"section_index": 1},
            ],
            contradictions=[],
            edge_cases=[],
        )
        # 2 out of 4 sections affected → clarity = 50%
        assert score.clarity == 50.0
        assert score.completeness == 100.0
        assert score.consistency == 100.0

    def test_completeness_drops_with_edge_cases(self):
        """Edge cases reduce completeness score."""
        score = compute_quality_score(
            total_sections=4,
            ambiguities=[],
            contradictions=[],
            edge_cases=[
                {"section_index": 2},
                {"section_index": 3},
            ],
        )
        # 2 out of 4 sections affected → completeness = 50%
        assert score.completeness == 50.0
        assert score.clarity == 100.0

    def test_consistency_drops_with_contradictions(self):
        """Contradictions reduce consistency score."""
        score = compute_quality_score(
            total_sections=4,
            ambiguities=[],
            contradictions=[
                {"section_a_index": 0},
                {"section_a_index": 1},
            ],
            edge_cases=[],
        )
        # 4 sections → 6 pairs, 2 contradictions → consistency = (1 - 2/6) * 100 = 66.7
        assert score.consistency == 66.7
        assert score.completeness == 100.0

    def test_zero_sections_returns_100(self):
        """Empty document returns perfect score."""
        score = compute_quality_score(
            total_sections=0,
            ambiguities=[],
            contradictions=[],
            edge_cases=[],
        )
        assert score.overall == 100.0

    def test_overall_is_weighted_average(self):
        """Overall score should be weighted average of sub-scores."""
        score = compute_quality_score(
            total_sections=2,
            ambiguities=[{"section_index": 0}],
            contradictions=[{"section_a_index": 0}],
            edge_cases=[{"section_index": 1}],
        )
        # clarity = 50%, completeness = 50%, consistency = (1 - 1/1) * 100 = 0%
        expected = 0.35 * 50.0 + 0.35 * 50.0 + 0.30 * 0.0
        assert score.overall == round(expected, 1)


# ── Unit Tests: Contradiction Node (mocked LLM) ────────


class TestContradictionNode:
    """Test contradiction detection with mocked LLM."""

    @pytest.mark.asyncio
    async def test_detect_contradictions_returns_results(self):
        """Mocked LLM returns contradictions between sections."""
        mock_response = [
            {
                "description": "Section A requires 30-day retention, Section B requires immediate deletion.",
                "severity": "HIGH",
                "suggested_resolution": "Clarify with compliance team.",
            },
        ]

        with patch("app.pipeline.nodes.contradiction_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            from app.pipeline.nodes.contradiction_node import detect_contradictions_between_sections

            results = await detect_contradictions_between_sections(
                heading_a="Data Storage",
                content_a="All user data must be retained for at least 30 days.",
                index_a=0,
                heading_b="Privacy Policy",
                content_b="User data must be deleted immediately after processing.",
                index_b=1,
            )

            assert len(results) == 1
            assert results[0].severity == Severity.HIGH
            assert "retention" in results[0].description.lower() or "deletion" in results[0].description.lower()

    @pytest.mark.asyncio
    async def test_contradiction_node_full_flow(self):
        """Run contradiction node on mocked state."""
        mock_response = [
            {
                "description": "Conflict found",
                "severity": "MEDIUM",
                "suggested_resolution": "Align definitions.",
            },
        ]

        with patch("app.pipeline.nodes.contradiction_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            from app.pipeline.nodes.contradiction_node import contradiction_node

            state: FSAnalysisState = {
                "fs_id": "test-c1",
                "parsed_sections": [
                    {"heading": "Reqs A", "content": "Store data for 90 days minimum.", "section_index": 0},
                    {"heading": "Reqs B", "content": "Delete data after processing within 24 hours.", "section_index": 1},
                ],
                "ambiguities": [],
                "contradictions": [],
                "errors": [],
            }

            result = await contradiction_node(state)
            assert len(result["contradictions"]) == 1
            assert result["contradictions"][0]["severity"] == "MEDIUM"

    @pytest.mark.asyncio
    async def test_contradiction_node_handles_error(self):
        """LLM failure should not crash the node."""
        with patch("app.pipeline.nodes.contradiction_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(side_effect=Exception("LLM down"))
            mock_get.return_value = mock_client

            from app.pipeline.nodes.contradiction_node import contradiction_node

            state: FSAnalysisState = {
                "fs_id": "test-err",
                "parsed_sections": [
                    {"heading": "A", "content": "Store all data permanently.", "section_index": 0},
                    {"heading": "B", "content": "Delete data after seven days.", "section_index": 1},
                ],
                "ambiguities": [],
                "contradictions": [],
                "errors": [],
            }

            result = await contradiction_node(state)
            assert len(result["contradictions"]) == 0

    @pytest.mark.asyncio
    async def test_skip_short_sections(self):
        """Very short sections should be skipped."""
        from app.pipeline.nodes.contradiction_node import detect_contradictions_between_sections

        results = await detect_contradictions_between_sections(
            heading_a="A", content_a="Short.", index_a=0,
            heading_b="B", content_b="Also short.", index_b=1,
        )
        assert len(results) == 0


# ── Unit Tests: Edge Case Node (mocked LLM) ────────────


class TestEdgeCaseNode:
    """Test edge case detection with mocked LLM."""

    @pytest.mark.asyncio
    async def test_detect_edge_cases_returns_gaps(self):
        """Mocked LLM returns edge case gaps."""
        mock_response = [
            {
                "scenario_description": "No behavior defined for payment gateway timeout.",
                "impact": "HIGH",
                "suggested_addition": "Add retry logic.",
            },
            {
                "scenario_description": "No empty input validation specified.",
                "impact": "LOW",
                "suggested_addition": "Add input validation rules.",
            },
        ]

        with patch("app.pipeline.nodes.edge_case_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            from app.pipeline.nodes.edge_case_node import detect_edge_cases_in_section

            gaps = await detect_edge_cases_in_section(
                heading="Payment Processing",
                content="The system processes payments through the payment gateway and confirms the transaction.",
                section_index=0,
            )

            assert len(gaps) == 2
            assert gaps[0].impact == Severity.HIGH
            assert "timeout" in gaps[0].scenario_description.lower()

    @pytest.mark.asyncio
    async def test_edge_case_node_full_flow(self):
        """Run edge case node on mocked state."""
        mock_response = [
            {
                "scenario_description": "Missing error handler",
                "impact": "MEDIUM",
                "suggested_addition": "Add error handling.",
            },
        ]

        with patch("app.pipeline.nodes.edge_case_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            from app.pipeline.nodes.edge_case_node import edge_case_node

            state: FSAnalysisState = {
                "fs_id": "test-ec1",
                "parsed_sections": [
                    {"heading": "Auth", "content": "Users log in with username and password to access the dashboard.", "section_index": 0},
                ],
                "ambiguities": [],
                "edge_cases": [],
                "errors": [],
            }

            result = await edge_case_node(state)
            assert len(result["edge_cases"]) == 1

    @pytest.mark.asyncio
    async def test_edge_case_node_handles_error(self):
        """LLM failure should not crash the node."""
        with patch("app.pipeline.nodes.edge_case_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(side_effect=Exception("LLM down"))
            mock_get.return_value = mock_client

            from app.pipeline.nodes.edge_case_node import edge_case_node

            state: FSAnalysisState = {
                "fs_id": "test-err",
                "parsed_sections": [
                    {"heading": "X", "content": "A section with enough content to analyze properly.", "section_index": 0},
                ],
                "ambiguities": [],
                "edge_cases": [],
                "errors": [],
            }

            result = await edge_case_node(state)
            assert len(result["edge_cases"]) == 0


# ── Unit Tests: Quality Node (mocked LLM) ──────────────


class TestQualityNode:
    """Test quality scoring node."""

    @pytest.mark.asyncio
    async def test_quality_node_computes_score(self):
        """Quality node should compute scores from existing data."""
        mock_response = [
            {"tag": "auth", "reason": "Login mentioned."},
        ]

        with patch("app.pipeline.nodes.quality_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            from app.pipeline.nodes.quality_node import quality_node

            state: FSAnalysisState = {
                "fs_id": "test-q1",
                "parsed_sections": [
                    {"heading": "Auth", "content": "Users authenticate via SSO login with enterprise credentials.", "section_index": 0},
                    {"heading": "Data", "content": "The system stores user data in encrypted databases at rest.", "section_index": 1},
                ],
                "ambiguities": [
                    {"section_index": 0, "flagged_text": "test"},
                ],
                "contradictions": [],
                "edge_cases": [
                    {"section_index": 1, "scenario_description": "test"},
                ],
                "compliance_tags": [],
                "errors": [],
            }

            result = await quality_node(state)
            quality = result["quality_score"]

            assert "completeness" in quality
            assert "clarity" in quality
            assert "consistency" in quality
            assert "overall" in quality
            assert quality["clarity"] == 50.0  # 1/2 sections has ambiguity
            assert quality["completeness"] == 50.0  # 1/2 sections has edge case
            assert quality["consistency"] == 100.0  # No contradictions
            assert len(result["compliance_tags"]) == 2  # Both sections get compliance tag from mock

    @pytest.mark.asyncio
    async def test_quality_node_handles_llm_error(self):
        """LLM failure for compliance should not crash — score still computed."""
        with patch("app.pipeline.nodes.quality_node.get_llm_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.call_llm_json = AsyncMock(side_effect=Exception("LLM down"))
            mock_get.return_value = mock_client

            from app.pipeline.nodes.quality_node import quality_node

            state: FSAnalysisState = {
                "fs_id": "test-err",
                "parsed_sections": [
                    {"heading": "X", "content": "Some content that is long enough to be analyzed properly.", "section_index": 0},
                ],
                "ambiguities": [],
                "contradictions": [],
                "edge_cases": [],
                "compliance_tags": [],
                "errors": [],
            }

            result = await quality_node(state)
            # Score should still be computed despite LLM failure
            assert result["quality_score"]["overall"] == 100.0
            assert len(result["compliance_tags"]) == 0


# ── Integration Tests: Full L4 Pipeline ─────────────────


class TestL4Pipeline:
    """Test the full L4 pipeline with mocked LLM."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_all_nodes(self):
        """Full pipeline runs all 5 nodes with mocked LLM."""
        ambiguity_response = [
            {"flagged_text": "appropriate measures", "reason": "Vague", "severity": "LOW", "clarification_question": "Specify."},
        ]
        contradiction_response = []
        edge_case_response = [
            {"scenario_description": "No error handling", "impact": "MEDIUM", "suggested_addition": "Add error handler."},
        ]
        compliance_response = [
            {"tag": "security", "reason": "Mentions encryption."},
        ]

        call_count = 0

        async def mock_call_json(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            prompt = kwargs.get("prompt", args[0] if args else "")

            if "ambiguities" in str(kwargs.get("system", "")):
                return ambiguity_response
            elif "CONTRADICTIONS" in str(kwargs.get("system", "")).upper():
                return contradiction_response
            elif "EDGE CASES" in str(kwargs.get("system", "")).upper():
                return edge_case_response
            elif "compliance" in str(kwargs.get("system", "")).lower():
                return compliance_response
            return []

        # Patch all LLM clients in all nodes
        patches = [
            patch("app.pipeline.nodes.ambiguity_node.get_llm_client"),
            patch("app.pipeline.nodes.contradiction_node.get_llm_client"),
            patch("app.pipeline.nodes.edge_case_node.get_llm_client"),
            patch("app.pipeline.nodes.quality_node.get_llm_client"),
        ]

        mock_client = AsyncMock()
        mock_client.call_llm_json = AsyncMock(side_effect=mock_call_json)

        started_patches = [p.start() for p in patches]
        for mp in started_patches:
            mp.return_value = mock_client

        try:
            import app.pipeline.graph as graph_mod
            graph_mod._compiled_graph = None

            from app.pipeline.graph import run_analysis_pipeline

            result = await run_analysis_pipeline(
                fs_id="test-l4-pipeline",
                sections=[
                    {
                        "heading": "Security",
                        "content": "The system shall implement appropriate measures with encryption to protect data.",
                        "section_index": 0,
                    },
                ],
            )

            assert "ambiguities" in result
            assert "contradictions" in result
            assert "edge_cases" in result
            assert "quality_score" in result
            assert "compliance_tags" in result

            # Ambiguities detected
            assert len(result["ambiguities"]) == 1

            # Quality score computed
            assert result["quality_score"]["overall"] > 0

            graph_mod._compiled_graph = None
        finally:
            for p in patches:
                p.stop()


# ── Integration Tests: L4 API Endpoints ─────────────────


class TestL4API:
    """Test L4 analysis endpoints via HTTP client."""

    @pytest.mark.asyncio
    async def test_contradictions_endpoint_empty(self, client):
        """List contradictions for a document with none."""
        content = b"Some content for test."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("test.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]

        response = await client.get(f"/api/fs/{doc_id}/contradictions")
        assert response.status_code == 200
        assert response.json()["data"] == []

    @pytest.mark.asyncio
    async def test_edge_cases_endpoint_empty(self, client):
        """List edge cases for a document with none."""
        content = b"Some content for test."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("test.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]

        response = await client.get(f"/api/fs/{doc_id}/edge-cases")
        assert response.status_code == 200
        assert response.json()["data"] == []

    @pytest.mark.asyncio
    async def test_quality_score_404_no_doc(self, client):
        """Quality score for non-existent document returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000099"
        response = await client.get(f"/api/fs/{fake_id}/quality-score")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_resolve_contradiction_404(self, client):
        """Resolving non-existent contradiction returns 404."""
        fake_doc = "00000000-0000-0000-0000-000000000001"
        fake_id = "00000000-0000-0000-0000-000000000002"
        response = await client.patch(f"/api/fs/{fake_doc}/contradictions/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_resolve_edge_case_404(self, client):
        """Resolving non-existent edge case returns 404."""
        fake_doc = "00000000-0000-0000-0000-000000000001"
        fake_id = "00000000-0000-0000-0000-000000000002"
        response = await client.patch(f"/api/fs/{fake_doc}/edge-cases/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_full_l4_analyze_flow(self, client):
        """Upload → parse → analyze (mocked) → check L4 endpoints."""
        ambiguity_response = [
            {"flagged_text": "should work", "reason": "Vague", "severity": "LOW", "clarification_question": "Clarify."},
        ]
        contradiction_response = []
        edge_case_response = [
            {"scenario_description": "No timeout handling", "impact": "HIGH", "suggested_addition": "Add timeout."},
        ]
        compliance_response = [
            {"tag": "auth", "reason": "Login mentioned."},
        ]

        async def mock_call_json(*args, **kwargs):
            system = str(kwargs.get("system", ""))
            if "ambiguities" in system.lower() or "ambiguous" in system.lower():
                return ambiguity_response
            elif "contradiction" in system.lower():
                return contradiction_response
            elif "edge case" in system.lower():
                return edge_case_response
            elif "compliance" in system.lower():
                return compliance_response
            return []

        # Upload
        content = b"""1. AUTHENTICATION
The system should work with SSO login and handle user sessions properly.
Users authenticate using enterprise credentials.
"""
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("spec.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]

        # Parse
        await client.post(f"/api/fs/{doc_id}/parse")

        # Analyze with mocked LLM
        patches = [
            patch("app.pipeline.nodes.ambiguity_node.get_llm_client"),
            patch("app.pipeline.nodes.contradiction_node.get_llm_client"),
            patch("app.pipeline.nodes.edge_case_node.get_llm_client"),
            patch("app.pipeline.nodes.quality_node.get_llm_client"),
        ]

        mock_client = AsyncMock()
        mock_client.call_llm_json = AsyncMock(side_effect=mock_call_json)

        started_patches = [p.start() for p in patches]
        for mp in started_patches:
            mp.return_value = mock_client

        try:
            import app.pipeline.graph as graph_mod
            graph_mod._compiled_graph = None

            response = await client.post(f"/api/fs/{doc_id}/analyze")
            assert response.status_code == 200

            data = response.json()["data"]
            assert data["status"] == "COMPLETE"
            assert data["ambiguities_count"] >= 1

            # Check quality score in response
            assert data["quality_score"] is not None
            assert "overall" in data["quality_score"]

            # Check contradictions endpoint
            response = await client.get(f"/api/fs/{doc_id}/contradictions")
            assert response.status_code == 200

            # Check edge cases endpoint
            response = await client.get(f"/api/fs/{doc_id}/edge-cases")
            assert response.status_code == 200
            edge_cases = response.json()["data"]
            assert len(edge_cases) >= 1

            # Resolve edge case
            if edge_cases:
                ec_id = edge_cases[0]["id"]
                response = await client.patch(f"/api/fs/{doc_id}/edge-cases/{ec_id}")
                assert response.status_code == 200
                assert response.json()["data"]["resolved"] is True

            # Check quality dashboard endpoint
            response = await client.get(f"/api/fs/{doc_id}/quality-score")
            assert response.status_code == 200
            dashboard = response.json()["data"]
            assert "quality_score" in dashboard
            assert "contradictions" in dashboard
            assert "edge_cases" in dashboard
            assert "compliance_tags" in dashboard

            graph_mod._compiled_graph = None
        finally:
            for p in patches:
                p.stop()
