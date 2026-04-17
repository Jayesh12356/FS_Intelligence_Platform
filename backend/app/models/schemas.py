"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


# ── Response Envelope ──────────────────────────────────


class APIResponse(BaseModel, Generic[T]):
    """Standard API response envelope: { data, error, meta }."""
    data: Optional[T] = None
    error: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


# ── FS Document Schemas ────────────────────────────────


class FSDocumentResponse(BaseModel):
    """Single FS document response."""
    id: UUID
    filename: str
    status: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    project_id: Optional[UUID] = None
    order_in_project: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FSDocumentDetail(FSDocumentResponse):
    """Extended document response with text fields."""
    original_text: Optional[str] = None
    parsed_text: Optional[str] = None
    file_path: Optional[str] = None
    sections: Optional[List["FSSectionSchema"]] = None


class FSDocumentListResponse(BaseModel):
    """List of FS documents."""
    documents: List[FSDocumentResponse]
    total: int


# ── Upload Response ────────────────────────────────────


class UploadResponse(BaseModel):
    """Response after successful file upload."""
    id: UUID
    filename: str
    status: str


# ── Parse Schemas (L2) ─────────────────────────────────


class FSSectionSchema(BaseModel):
    """A single parsed section from an FS document."""
    heading: str
    content: str
    section_index: int


class ParsedFSResponse(BaseModel):
    """Full parse result returned by the parse endpoint."""
    raw_text: str
    sections: List[FSSectionSchema]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParseResponse(BaseModel):
    """Response from POST /api/fs/{id}/parse."""
    id: UUID
    filename: str
    status: str
    sections_count: int
    chunks_stored: int
    sections: List[FSSectionSchema]


# ── Ambiguity Schemas (L3) ─────────────────────────────


class AmbiguityFlagSchema(BaseModel):
    """A single ambiguity flag detected in an FS document."""
    id: Optional[UUID] = None
    section_index: int
    section_heading: str
    flagged_text: str
    reason: str
    severity: str  # LOW, MEDIUM, HIGH
    clarification_question: str
    resolved: bool = False
    resolution_text: Optional[str] = None
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AmbiguityResolveRequest(BaseModel):
    """Optional body for PATCH /{doc_id}/ambiguities/{flag_id}."""
    resolution_text: Optional[str] = None
    resolved: bool = True


class AnalysisResponse(BaseModel):
    """Response from POST /api/fs/{id}/analyze."""
    id: UUID
    filename: str
    status: str
    ambiguities_count: int
    high_count: int
    medium_count: int
    low_count: int
    ambiguities: List[AmbiguityFlagSchema]
    contradictions_count: int = 0
    edge_cases_count: int = 0
    tasks_count: int = 0
    quality_score: Optional["QualityScoreSchema"] = None


# ── Contradiction Schemas (L4) ─────────────────────────


class ContradictionSchema(BaseModel):
    """A contradiction detected between two FS sections."""
    id: Optional[UUID] = None
    section_a_index: int
    section_a_heading: str
    section_b_index: int
    section_b_heading: str
    description: str
    severity: str  # LOW, MEDIUM, HIGH
    suggested_resolution: str
    resolved: bool = False

    model_config = {"from_attributes": True}


# ── Edge Case Schemas (L4) ─────────────────────────────


class EdgeCaseGapSchema(BaseModel):
    """An edge case gap detected in an FS section."""
    id: Optional[UUID] = None
    section_index: int
    section_heading: str
    scenario_description: str
    impact: str  # LOW, MEDIUM, HIGH
    suggested_addition: str
    resolved: bool = False

    model_config = {"from_attributes": True}


# ── Quality Score Schemas (L4) ─────────────────────────


class QualityScoreSchema(BaseModel):
    """Quality score breakdown for an FS document."""
    completeness: float
    clarity: float
    consistency: float
    overall: float

    model_config = {"from_attributes": True}


# ── Compliance Tag Schemas (L4) ────────────────────────


