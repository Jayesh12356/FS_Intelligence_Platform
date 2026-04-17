"""L10 — Integrations + Polish — Test Suite.

Covers:
  - JiraClient (epic + story creation, simulated mode)
  - ConfluenceClient (page creation, content building, simulated mode)
  - TestCaseDB model + TestType enum
  - testcase_node pipeline node
  - export_router endpoints (JIRA, Confluence, PDF, DOCX, test-cases, CSV)
  - Config settings (JIRA/Confluence fields)
  - Report generation (PDF/DOCX fallback text reports)
  - Pipeline integration (testcase_node in graph)
"""

import csv
import io
import json
import pytest
import uuid

from unittest.mock import patch, AsyncMock, MagicMock

import httpx
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.db.base import Base, engine, get_db
from app.db.models import (
    FSDocument,
    FSDocumentStatus,
    FSTaskDB,
    EffortLevel,
    TestCaseDB,
    TestType,
    TraceabilityEntryDB,
    AmbiguityFlagDB,
    AmbiguitySeverity,
)

# ── Fixtures ───────────────────────────────────────────

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

TEST_DB_URL = "sqlite+aiosqlite:///./test_l10.db"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session():
    async with TestSession() as session:
        yield session


@pytest.fixture
async def client(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def sample_doc(db_session):
    doc = FSDocument(
        filename="test_l10.txt",
        status=FSDocumentStatus.COMPLETE,
        original_text="Test content",
        parsed_text="# Section 1\nTest requirement\n\n# Section 2\nAnother requirement",
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
async def doc_with_tasks(db_session, sample_doc):
    tasks = [
        FSTaskDB(
            fs_id=sample_doc.id,
            task_id="T-001",
            title="Implement login",
            description="Create the login functionality",
            section_index=0,
            section_heading="Section 1",
            effort=EffortLevel.MEDIUM,
            acceptance_criteria=["User can enter credentials", "Invalid login shows error"],
            tags=["auth"],
            order=0,
            can_parallel=False,
        ),
        FSTaskDB(
            fs_id=sample_doc.id,
            task_id="T-002",
            title="Implement dashboard",
            description="Create the dashboard page",
            section_index=1,
            section_heading="Section 2",
            effort=EffortLevel.HIGH,
            acceptance_criteria=["Dashboard loads in < 2s"],
            tags=["ui"],
            order=1,
            can_parallel=True,
        ),
    ]
    for t in tasks:
        db_session.add(t)
    await db_session.commit()
    return sample_doc


@pytest.fixture
async def doc_with_test_cases(db_session, doc_with_tasks):
    test_cases = [
        TestCaseDB(
            fs_id=doc_with_tasks.id,
            task_id="T-001",
            title="Test valid login",
            preconditions="User exists in system",
            steps=["Enter valid credentials", "Click login"],
            expected_result="User is logged in successfully",
            test_type=TestType.E2E,
            section_index=0,
            section_heading="Section 1",
        ),
        TestCaseDB(
            fs_id=doc_with_tasks.id,
            task_id="T-001",
            title="Test invalid login",
            preconditions="User exists in system",
            steps=["Enter wrong password", "Click login"],
            expected_result="Error message displayed",
            test_type=TestType.E2E,
            section_index=0,
            section_heading="Section 1",
        ),
        TestCaseDB(
            fs_id=doc_with_tasks.id,
            task_id="T-002",
            title="Test dashboard load time",
            preconditions="User is authenticated",
            steps=["Navigate to dashboard"],
            expected_result="Dashboard loads in under 2 seconds",
            test_type=TestType.INTEGRATION,
            section_index=1,
            section_heading="Section 2",
        ),
    ]
    for tc in test_cases:
        db_session.add(tc)
    await db_session.commit()
    return doc_with_tasks


# ── Config Tests ───────────────────────────────────────


class TestConfig:
    """Test L10 config settings."""

    def test_jira_settings_exist(self):
        from app.config import Settings
        s = Settings()
        assert hasattr(s, "JIRA_URL")
        assert hasattr(s, "JIRA_EMAIL")
        assert hasattr(s, "JIRA_API_TOKEN")
        assert hasattr(s, "JIRA_PROJECT_KEY")

    def test_confluence_settings_exist(self):
        from app.config import Settings
        s = Settings()
        assert hasattr(s, "CONFLUENCE_URL")
        assert hasattr(s, "CONFLUENCE_EMAIL")
        assert hasattr(s, "CONFLUENCE_API_TOKEN")
        assert hasattr(s, "CONFLUENCE_SPACE_KEY")

    def test_jira_defaults(self):
        from app.config import Settings
        s = Settings()
        assert s.JIRA_PROJECT_KEY == "FSP"

    def test_confluence_defaults(self):
        from app.config import Settings
        s = Settings()
        assert s.CONFLUENCE_SPACE_KEY == "FSP"


# ── DB Model Tests ─────────────────────────────────────


class TestDBModels:
    """Test L10 database models."""

    @pytest.mark.asyncio
    async def test_create_test_case(self, db_session, sample_doc):
        tc = TestCaseDB(
            fs_id=sample_doc.id,
            task_id="T-001",
            title="Verify login works",
            preconditions="User exists",
            steps=["Open app", "Enter credentials", "Click login"],
            expected_result="User is logged in",
            test_type=TestType.E2E,
            section_index=0,
            section_heading="Authentication",
        )
        db_session.add(tc)
        await db_session.commit()
        await db_session.refresh(tc)

        assert tc.id is not None
        assert tc.task_id == "T-001"
        assert tc.test_type == TestType.E2E
        assert len(tc.steps) == 3

    @pytest.mark.asyncio
    async def test_test_type_enum(self):
        assert TestType.UNIT == "UNIT"
        assert TestType.INTEGRATION == "INTEGRATION"
        assert TestType.E2E == "E2E"
        assert TestType.ACCEPTANCE == "ACCEPTANCE"

    @pytest.mark.asyncio
    async def test_test_case_relationship(self, db_session, doc_with_test_cases):
        from sqlalchemy import select
        result = await db_session.execute(
            select(TestCaseDB).where(TestCaseDB.fs_id == doc_with_test_cases.id)
        )
        test_cases = result.scalars().all()
        assert len(test_cases) == 3

    @pytest.mark.asyncio
    async def test_test_case_cascade_delete(self, db_session, doc_with_test_cases):
        from sqlalchemy import select
        await db_session.delete(doc_with_test_cases)
        await db_session.commit()
        result = await db_session.execute(
            select(TestCaseDB).where(TestCaseDB.fs_id == doc_with_test_cases.id)
        )
        assert len(result.scalars().all()) == 0


# ── JiraClient Tests ───────────────────────────────────


class TestJiraClient:
    """Test JIRA integration client."""

    @pytest.mark.asyncio
    async def test_simulated_epic(self):
        from app.integrations.jira import JiraClient
        client = JiraClient()
        result = await client.create_epic("Test FS", "Test description")
        assert "key" in result
        assert result["simulated"] is True

    @pytest.mark.asyncio
    async def test_simulated_story(self):
        from app.integrations.jira import JiraClient
        client = JiraClient()
        task = {
            "task_id": "T-001",
            "title": "Implement feature",
            "description": "Feature description",
            "acceptance_criteria": ["AC1", "AC2"],
            "effort": "MEDIUM",
            "tags": ["backend"],
        }
        result = await client.create_story(task)
        assert result["simulated"] is True
        assert "T-001" in result["key"]

    @pytest.mark.asyncio
    async def test_export_fs_tasks(self):
        from app.integrations.jira import JiraClient
        client = JiraClient()
        tasks = [
            {"task_id": "T-001", "title": "Task 1", "description": "Desc 1"},
            {"task_id": "T-002", "title": "Task 2", "description": "Desc 2"},
        ]
        result = await client.export_fs_tasks("Test FS", tasks)
        assert result["total"] == 2
        assert len(result["stories"]) == 2
        assert "epic" in result

    @pytest.mark.asyncio
    async def test_is_configured_false(self):
        from app.integrations.jira import JiraClient
        client = JiraClient()
        assert client.is_configured is False

    @pytest.mark.asyncio
    async def test_story_with_acceptance_criteria(self):
        from app.integrations.jira import JiraClient
        client = JiraClient()
        task = {
            "task_id": "T-003",
            "title": "AC Task",
            "description": "Task with criteria",
            "acceptance_criteria": ["Must pass test A", "Must handle errors"],
            "effort": "HIGH",
            "tags": ["critical"],
        }
        result = await client.create_story(task)
        assert result["simulated"] is True


# ── ConfluenceClient Tests ─────────────────────────────


class TestConfluenceClient:
    """Test Confluence integration client."""

    @pytest.mark.asyncio
    async def test_simulated_page(self):
        from app.integrations.confluence import ConfluenceClient
        client = ConfluenceClient()
        result = await client.create_page("Test Page", "<p>Content</p>")
        assert result["simulated"] is True
        assert "Test Page" in result["title"]

    @pytest.mark.asyncio
    async def test_is_configured_false(self):
        from app.integrations.confluence import ConfluenceClient
        client = ConfluenceClient()
        assert client.is_configured is False

    @pytest.mark.asyncio
    async def test_build_page_content(self):
        from app.integrations.confluence import ConfluenceClient
        client = ConfluenceClient()
        content = client._build_page_content(
            sections=[{"heading": "Section 1", "content": "Content 1", "section_index": 0}],
            quality_score={"overall": 0.85, "completeness": 0.9, "clarity": 0.8, "consistency": 0.85},
            ambiguities=[{"section_heading": "Section 1", "severity": "HIGH", "reason": "Vague wording"}],
            tasks=[{"task_id": "T-001", "title": "Task 1", "effort": "MEDIUM", "section_heading": "Section 1"}],
            traceability=[{"task_id": "T-001", "task_title": "Task 1", "section_heading": "Section 1"}],
        )
        assert "Section 1" in content
        assert "Quality Score" in content
        assert "Ambiguity Flags" in content
        assert "T-001" in content

    @pytest.mark.asyncio
    async def test_build_page_empty(self):
        from app.integrations.confluence import ConfluenceClient
        client = ConfluenceClient()
        content = client._build_page_content(sections=[], quality_score=None)
        assert "No content" in content

    @pytest.mark.asyncio
    async def test_create_fs_page(self):
        from app.integrations.confluence import ConfluenceClient
        client = ConfluenceClient()
        result = await client.create_fs_page(
            title="My FS",
            sections=[{"heading": "Auth", "content": "Login flow", "section_index": 0}],
        )
        assert result["simulated"] is True
        assert "FS Analysis" in result["title"]


# ── TestCase Pipeline Node Tests ───────────────────────


class TestTestcaseNode:
    """Test the testcase_node pipeline node."""

    @pytest.mark.asyncio
    async def test_no_tasks(self):
        from app.pipeline.nodes.testcase_node import testcase_node
        state = {"tasks": [], "fs_id": "test", "errors": []}
        result = await testcase_node(state)
        assert result["test_cases"] == []

    @pytest.mark.asyncio
    async def test_task_without_criteria(self):
        import app.pipeline.nodes.testcase_node as tc_mod
        from app.pipeline.nodes.testcase_node import testcase_node

        # Ensure pipeline_call_llm is None (no-LLM fallback)
        original = tc_mod.pipeline_call_llm
        tc_mod.pipeline_call_llm = None
        try:
            state = {
                "tasks": [{
                    "task_id": "T-001",
                    "title": "Basic task",
                    "description": "A simple task",
                    "acceptance_criteria": [],
                    "section_index": 0,
                    "section_heading": "Section 1",
                }],
                "fs_id": "test",
                "errors": [],
            }
            result = await testcase_node(state)
            assert len(result["test_cases"]) == 1
            assert result["test_cases"][0]["test_type"] == "INTEGRATION"
            assert "Verify:" in result["test_cases"][0]["title"]
        finally:
            tc_mod.pipeline_call_llm = original

    @pytest.mark.asyncio
    async def test_task_with_criteria_llm_success(self):
        import app.pipeline.nodes.testcase_node as tc_mod
        from app.pipeline.nodes.testcase_node import testcase_node

        mock_response = json.dumps([
            {
                "title": "Test login flow",
                "preconditions": "User exists",
                "steps": ["Enter credentials", "Click login"],
                "expected_result": "User logged in",
                "test_type": "E2E",
            }
        ])

        state = {
            "tasks": [{
                "task_id": "T-001",
                "title": "Login",
                "description": "Implement login",
                "acceptance_criteria": ["User can login"],
                "section_index": 0,
                "section_heading": "Auth",
            }],
            "fs_id": "test",
            "errors": [],
        }

        mock_llm = AsyncMock(return_value=mock_response)
        original = tc_mod.pipeline_call_llm
        tc_mod.pipeline_call_llm = mock_llm
        try:
            result = await testcase_node(state)
            assert len(result["test_cases"]) == 1
            assert result["test_cases"][0]["title"] == "Test login flow"
            assert result["test_cases"][0]["test_type"] == "E2E"
        finally:
            tc_mod.pipeline_call_llm = original

    @pytest.mark.asyncio
    async def test_task_with_criteria_llm_json_error(self):
        import app.pipeline.nodes.testcase_node as tc_mod
        from app.pipeline.nodes.testcase_node import testcase_node

        state = {
            "tasks": [{
                "task_id": "T-001",
                "title": "Login",
                "description": "Implement login",
                "acceptance_criteria": ["User can login", "Error on bad password"],
                "section_index": 0,
                "section_heading": "Auth",
            }],
            "fs_id": "test",
            "errors": [],
        }

        # LLM returns invalid JSON — should fallback to criterion-based test cases
        mock_llm = AsyncMock(return_value="not valid json")
        original = tc_mod.pipeline_call_llm
        tc_mod.pipeline_call_llm = mock_llm
        try:
            result = await testcase_node(state)
            assert len(result["test_cases"]) == 2  # One per criterion
            assert result["test_cases"][0]["test_type"] == "ACCEPTANCE"
        finally:
            tc_mod.pipeline_call_llm = original

    @pytest.mark.asyncio
    async def test_llm_not_available(self):
        import app.pipeline.nodes.testcase_node as tc_mod
        from app.pipeline.nodes.testcase_node import testcase_node

        state = {
            "tasks": [{
                "task_id": "T-001",
                "title": "Task",
                "description": "Desc",
                "acceptance_criteria": [],
                "section_index": 0,
                "section_heading": "Section",
            }],
            "fs_id": "test",
            "errors": [],
        }

        original = tc_mod.pipeline_call_llm
        tc_mod.pipeline_call_llm = None
        try:
            result = await testcase_node(state)
            assert len(result["test_cases"]) == 1
        finally:
            tc_mod.pipeline_call_llm = original

    @pytest.mark.asyncio
    async def test_multiple_tasks(self):
        import app.pipeline.nodes.testcase_node as tc_mod
        from app.pipeline.nodes.testcase_node import testcase_node

        state = {
            "tasks": [
                {"task_id": "T-001", "title": "Login", "description": "Login flow", "acceptance_criteria": [], "section_index": 0, "section_heading": "Auth"},
                {"task_id": "T-002", "title": "Dashboard", "description": "Dashboard view", "acceptance_criteria": [], "section_index": 1, "section_heading": "UI"},
            ],
            "fs_id": "test",
            "errors": [],
        }

        original = tc_mod.pipeline_call_llm
        tc_mod.pipeline_call_llm = None
        try:
            result = await testcase_node(state)
            assert len(result["test_cases"]) == 2
        finally:
            tc_mod.pipeline_call_llm = original


# ── Export Router Tests ────────────────────────────────


class TestTestCasesEndpoint:
    """Test the test-cases API endpoint."""

    @pytest.mark.asyncio
    async def test_list_test_cases(self, client, doc_with_test_cases):
        resp = await client.get(f"/api/fs/{doc_with_test_cases.id}/test-cases")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 3
        assert len(data["test_cases"]) == 3
        assert "by_type" in data
        assert data["by_type"]["E2E"] == 2
        assert data["by_type"]["INTEGRATION"] == 1

    @pytest.mark.asyncio
    async def test_list_test_cases_empty(self, client, sample_doc):
        resp = await client.get(f"/api/fs/{sample_doc.id}/test-cases")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_test_cases_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/fs/{fake_id}/test-cases")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_csv_export(self, client, doc_with_test_cases):
        resp = await client.get(f"/api/fs/{doc_with_test_cases.id}/test-cases/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        content = resp.text
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 4  # header + 3 test cases
        assert rows[0][0] == "Task ID"

    @pytest.mark.asyncio
    async def test_csv_export_empty(self, client, sample_doc):
        resp = await client.get(f"/api/fs/{sample_doc.id}/test-cases/csv")
        assert resp.status_code == 200
        content = resp.text
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 1  # header only


class TestJiraExportEndpoint:
    """Test the JIRA export API endpoint."""

    @pytest.mark.asyncio
    async def test_jira_export(self, client, doc_with_tasks):
        resp = await client.post(f"/api/fs/{doc_with_tasks.id}/export/jira")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert len(data["stories"]) == 2
        assert data["simulated"] is True
        assert "epic" in data

    @pytest.mark.asyncio
    async def test_jira_export_no_tasks(self, client, sample_doc):
        resp = await client.post(f"/api/fs/{sample_doc.id}/export/jira")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_jira_export_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.post(f"/api/fs/{fake_id}/export/jira")
        assert resp.status_code == 404


class TestConfluenceExportEndpoint:
    """Test the Confluence export API endpoint."""

    @pytest.mark.asyncio
    async def test_confluence_export(self, client, doc_with_tasks):
        resp = await client.post(f"/api/fs/{doc_with_tasks.id}/export/confluence")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["simulated"] is True
        assert "page_id" in data
        assert "page_url" in data

    @pytest.mark.asyncio
    async def test_confluence_export_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.post(f"/api/fs/{fake_id}/export/confluence")
        assert resp.status_code == 404


class TestPdfExportEndpoint:
    """Test the PDF export API endpoint."""

    @pytest.mark.asyncio
    async def test_pdf_export_metadata(self, client, doc_with_test_cases):
        resp = await client.get(f"/api/fs/{doc_with_test_cases.id}/export/pdf")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["format"] == "pdf"
        assert data["filename"].endswith(".pdf")
        assert data["size_bytes"] > 0
        assert "download_url" in data

    @pytest.mark.asyncio
    async def test_pdf_download(self, client, doc_with_test_cases):
        resp = await client.get(f"/api/fs/{doc_with_test_cases.id}/export/pdf/download")
        assert resp.status_code == 200
        # Content should be non-empty (either PDF or text fallback)
        assert len(resp.content) > 0

    @pytest.mark.asyncio
    async def test_pdf_export_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/fs/{fake_id}/export/pdf")
        assert resp.status_code == 404


class TestDocxExportEndpoint:
    """Test the DOCX export API endpoint."""

    @pytest.mark.asyncio
    async def test_docx_export_metadata(self, client, doc_with_test_cases):
        resp = await client.get(f"/api/fs/{doc_with_test_cases.id}/export/docx")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["format"] == "docx"
        assert data["filename"].endswith(".docx")
        assert data["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_docx_download(self, client, doc_with_test_cases):
        resp = await client.get(f"/api/fs/{doc_with_test_cases.id}/export/docx/download")
        assert resp.status_code == 200
        assert len(resp.content) > 0

    @pytest.mark.asyncio
    async def test_docx_export_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/fs/{fake_id}/export/docx")
        assert resp.status_code == 404


# ── Report Generation Tests ────────────────────────────


class TestReportGeneration:
    """Test report content generation helpers."""

    def test_text_report_fallback(self):
        from app.api.export_router import _generate_text_report

        # Create minimal mock objects
        class MockTask:
            task_id = "T-001"
            title = "Test Task"
            class effort:
                value = "MEDIUM"

        class MockAmbiguity:
            severity = AmbiguitySeverity.HIGH
            section_heading = "Auth"
            reason = "Vague wording"

        class MockTestCase:
            task_id = "T-001"
            title = "Test login"
            test_type = TestType.E2E

        content = {
            "filename": "test.txt",
            "status": "COMPLETE",
            "tasks": [MockTask()],
            "ambiguities": [MockAmbiguity()],
            "contradictions": [],
            "edge_cases": [],
            "compliance": [],
            "traceability": [],
            "test_cases": [MockTestCase()],
        }

        result = _generate_text_report("test.txt", content, "PDF")
        text = result.decode("utf-8")
        assert "FS Intelligence Report" in text
        assert "T-001" in text
        assert "Test Task" in text
        assert "HIGH" in text
        assert "E2E" in text


# ── Pipeline Graph Integration ─────────────────────────


class TestPipelineIntegration:
    """Test that testcase_node is in the analysis graph."""

    def test_testcase_node_in_graph(self):
        from app.pipeline.graph import build_analysis_graph
        graph = build_analysis_graph()
        # The compiled graph should contain testcase_node
        node_names = [n for n in graph.nodes if n != "__start__" and n != "__end__"]
        assert "testcase_node" in node_names

    def test_graph_has_correct_node_count(self):
        from app.pipeline.graph import build_analysis_graph
        graph = build_analysis_graph()
        # 11 nodes: parse, ambiguity, debate, contradiction, edge_case, quality,
        # task_decomposition, dependency, traceability, duplicate, testcase
        real_nodes = [n for n in graph.nodes if n != "__start__" and n != "__end__"]
        assert len(real_nodes) == 11

    def test_initial_state_has_test_cases(self):
        """Verify the initial pipeline state includes test_cases field."""
        from app.pipeline.state import FSAnalysisState
        # TypedDict keys should include test_cases
        assert "test_cases" in FSAnalysisState.__annotations__


# ── Schema Tests ───────────────────────────────────────


class TestSchemas:
    """Test L10 Pydantic schemas."""

    def test_test_case_schema(self):
        from app.models.schemas import TestCaseSchema
        tc = TestCaseSchema(
            task_id="T-001",
            title="Test login",
            steps=["Step 1", "Step 2"],
            expected_result="Success",
            test_type="E2E",
        )
        assert tc.test_type == "E2E"
        assert len(tc.steps) == 2

    def test_jira_export_response(self):
        from app.models.schemas import JiraExportResponse
        resp = JiraExportResponse(
            epic={"id": "1", "key": "FSP-1"},
            stories=[{"id": "2", "key": "FSP-2"}],
            total=1,
            simulated=True,
        )
        assert resp.total == 1
        assert resp.simulated is True

    def test_confluence_export_response(self):
        from app.models.schemas import ConfluenceExportResponse
        resp = ConfluenceExportResponse(
            page_id="123",
            page_url="https://example.com/page",
            title="Test Page",
            simulated=True,
        )
        assert resp.page_id == "123"

    def test_report_export_response(self):
        from app.models.schemas import ReportExportResponse
        resp = ReportExportResponse(
            filename="report.pdf",
            format="pdf",
            size_bytes=1024,
            download_url="/api/fs/123/export/pdf/download",
        )
        assert resp.format == "pdf"

    def test_test_case_list_response(self):
        from app.models.schemas import TestCaseListResponse, TestCaseSchema
        tc = TestCaseSchema(task_id="T-001", title="Test", steps=[], expected_result="OK")
        resp = TestCaseListResponse(
            test_cases=[tc],
            total=1,
            by_type={"UNIT": 1},
        )
        assert resp.total == 1
        assert resp.by_type["UNIT"] == 1
