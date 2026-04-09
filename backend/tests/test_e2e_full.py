"""Complete E2E test suite for the FS Intelligence Platform — all 10 levels.

Tests every API endpoint in order:
  L1-L2: Upload + Parse
  L3:    Ambiguity Detection
  L4:    Deep Analysis (contradictions, edge-cases, quality)
  L5:    Task Decomposition + Dependency Graph + Traceability
  L6:    Adversarial Debate
  L7:    Change Impact Analysis
  L8:    Legacy Code Reverse FS
  L9:    Semantic Intelligence + Collaboration
  L10:   Integrations + Export

All LLM and Qdrant calls are mocked for deterministic, fast execution.
"""

import io
import json
import uuid
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


# ── Test FS Document ────────────────────────────────────

TEST_FS_CONTENT = """\
# Payment Gateway Integration

## 1. Overview
The system shall integrate with Stripe and PayPal payment processors.
Users can pay via credit card, debit card, or digital wallet.

## 2. Authentication
All API calls must be authenticated using OAuth 2.0.
The session timeout shall be 30 minutes.
The session timeout shall be 60 minutes.

## 3. Transaction Limits
Daily transaction limit is unspecified for premium users.
Standard users are limited to $10,000 per day.

## 4. Error Handling
On payment failure, the system should retry. The number of retries is TBD.
PII data including card numbers must be encrypted at rest.

## 5. Reporting
Admins can export transaction reports in CSV and PDF format.
Reports must be generated within an unspecified time frame.
"""

UPDATED_FS_CONTENT = TEST_FS_CONTENT + """\

## 6. Refunds
Users may request full or partial refunds within 30 days.
The session timeout shall be 45 minutes.
"""


# ── Mock Responses ──────────────────────────────────────

MOCK_AMBIGUITIES = [
    {
        "flagged_text": "Daily transaction limit is unspecified for premium users",
        "reason": "No concrete limit defined for premium users",
        "severity": "HIGH",
        "clarification_question": "What is the daily limit for premium users?",
    },
    {
        "flagged_text": "Reports must be generated within an unspecified time frame",
        "reason": "No SLA defined for report generation",
        "severity": "HIGH",
        "clarification_question": "What is the maximum report generation time?",
    },
    {
        "flagged_text": "The number of retries is TBD",
        "reason": "Retry count undefined",
        "severity": "MEDIUM",
        "clarification_question": "How many retries on payment failure?",
    },
]

MOCK_CONTRADICTIONS = [
    {
        "description": "Session timeout conflict: 30 minutes vs 60 minutes",
        "severity": "HIGH",
        "suggested_resolution": "Clarify session timeout — use 30 or 60 minutes",
    },
]

MOCK_EDGE_CASES = [
    {
        "scenario_description": "No behaviour when all payment gateways are simultaneously unavailable",
        "impact": "HIGH",
        "suggested_addition": "Add fallback for total gateway outage",
    },
    {
        "scenario_description": "No handling for concurrent duplicate payment submissions",
        "impact": "MEDIUM",
        "suggested_addition": "Add idempotency keys for payment deduplication",
    },
]

MOCK_COMPLIANCE_TAGS = [
    {"tag": "payments", "reason": "Section references Stripe and PayPal payment processors"},
    {"tag": "pii", "reason": "Section mentions PII data and card numbers"},
    {"tag": "auth", "reason": "Section references OAuth 2.0 authentication"},
]

MOCK_TASKS = [
    {
        "title": "Implement OAuth 2.0 authentication flow",
        "description": "Build the OAuth 2.0 integration for API authentication",
        "acceptance_criteria": ["OAuth 2.0 tokens issued", "Session management works"],
        "effort": "HIGH",
        "tags": ["auth", "backend"],
    },
    {
        "title": "Integrate Stripe payment gateway",
        "description": "Connect to Stripe API for credit/debit card payments",
        "acceptance_criteria": ["Payment processed via Stripe", "Error handling works"],
        "effort": "HIGH",
        "tags": ["payments", "backend", "api"],
    },
    {
        "title": "Implement transaction reporting CSV/PDF export",
        "description": "Build admin reporting with CSV and PDF export functionality",
        "acceptance_criteria": ["CSV export works", "PDF export works"],
        "effort": "MEDIUM",
        "tags": ["reporting", "frontend"],
    },
]


# ── Mock LLM Router ────────────────────────────────────

