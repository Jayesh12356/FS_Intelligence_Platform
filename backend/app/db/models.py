"""Database ORM models for the FS Intelligence Platform."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.types import JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class FSDocumentStatus(str, enum.Enum):
    """Processing status for an FS document."""
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    PARSED = "PARSED"
    ANALYZING = "ANALYZING"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"
    DELETED = "DELETED"


class AmbiguitySeverity(str, enum.Enum):
    """Severity level for ambiguity flags."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EffortLevel(str, enum.Enum):
    """Effort complexity for a dev task."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class ChangeType(str, enum.Enum):
    """Type of change between FS versions."""
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"


class ImpactType(str, enum.Enum):
    """Impact level on a task from an FS change."""
    INVALIDATED = "INVALIDATED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    UNAFFECTED = "UNAFFECTED"


class FSDocument(Base):
    """An uploaded Functional Specification document."""

    __tablename__ = "fs_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(512), nullable=False)
    original_text = Column(Text, nullable=True)
    parsed_text = Column(Text, nullable=True)
    status = Column(
        Enum(FSDocumentStatus),
        nullable=False,
        default=FSDocumentStatus.UPLOADED,
    )
    file_path = Column(String(1024), nullable=True)
    file_size = Column(Integer, nullable=True)
    content_type = Column(String(128), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    versions = relationship("FSVersion", back_populates="document", cascade="all, delete-orphan")
    analysis_results = relationship("AnalysisResult", back_populates="document", cascade="all, delete-orphan")
    ambiguity_flags = relationship("AmbiguityFlagDB", back_populates="document", cascade="all, delete-orphan")
    contradictions = relationship("ContradictionDB", back_populates="document", cascade="all, delete-orphan")
    edge_case_gaps = relationship("EdgeCaseGapDB", back_populates="document", cascade="all, delete-orphan")
    compliance_tags = relationship("ComplianceTagDB", back_populates="document", cascade="all, delete-orphan")
    tasks = relationship("FSTaskDB", back_populates="document", cascade="all, delete-orphan")
    traceability_entries = relationship("TraceabilityEntryDB", back_populates="document", cascade="all, delete-orphan")
    debate_results = relationship("DebateResultDB", back_populates="document", cascade="all, delete-orphan")
    fs_changes = relationship("FSChangeDB", back_populates="document", cascade="all, delete-orphan")
    task_impacts = relationship("TaskImpactDB", back_populates="document", cascade="all, delete-orphan")
    rework_estimates = relationship("ReworkEstimateDB", back_populates="document", cascade="all, delete-orphan")
    # L9 relationships
    duplicate_flags = relationship("DuplicateFlagDB", back_populates="document", cascade="all, delete-orphan")
    comments = relationship("FSCommentDB", back_populates="document", cascade="all, delete-orphan")
    approvals = relationship("FSApprovalDB", back_populates="document", cascade="all, delete-orphan")
    audit_events = relationship("AuditEventDB", back_populates="document", cascade="all, delete-orphan")
    # L10 relationships
    test_cases = relationship("TestCaseDB", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<FSDocument id={self.id} filename={self.filename} status={self.status}>"


class FSVersion(Base):
    """Version tracking for an FS document."""

    __tablename__ = "fs_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False, default=1)
    content_hash = Column(String(128), nullable=True)
    diff_summary = Column(Text, nullable=True)
    parsed_text = Column(Text, nullable=True)
    file_path = Column(String(1024), nullable=True)
    file_size = Column(Integer, nullable=True)
    content_type = Column(String(128), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="versions")
    changes = relationship("FSChangeDB", back_populates="version", cascade="all, delete-orphan")
    impacts = relationship("TaskImpactDB", back_populates="version", cascade="all, delete-orphan")
    rework_estimate = relationship("ReworkEstimateDB", back_populates="version", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<FSVersion id={self.id} fs_id={self.fs_id} v={self.version_number}>"


class AnalysisResult(Base):
    """Stores analysis results (ambiguity, tasks, etc.) for an FS document."""

    __tablename__ = "analysis_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    analysis_type = Column(String(64), nullable=False)
    result_json = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="analysis_results")

    def __repr__(self) -> str:
        return f"<AnalysisResult id={self.id} type={self.analysis_type}>"


class AmbiguityFlagDB(Base):
    """Persisted ambiguity flag detected in an FS document section."""

    __tablename__ = "ambiguity_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    section_index = Column(Integer, nullable=False)
    section_heading = Column(String(512), nullable=False)
    flagged_text = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    severity = Column(
        Enum(AmbiguitySeverity),
        nullable=False,
        default=AmbiguitySeverity.MEDIUM,
    )
    clarification_question = Column(Text, nullable=False)
    resolved = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="ambiguity_flags")

    def __repr__(self) -> str:
        return f"<AmbiguityFlagDB id={self.id} severity={self.severity} resolved={self.resolved}>"


class ContradictionDB(Base):
    """Persisted contradiction detected between two FS document sections."""

    __tablename__ = "contradictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    section_a_index = Column(Integer, nullable=False)
    section_a_heading = Column(String(512), nullable=False)
    section_b_index = Column(Integer, nullable=False)
    section_b_heading = Column(String(512), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(
        Enum(AmbiguitySeverity),
        nullable=False,
        default=AmbiguitySeverity.MEDIUM,
    )
    suggested_resolution = Column(Text, nullable=False)
    resolved = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="contradictions")

    def __repr__(self) -> str:
        return f"<ContradictionDB id={self.id} severity={self.severity}>"


class EdgeCaseGapDB(Base):
    """Persisted edge case gap detected in an FS document section."""

    __tablename__ = "edge_case_gaps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    section_index = Column(Integer, nullable=False)
    section_heading = Column(String(512), nullable=False)
    scenario_description = Column(Text, nullable=False)
    impact = Column(
        Enum(AmbiguitySeverity),
        nullable=False,
        default=AmbiguitySeverity.MEDIUM,
    )
    suggested_addition = Column(Text, nullable=False)
    resolved = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="edge_case_gaps")

    def __repr__(self) -> str:
        return f"<EdgeCaseGapDB id={self.id} impact={self.impact}>"


class ComplianceTagDB(Base):
    """Persisted compliance tag for an FS document section."""

    __tablename__ = "compliance_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    section_index = Column(Integer, nullable=False)
    section_heading = Column(String(512), nullable=False)
    tag = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="compliance_tags")

    def __repr__(self) -> str:
        return f"<ComplianceTagDB id={self.id} tag={self.tag}>"


class FSTaskDB(Base):
    """Persisted dev task decomposed from an FS section."""

    __tablename__ = "fs_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String(64), nullable=False, unique=True)  # Pipeline-assigned UUID
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=False)
    section_index = Column(Integer, nullable=False)
    section_heading = Column(String(512), nullable=False)
    depends_on = Column(JSON, nullable=False, default=list)  # List[str] of task_ids
    acceptance_criteria = Column(JSON, nullable=False, default=list)  # List[str]
    effort = Column(
        Enum(EffortLevel),
        nullable=False,
        default=EffortLevel.MEDIUM,
    )
    tags = Column(JSON, nullable=False, default=list)  # List[str]
    order = Column(Integer, nullable=False, default=0)
    can_parallel = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="tasks")

    def __repr__(self) -> str:
        return f"<FSTaskDB id={self.id} title={self.title[:40]} effort={self.effort}>"


class TraceabilityEntryDB(Base):
    """Persisted traceability entry linking a task to its source FS section."""

    __tablename__ = "traceability_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String(64), nullable=False)
    task_title = Column(String(512), nullable=False)
    section_index = Column(Integer, nullable=False)
    section_heading = Column(String(512), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="traceability_entries")

    def __repr__(self) -> str:
        return f"<TraceabilityEntryDB task={self.task_id} section={self.section_index}>"


class DebateResultDB(Base):
    """Persisted adversarial debate result for a HIGH severity ambiguity flag."""

    __tablename__ = "debate_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    section_index = Column(Integer, nullable=False)
    section_heading = Column(String(512), nullable=False)
    flagged_text = Column(Text, nullable=False)
    original_reason = Column(Text, nullable=False)
    verdict = Column(String(16), nullable=False)  # AMBIGUOUS or CLEAR
    red_argument = Column(Text, nullable=False)
    blue_argument = Column(Text, nullable=False)
    arbiter_reasoning = Column(Text, nullable=False)
    confidence = Column(Integer, nullable=False, default=50)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="debate_results")

    def __repr__(self) -> str:
        return f"<DebateResultDB id={self.id} verdict={self.verdict} confidence={self.confidence}>"


class FSChangeDB(Base):
    """Persisted FS change detected between two document versions (L7)."""

    __tablename__ = "fs_changes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    version_id = Column(UUID(as_uuid=True), ForeignKey("fs_versions.id", ondelete="CASCADE"), nullable=False)
    change_type = Column(
        Enum(ChangeType),
        nullable=False,
    )
    section_id = Column(String(256), nullable=False)
    section_heading = Column(String(512), nullable=False, default="")
    section_index = Column(Integer, nullable=False, default=0)
    old_text = Column(Text, nullable=True)
    new_text = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="fs_changes")
    version = relationship("FSVersion", back_populates="changes")

    def __repr__(self) -> str:
        return f"<FSChangeDB id={self.id} type={self.change_type} section={self.section_id}>"


class TaskImpactDB(Base):
    """Persisted task impact from an FS version change (L7)."""

    __tablename__ = "task_impacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    version_id = Column(UUID(as_uuid=True), ForeignKey("fs_versions.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String(64), nullable=False)
    task_title = Column(String(512), nullable=False, default="")
    impact_type = Column(
        Enum(ImpactType),
        nullable=False,
    )
    reason = Column(Text, nullable=False, default="")
    change_section = Column(String(512), nullable=False, default="")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="task_impacts")
    version = relationship("FSVersion", back_populates="impacts")

    def __repr__(self) -> str:
        return f"<TaskImpactDB id={self.id} task={self.task_id} impact={self.impact_type}>"


class ReworkEstimateDB(Base):
    """Persisted rework cost estimate for a version change (L7)."""

    __tablename__ = "rework_estimates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    version_id = Column(UUID(as_uuid=True), ForeignKey("fs_versions.id", ondelete="CASCADE"), nullable=False)
    invalidated_count = Column(Integer, nullable=False, default=0)
    review_count = Column(Integer, nullable=False, default=0)
    unaffected_count = Column(Integer, nullable=False, default=0)
    total_rework_days = Column(Float, nullable=False, default=0.0)
    affected_sections = Column(JSON, nullable=False, default=list)
    changes_summary = Column(Text, nullable=False, default="")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="rework_estimates")
    version = relationship("FSVersion", back_populates="rework_estimate")

    def __repr__(self) -> str:
        return f"<ReworkEstimateDB id={self.id} invalidated={self.invalidated_count} rework_days={self.total_rework_days}>"


# ── L8: Code Upload ────────────────────────────────────


class CodeUploadStatus(str, enum.Enum):
    """Status of a code upload through the reverse gen pipeline."""
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    PARSED = "PARSED"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    ERROR = "ERROR"


class CodeUploadDB(Base):
    """An uploaded codebase for reverse FS generation."""

    __tablename__ = "code_uploads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(512), nullable=False)
    zip_path = Column(String(1024), nullable=True)
    file_size = Column(Integer, nullable=True)

    status = Column(
        Enum(CodeUploadStatus),
        nullable=False,
        default=CodeUploadStatus.UPLOADED,
    )

    # Parsed snapshot (JSON)
    primary_language = Column(String(64), nullable=True)
    total_files = Column(Integer, nullable=True, default=0)
    total_lines = Column(Integer, nullable=True, default=0)
    languages = Column(JSON, nullable=True)
    snapshot_data = Column(JSON, nullable=True)  # Full CodebaseSnapshot as JSON

    # Generated FS
    generated_fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id"), nullable=True)
    generated_fs_text = Column(Text, nullable=True)
    generated_sections = Column(JSON, nullable=True)

    # Quality report
    coverage = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    gaps = Column(JSON, nullable=True)
    report_data = Column(JSON, nullable=True)  # Full GeneratedFSReport as JSON

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    generated_fs = relationship("FSDocument", foreign_keys=[generated_fs_id])

    def __repr__(self) -> str:
        return f"<CodeUploadDB id={self.id} filename={self.filename} status={self.status}>"


# ── L9: Semantic Intelligence + Collaboration ──────────


class ApprovalStatus(str, enum.Enum):
    """Approval workflow status."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AuditEventType(str, enum.Enum):
    """Type of audit event logged."""
    UPLOADED = "UPLOADED"
    PARSED = "PARSED"
    ANALYZED = "ANALYZED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    VERSION_ADDED = "VERSION_ADDED"
    TASKS_GENERATED = "TASKS_GENERATED"
    EXPORTED = "EXPORTED"
    COMMENT_ADDED = "COMMENT_ADDED"
    COMMENT_RESOLVED = "COMMENT_RESOLVED"
    SUBMITTED_FOR_APPROVAL = "SUBMITTED_FOR_APPROVAL"


