"""Pipeline state definition — shared TypedDict for all LangGraph nodes.

Every node reads and writes to this state. Fields are populated
progressively as the document moves through the pipeline.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


# ── Severity Enum ───────────────────────────────────────


class Severity(str, Enum):
    """Severity level for ambiguity flags."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ── Effort Enum ─────────────────────────────────────────


class EffortLevel(str, Enum):
    """Effort complexity for a dev task."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


# ── Pydantic Models ─────────────────────────────────────


class AmbiguityFlag(BaseModel):
    """A single ambiguity detected in an FS document section."""
    section_index: int
    section_heading: str
    flagged_text: str = Field(description="Exact text that is ambiguous")
    reason: str = Field(description="Why this text is ambiguous")
    severity: Severity = Field(description="Impact severity: LOW, MEDIUM, HIGH")
    clarification_question: str = Field(
        description="Question to ask the functional team for clarification"
    )

    model_config = {"from_attributes": True}


class Contradiction(BaseModel):
    """A contradiction detected between two sections in an FS document."""
    section_a_index: int
    section_a_heading: str
    section_b_index: int
    section_b_heading: str
    description: str = Field(description="What the conflict is")
    severity: Severity = Field(description="Impact severity: LOW, MEDIUM, HIGH")
    suggested_resolution: str = Field(description="Which section to trust or how to resolve")

    model_config = {"from_attributes": True}


class EdgeCaseGap(BaseModel):
    """A missing edge case / scenario detected in an FS section."""
    section_index: int
    section_heading: str
    scenario_description: str = Field(description="The edge case scenario that is not covered")
    impact: Severity = Field(description="Potential impact: LOW, MEDIUM, HIGH")
    suggested_addition: str = Field(description="What should be added to the FS")

    model_config = {"from_attributes": True}


class ComplianceTag(BaseModel):
    """A compliance-relevant tag for a section (payments, auth, PII, etc.)."""
    section_index: int
    section_heading: str
    tag: str = Field(description="Compliance area: payments, auth, pii, external_api, security, data_retention")
    reason: str = Field(description="Why this section is tagged for this compliance area")

    model_config = {"from_attributes": True}


class FSQualityScore(BaseModel):
    """Overall quality score for an FS document."""
    completeness: float = Field(description="Percentage of sections with no edge case gaps (0-100)")
    clarity: float = Field(description="Percentage of sections with no ambiguities (0-100)")
    consistency: float = Field(description="1 - contradiction_rate, as percentage (0-100)")
    overall: float = Field(description="Weighted average of the three sub-scores (0-100)")

    model_config = {"from_attributes": True}


class FSTask(BaseModel):
    """A dev task derived from FS requirements."""
    task_id: str = Field(description="Unique task identifier (uuid4)")
    title: str = Field(description="Short, actionable task title")
    description: str = Field(description="Detailed dev task description")
    section_index: int = Field(description="Source FS section index")
    section_heading: str = Field(description="Source FS section heading")
    depends_on: List[str] = Field(default_factory=list, description="List of task_ids this task depends on")
    acceptance_criteria: List[str] = Field(default_factory=list, description="Acceptance criteria")
    effort: EffortLevel = Field(default=EffortLevel.MEDIUM, description="Effort complexity: LOW/MEDIUM/HIGH/UNKNOWN")
    tags: List[str] = Field(default_factory=list, description="Tags: frontend, backend, db, auth, api, etc.")
    order: int = Field(default=0, description="Execution order from topological sort")
    can_parallel: bool = Field(default=False, description="Whether this task can be parallelised with others")

    model_config = {"from_attributes": True}


class TraceabilityEntry(BaseModel):
    """Maps a task back to its source FS section."""
    task_id: str
    task_title: str
    section_index: int
    section_heading: str

    model_config = {"from_attributes": True}


class DuplicateFlag(BaseModel):
    """A cross-document duplicate requirement detected via Qdrant similarity (L9)."""
    section_index: int
    section_heading: str
    similar_fs_id: str
    similar_section_heading: str = ""
    similarity_score: float
    flagged_text: str = ""
    similar_text: str = ""

    model_config = {"from_attributes": True}


class DebateVerdict(BaseModel):
    """Result of a Red vs Blue adversarial debate on an ambiguity flag."""
    verdict: str = Field(description="AMBIGUOUS or CLEAR")
    red_argument: str = Field(description="RedAgent's argument for why it IS ambiguous")
    blue_argument: str = Field(description="BlueAgent's argument for why it IS clear")
    arbiter_reasoning: str = Field(description="Arbiter's reasoning for the final verdict")
    confidence: int = Field(default=50, description="Arbiter confidence score 0-100")

    model_config = {"from_attributes": True}


# ── L7: Change Impact Enums ─────────────────────────────


class ChangeType(str, Enum):
    """Type of change between FS versions."""
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"


class ImpactType(str, Enum):
    """Impact level on a task from an FS change."""
    INVALIDATED = "INVALIDATED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    UNAFFECTED = "UNAFFECTED"


# ── L7: Change Impact Models ───────────────────────────


class FSChange(BaseModel):
    """A single change detected between two FS versions."""
    change_type: ChangeType = Field(description="ADDED, MODIFIED, or DELETED")
    section_id: str = Field(description="Section identifier (heading or index)")
    section_heading: str = Field(default="", description="Section heading text")
    section_index: int = Field(default=0, description="Section index in the document")
    old_text: Optional[str] = Field(default=None, description="Previous version text")
    new_text: Optional[str] = Field(default=None, description="New version text")

    model_config = {"from_attributes": True}


class TaskImpact(BaseModel):
    """Impact of an FS change on a specific task."""
    task_id: str = Field(description="ID of the affected task")
    task_title: str = Field(default="", description="Title of the affected task")
    impact_type: ImpactType = Field(description="INVALIDATED, REQUIRES_REVIEW, or UNAFFECTED")
    reason: str = Field(description="Why this task is affected")
    change_section: str = Field(default="", description="Section that changed")

    model_config = {"from_attributes": True}


class ReworkEstimate(BaseModel):
    """Rework cost estimate after FS version change."""
    invalidated_count: int = Field(default=0, description="Number of invalidated tasks")
    review_count: int = Field(default=0, description="Number of tasks needing review")
    unaffected_count: int = Field(default=0, description="Number of unaffected tasks")
    total_rework_days: float = Field(default=0.0, description="Estimated rework effort in days")
    affected_sections: List[str] = Field(default_factory=list, description="Sections affected by changes")
    changes_summary: str = Field(default="", description="Human-readable summary of changes")

    model_config = {"from_attributes": True}


class SectionInput(BaseModel):
    """A section passed into the pipeline for analysis."""
    heading: str
    content: str
    section_index: int


# ── Pipeline State (TypedDict for LangGraph) ────────────


class FSAnalysisState(TypedDict, total=False):
    """Shared state for the LangGraph FS analysis pipeline.

    Fields are populated progressively by each node:
      - parse_node: fs_id, parsed_sections
      - ambiguity_node: ambiguities (L3)
      - debate_node: debate_results, ambiguities filtered (L6)
      - contradiction_node: contradictions (L4)
      - edge_case_node: edge_cases (L4)
      - quality_node: quality_score, compliance_tags (L4)
      - task_decomposition_node: tasks (L5)
      - dependency_node: tasks (with depends_on, order, can_parallel) (L5)
      - traceability_node: traceability_matrix (L5)
    """
    # Input
    fs_id: str
    parsed_sections: List[dict]  # List of SectionInput-like dicts

    # Project context (summaries of sibling documents in the same project)
    project_context: List[dict]

    # L3: Ambiguity detection
    ambiguities: List[dict]  # List of AmbiguityFlag-like dicts

    # L6: Adversarial debate results
    debate_results: List[dict]  # List of DebateVerdict-like dicts

    # L4: Deep FS analysis
    contradictions: List[dict]  # List of Contradiction-like dicts
    edge_cases: List[dict]  # List of EdgeCaseGap-like dicts
    quality_score: dict  # FSQualityScore-like dict
    compliance_tags: List[dict]  # List of ComplianceTag-like dicts

    # L5: Task decomposition
    tasks: List[dict]  # List of FSTask-like dicts
    traceability_matrix: List[dict]  # List of TraceabilityEntry-like dicts

    # L9: Duplicate detection
    duplicates: List[dict]  # List of DuplicateFlag-like dicts

    # L10: Test case generation
    test_cases: List[dict]  # List of TestCase-like dicts

    # Errors
    errors: List[str]


class FSImpactState(TypedDict, total=False):
    """Shared state for the LangGraph FS impact analysis pipeline (L7).

    Fields are populated progressively by each node:
      - version_node: fs_changes
      - impact_node: task_impacts
      - rework_node: rework_estimate
    """
    # Input
    fs_id: str
    version_id: str
    old_sections: List[dict]  # Sections from previous version
    new_sections: List[dict]  # Sections from new version
    tasks: List[dict]  # Current task list from analysis

    # L7: Impact analysis
    fs_changes: List[dict]  # List of FSChange-like dicts
    task_impacts: List[dict]  # List of TaskImpact-like dicts
    rework_estimate: dict  # ReworkEstimate-like dict

    # Errors
    errors: List[str]


# ── L8: Legacy Code → FS Reverse Generation ────────────


class CodeEntity(BaseModel):
    """A single code entity (function, class, etc.) extracted from a source file."""
    name: str = ""
    entity_type: str = "function"  # function, class, method
    docstring: Optional[str] = None
    signature: str = ""
    line_number: int = 0


class CodeFile(BaseModel):
    """A single source code file with extracted entities."""
    path: str = ""
    language: str = ""
    content: str = ""
    entities: List[CodeEntity] = Field(default_factory=list)
    line_count: int = 0
    has_docstrings: bool = False


class CodebaseSnapshot(BaseModel):
    """Complete snapshot of a parsed codebase."""
    files: List[CodeFile] = Field(default_factory=list)
    primary_language: str = ""
    total_files: int = 0
    total_lines: int = 0
    languages: Dict[str, int] = Field(default_factory=dict)  # language -> file count
    parser_stats: Dict[str, Any] = Field(default_factory=dict)


class GeneratedFSReport(BaseModel):
    """Quality report for a generated FS document."""
    coverage: float = 0.0  # 0.0 to 1.0 — % of codebase documented
    gaps: List[str] = Field(default_factory=list)  # undocumented areas
    confidence: float = 0.0  # 0.0 to 1.0 — overall confidence
    total_entities: int = 0
    documented_entities: int = 0
    undocumented_files: List[str] = Field(default_factory=list)
    confidence_reasons: List[str] = Field(default_factory=list)
    generation_stats: Dict[str, Any] = Field(default_factory=dict)


class ReverseGenState(TypedDict, total=False):
    """Shared state for the LangGraph reverse FS generation pipeline (L8).

    Fields are populated progressively by each node:
      - reverse_fs_node: generated_sections, raw_fs_text
      - reverse_quality_node: report
    """
    # Input
    code_upload_id: str
    snapshot: dict  # CodebaseSnapshot-like dict

    # L8: Reverse generation
    module_summaries: List[dict]  # Per-file summaries
    user_flows: List[str]  # Identified user flows
    generated_sections: List[dict]  # Generated FS sections
    raw_fs_text: str  # Assembled FS document text

    # L8: Quality report
    report: dict  # GeneratedFSReport-like dict
    generation_stats: dict  # reverse generation diagnostics

    # Errors
    errors: List[str]