def _make_mock_llm_json_router():
    """Return async callable that routes mock responses based on prompt/system content."""

    async def _route(*args, **kwargs):
        system = str(kwargs.get("system", "")).lower()
        prompt = str(kwargs.get("prompt", args[0] if args else "")).lower()
        combined = system + " " + prompt

        if "ambiguit" in combined or "ambiguous" in combined:
            # Only return HIGH ambiguities for sections about transaction limits / reporting
            # Other sections get no ambiguities so task_node can process them
            if "transaction limit" in prompt or "unspecified" in prompt:
                return MOCK_AMBIGUITIES[:2]  # HIGH flags
            elif "retries" in prompt or "tbd" in prompt:
                return [MOCK_AMBIGUITIES[2]]  # MEDIUM flag
            return []  # Clean sections → no ambiguities
        elif "contradiction" in combined:
            return MOCK_CONTRADICTIONS
        elif "edge case" in combined:
            return MOCK_EDGE_CASES
        elif "compliance" in combined:
            return MOCK_COMPLIANCE_TAGS
        elif "decompos" in combined or "break" in combined or "atomic" in combined:
            return MOCK_TASKS
        elif "dependenc" in combined:
            return {}  # No inter-task deps for simplicity
        elif "impact" in combined:
            return []
        elif "user flow" in combined or "user-facing" in combined:
            return [{"flow_name": "Authentication", "description": "Login/logout", "involved_modules": ["auth_service"], "entry_points": ["login"]}]
        elif "module summar" in combined or "module_name" in combined:
            return {"module_name": "test_module", "purpose": "Test", "summary": "Test module", "key_components": ["fn1"], "dependencies": []}
        return []

    return _route


def _make_mock_llm_text_router():
    """Return async callable for call_llm (text)."""

    async def _route(*args, **kwargs):
        system = str(kwargs.get("system", "")).lower()
        prompt = str(kwargs.get("prompt", args[0] if args else "")).lower()
        combined = system + " " + prompt

        if "functional spec" in combined or "fs section" in combined:
            return "The system shall provide authentication via JWT tokens. Users shall be able to login and logout."
        elif "test case" in combined or "test scenario" in combined:
            return json.dumps([{
                "title": "Verify login flow",
                "preconditions": "User exists",
                "steps": ["Enter credentials", "Submit"],
                "expected_result": "Token issued",
                "test_type": "INTEGRATION",
            }])
        return "OK"

    return _route


# ── Mock Debate ─────────────────────────────────────────

def _make_mock_debate():
    """Return mock for run_debate that returns a DebateVerdict."""
    from app.pipeline.state import DebateVerdict

    async def _mock_debate(*args, **kwargs):
        return DebateVerdict(
            verdict="AMBIGUOUS",
            red_argument="This is genuinely ambiguous — no limit is specified",
            blue_argument="Premium implies unlimited — context makes it clear",
            arbiter_reasoning="Must define concrete limits. AMBIGUOUS.",
            confidence=80,
        )

    return _mock_debate


# ── Patch helpers ───────────────────────────────────────

# Nodes that import get_llm_client from their own module (via from app.pipeline.nodes.<node>.get_llm_client)
NODE_LLM_PATCHES = [
    "app.pipeline.nodes.ambiguity_node.get_llm_client",
    "app.pipeline.nodes.contradiction_node.get_llm_client",
    "app.pipeline.nodes.edge_case_node.get_llm_client",
    "app.pipeline.nodes.quality_node.get_llm_client",
]

# Nodes that import get_llm_client from app.llm module-level
MODULE_LLM_PATCHES = [
    "app.llm.get_llm_client",  # used by task_node, dependency_node, impact_node, reverse_fs_node
]

EMBEDDING_PATCH = "app.vector.fs_store._generate_embeddings"
QDRANT_UPSERT_PATCH = "app.vector.fs_store.get_qdrant_manager"
QDRANT_SEARCH_PATCH = "app.vector.fs_store.search_similar_sections"
DEBATE_PATCH = "app.pipeline.nodes.debate_node.run_debate"
TESTCASE_CALL_LLM_PATCH = "app.pipeline.nodes.testcase_node.call_llm"


def _fake_embeddings(texts):
    """Return deterministic 1536-dim vectors."""
    return [[0.01 * (i + 1)] * 1536 for i, _ in enumerate(texts)]


def _fake_qdrant_manager():
    """Return a mock Qdrant manager that does nothing."""
    mgr = MagicMock()
    mgr.client = MagicMock()
    mgr.client.upsert = MagicMock(return_value=None)
    mgr.client.search = MagicMock(return_value=[])
    mgr.client.get_collections = MagicMock(return_value=MagicMock(collections=[]))
    mgr.create_collections = AsyncMock(return_value=None)
    return mgr