class DuplicateFlagDB(Base):
    """Cross-document duplicate requirement detected via Qdrant similarity (L9)."""

    __tablename__ = "duplicate_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    section_index = Column(Integer, nullable=False)
    section_heading = Column(String(512), nullable=False)
    similar_fs_id = Column(UUID(as_uuid=True), nullable=False)  # The OTHER document
    similar_section_heading = Column(String(512), nullable=False, default="")
    similarity_score = Column(Float, nullable=False)
    flagged_text = Column(Text, nullable=False, default="")
    similar_text = Column(Text, nullable=False, default="")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="duplicate_flags")

    def __repr__(self) -> str:
        return f"<DuplicateFlagDB id={self.id} score={self.similarity_score:.2f}>"


class FSCommentDB(Base):
    """Section-level comment on an FS document (L9)."""

    __tablename__ = "fs_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    section_index = Column(Integer, nullable=False)
    user_id = Column(String(256), nullable=False, default="system")
    text = Column(Text, nullable=False)
    resolved = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="comments")
    mentions = relationship("FSMentionDB", back_populates="comment", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<FSCommentDB id={self.id} section={self.section_index} resolved={self.resolved}>"


class FSMentionDB(Base):
    """An @-mention within a comment (L9)."""

    __tablename__ = "fs_mentions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_id = Column(UUID(as_uuid=True), ForeignKey("fs_comments.id", ondelete="CASCADE"), nullable=False)
    mentioned_user_id = Column(String(256), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    comment = relationship("FSCommentDB", back_populates="mentions")

    def __repr__(self) -> str:
        return f"<FSMentionDB id={self.id} user={self.mentioned_user_id}>"


class FSApprovalDB(Base):
    """Approval workflow entry for an FS document (L9)."""

    __tablename__ = "fs_approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    approver_id = Column(String(256), nullable=False, default="system")
    status = Column(
        Enum(ApprovalStatus),
        nullable=False,
        default=ApprovalStatus.PENDING,
    )
    comment = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="approvals")

    def __repr__(self) -> str:
        return f"<FSApprovalDB id={self.id} status={self.status}>"


class AuditEventDB(Base):
    """Audit trail event for an FS document (L9)."""

    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(256), nullable=False, default="system")
    event_type = Column(
        Enum(AuditEventType),
        nullable=False,
    )
    payload_json = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="audit_events")

    def __repr__(self) -> str:
        return f"<AuditEventDB id={self.id} type={self.event_type}>"