class ComplianceTagSchema(BaseModel):
    """A compliance tag for an FS section."""
    id: Optional[UUID] = None
    section_index: int
    section_heading: str
    tag: str
    reason: str

    model_config = {"from_attributes": True}


# ── Full Quality Dashboard Response (L4) ───────────────


class QualityDashboardResponse(BaseModel):
    """Complete quality dashboard data for a document."""
    id: UUID
    filename: str
    quality_score: QualityScoreSchema
    contradictions: List[ContradictionSchema]
    edge_cases: List[EdgeCaseGapSchema]
    compliance_tags: List[ComplianceTagSchema]


class RefinementSuggestionSchema(BaseModel):
    issue: str
    original: str
    refined: str


class RefinementDiffLineSchema(BaseModel):
    line: str


class RefinementResponse(BaseModel):
    original_score: float
    refined_score: float
    changes_made: int
    refined_text: str
    diff: List[RefinementDiffLineSchema]
    suggestions: List[RefinementSuggestionSchema]


class AcceptRefinementRequest(BaseModel):
    refined_text: str


# ── Health Schemas ─────────────────────────────────────


class ServiceHealth(BaseModel):
    """Health status for a single service."""
    status: str  # "healthy" | "unhealthy"
    latency_ms: Optional[float] = None
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    """System-wide health check response."""
    status: str  # "healthy" | "degraded" | "unhealthy"
    db: ServiceHealth
    qdrant: ServiceHealth
    llm: ServiceHealth


# ── Task Schemas (L5) ──────────────────────────────────


class FSTaskSchema(BaseModel):
    """A dev task derived from FS requirements."""
    id: Optional[UUID] = None
    task_id: str
    title: str
    description: str
    section_index: int
    section_heading: str
    depends_on: List[str] = []
    acceptance_criteria: List[str] = []
    effort: str  # LOW, MEDIUM, HIGH, UNKNOWN
    tags: List[str] = []
    status: str = "PENDING"
    order: int = 0
    can_parallel: bool = False

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    """Response from GET /api/fs/{id}/tasks."""
    tasks: List[FSTaskSchema]
    total: int


class DependencyEdge(BaseModel):
    """A single edge in the dependency graph."""
    from_task: str
    to_task: str


class DependencyGraphResponse(BaseModel):
    """Dependency graph as adjacency list + edges."""
    nodes: List[str]  # List of task_ids
    edges: List[DependencyEdge]  # from → to edges
    adjacency: dict[str, List[str]]  # task_id → list of depends_on


class TraceabilityEntrySchema(BaseModel):
    """Maps a task back to its source FS section."""
    task_id: str
    task_title: str
    section_index: int
    section_heading: str

    model_config = {"from_attributes": True}


class TraceabilityResponse(BaseModel):
    """Full traceability matrix for a document."""
    entries: List[TraceabilityEntrySchema]
    total_tasks: int
    total_sections: int


# ── Debate Result Schemas (L6) ─────────────────────────


class DebateResultSchema(BaseModel):
    """Result of an adversarial debate on a HIGH severity ambiguity flag."""
    id: Optional[UUID] = None
    section_index: int
    section_heading: str
    flagged_text: str
    original_reason: str
    verdict: str  # AMBIGUOUS or CLEAR
    red_argument: str
    blue_argument: str
    arbiter_reasoning: str
    confidence: int  # 0-100

    model_config = {"from_attributes": True}


class DebateResultsResponse(BaseModel):
    """Response from GET /api/fs/{id}/debate-results."""
    results: List[DebateResultSchema]
    total_debated: int
    confirmed_ambiguous: int
    cleared: int


# ── L7: Change Impact Schemas ──────────────────────────


class FSVersionSchema(BaseModel):
    """A single FS document version."""
    id: UUID
    fs_id: UUID
    version_number: int
    content_hash: Optional[str] = None
    diff_summary: Optional[str] = None
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FSVersionListResponse(BaseModel):
    """Response from GET /api/fs/{id}/versions."""
    versions: List[FSVersionSchema]
    total: int


