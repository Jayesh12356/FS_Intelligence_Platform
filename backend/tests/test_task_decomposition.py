"""Tests for L5 task decomposition pipeline.

Tests:
- Pipeline state L5 models (FSTask, TraceabilityEntry, EffortLevel)
- Task decomposition node (mocked LLM)
- Dependency node (cycle detection, topological sort, parallel detection)
- Traceability node
- Full L5 pipeline flow
- L5 API endpoints (tasks, dependency-graph, traceability, task update)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.nodes.dependency_node import (
    detect_cycle,
    find_parallel_tasks,
    topological_sort,
)
from app.pipeline.state import (
    EffortLevel,
    FSAnalysisState,
    FSTask,
    TraceabilityEntry,
)

# ── Unit Tests: L5 State Models ─────────────────────────


class TestL5StateModels:
    """Test L5 pipeline state models."""

    def test_fstask_creation(self):
        task = FSTask(
            task_id="t1",
            title="Create user table",
            description="Create PostgreSQL users table with id, email, name.",
            section_index=0,
            section_heading="User Management",
            depends_on=[],
            acceptance_criteria=["Table exists", "Migrations run"],
            effort=EffortLevel.LOW,
            tags=["backend", "db"],
            order=0,
            can_parallel=False,
        )
        assert task.effort == EffortLevel.LOW
        assert len(task.tags) == 2
        assert task.task_id == "t1"

    def test_fstask_with_dependencies(self):
        task = FSTask(
            task_id="t2",
            title="Create user API",
            description="Build REST API for users.",
            section_index=0,
            section_heading="User Management",
            depends_on=["t1"],
            acceptance_criteria=["GET /users returns list"],
            effort=EffortLevel.MEDIUM,
            tags=["backend", "api"],
            order=1,
            can_parallel=False,
        )
        assert task.depends_on == ["t1"]
        assert task.order == 1

    def test_traceability_entry(self):
        entry = TraceabilityEntry(
            task_id="t1",
            task_title="Create user table",
            section_index=0,
            section_heading="User Management",
        )
        assert entry.section_index == 0

    def test_effort_enum_values(self):
        assert EffortLevel.LOW == "LOW"
        assert EffortLevel.HIGH == "HIGH"
        assert EffortLevel.UNKNOWN == "UNKNOWN"

    def test_analysis_state_l5_fields(self):
        state: FSAnalysisState = {
            "fs_id": "test-l5",
            "parsed_sections": [],
            "ambiguities": [],
            "contradictions": [],
            "edge_cases": [],
            "quality_score": {},
            "compliance_tags": [],
            "tasks": [],
            "traceability_matrix": [],
            "errors": [],
        }
        assert "tasks" in state
        assert "traceability_matrix" in state


# ── Unit Tests: Dependency Utilities ────────────────────


class TestDependencyUtilities:
    """Test cycle detection, topological sort, and parallel detection."""

    def test_no_cycle_simple(self):
        graph = {"a": ["b"], "b": [], "c": ["b"]}
        assert detect_cycle(graph) is False

    def test_cycle_detected(self):
        graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
        assert detect_cycle(graph) is True

    def test_self_cycle(self):
        graph = {"a": ["a"]}
        assert detect_cycle(graph) is True

    def test_no_cycle_empty(self):
        graph = {"a": [], "b": []}
        assert detect_cycle(graph) is False

    def test_topological_sort_simple(self):
        graph = {"a": [], "b": ["a"], "c": ["b"]}
        order = topological_sort(graph, {"a", "b", "c"})
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_topological_sort_independent(self):
        graph = {"a": [], "b": [], "c": []}
        order = topological_sort(graph, {"a", "b", "c"})
        assert len(order) == 3

    def test_find_parallel_tasks(self):
        tasks = [
            {"task_id": "t1", "depends_on": []},
            {"task_id": "t2", "depends_on": []},
            {"task_id": "t3", "depends_on": ["t1", "t2"]},
        ]
        graph = {"t1": [], "t2": [], "t3": ["t1", "t2"]}
        parallel = find_parallel_tasks(tasks, graph)
        # t1 and t2 are at the same depth (0) → parallel
        assert "t1" in parallel
        assert "t2" in parallel
        assert "t3" not in parallel

    def test_find_parallel_no_parallel(self):
        tasks = [
            {"task_id": "t1", "depends_on": []},
            {"task_id": "t2", "depends_on": ["t1"]},
        ]
        graph = {"t1": [], "t2": ["t1"]}
        parallel = find_parallel_tasks(tasks, graph)
        assert len(parallel) == 0


# ── Unit Tests: Task Decomposition Node ─────────────────


class TestTaskDecompositionNode:
    """Test task decomposition with mocked LLM."""

    @pytest.mark.asyncio
    async def test_decompose_section_returns_tasks(self):
        mock_response = [
            {
                "title": "Create users table",
                "description": "Build PostgreSQL users table.",
                "acceptance_criteria": ["Table has id, email columns", "Migration runs"],
                "effort": "LOW",
                "tags": ["backend", "db"],
            },
            {
                "title": "Create user registration endpoint",
                "description": "POST /api/users/register",
                "acceptance_criteria": ["Returns 201", "Validates email"],
                "effort": "MEDIUM",
                "tags": ["backend", "api", "auth"],
            },
        ]

        _llm_mock = AsyncMock(return_value=mock_response)
        with patch(
            "app.pipeline.nodes.task_node.pipeline_call_llm_json",
            new=_llm_mock,
        ):
            from app.pipeline.nodes.task_node import decompose_section_into_tasks

            tasks = await decompose_section_into_tasks(
                heading="User Management",
                content="The system shall allow users to register with email and password. User data is stored in PostgreSQL.",
                section_index=0,
            )

            assert len(tasks) == 2
            assert tasks[0].effort == EffortLevel.LOW
            assert "db" in tasks[0].tags
            assert len(tasks[1].acceptance_criteria) == 2

    @pytest.mark.asyncio
    async def test_task_node_full_flow(self):
        mock_response = [
            {
                "title": "Implement login",
                "description": "Build login endpoint.",
                "acceptance_criteria": ["Returns JWT token"],
                "effort": "MEDIUM",
                "tags": ["backend", "auth"],
            },
        ]

        _llm_mock = AsyncMock(return_value=mock_response)
        with patch(
            "app.pipeline.nodes.task_node.pipeline_call_llm_json",
            new=_llm_mock,
        ):
            from app.pipeline.nodes.task_node import task_decomposition_node

            state: FSAnalysisState = {
                "fs_id": "test-td1",
                "parsed_sections": [
                    {
                        "heading": "Auth",
                        "content": "Users authenticate via SSO login with enterprise credentials.",
                        "section_index": 0,
                    },
                ],
                "ambiguities": [],
                "tasks": [],
                "errors": [],
            }

            result = await task_decomposition_node(state)
            assert len(result["tasks"]) == 1
            assert result["tasks"][0]["title"] == "Implement login"

    @pytest.mark.asyncio
    async def test_task_node_does_not_skip_high_ambiguity_sections(self):
        """Even with unresolved HIGH ambiguities, we still attempt task generation."""
        _llm_mock = AsyncMock(return_value=[])
        with patch(
            "app.pipeline.nodes.task_node.pipeline_call_llm_json",
            new=_llm_mock,
        ):
            from app.pipeline.nodes.task_node import task_decomposition_node

            state: FSAnalysisState = {
                "fs_id": "test-skip",
                "parsed_sections": [
                    {
                        "heading": "Auth",
                        "content": "Users authenticate via SSO login with enterprise credentials.",
                        "section_index": 0,
                    },
                ],
                "ambiguities": [
                    {"section_index": 0, "severity": "HIGH", "resolved": False},
                ],
                "tasks": [],
                "errors": [],
            }

            result = await task_decomposition_node(state)
            assert len(result["tasks"]) == 0
            assert _llm_mock.call_count >= 1

    @pytest.mark.asyncio
    async def test_task_node_handles_error(self):
        _llm_mock = AsyncMock(side_effect=Exception("LLM down"))
        with patch(
            "app.pipeline.nodes.task_node.pipeline_call_llm_json",
            new=_llm_mock,
        ):
            from app.pipeline.nodes.task_node import task_decomposition_node

            state: FSAnalysisState = {
                "fs_id": "test-err",
                "parsed_sections": [
                    {
                        "heading": "X",
                        "content": "A section with enough content to decompose into tasks.",
                        "section_index": 0,
                    },
                ],
                "ambiguities": [],
                "tasks": [],
                "errors": [],
            }

            result = await task_decomposition_node(state)
            assert len(result["tasks"]) == 0


# ── Unit Tests: Dependency Node ─────────────────────────


class TestDependencyNode:
    """Test dependency node with mocked LLM."""

    @pytest.mark.asyncio
    async def test_dependency_node_infers_deps(self):
        t1_id = "task-1111"
        t2_id = "task-2222"

        mock_response = {
            t1_id: [],
            t2_id: [t1_id],
        }

        _llm_mock = AsyncMock(return_value=mock_response)
        with patch(
            "app.pipeline.nodes.dependency_node.pipeline_call_llm_json",
            new=_llm_mock,
        ):
            from app.pipeline.nodes.dependency_node import dependency_node

            state: FSAnalysisState = {
                "fs_id": "test-dep",
                "parsed_sections": [],
                "tasks": [
                    {
                        "task_id": t1_id,
                        "title": "Create DB",
                        "section_index": 0,
                        "section_heading": "Data",
                        "tags": ["db"],
                        "description": "Create database",
                        "depends_on": [],
                        "order": 0,
                        "can_parallel": False,
                    },
                    {
                        "task_id": t2_id,
                        "title": "Create API",
                        "section_index": 0,
                        "section_heading": "Data",
                        "tags": ["api"],
                        "description": "Create API endpoint",
                        "depends_on": [],
                        "order": 0,
                        "can_parallel": False,
                    },
                ],
                "errors": [],
            }

            result = await dependency_node(state)
            tasks = result["tasks"]

            # t1 should come before t2
            t1 = next(t for t in tasks if t["task_id"] == t1_id)
            t2 = next(t for t in tasks if t["task_id"] == t2_id)
            assert t1["order"] < t2["order"]
            assert t2["depends_on"] == [t1_id]

    @pytest.mark.asyncio
    async def test_dependency_node_handles_cycle(self):
        """Cycles should be detected and dependencies cleared."""
        t1_id = "task-c1"
        t2_id = "task-c2"

        mock_response = {
            t1_id: [t2_id],
            t2_id: [t1_id],
        }

        _llm_mock = AsyncMock(return_value=mock_response)
        with patch(
            "app.pipeline.nodes.dependency_node.pipeline_call_llm_json",
            new=_llm_mock,
        ):
            from app.pipeline.nodes.dependency_node import dependency_node

            state: FSAnalysisState = {
                "fs_id": "test-cycle",
                "parsed_sections": [],
                "tasks": [
                    {
                        "task_id": t1_id,
                        "title": "Task A",
                        "section_index": 0,
                        "section_heading": "S",
                        "tags": [],
                        "description": "A",
                        "depends_on": [],
                        "order": 0,
                        "can_parallel": False,
                    },
                    {
                        "task_id": t2_id,
                        "title": "Task B",
                        "section_index": 0,
                        "section_heading": "S",
                        "tags": [],
                        "description": "B",
                        "depends_on": [],
                        "order": 0,
                        "can_parallel": False,
                    },
                ],
                "errors": [],
            }

            result = await dependency_node(state)
            # All dependencies should be cleared due to cycle
            for t in result["tasks"]:
                assert t["depends_on"] == []

    @pytest.mark.asyncio
    async def test_dependency_node_empty_tasks(self):
        from app.pipeline.nodes.dependency_node import dependency_node

        state: FSAnalysisState = {
            "fs_id": "test-empty",
            "parsed_sections": [],
            "tasks": [],
            "errors": [],
        }

        result = await dependency_node(state)
        assert result["tasks"] == []


# ── Unit Tests: Traceability Node ───────────────────────


class TestTraceabilityNode:
    """Test traceability matrix building."""

    @pytest.mark.asyncio
    async def test_traceability_builds_matrix(self):
        from app.pipeline.nodes.traceability_node import traceability_node

        state: FSAnalysisState = {
            "fs_id": "test-trace",
            "parsed_sections": [
                {"heading": "Auth", "content": "Login system.", "section_index": 0},
                {"heading": "Data", "content": "Database schema.", "section_index": 1},
            ],
            "tasks": [
                {"task_id": "t1", "title": "Implement login", "section_index": 0, "section_heading": "Auth"},
                {"task_id": "t2", "title": "Create schema", "section_index": 1, "section_heading": "Data"},
                {"task_id": "t3", "title": "Auth middleware", "section_index": 0, "section_heading": "Auth"},
            ],
            "errors": [],
        }

        result = await traceability_node(state)
        matrix = result["traceability_matrix"]
        assert len(matrix) == 3
        # Section 0 should have 2 entries, section 1 should have 1
        sec0 = [e for e in matrix if e["section_index"] == 0]
        sec1 = [e for e in matrix if e["section_index"] == 1]
        assert len(sec0) == 2
        assert len(sec1) == 1

    @pytest.mark.asyncio
    async def test_traceability_empty_tasks(self):
        from app.pipeline.nodes.traceability_node import traceability_node

        state: FSAnalysisState = {
            "fs_id": "test-empty",
            "parsed_sections": [
                {"heading": "X", "content": "Content.", "section_index": 0},
            ],
            "tasks": [],
            "errors": [],
        }

        result = await traceability_node(state)
        assert result["traceability_matrix"] == []


# ── Integration Tests: Full L5 Pipeline ─────────────────


class TestL5Pipeline:
    """Test the full L5 pipeline with mocked LLM."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_l5_nodes(self):
        """Full 8-node pipeline with mocked LLM."""
        ambiguity_response = []
        contradiction_response = []
        edge_case_response = []
        compliance_response = []
        task_response = [
            {
                "title": "Create auth endpoint",
                "description": "Build POST /api/auth",
                "acceptance_criteria": ["Returns JWT"],
                "effort": "MEDIUM",
                "tags": ["backend", "auth"],
            },
        ]
        dependency_response = {}

        call_count = 0

        async def mock_call_json(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            system = str(kwargs.get("system", ""))

            if "ambig" in system.lower():
                return ambiguity_response
            elif "contradiction" in system.lower():
                return contradiction_response
            elif "edge case" in system.lower():
                return edge_case_response
            elif "compliance" in system.lower():
                return compliance_response
            elif "decompos" in system.lower():
                return task_response
            elif "dependenc" in system.lower():
                return dependency_response
            return []

        patches = [
            patch("app.pipeline.nodes.ambiguity_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.contradiction_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.edge_case_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.quality_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.task_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.dependency_node.pipeline_call_llm_json", new_callable=AsyncMock),
        ]

        started_patches = [p.start() for p in patches]
        for mp in started_patches:
            mp.side_effect = mock_call_json

        try:
            import app.pipeline.graph as graph_mod

            graph_mod._compiled_graph = None

            from app.pipeline.graph import run_analysis_pipeline

            result = await run_analysis_pipeline(
                fs_id="test-l5-pipeline",
                sections=[
                    {
                        "heading": "Authentication",
                        "content": "The system shall provide SSO-based authentication with JWT tokens for session management.",
                        "section_index": 0,
                    },
                ],
            )

            assert "tasks" in result
            assert "traceability_matrix" in result
            assert len(result["tasks"]) >= 1
            assert len(result["traceability_matrix"]) >= 1

            # Verify task structure
            task = result["tasks"][0]
            assert "task_id" in task
            assert "title" in task
            assert "acceptance_criteria" in task
            assert "effort" in task
            assert "tags" in task

            graph_mod._compiled_graph = None
        finally:
            for p in patches:
                p.stop()


# ── Integration Tests: L5 API Endpoints ─────────────────


class TestL5API:
    """Test L5 task-related endpoints via HTTP client."""

    @pytest.mark.asyncio
    async def test_tasks_endpoint_empty(self, client):
        """List tasks for a document with none."""
        content = b"Some content for test."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("test.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]

        response = await client.get(f"/api/fs/{doc_id}/tasks")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["tasks"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_dependency_graph_empty(self, client):
        """Dependency graph for a doc with no tasks."""
        content = b"Some content for test."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("test.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]

        response = await client.get(f"/api/fs/{doc_id}/tasks/dependency-graph")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["nodes"] == []
        assert data["edges"] == []

    @pytest.mark.asyncio
    async def test_traceability_404(self, client):
        """Traceability for non-existent doc returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000099"
        response = await client.get(f"/api/fs/{fake_id}/traceability")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_task_detail_404(self, client):
        """Getting non-existent task returns 404."""
        fake_doc = "00000000-0000-0000-0000-000000000001"
        response = await client.get(f"/api/fs/{fake_doc}/tasks/nonexistent-task-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_task_update_404(self, client):
        """Updating non-existent task returns 404."""
        fake_doc = "00000000-0000-0000-0000-000000000001"
        response = await client.patch(
            f"/api/fs/{fake_doc}/tasks/nonexistent-task-id",
            json={"title": "New title"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_full_l5_flow(self, client):
        """Upload → parse → analyze (mocked) → list tasks → get task → update task → dependency graph → traceability."""
        task_response = [
            {
                "title": "Build login API",
                "description": "Create POST /api/auth/login endpoint",
                "acceptance_criteria": ["Returns 200 with JWT", "Validates credentials"],
                "effort": "MEDIUM",
                "tags": ["backend", "auth", "api"],
            },
        ]

        async def mock_call_json(*args, **kwargs):
            system = str(kwargs.get("system", ""))
            if "decompos" in system.lower():
                return task_response
            elif "dependenc" in system.lower():
                return {}
            return []

        # Upload
        content = b"""1. AUTHENTICATION
The system should provide SSO-based login with JWT tokens.
Users authenticate using enterprise directory credentials.
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
            patch("app.pipeline.nodes.ambiguity_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.contradiction_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.edge_case_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.quality_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.task_node.pipeline_call_llm_json", new_callable=AsyncMock),
            patch("app.pipeline.nodes.dependency_node.pipeline_call_llm_json", new_callable=AsyncMock),
        ]

        started_patches = [p.start() for p in patches]
        for mp in started_patches:
            mp.side_effect = mock_call_json

        try:
            import app.pipeline.graph as graph_mod

            graph_mod._compiled_graph = None

            # Analyze
            response = await client.post(f"/api/fs/{doc_id}/analyze")
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["status"] == "COMPLETE"
            assert data["tasks_count"] >= 1

            # List tasks
            response = await client.get(f"/api/fs/{doc_id}/tasks")
            assert response.status_code == 200
            tasks_data = response.json()["data"]
            assert tasks_data["total"] >= 1
            task = tasks_data["tasks"][0]
            task_id = task["task_id"]

            # Get task detail
            response = await client.get(f"/api/fs/{doc_id}/tasks/{task_id}")
            assert response.status_code == 200
            detail = response.json()["data"]
            assert detail["title"] == "Build login API"
            assert detail["effort"] == "MEDIUM"

            # Update task
            response = await client.patch(
                f"/api/fs/{doc_id}/tasks/{task_id}",
                json={"title": "Build SSO login API", "effort": "HIGH"},
            )
            assert response.status_code == 200
            updated = response.json()["data"]
            assert updated["title"] == "Build SSO login API"
            assert updated["effort"] == "HIGH"

            # Dependency graph
            response = await client.get(f"/api/fs/{doc_id}/tasks/dependency-graph")
            assert response.status_code == 200
            graph = response.json()["data"]
            assert len(graph["nodes"]) >= 1
            assert task_id in graph["nodes"]

            # Traceability
            response = await client.get(f"/api/fs/{doc_id}/traceability")
            assert response.status_code == 200
            trace = response.json()["data"]
            assert trace["total_tasks"] >= 1

            graph_mod._compiled_graph = None
        finally:
            for p in patches:
                p.stop()