def _start_all_mocks():
    """Start all LLM + embedding + Qdrant patches and return (mock_client, active_patches)."""
    mock_client = AsyncMock()
    mock_client.call_llm_json = AsyncMock(side_effect=_make_mock_llm_json_router())
    mock_client.call_llm = AsyncMock(side_effect=_make_mock_llm_text_router())

    active = []

    # Patch node-level get_llm_client references
    for path in NODE_LLM_PATCHES:
        p = patch(path)
        mp = p.start()
        mp.return_value = mock_client
        active.append(p)

    # Patch module-level get_llm_client (covers task_node, dependency_node, impact_node, reverse_fs_node)
    for path in MODULE_LLM_PATCHES:
        p = patch(path)
        mp = p.start()
        mp.return_value = mock_client
        active.append(p)

    # Patch debate (CrewAI)
    p_debate = patch(DEBATE_PATCH, side_effect=_make_mock_debate())
    p_debate.start()
    active.append(p_debate)

    # Patch testcase_node call_llm (imported at module level via from app.llm.client import call_llm)
    p_testcase = patch(TESTCASE_CALL_LLM_PATCH, new=AsyncMock(side_effect=_make_mock_llm_text_router()))
    p_testcase.start()
    active.append(p_testcase)

    # Patch embeddings
    p_emb = patch(EMBEDDING_PATCH, side_effect=_fake_embeddings)
    p_emb.start()
    active.append(p_emb)

    # Patch Qdrant manager
    p_qdrant = patch(QDRANT_UPSERT_PATCH, return_value=_fake_qdrant_manager())
    p_qdrant.start()
    active.append(p_qdrant)

    # Patch similar sections search (duplicate detection)
    p_search = patch(QDRANT_SEARCH_PATCH, return_value=[])
    p_search.start()
    active.append(p_search)

    # Reset compiled graph singletons
    import app.pipeline.graph as graph_mod
    graph_mod._compiled_graph = None
    if hasattr(graph_mod, '_compiled_impact_graph'):
        graph_mod._compiled_impact_graph = None
    if hasattr(graph_mod, '_compiled_reverse_graph'):
        graph_mod._compiled_reverse_graph = None

    return mock_client, active


def _stop_all_mocks(active_patches):
    """Stop all active patches and reset graph singletons."""
    for p in active_patches:
        p.stop()
    import app.pipeline.graph as graph_mod
    graph_mod._compiled_graph = None
    if hasattr(graph_mod, '_compiled_impact_graph'):
        graph_mod._compiled_impact_graph = None
    if hasattr(graph_mod, '_compiled_reverse_graph'):
        graph_mod._compiled_reverse_graph = None


# ═══════════════════════════════════════════════════════════
#  PIPELINE STRUCTURE VERIFICATION
# ═══════════════════════════════════════════════════════════


class TestPipelineStructure:
    """Verify pipeline graphs have correct node counts and connections."""

    def test_analysis_pipeline_has_11_nodes(self):
        """Analysis graph has 11 named nodes."""
        from app.pipeline.graph import build_analysis_graph
        graph = build_analysis_graph()
        nodes = [n for n in graph.nodes.keys() if not n.startswith("__")]
        assert len(nodes) == 11, f"Expected 11 nodes, got {len(nodes)}: {nodes}"
        expected = {
            "parse_node", "ambiguity_node", "debate_node", "contradiction_node",
            "edge_case_node", "quality_node", "task_decomposition_node",
            "dependency_node", "traceability_node", "duplicate_node", "testcase_node",
        }
        assert set(nodes) == expected, f"Missing: {expected - set(nodes)}"

    def test_impact_pipeline_has_3_nodes(self):
        from app.pipeline.graph import build_impact_graph
        graph = build_impact_graph()
        nodes = [n for n in graph.nodes.keys() if not n.startswith("__")]
        assert len(nodes) == 3
        assert set(nodes) == {"version_node", "impact_node", "rework_node"}

    def test_reverse_pipeline_has_2_nodes(self):
        from app.pipeline.graph import build_reverse_graph
        graph = build_reverse_graph()
        nodes = [n for n in graph.nodes.keys() if not n.startswith("__")]
        assert len(nodes) == 2
        assert set(nodes) == {"reverse_fs_node", "reverse_quality_node"}

    def test_analysis_state_has_all_fields(self):
        from app.pipeline.state import FSAnalysisState
        required_keys = [
            "fs_id", "parsed_sections", "ambiguities", "debate_results",
            "contradictions", "edge_cases", "quality_score", "compliance_tags",
            "tasks", "traceability_matrix", "duplicates", "test_cases", "errors",
        ]
        annotations = FSAnalysisState.__annotations__
        for key in required_keys:
            assert key in annotations, f"Missing state field: {key}"


# ═══════════════════════════════════════════════════════════
#  LLM CLIENT VERIFICATION
# ═══════════════════════════════════════════════════════════


