"""Tests for L8 Legacy Code → FS Reverse Generation.

Tests:
- CodeEntity, CodeFile, CodebaseSnapshot, GeneratedFSReport models
- ReverseGenState with L8 fields
- Code parser (Python AST, JS/TS regex, file filtering, zip handling)
- reverse_quality_node (coverage computation)
- Pipeline graph (builds, singleton, basic run)
- API endpoints (upload, list, generate-fs, generated-fs, report, detail, 404s)
"""

import io
import json
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.state import (
    CodebaseSnapshot,
    CodeEntity,
    CodeFile,
    GeneratedFSReport,
    ReverseGenState,
)


# ── Unit Tests: CodeEntity Model ────────────────────────


class TestCodeEntityModel:
    """Test the CodeEntity Pydantic model."""

    def test_function_entity(self):
        entity = CodeEntity(
            name="process_data",
            entity_type="function",
            docstring="Process incoming data.",
            signature="def process_data(data: dict) -> list",
            line_number=42,
        )
        assert entity.name == "process_data"
        assert entity.entity_type == "function"
        assert entity.docstring is not None

    def test_class_entity(self):
        entity = CodeEntity(
            name="UserService",
            entity_type="class",
            docstring="Manages user operations.",
            signature="class UserService(BaseService)",
            line_number=10,
        )
        assert entity.entity_type == "class"

    def test_entity_defaults(self):
        entity = CodeEntity()
        assert entity.name == ""
        assert entity.entity_type == "function"
        assert entity.docstring is None
        assert entity.line_number == 0

    def test_serialisation(self):
        entity = CodeEntity(name="foo", entity_type="method")
        data = entity.model_dump()
        assert data["name"] == "foo"
        assert isinstance(data, dict)


# ── Unit Tests: CodeFile Model ──────────────────────────


class TestCodeFileModel:
    """Test the CodeFile Pydantic model."""

    def test_file_with_entities(self):
        cf = CodeFile(
            path="src/utils.py",
            language="python",
            content="def helper(): pass",
            entities=[CodeEntity(name="helper", entity_type="function")],
            line_count=1,
            has_docstrings=False,
        )
        assert cf.path == "src/utils.py"
        assert cf.language == "python"
        assert len(cf.entities) == 1

    def test_file_defaults(self):
        cf = CodeFile()
        assert cf.path == ""
        assert cf.entities == []
        assert cf.line_count == 0

    def test_file_serialisation(self):
        cf = CodeFile(path="test.py", language="python")
        data = cf.model_dump()
        assert data["language"] == "python"


# ── Unit Tests: CodebaseSnapshot Model ──────────────────


class TestCodebaseSnapshotModel:
    """Test the CodebaseSnapshot Pydantic model."""

    def test_snapshot_with_data(self):
        snap = CodebaseSnapshot(
            files=[CodeFile(path="main.py", language="python", line_count=100)],
            primary_language="python",
            total_files=1,
            total_lines=100,
            languages={"python": 1},
        )
        assert snap.primary_language == "python"
        assert snap.total_files == 1
        assert snap.total_lines == 100

    def test_snapshot_defaults(self):
        snap = CodebaseSnapshot()
        assert snap.files == []
        assert snap.primary_language == ""
        assert snap.total_files == 0

    def test_snapshot_serialisation(self):
        snap = CodebaseSnapshot(primary_language="go", total_files=5)
        data = snap.model_dump()
        assert data["primary_language"] == "go"
        assert data["total_files"] == 5


# ── Unit Tests: GeneratedFSReport Model ─────────────────


class TestGeneratedFSReportModel:
    """Test the GeneratedFSReport model."""

    def test_report_with_data(self):
        report = GeneratedFSReport(
            coverage=0.75,
            gaps=["File 'x.py' has 3 undocumented functions"],
            confidence=0.8,
            total_entities=20,
            documented_entities=15,
            undocumented_files=["x.py"],
        )
        assert report.coverage == 0.75
        assert report.confidence == 0.8
        assert len(report.gaps) == 1
        assert len(report.undocumented_files) == 1

    def test_report_defaults(self):
        report = GeneratedFSReport()
        assert report.coverage == 0.0
        assert report.confidence == 0.0
        assert report.gaps == []

    def test_report_serialisation(self):
        report = GeneratedFSReport(coverage=0.5, confidence=0.6)
        data = report.model_dump()
        assert data["coverage"] == 0.5