class FSChangeSchema(BaseModel):
    """A change detected between two FS versions."""
    id: Optional[UUID] = None
    change_type: str  # ADDED, MODIFIED, DELETED
    section_id: str
    section_heading: str = ""
    section_index: int = 0
    old_text: Optional[str] = None
    new_text: Optional[str] = None

    model_config = {"from_attributes": True}


class DiffResponse(BaseModel):
    """Response from GET /api/fs/{id}/versions/{v}/diff."""
    version_id: UUID
    version_number: int
    previous_version: Optional[int] = None
    changes: List[FSChangeSchema]
    total_changes: int
    added: int
    modified: int
    deleted: int


class TaskImpactSchema(BaseModel):
    """Impact of an FS change on a specific task."""
    id: Optional[UUID] = None
    task_id: str
    task_title: str = ""
    impact_type: str  # INVALIDATED, REQUIRES_REVIEW, UNAFFECTED
    reason: str = ""
    change_section: str = ""

    model_config = {"from_attributes": True}


class ReworkEstimateSchema(BaseModel):
    """Rework cost estimate for a version change."""
    invalidated_count: int = 0
    review_count: int = 0
    unaffected_count: int = 0
    total_rework_days: float = 0.0
    affected_sections: List[str] = []
    changes_summary: str = ""

    model_config = {"from_attributes": True}


class ImpactAnalysisResponse(BaseModel):
    """Response from GET /api/fs/{id}/impact/{version_id}."""
    fs_id: UUID
    version_id: UUID
    version_number: int
    changes: List[FSChangeSchema]
    task_impacts: List[TaskImpactSchema]
    rework_estimate: ReworkEstimateSchema
    invalidated_count: int = 0
    review_count: int = 0
    unaffected_count: int = 0


class ReworkResponse(BaseModel):
    """Response from GET /api/fs/{id}/impact/{version_id}/rework."""
    fs_id: UUID
    version_id: UUID
    version_number: int
    rework_estimate: ReworkEstimateSchema


# ── L8: Reverse FS Generation Schemas ──────────────────


class CodeUploadResponse(BaseModel):
    """Response from POST /api/code/upload."""
    id: UUID
    filename: str
    status: str
    file_size: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CodeEntitySchema(BaseModel):
    """Single code entity in a file."""
    name: str
    entity_type: str
    docstring: Optional[str] = None
    signature: str = ""
    line_number: int = 0


class CodeFileSchema(BaseModel):
    """Single source code file in the snapshot."""
    path: str
    language: str
    entities: List[CodeEntitySchema] = []
    line_count: int = 0
    has_docstrings: bool = False


class CodeSnapshotSchema(BaseModel):
    """Parsed codebase snapshot overview."""
    primary_language: str = ""
    total_files: int = 0
    total_lines: int = 0
    languages: dict = {}
    files: List[CodeFileSchema] = []
    parser_stats: dict = {}


class CodeReportSchema(BaseModel):
    """Quality report for generated FS."""
    coverage: float = 0.0
    confidence: float = 0.0
    gaps: List[str] = []
    total_entities: int = 0
    documented_entities: int = 0
    undocumented_files: List[str] = []
    confidence_reasons: List[str] = []
    generation_stats: dict = {}


class GeneratedFSResponse(BaseModel):
    """Response from GET /api/code/{id}/generated-fs."""
    code_upload_id: UUID
    generated_fs_id: Optional[UUID] = None
    status: str
    sections: List[FSSectionSchema] = []
    raw_text: str = ""
    report: Optional[CodeReportSchema] = None


class CodeUploadDetailResponse(BaseModel):
    """Detailed response for a code upload with all data."""
    id: UUID
    filename: str
    status: str
    file_size: Optional[int] = None
    primary_language: Optional[str] = None
    total_files: Optional[int] = None
    total_lines: Optional[int] = None
    languages: Optional[dict] = None
    generated_fs_id: Optional[UUID] = None
    coverage: Optional[float] = None
    confidence: Optional[float] = None
    gaps: Optional[List[str]] = None
    parser_stats: Optional[dict] = None
    generation_stats: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CodeUploadListResponse(BaseModel):
    """Response from GET /api/code/uploads."""
    uploads: List[CodeUploadResponse]
    total: int