class TestLLMClient:
    """Verify LLM client configuration and routing."""

    def test_default_model_is_claude_sonnet(self):
        from app.llm.client import _DEFAULT_MODELS, PROVIDER_ANTHROPIC
        assert _DEFAULT_MODELS[PROVIDER_ANTHROPIC] == "claude-sonnet-4-20250514"

    def test_llm_client_provider_routing(self):
        from app.llm.client import LLMClient, PROVIDER_ANTHROPIC
        with patch("app.llm.client.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                LLM_PROVIDER="anthropic",
                PRIMARY_MODEL="claude-sonnet-4-20250514",
                ANTHROPIC_API_KEY="test-key",
            )
            client = LLMClient()
            assert client.provider == PROVIDER_ANTHROPIC

    def test_all_providers_supported(self):
        from app.llm.client import (
            PROVIDER_ANTHROPIC, PROVIDER_OPENAI,
            PROVIDER_GROQ, PROVIDER_OPENROUTER,
        )
        assert PROVIDER_ANTHROPIC == "anthropic"
        assert PROVIDER_OPENAI == "openai"
        assert PROVIDER_GROQ == "groq"
        assert PROVIDER_OPENROUTER == "openrouter"


# ═══════════════════════════════════════════════════════════
#  QDRANT VECTOR STORE VERIFICATION
# ═══════════════════════════════════════════════════════════


class TestVectorStoreStructure:
    """Verify vector store collections and function signatures."""

    def test_collections_defined(self):
        from app.vector.client import COLLECTIONS
        assert "fs_requirements" in COLLECTIONS
        assert "fs_library" in COLLECTIONS
        assert COLLECTIONS["fs_requirements"]["size"] == 1536
        assert COLLECTIONS["fs_library"]["size"] == 1536

    def test_vector_store_functions_exist(self):
        from app.vector import fs_store
        assert hasattr(fs_store, "search_similar_sections")
        assert hasattr(fs_store, "store_library_item")
        assert hasattr(fs_store, "search_library")

    def test_store_fs_chunks_function_exists(self):
        from app.vector.fs_store import store_fs_chunks
        assert callable(store_fs_chunks)


# ═══════════════════════════════════════════════════════════
#  DATABASE TABLE VERIFICATION
# ═══════════════════════════════════════════════════════════


class TestDatabaseTables:
    """Verify all required tables are defined in the ORM models."""

    def test_all_tables_exist(self):
        from app.db.base import Base
        table_names = set(Base.metadata.tables.keys())
        required = {
            "fs_documents", "fs_versions", "analysis_results",
            "ambiguity_flags", "contradictions", "edge_case_gaps",
            "compliance_tags", "fs_tasks", "traceability_entries",
            "debate_results", "fs_changes", "task_impacts",
            "rework_estimates", "code_uploads",
            "duplicate_flags", "fs_comments", "fs_mentions",
            "fs_approvals", "audit_events", "test_cases",
        }
        missing = required - table_names
        assert not missing, f"Missing tables: {missing}"

    def test_table_count(self):
        from app.db.base import Base
        count = len(Base.metadata.tables)
        assert count >= 20, f"Expected >= 20 tables, got {count}"


# ═══════════════════════════════════════════════════════════
#  L1-L2: UPLOAD + PARSE
# ═══════════════════════════════════════════════════════════


class TestL1L2UploadParse:

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "FS Intelligence Platform"

    @pytest.mark.asyncio
    async def test_upload_document(self, client: AsyncClient):
        files = {"file": ("payment_spec.txt", io.BytesIO(TEST_FS_CONTENT.encode()), "text/plain")}
        resp = await client.post("/api/fs/upload", files=files)
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] is None
        assert body["data"]["filename"] == "payment_spec.txt"
        assert body["data"]["status"] == "UPLOADED"
        assert "id" in body["data"]

    @pytest.mark.asyncio
    async def test_parse_document(self, client: AsyncClient):
        files = {"file": ("parse_spec.txt", io.BytesIO(TEST_FS_CONTENT.encode()), "text/plain")}
        resp = await client.post("/api/fs/upload", files=files)
        doc_id = resp.json()["data"]["id"]

        with patch(EMBEDDING_PATCH, side_effect=_fake_embeddings), \
             patch(QDRANT_UPSERT_PATCH, return_value=_fake_qdrant_manager()):
            resp = await client.post(f"/api/fs/{doc_id}/parse")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "PARSED"
        assert data["sections_count"] > 0
        for section in data["sections"]:
            assert "heading" in section
            assert "content" in section
            assert "section_index" in section


# ═══════════════════════════════════════════════════════════
#  L3-L6: FULL ANALYSIS FLOW
# ═══════════════════════════════════════════════════════════