# ── Unit Tests: ReverseGenState ─────────────────────────


class TestReverseGenState:
    """Test ReverseGenState TypedDict."""

    def test_state_has_all_fields(self):
        state: ReverseGenState = {
            "code_upload_id": "test-123",
            "snapshot": {},
            "module_summaries": [],
            "user_flows": [],
            "generated_sections": [],
            "raw_fs_text": "",
            "report": {},
            "errors": [],
        }
        assert "snapshot" in state
        assert "generated_sections" in state
        assert "report" in state

    def test_state_with_data(self):
        state: ReverseGenState = {
            "code_upload_id": "test-456",
            "snapshot": {"total_files": 5, "primary_language": "python"},
            "module_summaries": [{"module_name": "main"}],
            "user_flows": ["Authentication"],
            "generated_sections": [{"heading": "Auth", "content": "..."}],
            "raw_fs_text": "# Generated FS",
            "report": {"coverage": 0.8, "confidence": 0.7},
            "errors": [],
        }
        assert state["snapshot"]["total_files"] == 5
        assert len(state["generated_sections"]) == 1


# ── Unit Tests: Code Parser ─────────────────────────────


def _create_test_zip(files: dict[str, str]) -> str:
    """Create a temporary zip with the given file contents."""
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with zipfile.ZipFile(tmp.name, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return tmp.name


class TestCodeParser:
    """Test the code_parser module."""

    def test_parse_python_file(self):
        """Python files should be parsed with AST."""
        zip_path = _create_test_zip({
            "myproject/main.py": '''
"""Main module docstring."""

def greet(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}"

class UserService:
    """Manages users."""

    def get_user(self, user_id: int) -> dict:
        """Get user by ID."""
        return {"id": user_id}

    def delete_user(self, user_id: int) -> None:
        pass
''',
        })

        try:
            from app.parsers.code_parser import parse_codebase
            snapshot = parse_codebase(zip_path)

            assert snapshot.total_files == 1
            assert snapshot.primary_language == "python"
            assert snapshot.total_lines > 0

            file = snapshot.files[0]
            assert file.language == "python"
            assert file.has_docstrings is True

            names = [e.name for e in file.entities]
            assert "greet" in names
            assert "UserService" in names
        finally:
            os.unlink(zip_path)

    def test_parse_javascript_file(self):
        """JS files should be parsed with regex."""
        zip_path = _create_test_zip({
            "app/server.js": '''
/**
 * Start the server
 */
function startServer(port) {
    console.log("Starting on " + port);
}

class Router {
    constructor() {}
}

const handleRequest = (req) => {
    return "OK";
};
''',
        })

        try:
            from app.parsers.code_parser import parse_codebase
            snapshot = parse_codebase(zip_path)

            assert snapshot.total_files == 1
            assert snapshot.primary_language == "javascript"

            file = snapshot.files[0]
            names = [e.name for e in file.entities]
            assert "startServer" in names
            assert "Router" in names
            assert "handleRequest" in names
        finally:
            os.unlink(zip_path)

    def test_parse_typescript_file(self):
        """TS files should be detected as typescript."""
        zip_path = _create_test_zip({
            "src/index.ts": '''
export function main(): void {
    console.log("Hello");
}

export class AppService {
    start(): void {}
}
''',
        })

        try:
            from app.parsers.code_parser import parse_codebase
            snapshot = parse_codebase(zip_path)
            assert snapshot.primary_language == "typescript"
            file = snapshot.files[0]
            names = [e.name for e in file.entities]
            assert "main" in names
            assert "AppService" in names
        finally:
            os.unlink(zip_path)

    def test_parse_multiple_languages(self):
        """Multiple languages should be detected."""
        zip_path = _create_test_zip({
            "backend/app.py": 'def run(): pass',
            "frontend/app.js": 'function render() {}',
            "frontend/utils.ts": 'export function helper(): void {}',
        })

        try:
            from app.parsers.code_parser import parse_codebase
            snapshot = parse_codebase(zip_path)

            assert snapshot.total_files == 3
            assert "python" in snapshot.languages
            assert "javascript" in snapshot.languages
            assert "typescript" in snapshot.languages
        finally:
            os.unlink(zip_path)

    def test_skip_node_modules(self):
        """node_modules should be skipped."""
        zip_path = _create_test_zip({
            "app.js": 'function main() {}',
            "node_modules/express/index.js": 'module.exports = {}',
        })

        try:
            from app.parsers.code_parser import parse_codebase
            snapshot = parse_codebase(zip_path)
            assert snapshot.total_files == 1
            assert all("node_modules" not in f.path for f in snapshot.files)
        finally:
            os.unlink(zip_path)

    def test_skip_pycache(self):
        """__pycache__ should be skipped."""
        zip_path = _create_test_zip({
            "main.py": 'def run(): pass',
            "__pycache__/main.cpython-312.pyc": 'binary data',
        })

        try:
            from app.parsers.code_parser import parse_codebase
            snapshot = parse_codebase(zip_path)
            assert snapshot.total_files == 1
        finally:
            os.unlink(zip_path)

    def test_skip_git_dir(self):
        """.git should be skipped."""
        zip_path = _create_test_zip({
            "main.py": 'def run(): pass',
            ".git/HEAD": 'ref: refs/heads/main',
        })

        try:
            from app.parsers.code_parser import parse_codebase
            snapshot = parse_codebase(zip_path)
            assert snapshot.total_files == 1
        finally:
            os.unlink(zip_path)

    def test_empty_zip_raises(self):
        """Empty zip with no source files should raise."""
        zip_path = _create_test_zip({
            "README.md": "# Hello",
            "data.json": "{}",
        })

        try:
            from app.parsers.code_parser import parse_codebase
            with pytest.raises(ValueError, match="No supported source files"):
                parse_codebase(zip_path)
        finally:
            os.unlink(zip_path)

    def test_invalid_zip_raises(self):
        """Non-zip file should raise."""
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.write(b"this is not a zip")
        tmp.close()

        try:
            from app.parsers.code_parser import parse_codebase
            with pytest.raises(ValueError, match="Not a valid zip"):
                parse_codebase(tmp.name)
        finally:
            os.unlink(tmp.name)

    def test_missing_file_raises(self):
        """Missing file should raise."""
        from app.parsers.code_parser import parse_codebase
        with pytest.raises(ValueError, match="not found"):
            parse_codebase("/nonexistent/path.zip")

    def test_single_folder_wrapper(self):
        """Zip with single root folder should unwrap."""
        zip_path = _create_test_zip({
            "myproject/src/main.py": 'def main(): pass',
            "myproject/src/utils.py": 'def helper(): pass',
        })

        try:
            from app.parsers.code_parser import parse_codebase
            snapshot = parse_codebase(zip_path)
            assert snapshot.total_files == 2
            # Paths should be relative to the unwrapped root
            paths = [f.path for f in snapshot.files]
            assert all("myproject" not in p for p in paths)
        finally:
            os.unlink(zip_path)

    def test_parser_stats_are_present(self):
        """Parser should return skip/parse diagnostics for observability."""
        zip_path = _create_test_zip({
            "src/main.py": "def main():\n    return 1\n",
            "src/helper.ts": "export const helper = () => 1;\n",
            "node_modules/pkg/index.js": "module.exports = {}\n",
        })
        try:
            from app.parsers.code_parser import parse_codebase
            snapshot = parse_codebase(zip_path)
            assert isinstance(snapshot.parser_stats, dict)
            assert snapshot.parser_stats.get("parsed_files", 0) >= 2
            assert snapshot.parser_stats.get("skipped_files", 0) >= 1
        finally:
            os.unlink(zip_path)

    def test_parser_respects_max_files_limit(self, monkeypatch):
        """Parser should stop at REVERSE_MAX_FILES_TO_PARSE."""
        zip_path = _create_test_zip({
            "a.py": "def a(): pass\n",
            "b.py": "def b(): pass\n",
            "c.py": "def c(): pass\n",
            "d.py": "def d(): pass\n",
        })
        try:
            from app.parsers.code_parser import parse_codebase
            with patch("app.parsers.code_parser._build_filter_config", return_value={
                "skip_dirs": set(),
                "skip_files": set(),
                "include_extensions": {".py"},
                "max_file_size_bytes": 500000,
                "max_files_to_parse": 2,
            }):
                snapshot = parse_codebase(zip_path)
            assert snapshot.total_files <= 2
            assert snapshot.parser_stats.get("skipped_by_limit", 0) >= 1
        finally:
            os.unlink(zip_path)


# ── Unit Tests: Python AST Extraction ───────────────────


class TestPythonExtraction:
    """Test Python-specific AST extraction."""

    def test_extract_functions(self):
        from app.parsers.code_parser import _extract_python_entities

        code = '''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def subtract(a, b):
    return a - b
'''
        entities = _extract_python_entities(code)
        names = [e.name for e in entities]
        assert "add" in names
        assert "subtract" in names

        add_entity = next(e for e in entities if e.name == "add")
        assert add_entity.docstring == "Add two numbers."
        assert "a: int" in add_entity.signature

    def test_extract_classes(self):
        from app.parsers.code_parser import _extract_python_entities

        code = '''
class Animal:
    """Base animal class."""

    def speak(self) -> str:
        """Make a sound."""
        return ""

class Dog(Animal):
    def speak(self) -> str:
        return "Woof"
'''
        entities = _extract_python_entities(code)
        class_entities = [e for e in entities if e.entity_type == "class"]
        assert len(class_entities) == 2

        methods = [e for e in entities if e.entity_type == "method"]
        assert len(methods) >= 2

    def test_invalid_syntax(self):
        from app.parsers.code_parser import _extract_python_entities

        # Should return empty list on syntax error
        entities = _extract_python_entities("def broken(:")
        assert entities == []

    def test_async_functions(self):
        from app.parsers.code_parser import _extract_python_entities

        code = '''
async def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    pass
'''
        entities = _extract_python_entities(code)
        assert len(entities) == 1
        assert entities[0].name == "fetch_data"
        assert entities[0].docstring == "Fetch data from URL."


# ── Unit Tests: Generic Extraction ──────────────────────


class TestGenericExtraction:
    """Test regex-based extraction for JS/TS/Java/Go."""

    def test_js_functions(self):
        from app.parsers.code_parser import _extract_generic_entities

        code = '''
function handleClick(event) {
    console.log(event);
}

async function fetchData(url) {
    return fetch(url);
}
'''
        entities = _extract_generic_entities(code, "javascript")
        names = [e.name for e in entities]
        assert "handleClick" in names
        assert "fetchData" in names

    def test_js_arrow_functions(self):
        from app.parsers.code_parser import _extract_generic_entities

        code = '''
const multiply = (a, b) => a * b;
const divide = async (a, b) => a / b;
'''
        entities = _extract_generic_entities(code, "javascript")
        names = [e.name for e in entities]
        assert "multiply" in names
        assert "divide" in names

    def test_js_classes(self):
        from app.parsers.code_parser import _extract_generic_entities

        code = '''
class UserController extends BaseController {
    constructor() {}
}
'''
        entities = _extract_generic_entities(code, "javascript")
        class_entities = [e for e in entities if e.entity_type == "class"]
        assert len(class_entities) == 1
        assert class_entities[0].name == "UserController"
        assert "extends BaseController" in class_entities[0].signature

    def test_go_functions(self):
        from app.parsers.code_parser import _extract_generic_entities

        code = '''
// ProcessOrder handles order processing
func ProcessOrder(orderId string, items []Item) error {
    return nil
}

func (s *Server) Start(port int) error {
    return nil
}
'''
        entities = _extract_generic_entities(code, "go")
        names = [e.name for e in entities]
        assert "ProcessOrder" in names
        assert "Start" in names

    def test_java_classes_and_methods(self):
        from app.parsers.code_parser import _extract_generic_entities

        code = '''
public class PaymentService extends BaseService {
    public void processPayment(String paymentId, double amount) {
        // process
    }

    private boolean validateCard(String cardNumber) {
        return true;
    }
}
'''
        entities = _extract_generic_entities(code, "java")
        class_entities = [e for e in entities if e.entity_type == "class"]
        method_entities = [e for e in entities if e.entity_type == "method"]
        assert len(class_entities) >= 1
        assert class_entities[0].name == "PaymentService"
        assert len(method_entities) >= 2

    def test_unknown_language(self):
        from app.parsers.code_parser import _extract_generic_entities

        entities = _extract_generic_entities("some code", "rust")
        assert entities == []


# ── Unit Tests: Quality Node ────────────────────────────


class TestReverseQualityNode:
    """Test reverse_quality_node quality computation."""

    @pytest.mark.asyncio
    async def test_quality_all_documented(self):
        """Fully documented codebase should have high coverage."""
        from app.pipeline.nodes.reverse_quality_node import reverse_quality_node

        state: ReverseGenState = {
            "code_upload_id": "test-quality",
            "snapshot": {
                "files": [
                    {
                        "path": "main.py",
                        "language": "python",
                        "entities": [
                            {"name": "func1", "entity_type": "function", "docstring": "Does stuff"},
                            {"name": "func2", "entity_type": "function", "docstring": "Does more"},
                        ],
                        "has_docstrings": True,
                    },
                ],
                "total_files": 1,
            },
            "module_summaries": [],
            "user_flows": [],
            "generated_sections": [
                {"heading": "Feature 1", "content": "This section describes the main feature in detail.", "section_index": 0},
            ],
            "raw_fs_text": "# FS",
            "report": {},
            "errors": [],
        }
        result = await reverse_quality_node(state)
        report = result["report"]
        assert report["coverage"] > 0.0
        assert report["confidence"] > 0.0
        assert "confidence_reasons" in report

    @pytest.mark.asyncio
    async def test_quality_undocumented(self):
        """Undocumented codebase should have gaps."""
        from app.pipeline.nodes.reverse_quality_node import reverse_quality_node

        state: ReverseGenState = {
            "code_upload_id": "test-undoc",
            "snapshot": {
                "files": [
                    {
                        "path": "main.py",
                        "language": "python",
                        "entities": [
                            {"name": "f1", "entity_type": "function", "docstring": None},
                            {"name": "f2", "entity_type": "function", "docstring": None},
                            {"name": "f3", "entity_type": "function", "docstring": None},
                            {"name": "f4", "entity_type": "function", "docstring": None},
                        ],
                        "has_docstrings": False,
                    },
                ],
                "total_files": 1,
            },
            "module_summaries": [],
            "user_flows": [],
            "generated_sections": [],
            "raw_fs_text": "",
            "report": {},
            "errors": [],
        }
        result = await reverse_quality_node(state)
        report = result["report"]
        assert len(report["gaps"]) > 0
        assert len(report["undocumented_files"]) > 0

    @pytest.mark.asyncio
    async def test_quality_failed_sections(self):
        """Failed sections should be flagged as gaps."""
        from app.pipeline.nodes.reverse_quality_node import reverse_quality_node

        state: ReverseGenState = {
            "code_upload_id": "test-fail",
            "snapshot": {
                "files": [
                    {
                        "path": "main.py",
                        "language": "python",
                        "entities": [{"name": "f", "entity_type": "function", "docstring": "doc"}],
                        "has_docstrings": True,
                    },
                ],
                "total_files": 1,
            },
            "module_summaries": [],
            "user_flows": [],
            "generated_sections": [
                {"heading": "Failed", "content": "[Generation failed: LLM error]", "section_index": 0},
            ],
            "raw_fs_text": "",
            "report": {},
            "errors": [],
        }
        result = await reverse_quality_node(state)
        report = result["report"]
        assert any("failed to generate" in g.lower() for g in report["gaps"])

    @pytest.mark.asyncio
    async def test_quality_empty_snapshot(self):
        """Empty snapshot should produce zeros."""
        from app.pipeline.nodes.reverse_quality_node import reverse_quality_node

        state: ReverseGenState = {
            "code_upload_id": "test-empty",
            "snapshot": {"files": [], "total_files": 0},
            "module_summaries": [],
            "user_flows": [],
            "generated_sections": [],
            "raw_fs_text": "",
            "report": {},
            "errors": [],
        }
        result = await reverse_quality_node(state)
        report = result["report"]
        assert report["coverage"] == 0.0
        assert report["total_entities"] == 0


# ── Unit Tests: Coverage Computation ────────────────────


class TestComputeCoverage:
    """Test the compute_coverage pure function."""

    def test_mixed_coverage(self):
        from app.pipeline.nodes.reverse_quality_node import compute_coverage

        snapshot = {
            "files": [
                {
                    "path": "a.py",
                    "entities": [
                        {"name": "f1", "docstring": "yes"},
                        {"name": "f2", "docstring": None},
                    ],
                    "has_docstrings": True,
                },
                {
                    "path": "b.py",
                    "entities": [
                        {"name": "f3", "docstring": None},
                        {"name": "f4", "docstring": None},
                        {"name": "f5", "docstring": None},
                        {"name": "f6", "docstring": None},
                    ],
                    "has_docstrings": False,
                },
            ],
        }
        sections = [
            {"heading": "Feature", "content": "Full content description here.", "section_index": 0},
        ]
        report = compute_coverage(snapshot, sections)
        assert 0.0 <= report.coverage <= 1.0
        assert 0.0 <= report.confidence <= 1.0
        assert report.total_entities > 0
        assert "b.py" in report.undocumented_files


# ── Integration Tests: Pipeline Graph ──────────────────


class TestReversePipelineGraph:
    """Test that the reverse pipeline graph is correctly built."""

    def test_reverse_graph_builds(self):
        import app.pipeline.graph as graph_mod
        graph_mod._compiled_reverse_graph = None

        with patch("app.pipeline.nodes.reverse_fs_node.pipeline_call_llm"), patch(
            "app.pipeline.nodes.reverse_fs_node.pipeline_call_llm_json"
        ):
            graph = graph_mod.build_reverse_graph()
            assert graph is not None

        graph_mod._compiled_reverse_graph = None

    def test_reverse_graph_singleton(self):
        import app.pipeline.graph as graph_mod
        graph_mod._compiled_reverse_graph = None

        with patch("app.pipeline.nodes.reverse_fs_node.pipeline_call_llm"), patch(
            "app.pipeline.nodes.reverse_fs_node.pipeline_call_llm_json"
        ):
            g1 = graph_mod.get_compiled_reverse_graph()
            g2 = graph_mod.get_compiled_reverse_graph()
            assert g1 is g2

        graph_mod._compiled_reverse_graph = None


# ── Integration Tests: API Endpoints ───────────────────


class TestCodeAPI:
    """Test code upload and reverse FS API endpoints."""

    @pytest.mark.asyncio
    async def test_upload_non_zip_rejected(self, client):
        """Non-zip files should be rejected."""
        response = await client.post(
            "/api/code/upload",
            files={"file": ("test.txt", b"not a zip", "text/plain")},
        )
        assert response.status_code == 400
        assert "zip" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_upload_valid_zip(self, client):
        """Valid zip with source files should be accepted and parsed."""
        # Create a small zip in memory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("main.py", 'def hello():\n    """Say hello."""\n    print("hi")\n')
        buf.seek(0)

        response = await client.post(
            "/api/code/upload",
            files={"file": ("test_codebase.zip", buf.getvalue(), "application/zip")},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "PARSED"
        assert data["filename"] == "test_codebase.zip"

    @pytest.mark.asyncio
    async def test_list_uploads(self, client):
        """Should list all code uploads."""
        response = await client.get("/api/code/uploads")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "uploads" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_upload_detail_not_found(self, client):
        """Non-existent upload should 404."""
        fake_id = "00000000-0000-0000-0000-000000000099"
        response = await client.get(f"/api/code/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_generated_fs_not_ready(self, client):
        """Getting generated FS before generation should fail."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("app.py", 'def run(): pass\n')
        buf.seek(0)

        upload_resp = await client.post(
            "/api/code/upload",
            files={"file": ("code.zip", buf.getvalue(), "application/zip")},
        )
        upload_id = upload_resp.json()["data"]["id"]

        response = await client.get(f"/api/code/{upload_id}/generated-fs")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_report_not_available(self, client):
        """Getting report before generation should fail."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("app.py", 'def run(): pass\n')
        buf.seek(0)

        upload_resp = await client.post(
            "/api/code/upload",
            files={"file": ("code2.zip", buf.getvalue(), "application/zip")},
        )
        upload_id = upload_resp.json()["data"]["id"]

        response = await client.get(f"/api/code/{upload_id}/report")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_generate_fs_not_found(self, client):
        """Generating FS for non-existent upload should 404."""
        fake_id = "00000000-0000-0000-0000-000000000099"
        response = await client.post(f"/api/code/{fake_id}/generate-fs")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_detail(self, client):
        """Upload detail should return metadata."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("main.py", 'def main():\n    """Entry point."""\n    pass\n')
            zf.writestr("utils.py", 'def helper(): pass\n')
        buf.seek(0)

        upload_resp = await client.post(
            "/api/code/upload",
            files={"file": ("detail_test.zip", buf.getvalue(), "application/zip")},
        )
        upload_id = upload_resp.json()["data"]["id"]

        response = await client.get(f"/api/code/{upload_id}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "PARSED"
        assert data["primary_language"] == "python"
        assert data["total_files"] == 2
        assert "parser_stats" in data

    @pytest.mark.asyncio
    async def test_upload_empty_zip_rejected(self, client):
        """Zip with no source files should be rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("README.md", "# Hello\n")
        buf.seek(0)

        response = await client.post(
            "/api/code/upload",
            files={"file": ("empty.zip", buf.getvalue(), "application/zip")},
        )
        assert response.status_code == 400


# ── Unit Tests: File Filtering ──────────────────────────


class TestFileFiltering:
    """Test the _should_skip_file function."""

    def test_skip_node_modules(self):
        from app.parsers.code_parser import _should_skip_file
        assert _should_skip_file(Path("node_modules/express/index.js")) is True

    def test_skip_pycache(self):
        from app.parsers.code_parser import _should_skip_file
        assert _should_skip_file(Path("__pycache__/main.cpython.pyc")) is True

    def test_skip_git(self):
        from app.parsers.code_parser import _should_skip_file
        assert _should_skip_file(Path(".git/HEAD")) is True

    def test_skip_venv(self):
        from app.parsers.code_parser import _should_skip_file
        assert _should_skip_file(Path("venv/lib/site-packages/pkg.py")) is True

    def test_skip_unsupported_extension(self):
        from app.parsers.code_parser import _should_skip_file
        assert _should_skip_file(Path("readme.md")) is True
        assert _should_skip_file(Path("data.json")) is True
        assert _should_skip_file(Path("style.css")) is True

    def test_allow_python(self):
        from app.parsers.code_parser import _should_skip_file
        assert _should_skip_file(Path("main.py")) is False

    def test_allow_javascript(self):
        from app.parsers.code_parser import _should_skip_file
        assert _should_skip_file(Path("app.js")) is False

    def test_allow_typescript(self):
        from app.parsers.code_parser import _should_skip_file
        assert _should_skip_file(Path("index.ts")) is False

    def test_allow_java(self):
        from app.parsers.code_parser import _should_skip_file
        assert _should_skip_file(Path("Main.java")) is False

    def test_allow_go(self):
        from app.parsers.code_parser import _should_skip_file
        assert _should_skip_file(Path("main.go")) is False

    def test_skip_lock_files(self):
        from app.parsers.code_parser import _should_skip_file
        assert _should_skip_file(Path("package-lock.json")) is True


# ── Unit Tests: FS Assembly ─────────────────────────────


class TestFSAssembly:
    """Test the FS assembly function."""

    def test_assemble_sections(self):
        from app.pipeline.nodes.reverse_fs_node import _assemble_fs_text

        sections = [
            {"heading": "Authentication", "content": "Users shall authenticate via OAuth2."},
            {"heading": "Data Storage", "content": "The system shall use PostgreSQL."},
        ]
        result = _assemble_fs_text(sections)
        assert "# Generated Functional Specification" in result
        assert "## Authentication" in result
        assert "## Data Storage" in result
        assert "OAuth2" in result

    def test_assemble_empty(self):
        from app.pipeline.nodes.reverse_fs_node import _assemble_fs_text

        result = _assemble_fs_text([])
        assert "# Generated Functional Specification" in result