# ── L9: Semantic Intelligence + Collaboration Schemas ──


class DuplicateFlagSchema(BaseModel):
    """A cross-document duplicate requirement flag."""
    id: Optional[UUID] = None
    section_index: int
    section_heading: str
    similar_fs_id: UUID
    similar_section_heading: str = ""
    similarity_score: float
    flagged_text: str = ""
    similar_text: str = ""

    model_config = {"from_attributes": True}


class DuplicateListResponse(BaseModel):
    """Response from GET /api/fs/{id}/duplicates."""
    duplicates: List[DuplicateFlagSchema]
    total: int


class LibraryItemSchema(BaseModel):
    """A single item in the reusable requirement library."""
    id: str  # Qdrant point ID
    fs_id: str
    section_index: int
    section_heading: str
    text: str
    score: Optional[float] = None

    model_config = {"from_attributes": True}


class LibrarySearchResponse(BaseModel):
    """Response from GET /api/library/search."""
    results: List[LibraryItemSchema]
    total: int
    query: str


class SuggestionResponse(BaseModel):
    """Response from POST /api/fs/{id}/suggestions."""
    suggestions: List[LibraryItemSchema]
    total: int


class CommentCreateRequest(BaseModel):
    """Request body for creating a comment."""
    text: str
    user_id: str = "anonymous"
    mentions: List[str] = []  # List of user_ids to @-mention


class FSCommentSchema(BaseModel):
    """A comment on an FS document section."""
    id: Optional[UUID] = None
    fs_id: UUID
    section_index: int
    user_id: str
    text: str
    resolved: bool = False
    mentions: List[str] = []
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CommentListResponse(BaseModel):
    """Response from GET /api/fs/{id}/comments."""
    comments: List[FSCommentSchema]
    total: int
    resolved_count: int


class ApprovalActionRequest(BaseModel):
    """Request body for approve/reject actions."""
    approver_id: str = "system"
    comment: Optional[str] = None


class FSApprovalSchema(BaseModel):
    """An approval record for an FS document."""
    id: Optional[UUID] = None
    fs_id: UUID
    approver_id: str
    status: str  # PENDING, APPROVED, REJECTED
    comment: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ApprovalStatusResponse(BaseModel):
    """Response from GET /api/fs/{id}/approval-status."""
    fs_id: UUID
    current_status: str  # PENDING, APPROVED, REJECTED, or NONE
    history: List[FSApprovalSchema]
    total: int


class AuditEventSchema(BaseModel):
    """A single audit event."""
    id: Optional[UUID] = None
    fs_id: UUID
    user_id: str
    event_type: str
    payload_json: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AuditLogResponse(BaseModel):
    """Response from GET /api/fs/{id}/audit-log."""
    events: List[AuditEventSchema]
    total: int


# ── L10 Schemas — Integrations + Polish ────────────────


class TestCaseSchema(BaseModel):
    """Schema for a generated test case."""
    id: Optional[UUID] = None
    fs_id: Optional[UUID] = None
    task_id: str
    title: str
    preconditions: str = ""
    steps: List[str] = []
    expected_result: str = ""
    test_type: str = "UNIT"
    section_index: int = 0
    section_heading: str = ""
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TestCaseListResponse(BaseModel):
    """Response from GET /api/fs/{id}/test-cases."""
    test_cases: List[TestCaseSchema]
    total: int
    by_type: dict = {}


class JiraExportResponse(BaseModel):
    """Response from POST /api/fs/{id}/export/jira."""
    epic: dict
    stories: List[dict]
    total: int
    simulated: bool = False


class ConfluenceExportResponse(BaseModel):
    """Response from POST /api/fs/{id}/export/confluence."""
    page_id: str
    page_url: str
    title: str
    simulated: bool = False