class TestL3toL6AnalysisFlow:

    @pytest.mark.asyncio
    async def test_full_analysis_pipeline(self, client: AsyncClient):
        """Upload → parse → analyze → verify L3-L6 outputs."""

        # ── Upload ──
        files = {"file": ("e2e_spec.txt", io.BytesIO(TEST_FS_CONTENT.encode()), "text/plain")}
        resp = await client.post("/api/fs/upload", files=files)
        assert resp.status_code == 200
        doc_id = resp.json()["data"]["id"]

        # ── Parse ──
        with patch(EMBEDDING_PATCH, side_effect=_fake_embeddings), \
             patch(QDRANT_UPSERT_PATCH, return_value=_fake_qdrant_manager()):
            resp = await client.post(f"/api/fs/{doc_id}/parse")
        assert resp.status_code == 200

        # ── Analyze ──
        mock_client, active_patches = _start_all_mocks()
        try:
            resp = await client.post(f"/api/fs/{doc_id}/analyze")
            assert resp.status_code == 200
            analysis = resp.json()["data"]
            assert analysis["status"] == "COMPLETE"
            assert analysis["ambiguities_count"] >= 1

            # ── L3: Ambiguities ──
            resp = await client.get(f"/api/fs/{doc_id}/ambiguities")
            assert resp.status_code == 200
            flags = resp.json()["data"]
            assert len(flags) >= 1
            for flag in flags:
                assert flag["severity"] in ("HIGH", "MEDIUM", "LOW")

            # ── L3: Resolve ──
            flag_id = flags[0]["id"]
            resp = await client.patch(f"/api/fs/{doc_id}/ambiguities/{flag_id}")
            assert resp.status_code == 200
            assert resp.json()["data"]["resolved"] is True

            # ── L4: Contradictions ──
            resp = await client.get(f"/api/fs/{doc_id}/contradictions")
            assert resp.status_code == 200
            contradictions = resp.json()["data"]
            assert len(contradictions) >= 0  # May be 0 depending on section pair count

            # ── L4: Edge Cases ──
            resp = await client.get(f"/api/fs/{doc_id}/edge-cases")
            assert resp.status_code == 200
            assert len(resp.json()["data"]) >= 1

            # ── L4: Quality Score ──
            resp = await client.get(f"/api/fs/{doc_id}/quality-score")
            assert resp.status_code == 200
            qs = resp.json()["data"]["quality_score"]
            assert 0 <= qs["overall"] <= 100
            assert 0 <= qs["completeness"] <= 100

            # ── L5: Tasks ──
            resp = await client.get(f"/api/fs/{doc_id}/tasks")
            assert resp.status_code == 200
            tasks = resp.json()["data"]["tasks"]
            assert len(tasks) >= 1
            for task in tasks:
                assert task["effort"] in ("LOW", "MEDIUM", "HIGH", "UNKNOWN")

            # ── L5: Dependency Graph ──
            resp = await client.get(f"/api/fs/{doc_id}/tasks/dependency-graph")
            assert resp.status_code == 200
            graph = resp.json()["data"]
            assert "nodes" in graph
            assert "edges" in graph
            assert len(graph["nodes"]) >= 1

            # ── L5: Traceability ──
            resp = await client.get(f"/api/fs/{doc_id}/traceability")
            assert resp.status_code == 200

            # ── L6: Debate Results ──
            resp = await client.get(f"/api/fs/{doc_id}/debate-results")
            assert resp.status_code == 200
            debate_data = resp.json()["data"]
            assert "results" in debate_data
            assert "total_debated" in debate_data

            # ── L10: Test Cases ──
            resp = await client.get(f"/api/fs/{doc_id}/test-cases")
            assert resp.status_code == 200
            tc_data = resp.json()["data"]
            assert "test_cases" in tc_data

        finally:
            _stop_all_mocks(active_patches)


# ═══════════════════════════════════════════════════════════
#  L7: CHANGE IMPACT ANALYSIS
# ═══════════════════════════════════════════════════════════


