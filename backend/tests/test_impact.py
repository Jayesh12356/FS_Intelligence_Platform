"""Tests for L7 FS change impact analysis pipeline.

Tests:
- FSChange, TaskImpact, ReworkEstimate models
- FSImpactState with L7 fields
- version_node (diff computation)
- impact_node (mocked LLM)
- rework_node (cost estimation)
- Impact pipeline graph
- Impact API endpoints (versions, diff, impact, rework)
- Version upload API
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.state import (
    ChangeType,
    FSChange,
    FSImpactState,
    ImpactType,
    ReworkEstimate,
    TaskImpact,
)


# ── Unit Tests: FSChange Model ──────────────────────────


class TestFSChangeModel:
    """Test the FSChange Pydantic model."""

    def test_added_change(self):
        change = FSChange(
            change_type=ChangeType.ADDED,
            section_id="section_3",
            section_heading="New Feature",
            section_index=3,
            old_text=None,
            new_text="This is a new section about payments.",
        )
        assert change.change_type == ChangeType.ADDED
        assert change.old_text is None
        assert "payments" in change.new_text

    def test_modified_change(self):
        change = FSChange(
            change_type=ChangeType.MODIFIED,
            section_id="section_1",
            section_heading="Authentication",
            section_index=1,
            old_text="Use JWT tokens for auth.",
            new_text="Use OAuth2 for auth.",
        )
        assert change.change_type == ChangeType.MODIFIED
        assert change.old_text is not None
        assert change.new_text is not None

    def test_deleted_change(self):
        change = FSChange(
            change_type=ChangeType.DELETED,
            section_id="section_2",
            section_heading="Legacy Support",
            section_index=2,
            old_text="Support IE11.",
            new_text=None,
        )
        assert change.change_type == ChangeType.DELETED
        assert change.new_text is None

    def test_serialisation(self):
        change = FSChange(
            change_type=ChangeType.MODIFIED,
            section_id="section_0",
            section_heading="Auth",
            section_index=0,
            old_text="old",
            new_text="new",
        )
        data = change.model_dump()
        assert data["change_type"] == "MODIFIED"
        assert isinstance(data, dict)

    def test_change_type_enum_values(self):
        assert ChangeType.ADDED.value == "ADDED"
        assert ChangeType.MODIFIED.value == "MODIFIED"
        assert ChangeType.DELETED.value == "DELETED"


# ── Unit Tests: TaskImpact Model ────────────────────────


class TestTaskImpactModel:
    """Test the TaskImpact Pydantic model."""

    def test_invalidated_impact(self):
        impact = TaskImpact(
            task_id="task-001",
            task_title="Implement JWT auth",
            impact_type=ImpactType.INVALIDATED,
            reason="Auth method changed from JWT to OAuth2",
            change_section="Authentication",
        )
        assert impact.impact_type == ImpactType.INVALIDATED
        assert "OAuth2" in impact.reason

    def test_review_impact(self):
        impact = TaskImpact(
            task_id="task-002",
            task_title="Create dashboard",
            impact_type=ImpactType.REQUIRES_REVIEW,
            reason="Related to auth changes",
        )
        assert impact.impact_type == ImpactType.REQUIRES_REVIEW

    def test_unaffected_impact(self):
        impact = TaskImpact(
            task_id="task-003",
            task_title="Setup CI/CD",
            impact_type=ImpactType.UNAFFECTED,
            reason="Infrastructure not affected",
        )
        assert impact.impact_type == ImpactType.UNAFFECTED

    def test_impact_type_enum_values(self):
        assert ImpactType.INVALIDATED.value == "INVALIDATED"
        assert ImpactType.REQUIRES_REVIEW.value == "REQUIRES_REVIEW"
        assert ImpactType.UNAFFECTED.value == "UNAFFECTED"

    def test_serialisation(self):
        impact = TaskImpact(
            task_id="task-001",
            task_title="Test",
            impact_type=ImpactType.INVALIDATED,
            reason="reason",
        )
        data = impact.model_dump()
        assert data["impact_type"] == "INVALIDATED"
        assert data["task_id"] == "task-001"


# ── Unit Tests: ReworkEstimate Model ────────────────────


class TestReworkEstimateModel:
    """Test the ReworkEstimate Pydantic model."""

    def test_rework_with_data(self):
        estimate = ReworkEstimate(
            invalidated_count=3,
            review_count=2,
            unaffected_count=5,
            total_rework_days=8.5,
            affected_sections=["Auth", "Payments"],
            changes_summary="3 tasks invalidated. 2 tasks require review. Estimated total rework: 8.5 days.",
        )
        assert estimate.invalidated_count == 3
        assert estimate.total_rework_days == 8.5
        assert len(estimate.affected_sections) == 2

    def test_rework_defaults(self):
        estimate = ReworkEstimate()
        assert estimate.invalidated_count == 0
        assert estimate.review_count == 0
        assert estimate.total_rework_days == 0.0
        assert estimate.affected_sections == []

    def test_rework_serialisation(self):
        estimate = ReworkEstimate(
            invalidated_count=1,
            review_count=2,
            total_rework_days=3.5,
        )
        data = estimate.model_dump()
        assert data["invalidated_count"] == 1
        assert isinstance(data["total_rework_days"], float)


# ── Unit Tests: FSImpactState ───────────────────────────


class TestFSImpactState:
    """Test FSImpactState TypedDict includes all L7 fields."""

    def test_state_has_all_fields(self):
        state: FSImpactState = {
            "fs_id": "test-123",
            "version_id": "v-456",
            "old_sections": [],
            "new_sections": [],
            "tasks": [],
            "fs_changes": [],
            "task_impacts": [],
            "rework_estimate": {},
            "errors": [],
        }
        assert "fs_changes" in state
        assert "task_impacts" in state
        assert "rework_estimate" in state
        assert "version_id" in state

    def test_state_with_data(self):
        state: FSImpactState = {
            "fs_id": "test-789",
            "version_id": "v-012",
            "old_sections": [{"heading": "Auth", "content": "old text", "section_index": 0}],
            "new_sections": [{"heading": "Auth", "content": "new text", "section_index": 0}],
            "tasks": [{"task_id": "t1", "title": "Auth task", "effort": "MEDIUM"}],
            "fs_changes": [{"change_type": "MODIFIED", "section_id": "section_0"}],
            "task_impacts": [{"task_id": "t1", "impact_type": "INVALIDATED"}],
            "rework_estimate": {"invalidated_count": 1, "total_rework_days": 2.0},
            "errors": [],
        }
        assert len(state["fs_changes"]) == 1
        assert state["rework_estimate"]["invalidated_count"] == 1


# ── Unit Tests: Version Node (diff computation) ────────


class TestVersionNode:
    """Test version_node diff computation."""

    @pytest.mark.asyncio
    async def test_no_changes(self):
        """Identical sections should produce no changes."""
        from app.pipeline.nodes.version_node import version_node

        state: FSImpactState = {
            "fs_id": "test-no-change",
            "version_id": "v1",
            "old_sections": [
                {"heading": "Auth", "content": "JWT-based authentication.", "section_index": 0},
            ],
            "new_sections": [
                {"heading": "Auth", "content": "JWT-based authentication.", "section_index": 0},
            ],
            "tasks": [],
            "fs_changes": [],
            "task_impacts": [],
            "rework_estimate": {},
            "errors": [],
        }
        result = await version_node(state)
        assert len(result["fs_changes"]) == 0

    @pytest.mark.asyncio
    async def test_modified_section(self):
        """Changed content should produce a MODIFIED change."""
        from app.pipeline.nodes.version_node import version_node

        state: FSImpactState = {
            "fs_id": "test-modify",
            "version_id": "v2",
            "old_sections": [
                {"heading": "Auth", "content": "Use JWT tokens for authentication. All tokens expire after 24 hours.", "section_index": 0},
            ],
            "new_sections": [
                {"heading": "Auth", "content": "Use OAuth2 for authentication. Refresh tokens every 1 hour.", "section_index": 0},
            ],
            "tasks": [],
            "fs_changes": [],
            "task_impacts": [],
            "rework_estimate": {},
            "errors": [],
        }
        result = await version_node(state)
        assert len(result["fs_changes"]) == 1
        assert result["fs_changes"][0]["change_type"] == "MODIFIED"
        assert result["fs_changes"][0]["section_heading"] == "Auth"

    @pytest.mark.asyncio
    async def test_added_section(self):
        """New sections should produce ADDED changes."""
        from app.pipeline.nodes.version_node import version_node

        state: FSImpactState = {
            "fs_id": "test-add",
            "version_id": "v2",
            "old_sections": [
                {"heading": "Auth", "content": "JWT auth.", "section_index": 0},
            ],
            "new_sections": [
                {"heading": "Auth", "content": "JWT auth.", "section_index": 0},
                {"heading": "Payments", "content": "Stripe integration for payments.", "section_index": 1},
            ],
            "tasks": [],
            "fs_changes": [],
            "task_impacts": [],
            "rework_estimate": {},
            "errors": [],
        }
        result = await version_node(state)
        assert len(result["fs_changes"]) == 1
        assert result["fs_changes"][0]["change_type"] == "ADDED"
        assert result["fs_changes"][0]["section_heading"] == "Payments"

    @pytest.mark.asyncio
    async def test_deleted_section(self):
        """Removed sections should produce DELETED changes."""
        from app.pipeline.nodes.version_node import version_node

        state: FSImpactState = {
            "fs_id": "test-delete",
            "version_id": "v2",
            "old_sections": [
                {"heading": "Auth", "content": "JWT auth.", "section_index": 0},
                {"heading": "Legacy", "content": "IE11 support required.", "section_index": 1},
            ],
            "new_sections": [
                {"heading": "Auth", "content": "JWT auth.", "section_index": 0},
            ],
            "tasks": [],
            "fs_changes": [],
            "task_impacts": [],
            "rework_estimate": {},
            "errors": [],
        }
        result = await version_node(state)
        assert len(result["fs_changes"]) == 1
        assert result["fs_changes"][0]["change_type"] == "DELETED"
        assert result["fs_changes"][0]["section_heading"] == "Legacy"

    @pytest.mark.asyncio
    async def test_multiple_changes(self):
        """Multiple types of changes should be detected."""
        from app.pipeline.nodes.version_node import version_node

        state: FSImpactState = {
            "fs_id": "test-multi",
            "version_id": "v2",
            "old_sections": [
                {"heading": "Auth", "content": "JWT-based authentication with 24h token expiry. Support for MFA.", "section_index": 0},
                {"heading": "Legacy", "content": "IE11 support required for all pages.", "section_index": 1},
            ],
            "new_sections": [
                {"heading": "Auth", "content": "OAuth2-based authentication with 1h refresh. No MFA requirement initially.", "section_index": 0},
                {"heading": "Payments", "content": "Stripe for payment processing.", "section_index": 1},
            ],
            "tasks": [],
            "fs_changes": [],
            "task_impacts": [],
            "rework_estimate": {},
            "errors": [],
        }
        result = await version_node(state)
        change_types = {c["change_type"] for c in result["fs_changes"]}
        assert "MODIFIED" in change_types  # Auth changed
        assert "DELETED" in change_types  # Legacy removed
        assert "ADDED" in change_types  # Payments added

    @pytest.mark.asyncio
    async def test_empty_sections(self):
        """Empty section lists should produce no changes."""
        from app.pipeline.nodes.version_node import version_node

        state: FSImpactState = {
            "fs_id": "test-empty",
            "version_id": "v1",
            "old_sections": [],
            "new_sections": [],
            "tasks": [],
            "fs_changes": [],
            "task_impacts": [],
            "rework_estimate": {},
            "errors": [],
        }
        result = await version_node(state)
        assert len(result["fs_changes"]) == 0

    @pytest.mark.asyncio
    async def test_minor_change_ignored(self):
        """Very minor text changes (>95% similar) should be ignored."""
        from app.pipeline.nodes.version_node import version_node

        state: FSImpactState = {
            "fs_id": "test-minor",
            "version_id": "v2",
            "old_sections": [
                {"heading": "Auth", "content": "Use JWT for authentication", "section_index": 0},
            ],
            "new_sections": [
                {"heading": "Auth", "content": "Use JWT for authentication.", "section_index": 0},
            ],
            "tasks": [],
            "fs_changes": [],
            "task_impacts": [],
            "rework_estimate": {},
            "errors": [],
        }
        result = await version_node(state)
        # Very minor change (just a period) should be ignored
        assert len(result["fs_changes"]) == 0


# ── Unit Tests: Rework Node ─────────────────────────────


class TestReworkNode:
    """Test rework_node cost estimation."""

    @pytest.mark.asyncio
    async def test_basic_rework_computation(self):
        """Rework should sum effort for invalidated tasks."""
        from app.pipeline.nodes.rework_node import rework_node

        state: FSImpactState = {
            "fs_id": "test-rework",
            "version_id": "v2",
            "old_sections": [],
            "new_sections": [],
            "tasks": [
                {"task_id": "t1", "title": "Auth API", "effort": "HIGH"},
                {"task_id": "t2", "title": "Dashboard", "effort": "MEDIUM"},
                {"task_id": "t3", "title": "CI/CD", "effort": "LOW"},
            ],
            "fs_changes": [],
            "task_impacts": [
                {"task_id": "t1", "impact_type": "INVALIDATED", "reason": "Auth changed", "change_section": "Auth"},
                {"task_id": "t2", "impact_type": "REQUIRES_REVIEW", "reason": "May be affected", "change_section": "Auth"},
                {"task_id": "t3", "impact_type": "UNAFFECTED", "reason": "Not related"},
            ],
            "rework_estimate": {},
            "errors": [],
        }
        result = await rework_node(state)
        estimate = result["rework_estimate"]

        assert estimate["invalidated_count"] == 1
        assert estimate["review_count"] == 1
        assert estimate["unaffected_count"] == 1
        # HIGH = 5 days + MEDIUM * 0.25 = 0.5 days = 5.5 days
        assert estimate["total_rework_days"] == 5.5
        assert "Auth" in estimate["affected_sections"]

    @pytest.mark.asyncio
    async def test_no_impacts(self):
        """No impacts should produce zero rework."""
        from app.pipeline.nodes.rework_node import rework_node

        state: FSImpactState = {
            "fs_id": "test-no-impact",
            "version_id": "v2",
            "old_sections": [],
            "new_sections": [],
            "tasks": [],
            "fs_changes": [],
            "task_impacts": [],
            "rework_estimate": {},
            "errors": [],
        }
        result = await rework_node(state)
        assert result["rework_estimate"]["total_rework_days"] == 0.0
        assert result["rework_estimate"]["invalidated_count"] == 0

    @pytest.mark.asyncio
    async def test_all_invalidated(self):
        """All tasks invalidated should sum all effort."""
        from app.pipeline.nodes.rework_node import rework_node

        state: FSImpactState = {
            "fs_id": "test-all-invalid",
            "version_id": "v2",
            "old_sections": [],
            "new_sections": [],
            "tasks": [
                {"task_id": "t1", "title": "Task A", "effort": "LOW"},
                {"task_id": "t2", "title": "Task B", "effort": "LOW"},
            ],
            "fs_changes": [],
            "task_impacts": [
                {"task_id": "t1", "impact_type": "INVALIDATED", "reason": "R1", "change_section": "S1"},
                {"task_id": "t2", "impact_type": "INVALIDATED", "reason": "R2", "change_section": "S1"},
            ],
            "rework_estimate": {},
            "errors": [],
        }
        result = await rework_node(state)
        assert result["rework_estimate"]["invalidated_count"] == 2
        # 2 * LOW (0.5 days) = 1.0 day
        assert result["rework_estimate"]["total_rework_days"] == 1.0

    @pytest.mark.asyncio
    async def test_unknown_effort_defaults(self):
        """UNKNOWN effort should default to 2 days."""
        from app.pipeline.nodes.rework_node import rework_node

        state: FSImpactState = {
            "fs_id": "test-unknown",
            "version_id": "v2",
            "old_sections": [],
            "new_sections": [],
            "tasks": [
                {"task_id": "t1", "title": "Task A", "effort": "UNKNOWN"},
            ],
            "fs_changes": [],
            "task_impacts": [
                {"task_id": "t1", "impact_type": "INVALIDATED", "reason": "R1"},
            ],
            "rework_estimate": {},
            "errors": [],
        }
        result = await rework_node(state)
        assert result["rework_estimate"]["total_rework_days"] == 2.0


# ── Unit Tests: Diff Summary Generation ─────────────────


class TestDiffSummary:
    """Test human-readable diff summary generation."""

    def test_summary_with_changes(self):
        from app.pipeline.nodes.version_node import generate_diff_summary

        changes = [
            FSChange(change_type=ChangeType.ADDED, section_id="s1", section_heading="Payments"),
            FSChange(change_type=ChangeType.MODIFIED, section_id="s0", section_heading="Auth"),
            FSChange(change_type=ChangeType.DELETED, section_id="s2", section_heading="Legacy"),
        ]
        summary = generate_diff_summary(changes)
        assert "3 change(s)" in summary
        assert "ADDED: Payments" in summary
        assert "MODIFIED: Auth" in summary
        assert "DELETED: Legacy" in summary

    def test_summary_no_changes(self):
        from app.pipeline.nodes.version_node import generate_diff_summary

        summary = generate_diff_summary([])
        assert "No changes" in summary


# ── Unit Tests: Section Diff Function ───────────────────


class TestComputeSectionDiff:
    """Test the compute_section_diff function directly."""

    def test_heading_case_insensitive(self):
        """Matching should be case-insensitive."""
        from app.pipeline.nodes.version_node import compute_section_diff

        old = [{"heading": "AUTH", "content": "old text about auth stuff here.", "section_index": 0}]
        new = [{"heading": "auth", "content": "new text about auth stuff here that is different.", "section_index": 0}]
        changes = compute_section_diff(old, new)
        # Should match by heading and detect modification
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.MODIFIED

    def test_from_empty_to_sections(self):
        """Going from no sections to having sections should show all as ADDED."""
        from app.pipeline.nodes.version_node import compute_section_diff

        changes = compute_section_diff(
            [],
            [
                {"heading": "Auth", "content": "JWT auth system.", "section_index": 0},
                {"heading": "Data", "content": "PostgreSQL backend.", "section_index": 1},
            ],
        )
        assert len(changes) == 2
        assert all(c.change_type == ChangeType.ADDED for c in changes)


# ── Unit Tests: Impact Node (mocked LLM) ───────────────


class TestImpactNode:
    """Test impact_node with mocked LLM."""

    @pytest.mark.asyncio
    async def test_impact_node_no_changes(self):
        """No changes should produce no impacts."""
        from app.pipeline.nodes.impact_node import impact_node

        state: FSImpactState = {
            "fs_id": "test-no-changes",
            "version_id": "v2",
            "old_sections": [],
            "new_sections": [],
            "tasks": [{"task_id": "t1", "title": "Task", "effort": "MEDIUM"}],
            "fs_changes": [],
            "task_impacts": [],
            "rework_estimate": {},
            "errors": [],
        }
        result = await impact_node(state)
        assert result["task_impacts"] == []

    @pytest.mark.asyncio
    async def test_impact_node_no_tasks(self):
        """No tasks should produce no impacts."""
        from app.pipeline.nodes.impact_node import impact_node

        state: FSImpactState = {
            "fs_id": "test-no-tasks",
            "version_id": "v2",
            "old_sections": [],
            "new_sections": [],
            "tasks": [],
            "fs_changes": [{"change_type": "MODIFIED", "section_heading": "Auth"}],
            "task_impacts": [],
            "rework_estimate": {},
            "errors": [],
        }
        result = await impact_node(state)
        assert result["task_impacts"] == []

    @pytest.mark.asyncio
    async def test_impact_node_with_llm(self):
        """Impact node should call LLM and parse results."""
        mock_response = [
            {
                "task_id": "t1",
                "task_title": "Auth API",
                "impact_type": "INVALIDATED",
                "reason": "Auth changed",
            },
            {
                "task_id": "t2",
                "task_title": "Dashboard",
                "impact_type": "UNAFFECTED",
                "reason": "Not related",
            },
        ]

        with patch(
            "app.pipeline.nodes.impact_node.pipeline_call_llm_json",
            new=AsyncMock(return_value=mock_response),
        ):
            from app.pipeline.nodes.impact_node import impact_node

            state: FSImpactState = {
                "fs_id": "test-llm",
                "version_id": "v2",
                "old_sections": [],
                "new_sections": [],
                "tasks": [
                    {"task_id": "t1", "title": "Auth API", "effort": "HIGH", "section_heading": "Auth"},
                    {"task_id": "t2", "title": "Dashboard", "effort": "MEDIUM", "section_heading": "UI"},
                ],
                "fs_changes": [
                    {
                        "change_type": "MODIFIED",
                        "section_heading": "Auth",
                        "section_index": 0,
                        "old_text": "JWT auth",
                        "new_text": "OAuth2 auth",
                    },
                ],
                "task_impacts": [],
                "rework_estimate": {},
                "errors": [],
            }
            result = await impact_node(state)
            assert len(result["task_impacts"]) == 2
            invalidated = [i for i in result["task_impacts"] if i["impact_type"] == "INVALIDATED"]
            assert len(invalidated) == 1
            assert invalidated[0]["task_id"] == "t1"

    @pytest.mark.asyncio
    async def test_impact_node_llm_failure(self):
        """LLM failure should produce errors but not crash."""
        with patch(
            "app.pipeline.nodes.impact_node.pipeline_call_llm_json",
            new=AsyncMock(side_effect=Exception("LLM error")),
        ):
            from app.pipeline.nodes.impact_node import impact_node

            state: FSImpactState = {
                "fs_id": "test-fail",
                "version_id": "v2",
                "old_sections": [],
                "new_sections": [],
                "tasks": [{"task_id": "t1", "title": "Task", "effort": "MEDIUM"}],
                "fs_changes": [
                    {"change_type": "MODIFIED", "section_heading": "Auth", "old_text": "old", "new_text": "new"},
                ],
                "task_impacts": [],
                "rework_estimate": {},
                "errors": [],
            }
            result = await impact_node(state)
            assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_impact_node_worst_case_aggregation(self):
        """When multiple changes affect the same task, the worst impact should be kept."""
        call_count = 0

        async def mock_llm_json(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [
                    {"task_id": "t1", "task_title": "Shared Task", "impact_type": "REQUIRES_REVIEW", "reason": "Reason 1"},
                ]
            else:
                return [
                    {"task_id": "t1", "task_title": "Shared Task", "impact_type": "INVALIDATED", "reason": "Reason 2"},
                ]

        with patch(
            "app.pipeline.nodes.impact_node.pipeline_call_llm_json",
            new=AsyncMock(side_effect=mock_llm_json),
        ):
            from app.pipeline.nodes.impact_node import impact_node

            state: FSImpactState = {
                "fs_id": "test-worst",
                "version_id": "v2",
                "old_sections": [],
                "new_sections": [],
                "tasks": [{"task_id": "t1", "title": "Shared Task", "effort": "MEDIUM", "section_heading": "S1"}],
                "fs_changes": [
                    {"change_type": "MODIFIED", "section_heading": "Auth", "old_text": "old1", "new_text": "new1"},
                    {"change_type": "ADDED", "section_heading": "Payments", "old_text": None, "new_text": "new2"},
                ],
                "task_impacts": [],
                "rework_estimate": {},
                "errors": [],
            }
            result = await impact_node(state)
            assert len(result["task_impacts"]) == 1
            assert result["task_impacts"][0]["impact_type"] == "INVALIDATED"


# ── Unit Tests: Rework Computation Function ─────────────


class TestComputeReworkEstimate:
    """Test the compute_rework_estimate pure function."""

    def test_effort_map_values(self):
        from app.pipeline.nodes.rework_node import EFFORT_MAP

        assert EFFORT_MAP["LOW"] == 0.5
        assert EFFORT_MAP["MEDIUM"] == 2.0
        assert EFFORT_MAP["HIGH"] == 5.0
        assert EFFORT_MAP["UNKNOWN"] == 2.0

    def test_review_multiplier(self):
        from app.pipeline.nodes.rework_node import REVIEW_EFFORT_MULTIPLIER

        assert REVIEW_EFFORT_MULTIPLIER == 0.25

    def test_compute_mixed_impacts(self):
        from app.pipeline.nodes.rework_node import compute_rework_estimate

        impacts = [
            {"task_id": "t1", "impact_type": "INVALIDATED", "change_section": "Auth"},
            {"task_id": "t2", "impact_type": "REQUIRES_REVIEW", "change_section": "Auth"},
            {"task_id": "t3", "impact_type": "UNAFFECTED"},
        ]
        tasks = [
            {"task_id": "t1", "title": "Auth API", "effort": "MEDIUM"},
            {"task_id": "t2", "title": "Dashboard", "effort": "LOW"},
            {"task_id": "t3", "title": "CI/CD", "effort": "HIGH"},
        ]
        estimate = compute_rework_estimate(impacts, tasks)
        assert estimate.invalidated_count == 1
        assert estimate.review_count == 1
        assert estimate.unaffected_count == 1
        # MEDIUM(2.0) + LOW(0.5) * 0.25 = 2.125 → rounded to 2.1
        assert estimate.total_rework_days == 2.1
        assert "Auth" in estimate.affected_sections

    def test_compute_empty(self):
        from app.pipeline.nodes.rework_node import compute_rework_estimate

        estimate = compute_rework_estimate([], [])
        assert estimate.invalidated_count == 0
        assert estimate.total_rework_days == 0.0
        assert "0 days" in estimate.changes_summary


# ── Integration Tests: Pipeline Graph ──────────────────


class TestImpactPipelineGraph:
    """Test that the impact pipeline graph is correctly built."""

    def test_impact_graph_builds(self):
        """The impact graph should compile without errors."""
        import app.pipeline.graph as graph_mod
        graph_mod._compiled_impact_graph = None

        with patch(
            "app.pipeline.nodes.impact_node.pipeline_call_llm_json",
            new=AsyncMock(return_value=[]),
        ):
            graph = graph_mod.build_impact_graph()
            assert graph is not None

        graph_mod._compiled_impact_graph = None

    def test_impact_graph_singleton(self):
        """get_compiled_impact_graph should return a singleton."""
        import app.pipeline.graph as graph_mod
        graph_mod._compiled_impact_graph = None

        with patch(
            "app.pipeline.nodes.impact_node.pipeline_call_llm_json",
            new=AsyncMock(return_value=[]),
        ):
            g1 = graph_mod.get_compiled_impact_graph()
            g2 = graph_mod.get_compiled_impact_graph()
            assert g1 is g2

        graph_mod._compiled_impact_graph = None

    @pytest.mark.asyncio
    async def test_impact_pipeline_end_to_end(self):
        """Full impact pipeline should work with mocked LLM."""
        import app.pipeline.graph as graph_mod
        graph_mod._compiled_impact_graph = None

        mock_llm_response = [
            {"task_id": "t1", "task_title": "Auth Task", "impact_type": "INVALIDATED", "reason": "Auth changed"},
        ]
        with patch(
            "app.pipeline.nodes.impact_node.pipeline_call_llm_json",
            new=AsyncMock(return_value=mock_llm_response),
        ):
            result = await graph_mod.run_impact_pipeline(
                fs_id="test-e2e",
                version_id="v2",
                old_sections=[{"heading": "Auth", "content": "JWT auth with 24h expiry.", "section_index": 0}],
                new_sections=[{"heading": "Auth", "content": "OAuth2 auth with 1h refresh.", "section_index": 0}],
                tasks=[{"task_id": "t1", "title": "Auth Task", "effort": "HIGH", "section_heading": "Auth"}],
            )

            assert len(result["fs_changes"]) == 1
            assert result["fs_changes"][0]["change_type"] == "MODIFIED"
            assert len(result["task_impacts"]) >= 1
            assert "rework_estimate" in result
            assert result["rework_estimate"]["invalidated_count"] >= 0

        graph_mod._compiled_impact_graph = None


# ── Integration Tests: Impact API Endpoints ─────────────


class TestImpactAPI:
    """Test impact analysis API endpoints."""

    @pytest.mark.asyncio
    async def test_versions_empty(self, client):
        """Versions should be empty for a new document."""
        content = b"Test document for impact analysis section one."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("impact_test.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]

        response = await client.get(f"/api/fs/{doc_id}/versions")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 0
        assert data["versions"] == []

    @pytest.mark.asyncio
    async def test_versions_not_found(self, client):
        """Versions for non-existent document should 404."""
        fake_id = "00000000-0000-0000-0000-000000000099"
        response = await client.get(f"/api/fs/{fake_id}/versions")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_impact_version_not_found(self, client):
        """Impact for non-existent version should 404."""
        content = b"Test document for impact version check."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("impact_v_test.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]
        fake_version = "00000000-0000-0000-0000-000000000099"

        response = await client.get(f"/api/fs/{doc_id}/impact/{fake_version}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rework_version_not_found(self, client):
        """Rework for non-existent version should 404."""
        content = b"Test document for rework version check."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("rework_v_test.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]
        fake_version = "00000000-0000-0000-0000-000000000099"

        response = await client.get(f"/api/fs/{doc_id}/impact/{fake_version}/rework")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_diff_version_not_found(self, client):
        """Diff for non-existent version should 404."""
        content = b"Test document for diff version check."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("diff_v_test.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]
        fake_version = "00000000-0000-0000-0000-000000000099"

        response = await client.get(f"/api/fs/{doc_id}/versions/{fake_version}/diff")
        assert response.status_code == 404


# ── Unit Tests: chunk_text_into_sections ─────────────────


class TestChunkTextIntoSections:
    """Test the chunk_text_into_sections helper."""

    def test_empty_text(self):
        from app.parsers.chunker import chunk_text_into_sections

        result = chunk_text_into_sections("")
        assert result == []

    def test_none_text(self):
        from app.parsers.chunker import chunk_text_into_sections

        result = chunk_text_into_sections(None)
        assert result == []

    def test_text_without_headings(self):
        from app.parsers.chunker import chunk_text_into_sections

        result = chunk_text_into_sections("This is just plain text without any headings.")
        assert len(result) == 1
        assert result[0]["heading"] == "Document"

    def test_markdown_headings(self):
        from app.parsers.chunker import chunk_text_into_sections

        text = """# Introduction
This is the intro section.

## Authentication
Use JWT tokens for authentication.

## Data Storage
PostgreSQL for the backend."""

        result = chunk_text_into_sections(text)
        assert len(result) >= 2
        headings = [s["heading"] for s in result]
        assert any("Introduction" in h for h in headings)

    def test_numbered_headings(self):
        from app.parsers.chunker import chunk_text_into_sections

        text = """1. Overview
This system handles user management.

2. Authentication
JWT based auth with refresh tokens.

3. Data Model
Users, roles, and permissions tables."""

        result = chunk_text_into_sections(text)
        assert len(result) >= 2