class ReportExportResponse(BaseModel):
    """Response from GET /api/fs/{id}/export/pdf or /export/docx."""
    filename: str
    format: str
    size_bytes: int = 0
    download_url: str = ""


# ── MCP Monitoring Schemas ─────────────────────────────


# ── Project Schemas ─────────────────────────────────────


class FSProjectCreateRequest(BaseModel):
    """Request to create a new project."""
    name: str
    description: Optional[str] = None


class FSProjectUpdateRequest(BaseModel):
    """Request to update a project."""
    name: Optional[str] = None
    description: Optional[str] = None


class FSProjectSchema(BaseModel):
    """A project grouping related FS documents."""
    id: UUID
    name: str
    description: Optional[str] = None
    document_count: int = 0
    created_at: datetime
    updated_at: datetime


class FSProjectDetailSchema(FSProjectSchema):
    """Project with documents list."""
    documents: List[FSDocumentResponse] = []


class FSProjectListResponse(BaseModel):
    """List of projects."""
    projects: List[FSProjectSchema]
    total: int


# ── Section Edit Schemas ───────────────────────────────


class SectionEditRequest(BaseModel):
    """Request to edit a section in a document."""
    heading: Optional[str] = None
    content: Optional[str] = None


class SectionAddRequest(BaseModel):
    """Request to add a new section to a document."""
    heading: str
    content: str
    insert_after: Optional[int] = None


# ── Activity Log Schemas ───────────────────────────────


class ActivityLogEntry(BaseModel):
    """A single entry in the global activity log."""
    id: Optional[UUID] = None
    fs_id: UUID
    document_name: str = ""
    event_type: str
    event_label: str = ""
    detail: Optional[str] = None
    user_id: str = "system"
    created_at: Optional[datetime] = None


class ActivityLogResponse(BaseModel):
    """Response for the global activity log."""
    events: List[ActivityLogEntry]
    total: int


class MCPSessionCreateRequest(BaseModel):
    document_id: Optional[UUID] = None
    target_stack: str = ""
    source: str = "mcp"
    dry_run: bool = False
    total_phases: int = 0
    meta: Optional[dict] = None


class MCPSessionEventCreateRequest(BaseModel):
    event_type: str
    phase: int = 0
    status: str = "ok"
    message: str = ""
    payload: Optional[dict] = None


class MCPSessionSchema(BaseModel):
    id: UUID
    fs_id: Optional[UUID] = None
    target_stack: str
    source: str
    status: str
    phase: int
    total_phases: int
    current_step: str
    dry_run: bool
    meta_json: Optional[dict] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MCPSessionEventSchema(BaseModel):
    id: UUID
    session_id: UUID
    event_type: str
    phase: int
    status: str
    message: str
    payload_json: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MCPSessionListResponse(BaseModel):
    sessions: List[MCPSessionSchema]
    total: int


class MCPSessionEventListResponse(BaseModel):
    events: List[MCPSessionEventSchema]
    total: int


# ── Phase 2: Idea + Orchestration Schemas ─────────────


class IdeaQuickRequest(BaseModel):
    idea: str
    industry: Optional[str] = None
    complexity: Optional[str] = None


class IdeaGuidedRequest(BaseModel):
    session_id: Optional[str] = None
    idea: str = ""
    step: int = 0
    answers: Optional[dict] = None
    industry: Optional[str] = None
    complexity: Optional[str] = None


class IdeaSessionResponse(BaseModel):
    id: UUID
    idea_text: str
    industry: str
    complexity: str
    mode: str
    generated_fs_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ToolConfigSchema(BaseModel):
    id: UUID
    llm_provider: str
    build_provider: str
    frontend_provider: str
    fallback_chain: List[str]
    cursor_config: Optional[dict] = None
    claude_code_config: Optional[dict] = None

    model_config = {"from_attributes": True}


class ProviderHealthSchema(BaseModel):
    name: str
    display_name: str
    capabilities: List[str]
    healthy: Optional[bool] = None