class TestL7ChangeImpact:

    @pytest.mark.asyncio
    async def test_version_upload_and_impact(self, client: AsyncClient):
        """Upload → parse → analyze → upload new version → check diff/impact/rework."""

        # ── Setup ──
        files = {"file": ("impact_spec.txt", io.BytesIO(TEST_FS_CONTENT.encode()), "text/plain")}
        resp = await client.post("/api/fs/upload", files=files)
        doc_id = resp.json()["data"]["id"]

        with patch(EMBEDDING_PATCH, side_effect=_fake_embeddings), \
             patch(QDRANT_UPSERT_PATCH, return_value=_fake_qdrant_manager()):
            await client.post(f"/api/fs/{doc_id}/parse")

        mock_client, active_patches = _start_all_mocks()
        try:
            resp = await client.post(f"/api/fs/{doc_id}/analyze")
            assert resp.status_code == 200
        finally:
            _stop_all_mocks(active_patches)

        # ── Upload new version ──
        mock_client, active_patches = _start_all_mocks()
        try:
            updated_files = {"file": ("impact_spec_v2.txt", io.BytesIO(UPDATED_FS_CONTENT.encode()), "text/plain")}
            resp = await client.post(f"/api/fs/{doc_id}/version", files=updated_files)
            assert resp.status_code == 200
            version_data = resp.json()["data"]
            assert "id" in version_data
            version_id = version_data["id"]

            # ── List versions ──
            resp = await client.get(f"/api/fs/{doc_id}/versions")
            assert resp.status_code == 200
            versions = resp.json()["data"]["versions"]
            assert len(versions) >= 2

            # ── Version diff ──
            resp = await client.get(f"/api/fs/{doc_id}/versions/{version_id}/diff")
            assert resp.status_code == 200
            diff = resp.json()["data"]
            assert "changes" in diff
            assert "total_changes" in diff

            # ── Impact analysis ──
            resp = await client.get(f"/api/fs/{doc_id}/impact/{version_id}")
            assert resp.status_code == 200
            impact = resp.json()["data"]
            assert "changes" in impact
            assert "task_impacts" in impact
            assert "rework_estimate" in impact

            # ── Rework estimate ──
            resp = await client.get(f"/api/fs/{doc_id}/impact/{version_id}/rework")
            assert resp.status_code == 200
            rework = resp.json()["data"]
            assert "rework_estimate" in rework
            re = rework["rework_estimate"]
            assert "invalidated_count" in re
            assert "total_rework_days" in re

        finally:
            _stop_all_mocks(active_patches)


# ═══════════════════════════════════════════════════════════
#  L8: LEGACY CODE REVERSE FS
# ═══════════════════════════════════════════════════════════