# ── L10 Enums ──────────────────────────────────────────


class TestType(str, enum.Enum):
    """Type of test case."""
    UNIT = "UNIT"
    INTEGRATION = "INTEGRATION"
    E2E = "E2E"
    ACCEPTANCE = "ACCEPTANCE"


class MCPSessionStatus(str, enum.Enum):
    """Lifecycle status for an MCP-driven build session."""
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ── L10 Models ─────────────────────────────────────────


class TestCaseDB(Base):
    """Generated test case linked to an FS task (L10)."""

    __tablename__ = "test_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String(64), nullable=False)
    title = Column(String(512), nullable=False)
    preconditions = Column(Text, nullable=True, default="")
    steps = Column(JSON, nullable=False, default=list)  # List[str]
    expected_result = Column(Text, nullable=False, default="")
    test_type = Column(
        Enum(TestType),
        nullable=False,
        default=TestType.UNIT,
    )
    section_index = Column(Integer, nullable=False, default=0)
    section_heading = Column(String(512), nullable=True, default="")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    document = relationship("FSDocument", back_populates="test_cases")

    def __repr__(self) -> str:
        return f"<TestCaseDB id={self.id} task={self.task_id} type={self.test_type}>"


class MCPSessionDB(Base):
    """Persisted MCP build session metadata."""

    __tablename__ = "mcp_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fs_id = Column(UUID(as_uuid=True), ForeignKey("fs_documents.id", ondelete="SET NULL"), nullable=True)
    target_stack = Column(String(256), nullable=False, default="")
    source = Column(String(64), nullable=False, default="mcp")
    status = Column(
        Enum(MCPSessionStatus),
        nullable=False,
        default=MCPSessionStatus.RUNNING,
    )
    phase = Column(Integer, nullable=False, default=0)
    total_phases = Column(Integer, nullable=False, default=0)
    current_step = Column(String(512), nullable=False, default="")
    dry_run = Column(Boolean, nullable=False, default=False)
    meta_json = Column(JSON, nullable=True)
    started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    document = relationship("FSDocument")
    events = relationship("MCPSessionEventDB", back_populates="session", cascade="all, delete-orphan")


class MCPSessionEventDB(Base):
    """Event emitted during MCP session execution."""

    __tablename__ = "mcp_session_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("mcp_sessions.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(128), nullable=False, default="info")
    phase = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="ok")
    message = Column(Text, nullable=False, default="")
    payload_json = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    session = relationship("MCPSessionDB", back_populates="events")
