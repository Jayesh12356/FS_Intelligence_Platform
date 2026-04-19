"""L9 Semantic Intelligence + Collaboration — test suite.

Tests cover:
  - Duplicate detection node
  - Library operations (vector store)
  - Comments (create, list, resolve, mentions)
  - Approval workflow (submit, approve, reject, status transitions)
  - Audit trail (event logging, retrieval, ordering)
  - API endpoint integration
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base, get_db
from app.db.models import (
    ApprovalStatus,
    AuditEventDB,
    AuditEventType,
    DuplicateFlagDB,
    FSApprovalDB,
    FSCommentDB,
    FSDocument,
    FSDocumentStatus,
    FSMentionDB,
)
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_l9.db"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_db():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(test_db: AsyncSession):
    async def _override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _create_test_doc(db: AsyncSession, status=FSDocumentStatus.COMPLETE):
    """Helper to create a test FS document."""
    doc = FSDocument(
        id=uuid.uuid4(),
        filename="test_spec.pdf",
        status=status,
        file_size=1024,
        content_type="application/pdf",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


# ── Duplicate Detection Node Tests ─────────────────────


class TestDuplicateNode:
    """Tests for the duplicate detection pipeline node."""

    @pytest.mark.asyncio
    async def test_duplicate_node_no_sections(self):
        """Node returns empty duplicates when no sections provided."""
        from app.pipeline.nodes.duplicate_node import duplicate_node

        state = {
            "fs_id": str(uuid.uuid4()),
            "parsed_sections": [],
            "errors": [],
            "duplicates": [],
        }
        result = await duplicate_node(state)
        assert result["duplicates"] == []

    @pytest.mark.asyncio
    async def test_duplicate_node_short_content_skipped(self):
        """Node skips sections with very short content."""
        from app.pipeline.nodes.duplicate_node import duplicate_node

        state = {
            "fs_id": str(uuid.uuid4()),
            "parsed_sections": [{"heading": "Short", "content": "hi", "section_index": 0}],
            "errors": [],
            "duplicates": [],
        }
        result = await duplicate_node(state)
        assert result["duplicates"] == []

    @pytest.mark.asyncio
    async def test_duplicate_node_with_matches(self):
        """Node returns duplicates when vector store returns matches."""
        from app.pipeline.nodes.duplicate_node import duplicate_node

        mock_matches = [
            {
                "fs_id": str(uuid.uuid4()),
                "section_heading": "Login Flow",
                "text": "The user shall be able to login.",
                "score": 0.92,
            }
        ]

        state = {
            "fs_id": str(uuid.uuid4()),
            "parsed_sections": [
                {
                    "heading": "Authentication",
                    "content": "The system shall provide user authentication via login.",
                    "section_index": 0,
                }
            ],
            "errors": [],
            "duplicates": [],
        }

        with patch(
            "app.vector.fs_store.search_similar_sections",
            return_value=mock_matches,
        ):
            result = await duplicate_node(state)

        assert len(result["duplicates"]) == 1
        assert result["duplicates"][0]["similarity_score"] == 0.92

    @pytest.mark.asyncio
    async def test_duplicate_node_handles_import_error(self):
        """Node gracefully handles missing vector store."""
        from app.pipeline.nodes.duplicate_node import duplicate_node

        state = {
            "fs_id": str(uuid.uuid4()),
            "parsed_sections": [
                {
                    "heading": "Test",
                    "content": "A reasonably long section content for testing purposes.",
                    "section_index": 0,
                }
            ],
            "errors": [],
            "duplicates": [],
        }

        with patch(
            "app.vector.fs_store.search_similar_sections",
            side_effect=Exception("Qdrant down"),
        ):
            result = await duplicate_node(state)

        # Should have empty duplicates but no crash
        assert isinstance(result["duplicates"], list)

    @pytest.mark.asyncio
    async def test_duplicate_threshold(self):
        """Verify the threshold constant is set correctly."""
        from app.pipeline.nodes.duplicate_node import DUPLICATE_THRESHOLD

        assert DUPLICATE_THRESHOLD == 0.88


# ── Comment Tests ──────────────────────────────────────


class TestComments:
    """Tests for the comments/collaboration API."""

    @pytest.mark.asyncio
    async def test_add_comment(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        resp = await client.post(
            f"/api/fs/{doc.id}/sections/0/comments",
            json={"text": "This section needs clarity", "user_id": "alice"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["text"] == "This section needs clarity"
        assert data["user_id"] == "alice"
        assert data["section_index"] == 0
        assert data["resolved"] is False

    @pytest.mark.asyncio
    async def test_add_comment_empty_text(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        resp = await client.post(
            f"/api/fs/{doc.id}/sections/0/comments",
            json={"text": "   ", "user_id": "alice"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_add_comment_with_mentions(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        resp = await client.post(
            f"/api/fs/{doc.id}/sections/1/comments",
            json={
                "text": "Hey @bob, can you review this?",
                "user_id": "alice",
                "mentions": ["bob"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "bob" in data["mentions"]

    @pytest.mark.asyncio
    async def test_add_comment_auto_extract_mentions(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        resp = await client.post(
            f"/api/fs/{doc.id}/sections/2/comments",
            json={"text": "CC @charlie and @dave please", "user_id": "alice"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "charlie" in data["mentions"]
        assert "dave" in data["mentions"]

    @pytest.mark.asyncio
    async def test_list_comments(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        # Add 2 comments
        await client.post(
            f"/api/fs/{doc.id}/sections/0/comments",
            json={"text": "Comment 1", "user_id": "alice"},
        )
        await client.post(
            f"/api/fs/{doc.id}/sections/1/comments",
            json={"text": "Comment 2", "user_id": "bob"},
        )

        resp = await client.get(f"/api/fs/{doc.id}/comments")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert data["resolved_count"] == 0

    @pytest.mark.asyncio
    async def test_resolve_comment(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        # Add a comment
        add_resp = await client.post(
            f"/api/fs/{doc.id}/sections/0/comments",
            json={"text": "Needs fix", "user_id": "alice"},
        )
        comment_id = add_resp.json()["data"]["id"]

        # Resolve it
        resp = await client.patch(f"/api/fs/{doc.id}/comments/{comment_id}/resolve")
        assert resp.status_code == 200
        assert resp.json()["data"]["resolved"] is True

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_comment(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        fake_id = str(uuid.uuid4())
        resp = await client.patch(f"/api/fs/{doc.id}/comments/{fake_id}/resolve")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_comment_on_nonexistent_doc(self, client: AsyncClient, test_db: AsyncSession):
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/fs/{fake_id}/sections/0/comments",
            json={"text": "Comment", "user_id": "alice"},
        )
        assert resp.status_code == 404


# ── Approval Workflow Tests ────────────────────────────


class TestApprovalWorkflow:
    """Tests for the approval workflow API."""

    @pytest.mark.asyncio
    async def test_submit_for_approval(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db, status=FSDocumentStatus.COMPLETE)
        resp = await client.post(f"/api/fs/{doc.id}/submit-for-approval")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_submit_unparsed_doc_fails(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db, status=FSDocumentStatus.UPLOADED)
        resp = await client.post(f"/api/fs/{doc.id}/submit-for-approval")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_double_submit_fails(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db, status=FSDocumentStatus.COMPLETE)
        await client.post(f"/api/fs/{doc.id}/submit-for-approval")
        resp = await client.post(f"/api/fs/{doc.id}/submit-for-approval")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_approve_document(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db, status=FSDocumentStatus.COMPLETE)
        await client.post(f"/api/fs/{doc.id}/submit-for-approval")

        resp = await client.post(
            f"/api/fs/{doc.id}/approve",
            json={"approver_id": "reviewer1", "comment": "Looks good"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "APPROVED"
        assert data["approver_id"] == "reviewer1"

    @pytest.mark.asyncio
    async def test_approve_without_pending_fails(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db, status=FSDocumentStatus.COMPLETE)
        resp = await client.post(f"/api/fs/{doc.id}/approve")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reject_document(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db, status=FSDocumentStatus.COMPLETE)
        await client.post(f"/api/fs/{doc.id}/submit-for-approval")

        resp = await client.post(
            f"/api/fs/{doc.id}/reject",
            json={"approver_id": "reviewer1", "comment": "Needs work"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "REJECTED"

    @pytest.mark.asyncio
    async def test_approval_status(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db, status=FSDocumentStatus.COMPLETE)

        # Initially NONE
        resp = await client.get(f"/api/fs/{doc.id}/approval-status")
        assert resp.status_code == 200
        assert resp.json()["data"]["current_status"] == "NONE"

        # Submit → PENDING
        await client.post(f"/api/fs/{doc.id}/submit-for-approval")
        resp = await client.get(f"/api/fs/{doc.id}/approval-status")
        assert resp.json()["data"]["current_status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_resubmit_after_rejection(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db, status=FSDocumentStatus.COMPLETE)

        # Submit and reject
        await client.post(f"/api/fs/{doc.id}/submit-for-approval")
        await client.post(f"/api/fs/{doc.id}/reject")

        # Resubmit should succeed
        resp = await client.post(f"/api/fs/{doc.id}/submit-for-approval")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_approval_history(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db, status=FSDocumentStatus.COMPLETE)

        await client.post(f"/api/fs/{doc.id}/submit-for-approval")
        await client.post(f"/api/fs/{doc.id}/reject", json={"comment": "Fix section 3"})
        await client.post(f"/api/fs/{doc.id}/submit-for-approval")
        await client.post(f"/api/fs/{doc.id}/approve", json={"comment": "LGTM"})

        resp = await client.get(f"/api/fs/{doc.id}/approval-status")
        data = resp.json()["data"]
        assert data["current_status"] == "APPROVED"
        # approval_status returns FSApproval records, not audit events
        # 2 submissions (PENDING) + 1 rejection update + 1 approval update = 2 rows
        # (submit creates PENDING, reject updates to REJECTED, resubmit creates new PENDING, approve updates to APPROVED)
        assert data["total"] >= 2  # At least the 2 PENDING submissions turned into REJECTED/APPROVED


# ── Audit Trail Tests ──────────────────────────────────


class TestAuditTrail:
    """Tests for the audit trail API."""

    @pytest.mark.asyncio
    async def test_audit_log_empty(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        resp = await client.get(f"/api/fs/{doc.id}/audit-log")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_audit_log_after_comment(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        # Adding a comment should create COMMENT_ADDED audit event
        await client.post(
            f"/api/fs/{doc.id}/sections/0/comments",
            json={"text": "Test comment", "user_id": "alice"},
        )

        resp = await client.get(f"/api/fs/{doc.id}/audit-log")
        data = resp.json()["data"]
        assert data["total"] >= 1
        event_types = [e["event_type"] for e in data["events"]]
        assert "COMMENT_ADDED" in event_types

    @pytest.mark.asyncio
    async def test_audit_log_after_approval_flow(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db, status=FSDocumentStatus.COMPLETE)
        await client.post(f"/api/fs/{doc.id}/submit-for-approval")
        await client.post(f"/api/fs/{doc.id}/approve")

        resp = await client.get(f"/api/fs/{doc.id}/audit-log")
        data = resp.json()["data"]
        event_types = [e["event_type"] for e in data["events"]]
        assert "SUBMITTED_FOR_APPROVAL" in event_types
        assert "APPROVED" in event_types

    @pytest.mark.asyncio
    async def test_audit_log_chronological_order(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db, status=FSDocumentStatus.COMPLETE)
        await client.post(
            f"/api/fs/{doc.id}/sections/0/comments",
            json={"text": "First", "user_id": "alice"},
        )
        await client.post(f"/api/fs/{doc.id}/submit-for-approval")

        resp = await client.get(f"/api/fs/{doc.id}/audit-log")
        events = resp.json()["data"]["events"]
        assert len(events) >= 2
        # Verify chronological order
        for i in range(1, len(events)):
            if events[i]["created_at"] and events[i - 1]["created_at"]:
                assert events[i]["created_at"] >= events[i - 1]["created_at"]

    @pytest.mark.asyncio
    async def test_audit_log_nonexistent_doc(self, client: AsyncClient, test_db: AsyncSession):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/fs/{fake_id}/audit-log")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_audit_event_payload(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        await client.post(
            f"/api/fs/{doc.id}/sections/3/comments",
            json={"text": "Note", "user_id": "reporter"},
        )

        resp = await client.get(f"/api/fs/{doc.id}/audit-log")
        events = resp.json()["data"]["events"]
        comment_event = [e for e in events if e["event_type"] == "COMMENT_ADDED"]
        assert len(comment_event) == 1
        assert comment_event[0]["payload_json"]["section_index"] == 3


# ── Duplicate Router Tests ─────────────────────────────


class TestDuplicateRouter:
    """Tests for the duplicate flags API endpoint."""

    @pytest.mark.asyncio
    async def test_list_duplicates_empty(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        resp = await client.get(f"/api/fs/{doc.id}/duplicates")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["duplicates"] == []

    @pytest.mark.asyncio
    async def test_list_duplicates_with_flags(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        other_doc = await _create_test_doc(test_db)

        flag = DuplicateFlagDB(
            fs_id=doc.id,
            section_index=0,
            section_heading="Authentication",
            similar_fs_id=other_doc.id,
            similar_section_heading="Login",
            similarity_score=0.91,
            flagged_text="User shall authenticate",
            similar_text="User must log in",
        )
        test_db.add(flag)
        await test_db.flush()

        resp = await client.get(f"/api/fs/{doc.id}/duplicates")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["duplicates"][0]["similarity_score"] == 0.91

    @pytest.mark.asyncio
    async def test_list_duplicates_nonexistent_doc(self, client: AsyncClient, test_db: AsyncSession):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/fs/{fake_id}/duplicates")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicates_sorted_by_score(self, client: AsyncClient, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        other = await _create_test_doc(test_db)

        for score in [0.89, 0.95, 0.91]:
            test_db.add(
                DuplicateFlagDB(
                    fs_id=doc.id,
                    section_index=0,
                    section_heading="Test",
                    similar_fs_id=other.id,
                    similar_section_heading="Test",
                    similarity_score=score,
                )
            )
        await test_db.flush()

        resp = await client.get(f"/api/fs/{doc.id}/duplicates")
        dups = resp.json()["data"]["duplicates"]
        scores = [d["similarity_score"] for d in dups]
        assert scores == sorted(scores, reverse=True)


# ── Audit Helper Tests ─────────────────────────────────


class TestAuditHelper:
    """Tests for the audit event logging helper."""

    @pytest.mark.asyncio
    async def test_log_audit_event(self, test_db: AsyncSession):
        from app.db.audit import log_audit_event

        doc = await _create_test_doc(test_db)
        event = await log_audit_event(
            test_db,
            doc.id,
            AuditEventType.UPLOADED,
            user_id="uploader",
            payload={"filename": "test.pdf"},
        )
        await test_db.flush()

        assert event.fs_id == doc.id
        assert event.event_type == AuditEventType.UPLOADED
        assert event.user_id == "uploader"
        assert event.payload_json["filename"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_log_multiple_events(self, test_db: AsyncSession):
        from app.db.audit import log_audit_event

        doc = await _create_test_doc(test_db)
        await log_audit_event(test_db, doc.id, AuditEventType.UPLOADED)
        await log_audit_event(test_db, doc.id, AuditEventType.PARSED)
        await log_audit_event(test_db, doc.id, AuditEventType.ANALYZED)
        await test_db.flush()

        result = await test_db.execute(select(AuditEventDB).where(AuditEventDB.fs_id == doc.id))
        events = result.scalars().all()
        assert len(events) == 3


# ── DB Model Tests ─────────────────────────────────────


class TestDBModels:
    """Tests for the L9 database models."""

    @pytest.mark.asyncio
    async def test_create_duplicate_flag(self, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)
        other_doc = await _create_test_doc(test_db)

        flag = DuplicateFlagDB(
            fs_id=doc.id,
            section_index=1,
            section_heading="Section A",
            similar_fs_id=other_doc.id,
            similar_section_heading="Section B",
            similarity_score=0.93,
        )
        test_db.add(flag)
        await test_db.flush()
        await test_db.refresh(flag)
        assert flag.id is not None
        assert flag.similarity_score == 0.93

    @pytest.mark.asyncio
    async def test_create_comment_with_mention(self, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)

        comment = FSCommentDB(
            fs_id=doc.id,
            section_index=0,
            user_id="alice",
            text="Review this @bob",
        )
        test_db.add(comment)
        await test_db.flush()
        await test_db.refresh(comment)

        mention = FSMentionDB(
            comment_id=comment.id,
            mentioned_user_id="bob",
        )
        test_db.add(mention)
        await test_db.flush()
        await test_db.refresh(mention)

        assert mention.comment_id == comment.id
        assert mention.mentioned_user_id == "bob"

    @pytest.mark.asyncio
    async def test_create_approval(self, test_db: AsyncSession):
        doc = await _create_test_doc(test_db)

        approval = FSApprovalDB(
            fs_id=doc.id,
            approver_id="manager",
            status=ApprovalStatus.PENDING,
        )
        test_db.add(approval)
        await test_db.flush()
        await test_db.refresh(approval)

        assert approval.status == ApprovalStatus.PENDING

        approval.status = ApprovalStatus.APPROVED
        await test_db.flush()
        await test_db.refresh(approval)
        assert approval.status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_audit_event_types(self):
        """Verify all expected audit event types exist."""
        expected = [
            "UPLOADED",
            "PARSED",
            "ANALYZED",
            "APPROVED",
            "REJECTED",
            "VERSION_ADDED",
            "TASKS_GENERATED",
            "EXPORTED",
            "COMMENT_ADDED",
            "COMMENT_RESOLVED",
            "SUBMITTED_FOR_APPROVAL",
        ]
        for e in expected:
            assert hasattr(AuditEventType, e)

    @pytest.mark.asyncio
    async def test_approval_status_enum(self):
        """Verify approval status enum values."""
        assert ApprovalStatus.PENDING.value == "PENDING"
        assert ApprovalStatus.APPROVED.value == "APPROVED"
        assert ApprovalStatus.REJECTED.value == "REJECTED"


# ── Comment Mention Extraction Tests ────────────────────


class TestMentionExtraction:
    """Tests for the @-mention extraction utility."""

    def test_extract_single_mention(self):
        from app.api.collab_router import _extract_mentions

        assert _extract_mentions("Hello @alice") == ["alice"]

    def test_extract_multiple_mentions(self):
        from app.api.collab_router import _extract_mentions

        result = _extract_mentions("CC @alice and @bob please")
        assert "alice" in result
        assert "bob" in result

    def test_extract_no_mentions(self):
        from app.api.collab_router import _extract_mentions

        assert _extract_mentions("No mentions here") == []

    def test_extract_mention_at_start(self):
        from app.api.collab_router import _extract_mentions

        assert _extract_mentions("@admin check this") == ["admin"]