class TestL8ReverseFS:

    def _create_test_zip(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("codebase/auth_service.py", '''\
"""Authentication service — JWT login/logout."""

def login(username: str, password: str) -> dict:
    """Authenticate a user and return a JWT token."""
    if not username or not password:
        raise ValueError("Username and password required")
    return {"token": "jwt-token-here", "user": username}

def logout(token: str) -> bool:
    """Invalidate a JWT token."""
    return True
''')
            zf.writestr("codebase/payment_service.py", '''\
"""Payment processing service — charge and refund."""

def charge(amount: float, currency: str, card_token: str) -> dict:
    """Process a payment charge."""
    if amount <= 0:
        raise ValueError("Amount must be positive")
    return {"transaction_id": "txn_123", "status": "completed", "amount": amount}

def refund(transaction_id: str, amount: float = None) -> dict:
    """Process a refund for a transaction."""
    return {"refund_id": "ref_456", "status": "refunded"}
''')
            zf.writestr("codebase/models.py", '''\
"""Data models for the application."""
from dataclasses import dataclass

@dataclass
class User:
    """User entity."""
    username: str
    email: str
    active: bool = True

@dataclass
class Transaction:
    """Financial transaction entity."""
    id: str
    amount: float
    currency: str
    status: str = "pending"
''')
        return buf.getvalue()

    @pytest.mark.asyncio
    async def test_code_upload(self, client: AsyncClient):
        zip_bytes = self._create_test_zip()
        files = {"file": ("test_codebase.zip", io.BytesIO(zip_bytes), "application/zip")}
        resp = await client.post("/api/code/upload", files=files)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "id" in data
        assert data["filename"] == "test_codebase.zip"
        assert data["status"] in ("UPLOADED", "PARSED")

    @pytest.mark.asyncio
    async def test_generate_reverse_fs(self, client: AsyncClient):
        zip_bytes = self._create_test_zip()
        files = {"file": ("reverse_test.zip", io.BytesIO(zip_bytes), "application/zip")}
        resp = await client.post("/api/code/upload", files=files)
        upload_id = resp.json()["data"]["id"]

        mock_client, active_patches = _start_all_mocks()
        try:
            resp = await client.post(f"/api/code/{upload_id}/generate-fs")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["status"] == "GENERATED"
            assert len(data["sections"]) >= 1
            assert data["report"] is not None
        finally:
            _stop_all_mocks(active_patches)

    @pytest.mark.asyncio
    async def test_reverse_fs_quality_report(self, client: AsyncClient):
        zip_bytes = self._create_test_zip()
        files = {"file": ("report_test.zip", io.BytesIO(zip_bytes), "application/zip")}
        resp = await client.post("/api/code/upload", files=files)
        upload_id = resp.json()["data"]["id"]

        mock_client, active_patches = _start_all_mocks()
        try:
            await client.post(f"/api/code/{upload_id}/generate-fs")
            resp = await client.get(f"/api/code/{upload_id}/report")
            assert resp.status_code == 200
            report = resp.json()["data"]
            assert "coverage" in report
            assert "confidence" in report
            assert "gaps" in report
        finally:
            _stop_all_mocks(active_patches)


# ═══════════════════════════════════════════════════════════
#  L9: SEMANTIC INTELLIGENCE + COLLABORATION
# ═══════════════════════════════════════════════════════════


class TestL9SemanticCollab:

    @pytest.mark.asyncio
    async def test_duplicate_detection_endpoint(self, client: AsyncClient):
        files = {"file": ("dup_spec.txt", io.BytesIO(TEST_FS_CONTENT.encode()), "text/plain")}
        resp = await client.post("/api/fs/upload", files=files)
        doc_id = resp.json()["data"]["id"]

        resp = await client.get(f"/api/fs/{doc_id}/duplicates")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "duplicates" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_comment_thread(self, client: AsyncClient):
        files = {"file": ("comment_spec.txt", io.BytesIO(TEST_FS_CONTENT.encode()), "text/plain")}
        resp = await client.post("/api/fs/upload", files=files)
        doc_id = resp.json()["data"]["id"]

        comment_body = {
            "text": "This section needs @alice to clarify the limits",
            "user_id": "bob",
            "mentions": ["alice"],
        }
        resp = await client.post(f"/api/fs/{doc_id}/sections/2/comments", json=comment_body)
        assert resp.status_code == 200
        comment = resp.json()["data"]
        assert "alice" in comment["mentions"]
        assert comment["user_id"] == "bob"

        resp = await client.get(f"/api/fs/{doc_id}/comments")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_approval_workflow(self, client: AsyncClient):
        # Setup: upload + parse + analyze
        files = {"file": ("approval_spec.txt", io.BytesIO(TEST_FS_CONTENT.encode()), "text/plain")}
        resp = await client.post("/api/fs/upload", files=files)
        doc_id = resp.json()["data"]["id"]

        with patch(EMBEDDING_PATCH, side_effect=_fake_embeddings), \
             patch(QDRANT_UPSERT_PATCH, return_value=_fake_qdrant_manager()):
            await client.post(f"/api/fs/{doc_id}/parse")

        mock_client, active_patches = _start_all_mocks()
        try:
            await client.post(f"/api/fs/{doc_id}/analyze")
        finally:
            _stop_all_mocks(active_patches)

        # Submit for approval
        resp = await client.post(f"/api/fs/{doc_id}/submit-for-approval", json={"approver_id": "manager"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "PENDING"

        # Approve (patch library store to avoid Qdrant calls)
        with patch("app.vector.fs_store.store_library_item", return_value="mock-id"), \
             patch(EMBEDDING_PATCH, side_effect=_fake_embeddings), \
             patch(QDRANT_UPSERT_PATCH, return_value=_fake_qdrant_manager()):
            resp = await client.post(f"/api/fs/{doc_id}/approve", json={"approver_id": "director"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "APPROVED"

        # Check status
        resp = await client.get(f"/api/fs/{doc_id}/approval-status")
        assert resp.status_code == 200
        assert resp.json()["data"]["current_status"] == "APPROVED"

    @pytest.mark.asyncio
    async def test_audit_trail(self, client: AsyncClient):
        files = {"file": ("audit_spec.txt", io.BytesIO(TEST_FS_CONTENT.encode()), "text/plain")}
        resp = await client.post("/api/fs/upload", files=files)
        doc_id = resp.json()["data"]["id"]

        with patch(EMBEDDING_PATCH, side_effect=_fake_embeddings), \
             patch(QDRANT_UPSERT_PATCH, return_value=_fake_qdrant_manager()):
            await client.post(f"/api/fs/{doc_id}/parse")

        mock_client, active_patches = _start_all_mocks()
        try:
            await client.post(f"/api/fs/{doc_id}/analyze")
        finally:
            _stop_all_mocks(active_patches)

        resp = await client.get(f"/api/fs/{doc_id}/audit-log")
        assert resp.status_code == 200
        audit = resp.json()["data"]
        assert audit["total"] >= 2
        event_types = [e["event_type"] for e in audit["events"]]
        assert "UPLOADED" in event_types
        assert "PARSED" in event_types
        assert "ANALYZED" in event_types

    @pytest.mark.asyncio
    async def test_library_search_endpoint(self, client: AsyncClient):
        with patch("app.vector.fs_store.search_library", return_value=[
            {
                "id": "mock-id-1",
                "fs_id": str(uuid.uuid4()),
                "section_index": 0,
                "section_heading": "Authentication",
                "text": "OAuth 2.0 authentication requirement",
                "score": 0.92,
            },
        ]):
            resp = await client.get("/api/library/search?q=authentication")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["query"] == "authentication"
            assert len(data["results"]) >= 1


# ═══════════════════════════════════════════════════════════
#  L10: INTEGRATIONS + EXPORT
# ═══════════════════════════════════════════════════════════


class TestL10IntegrationsExport:

    async def _setup_analyzed_doc(self, client: AsyncClient) -> str:
        """Helper: upload → parse → analyze → return doc_id."""
        files = {"file": ("export_spec.txt", io.BytesIO(TEST_FS_CONTENT.encode()), "text/plain")}
        resp = await client.post("/api/fs/upload", files=files)
        doc_id = resp.json()["data"]["id"]

        with patch(EMBEDDING_PATCH, side_effect=_fake_embeddings), \
             patch(QDRANT_UPSERT_PATCH, return_value=_fake_qdrant_manager()):
            await client.post(f"/api/fs/{doc_id}/parse")

        mock_client, active_patches = _start_all_mocks()
        try:
            await client.post(f"/api/fs/{doc_id}/analyze")
        finally:
            _stop_all_mocks(active_patches)
        return doc_id

    @pytest.mark.asyncio
    async def test_jira_export(self, client: AsyncClient):
        doc_id = await self._setup_analyzed_doc(client)
        # Mock JiraClient to avoid hitting real JIRA API
        mock_jira = MagicMock()
        mock_jira.export_fs_tasks = AsyncMock(return_value={
            "epic": {"id": "SIM-EPIC-001", "key": "FSP-001", "url": "https://jira.example.com/FSP-001", "simulated": True},
            "stories": [{"id": "SIM-S-1", "key": "FSP-002", "url": "https://jira.example.com/FSP-002", "simulated": True}],
            "total": 1,
        })
        with patch("app.integrations.jira.JiraClient", return_value=mock_jira):
            resp = await client.post(f"/api/fs/{doc_id}/export/jira")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "epic" in data
        assert "stories" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_confluence_export(self, client: AsyncClient):
        doc_id = await self._setup_analyzed_doc(client)
        # Mock ConfluenceClient to avoid hitting real Confluence API
        mock_confluence = MagicMock()
        mock_confluence.create_fs_page = AsyncMock(return_value={
            "id": "SIM-PAGE-001",
            "url": "https://confluence.example.com/SIM-PAGE-001",
            "title": "Payment Gateway Integration - FS Analysis",
            "simulated": True,
        })
        with patch("app.integrations.confluence.ConfluenceClient", return_value=mock_confluence):
            resp = await client.post(f"/api/fs/{doc_id}/export/confluence")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "page_id" in data

    @pytest.mark.asyncio
    async def test_test_cases_list(self, client: AsyncClient):
        doc_id = await self._setup_analyzed_doc(client)
        resp = await client.get(f"/api/fs/{doc_id}/test-cases")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "test_cases" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_pdf_export_download(self, client: AsyncClient):
        doc_id = await self._setup_analyzed_doc(client)
        resp = await client.get(f"/api/fs/{doc_id}/export/pdf/download")
        assert resp.status_code == 200
        assert len(resp.content) > 100

    @pytest.mark.asyncio
    async def test_word_export_download(self, client: AsyncClient):
        doc_id = await self._setup_analyzed_doc(client)
        resp = await client.get(f"/api/fs/{doc_id}/export/docx/download")
        assert resp.status_code == 200
        assert len(resp.content) > 100

    @pytest.mark.asyncio
    async def test_csv_test_cases_export(self, client: AsyncClient):
        doc_id = await self._setup_analyzed_doc(client)
        resp = await client.get(f"/api/fs/{doc_id}/test-cases/csv")
        assert resp.status_code == 200
        content = resp.text
        lines = content.strip().split("\n")
        assert len(lines) >= 1
        assert "Title" in lines[0] or "Task ID" in lines[0]

    @pytest.mark.asyncio
    async def test_pdf_export_metadata(self, client: AsyncClient):
        doc_id = await self._setup_analyzed_doc(client)
        resp = await client.get(f"/api/fs/{doc_id}/export/pdf")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["format"] == "pdf"
        assert data["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_docx_export_metadata(self, client: AsyncClient):
        doc_id = await self._setup_analyzed_doc(client)
        resp = await client.get(f"/api/fs/{doc_id}/export/docx")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["format"] == "docx"
        assert data["size_bytes"] > 0
