/**
 * Typed API client for the FS Intelligence Platform backend.
 *
 * All calls go through the backend API at NEXT_PUBLIC_API_URL.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ──────────────────────────────────────────────

export interface FSDocumentResponse {
  id: string;
  filename: string;
  status: string;
  file_size: number | null;
  content_type: string | null;
  created_at: string;
  updated_at: string;
}

export interface FSSection {
  heading: string;
  content: string;
  section_index: number;
}

export interface FSDocumentDetail extends FSDocumentResponse {
  original_text: string | null;
  parsed_text: string | null;
  file_path: string | null;
  sections: FSSection[] | null;
}

export interface UploadResponse {
  id: string;
  filename: string;
  status: string;
}

export interface ParseResponse {
  id: string;
  filename: string;
  status: string;
  sections_count: number;
  chunks_stored: number;
  sections: FSSection[];
}

export interface AmbiguityFlag {
  id: string | null;
  section_index: number;
  section_heading: string;
  flagged_text: string;
  reason: string;
  severity: "LOW" | "MEDIUM" | "HIGH";
  clarification_question: string;
  resolved: boolean;
}

export interface QualityScore {
  completeness: number;
  clarity: number;
  consistency: number;
  overall: number;
}

export interface AnalysisResponse {
  id: string;
  filename: string;
  status: string;
  ambiguities_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  ambiguities: AmbiguityFlag[];
  contradictions_count: number;
  edge_cases_count: number;
  tasks_count: number;
  quality_score: QualityScore | null;
}

export interface Contradiction {
  id: string | null;
  section_a_index: number;
  section_a_heading: string;
  section_b_index: number;
  section_b_heading: string;
  description: string;
  severity: "LOW" | "MEDIUM" | "HIGH";
  suggested_resolution: string;
  resolved: boolean;
}

export interface EdgeCaseGap {
  id: string | null;
  section_index: number;
  section_heading: string;
  scenario_description: string;
  impact: "LOW" | "MEDIUM" | "HIGH";
  suggested_addition: string;
  resolved: boolean;
}

export interface ComplianceTag {
  id: string | null;
  section_index: number;
  section_heading: string;
  tag: string;
  reason: string;
}

export interface QualityDashboardResponse {
  id: string;
  filename: string;
  quality_score: QualityScore;
  contradictions: Contradiction[];
  edge_cases: EdgeCaseGap[];
  compliance_tags: ComplianceTag[];
}

export interface APIResponse<T> {
  data: T;
  error: string | null;
  meta: Record<string, unknown> | null;
}

export interface DocumentListData {
  documents: FSDocumentResponse[];
  total: number;
}

// L5 Types

export interface FSTaskItem {
  id: string | null;
  task_id: string;
  title: string;
  description: string;
  section_index: number;
  section_heading: string;
  depends_on: string[];
  acceptance_criteria: string[];
  effort: "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";
  tags: string[];
  order: number;
  can_parallel: boolean;
}

export interface TaskListData {
  tasks: FSTaskItem[];
  total: number;
}

export interface DependencyEdge {
  from_task: string;
  to_task: string;
}

export interface DependencyGraphData {
  nodes: string[];
  edges: DependencyEdge[];
  adjacency: Record<string, string[]>;
}

export interface TraceabilityEntry {
  task_id: string;
  task_title: string;
  section_index: number;
  section_heading: string;
}

export interface TraceabilityData {
  entries: TraceabilityEntry[];
  total_tasks: number;
  total_sections: number;
}

// ── Helper ─────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<APIResponse<T>> {
  const url = `${API_BASE}${path}`;

  const res = await fetch(url, {
    ...options,
    headers: {
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const message =
      body?.detail || body?.error || `API error: ${res.status} ${res.statusText}`;
    throw new Error(message);
  }

  return res.json();
}

// ── API Functions ──────────────────────────────────────

/**
 * Upload a file (PDF, DOCX, or TXT).
 */
export async function uploadFile(
  file: File
): Promise<APIResponse<UploadResponse>> {
  const formData = new FormData();
  formData.append("file", file);

  return apiFetch<UploadResponse>("/api/fs/upload", {
    method: "POST",
    body: formData,
  });
}

/**
 * List all non-deleted documents.
 */
export async function listDocuments(): Promise<
  APIResponse<DocumentListData>
> {
  return apiFetch<DocumentListData>("/api/fs/");
}

/**
 * Get a single document by ID.
 */
export async function getDocument(
  id: string
): Promise<APIResponse<FSDocumentDetail>> {
  return apiFetch<FSDocumentDetail>(`/api/fs/${id}`);
}

/**
 * Soft-delete a document.
 */
export async function deleteDocument(
  id: string
): Promise<APIResponse<{ id: string; deleted: boolean }>> {
  return apiFetch<{ id: string; deleted: boolean }>(`/api/fs/${id}`, {
    method: "DELETE",
  });
}

/**
 * Trigger document parsing (L2).
 * Parses the document into sections, chunks, and stores embeddings.
 */
export async function parseDocument(
  id: string
): Promise<APIResponse<ParseResponse>> {
  return apiFetch<ParseResponse>(`/api/fs/${id}/parse`, {
    method: "POST",
  });
}

/**
 * Trigger document analysis (L3+L4).
 * Runs the LangGraph pipeline to detect ambiguities, contradictions,
 * edge cases, and compute quality scores.
 */
export async function analyzeDocument(
  id: string
): Promise<APIResponse<AnalysisResponse>> {
  return apiFetch<AnalysisResponse>(`/api/fs/${id}/analyze`, {
    method: "POST",
  });
}

/**
 * List ambiguity flags for a document.
 */
export async function listAmbiguities(
  id: string
): Promise<APIResponse<AmbiguityFlag[]>> {
  return apiFetch<AmbiguityFlag[]>(`/api/fs/${id}/ambiguities`);
}

/**
 * Mark an ambiguity flag as resolved.
 */
export async function resolveAmbiguity(
  docId: string,
  flagId: string
): Promise<APIResponse<AmbiguityFlag>> {
  return apiFetch<AmbiguityFlag>(`/api/fs/${docId}/ambiguities/${flagId}`, {
    method: "PATCH",
  });
}

/**
 * List contradictions for a document. (L4)
 */
export async function listContradictions(
  id: string
): Promise<APIResponse<Contradiction[]>> {
  return apiFetch<Contradiction[]>(`/api/fs/${id}/contradictions`);
}

/**
 * Mark a contradiction as resolved. (L4)
 */
export async function resolveContradiction(
  docId: string,
  contradictionId: string
): Promise<APIResponse<Contradiction>> {
  return apiFetch<Contradiction>(`/api/fs/${docId}/contradictions/${contradictionId}`, {
    method: "PATCH",
  });
}

/**
 * List edge case gaps for a document. (L4)
 */
export async function listEdgeCases(
  id: string
): Promise<APIResponse<EdgeCaseGap[]>> {
  return apiFetch<EdgeCaseGap[]>(`/api/fs/${id}/edge-cases`);
}

/**
 * Mark an edge case gap as resolved. (L4)
 */
export async function resolveEdgeCase(
  docId: string,
  edgeCaseId: string
): Promise<APIResponse<EdgeCaseGap>> {
  return apiFetch<EdgeCaseGap>(`/api/fs/${docId}/edge-cases/${edgeCaseId}`, {
    method: "PATCH",
  });
}

/**
 * Get complete quality dashboard data for a document. (L4)
 */
export async function getQualityDashboard(
  id: string
): Promise<APIResponse<QualityDashboardResponse>> {
  return apiFetch<QualityDashboardResponse>(`/api/fs/${id}/quality-score`);
}

/**
 * Check system health.
 */
export async function checkHealth(): Promise<
  APIResponse<{
    status: string;
    db: { status: string; latency_ms: number | null };
    qdrant: { status: string; latency_ms: number | null };
    llm: { status: string; latency_ms: number | null };
  }>
> {
  return apiFetch("/health");
}

// ── L5 Task API Functions ──────────────────────────────

/**
 * List all tasks for a document, ordered by execution order. (L5)
 */
export async function listTasks(
  id: string
): Promise<APIResponse<TaskListData>> {
  return apiFetch<TaskListData>(`/api/fs/${id}/tasks`);
}

/**
 * Get a single task by task_id. (L5)
 */
export async function getTask(
  docId: string,
  taskId: string
): Promise<APIResponse<FSTaskItem>> {
  return apiFetch<FSTaskItem>(`/api/fs/${docId}/tasks/${taskId}`);
}

/**
 * Update a task (manual edit). (L5)
 */
export async function updateTask(
  docId: string,
  taskId: string,
  body: {
    title?: string;
    description?: string;
    effort?: string;
    tags?: string[];
    acceptance_criteria?: string[];
  }
): Promise<APIResponse<FSTaskItem>> {
  return apiFetch<FSTaskItem>(`/api/fs/${docId}/tasks/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * Get the dependency graph for a document's tasks. (L5)
 */
export async function getDependencyGraph(
  id: string
): Promise<APIResponse<DependencyGraphData>> {
  return apiFetch<DependencyGraphData>(`/api/fs/${id}/tasks/dependency-graph`);
}

/**
 * Get the traceability matrix for a document. (L5)
 */
export async function getTraceability(
  id: string
): Promise<APIResponse<TraceabilityData>> {
  return apiFetch<TraceabilityData>(`/api/fs/${id}/traceability`);
}

// ── L6 Debate API Types & Functions ────────────────────

export interface DebateResult {
  id: string | null;
  section_index: number;
  section_heading: string;
  flagged_text: string;
  original_reason: string;
  verdict: "AMBIGUOUS" | "CLEAR";
  red_argument: string;
  blue_argument: string;
  arbiter_reasoning: string;
  confidence: number;
}

export interface DebateResultsData {
  results: DebateResult[];
  total_debated: number;
  confirmed_ambiguous: number;
  cleared: number;
}

/**
 * Get adversarial debate results for a document. (L6)
 * Returns transcripts of Red vs Blue agent debates on HIGH severity flags.
 */
export async function getDebateResults(
  id: string
): Promise<APIResponse<DebateResultsData>> {
  return apiFetch<DebateResultsData>(`/api/fs/${id}/debate-results`);
}

// ── L7 Impact Analysis API Types & Functions ───────────

export interface FSVersionItem {
  id: string;
  fs_id: string;
  version_number: number;
  content_hash: string | null;
  diff_summary: string | null;
  file_size: number | null;
  content_type: string | null;
  created_at: string;
}

export interface VersionListData {
  versions: FSVersionItem[];
  total: number;
}

export interface FSChangeItem {
  id: string | null;
  change_type: "ADDED" | "MODIFIED" | "DELETED";
  section_id: string;
  section_heading: string;
  section_index: number;
  old_text: string | null;
  new_text: string | null;
}

export interface DiffData {
  version_id: string;
  version_number: number;
  previous_version: number | null;
  changes: FSChangeItem[];
  total_changes: number;
  added: number;
  modified: number;
  deleted: number;
}

export interface TaskImpactItem {
  id: string | null;
  task_id: string;
  task_title: string;
  impact_type: "INVALIDATED" | "REQUIRES_REVIEW" | "UNAFFECTED";
  reason: string;
  change_section: string;
}

export interface ReworkEstimateData {
  invalidated_count: number;
  review_count: number;
  unaffected_count: number;
  total_rework_days: number;
  affected_sections: string[];
  changes_summary: string;
}

export interface ImpactAnalysisData {
  fs_id: string;
  version_id: string;
  version_number: number;
  changes: FSChangeItem[];
  task_impacts: TaskImpactItem[];
  rework_estimate: ReworkEstimateData;
  invalidated_count: number;
  review_count: number;
  unaffected_count: number;
}

export interface ReworkResponseData {
  fs_id: string;
  version_id: string;
  version_number: number;
  rework_estimate: ReworkEstimateData;
}

/**
 * Upload a new version of an FS document. (L7)
 * Triggers parse + diff + impact analysis automatically.
 */
export async function uploadVersion(
  docId: string,
  file: File
): Promise<APIResponse<FSVersionItem>> {
  const formData = new FormData();
  formData.append("file", file);

  return apiFetch<FSVersionItem>(`/api/fs/${docId}/version`, {
    method: "POST",
    body: formData,
  });
}

/**
 * List all versions for a document. (L7)
 */
export async function listVersions(
  id: string
): Promise<APIResponse<VersionListData>> {
  return apiFetch<VersionListData>(`/api/fs/${id}/versions`);
}

/**
 * Get diff between a version and its predecessor. (L7)
 */
export async function getVersionDiff(
  docId: string,
  versionId: string
): Promise<APIResponse<DiffData>> {
  return apiFetch<DiffData>(`/api/fs/${docId}/versions/${versionId}/diff`);
}

/**
 * Get full impact analysis for a version change. (L7)
 */
export async function getImpactAnalysis(
  docId: string,
  versionId: string
): Promise<APIResponse<ImpactAnalysisData>> {
  return apiFetch<ImpactAnalysisData>(`/api/fs/${docId}/impact/${versionId}`);
}

/**
 * Get rework cost estimate for a version change. (L7)
 */
export async function getReworkEstimate(
  docId: string,
  versionId: string
): Promise<APIResponse<ReworkResponseData>> {
  return apiFetch<ReworkResponseData>(
    `/api/fs/${docId}/impact/${versionId}/rework`
  );
}

// ── L8 Reverse FS Generation API Types & Functions ─────

export interface CodeUploadItem {
  id: string;
  filename: string;
  status: string;
  file_size: number | null;
  created_at: string;
}

export interface CodeUploadListData {
  uploads: CodeUploadItem[];
  total: number;
}

export interface CodeEntityItem {
  name: string;
  entity_type: string;
  docstring: string | null;
  signature: string;
  line_number: number;
}

export interface CodeFileItem {
  path: string;
  language: string;
  entities: CodeEntityItem[];
  line_count: number;
  has_docstrings: boolean;
}

export interface CodeReportData {
  coverage: number;
  confidence: number;
  gaps: string[];
  total_entities: number;
  documented_entities: number;
  undocumented_files: string[];
}

export interface FSSectionItem {
  heading: string;
  content: string;
  section_index: number;
}

export interface GeneratedFSData {
  code_upload_id: string;
  generated_fs_id: string | null;
  status: string;
  sections: FSSectionItem[];
  raw_text: string;
  report: CodeReportData | null;
}

export interface CodeUploadDetailData {
  id: string;
  filename: string;
  status: string;
  file_size: number | null;
  primary_language: string | null;
  total_files: number | null;
  total_lines: number | null;
  languages: Record<string, number> | null;
  generated_fs_id: string | null;
  coverage: number | null;
  confidence: number | null;
  gaps: string[] | null;
  created_at: string;
}

/**
 * Upload a codebase zip file. (L8)
 */
export async function uploadCodebase(
  file: File
): Promise<APIResponse<CodeUploadItem>> {
  const formData = new FormData();
  formData.append("file", file);

  return apiFetch<CodeUploadItem>("/api/code/upload", {
    method: "POST",
    body: formData,
  });
}

/**
 * List all code uploads. (L8)
 */
export async function listCodeUploads(): Promise<
  APIResponse<CodeUploadListData>
> {
  return apiFetch<CodeUploadListData>("/api/code/uploads");
}

/**
 * Get code upload details. (L8)
 */
export async function getCodeUploadDetail(
  id: string
): Promise<APIResponse<CodeUploadDetailData>> {
  return apiFetch<CodeUploadDetailData>(`/api/code/${id}`);
}

/**
 * Trigger reverse FS generation. (L8)
 */
export async function generateFS(
  id: string
): Promise<APIResponse<GeneratedFSData>> {
  return apiFetch<GeneratedFSData>(`/api/code/${id}/generate-fs`, {
    method: "POST",
  });
}

/**
 * Get generated FS for a code upload. (L8)
 */
export async function getGeneratedFS(
  id: string
): Promise<APIResponse<GeneratedFSData>> {
  return apiFetch<GeneratedFSData>(`/api/code/${id}/generated-fs`);
}

/**
 * Get quality report for a code upload. (L8)
 */
export async function getCodeReport(
  id: string
): Promise<APIResponse<CodeReportData>> {
  return apiFetch<CodeReportData>(`/api/code/${id}/report`);
}

// ── L9 Semantic Intelligence + Collaboration ──────────

// ── Duplicate Detection Types & Functions ──────────────

export interface DuplicateFlag {
  id: string | null;
  section_index: number;
  section_heading: string;
  similar_fs_id: string;
  similar_section_heading: string;
  similarity_score: number;
  flagged_text: string;
  similar_text: string;
}

export interface DuplicateListData {
  duplicates: DuplicateFlag[];
  total: number;
}

/**
 * List duplicate flags for a document. (L9)
 */
export async function listDuplicates(
  id: string
): Promise<APIResponse<DuplicateListData>> {
  return apiFetch<DuplicateListData>(`/api/fs/${id}/duplicates`);
}

// ── Library Types & Functions ─────────────────────────

export interface LibraryItem {
  id: string;
  fs_id: string;
  section_index: number;
  section_heading: string;
  text: string;
  score: number | null;
}

export interface LibrarySearchData {
  results: LibraryItem[];
  total: number;
  query: string;
}

export interface SuggestionData {
  suggestions: LibraryItem[];
  total: number;
}

/**
 * Search the requirement library. (L9)
 */
export async function searchLibrary(
  query: string,
  limit: number = 10
): Promise<APIResponse<LibrarySearchData>> {
  return apiFetch<LibrarySearchData>(
    `/api/library/search?q=${encodeURIComponent(query)}&limit=${limit}`
  );
}

/**
 * Get a specific library item. (L9)
 */
export async function getLibraryItem(
  id: string
): Promise<APIResponse<LibraryItem>> {
  return apiFetch<LibraryItem>(`/api/library/${id}`);
}

/**
 * Get suggestions from the library for a document. (L9)
 */
export async function getSuggestions(
  docId: string
): Promise<APIResponse<SuggestionData>> {
  return apiFetch<SuggestionData>(`/api/fs/${docId}/suggestions`, {
    method: "POST",
  });
}

// ── Comment Types & Functions ─────────────────────────

export interface FSComment {
  id: string | null;
  fs_id: string;
  section_index: number;
  user_id: string;
  text: string;
  resolved: boolean;
  mentions: string[];
  created_at: string | null;
}

export interface CommentListData {
  comments: FSComment[];
  total: number;
  resolved_count: number;
}

/**
 * Add a comment to a section. (L9)
 */
export async function addComment(
  docId: string,
  sectionIndex: number,
  text: string,
  userId: string = "anonymous",
  mentions: string[] = []
): Promise<APIResponse<FSComment>> {
  return apiFetch<FSComment>(
    `/api/fs/${docId}/sections/${sectionIndex}/comments`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, user_id: userId, mentions }),
    }
  );
}

/**
 * List all comments for a document. (L9)
 */
export async function listComments(
  docId: string
): Promise<APIResponse<CommentListData>> {
  return apiFetch<CommentListData>(`/api/fs/${docId}/comments`);
}

/**
 * Resolve a comment. (L9)
 */
export async function resolveComment(
  docId: string,
  commentId: string
): Promise<APIResponse<FSComment>> {
  return apiFetch<FSComment>(
    `/api/fs/${docId}/comments/${commentId}/resolve`,
    { method: "PATCH" }
  );
}

// ── Approval Types & Functions ────────────────────────

export interface FSApproval {
  id: string | null;
  fs_id: string;
  approver_id: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  comment: string | null;
  created_at: string | null;
}

export interface ApprovalStatusData {
  fs_id: string;
  current_status: string;
  history: FSApproval[];
  total: number;
}

/**
 * Submit a document for approval. (L9)
 */
export async function submitForApproval(
  docId: string,
  approverId: string = "system"
): Promise<APIResponse<FSApproval>> {
  return apiFetch<FSApproval>(`/api/fs/${docId}/submit-for-approval`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approver_id: approverId }),
  });
}

/**
 * Approve a document. (L9)
 */
export async function approveDocument(
  docId: string,
  approverId: string = "system",
  comment?: string
): Promise<APIResponse<FSApproval>> {
  return apiFetch<FSApproval>(`/api/fs/${docId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approver_id: approverId, comment }),
  });
}

/**
 * Reject a document. (L9)
 */
export async function rejectDocument(
  docId: string,
  approverId: string = "system",
  comment?: string
): Promise<APIResponse<FSApproval>> {
  return apiFetch<FSApproval>(`/api/fs/${docId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approver_id: approverId, comment }),
  });
}

/**
 * Get approval status for a document. (L9)
 */
export async function getApprovalStatus(
  docId: string
): Promise<APIResponse<ApprovalStatusData>> {
  return apiFetch<ApprovalStatusData>(`/api/fs/${docId}/approval-status`);
}

// ── Audit Types & Functions ───────────────────────────

export interface AuditEvent {
  id: string | null;
  fs_id: string;
  user_id: string;
  event_type: string;
  payload_json: Record<string, unknown> | null;
  created_at: string | null;
}

export interface AuditLogData {
  events: AuditEvent[];
  total: number;
}

/**
 * Get the audit log for a document. (L9)
 */
export async function getAuditLog(
  docId: string
): Promise<APIResponse<AuditLogData>> {
  return apiFetch<AuditLogData>(`/api/fs/${docId}/audit-log`);
}

// ── L10 Integrations + Polish ─────────────────────────

// ── Test Cases ────────────────────────────────────────

export interface TestCase {
  id: string | null;
  fs_id: string | null;
  task_id: string;
  title: string;
  preconditions: string;
  steps: string[];
  expected_result: string;
  test_type: string;
  section_index: number;
  section_heading: string;
  created_at: string | null;
}

export interface TestCaseListData {
  test_cases: TestCase[];
  total: number;
  by_type: Record<string, number>;
}

/**
 * List generated test cases for a document. (L10)
 */
export async function listTestCases(
  docId: string
): Promise<APIResponse<TestCaseListData>> {
  return apiFetch<TestCaseListData>(`/api/fs/${docId}/test-cases`);
}

// ── JIRA Export ───────────────────────────────────────

export interface JiraExportData {
  epic: Record<string, unknown>;
  stories: Record<string, unknown>[];
  total: number;
  simulated: boolean;
}

/**
 * Export tasks to JIRA. (L10)
 */
export async function exportToJira(
  docId: string
): Promise<APIResponse<JiraExportData>> {
  return apiFetch<JiraExportData>(`/api/fs/${docId}/export/jira`, {
    method: "POST",
  });
}

// ── Confluence Export ─────────────────────────────────

export interface ConfluenceExportData {
  page_id: string;
  page_url: string;
  title: string;
  simulated: boolean;
}

/**
 * Export analysis to Confluence. (L10)
 */
export async function exportToConfluence(
  docId: string
): Promise<APIResponse<ConfluenceExportData>> {
  return apiFetch<ConfluenceExportData>(
    `/api/fs/${docId}/export/confluence`,
    { method: "POST" }
  );
}

// ── Report Export ─────────────────────────────────────

export interface ReportExportData {
  filename: string;
  format: string;
  size_bytes: number;
  download_url: string;
}

/**
 * Generate a PDF report. (L10)
 */
export async function exportPdfReport(
  docId: string
): Promise<APIResponse<ReportExportData>> {
  return apiFetch<ReportExportData>(`/api/fs/${docId}/export/pdf`);
}

/**
 * Generate a DOCX report. (L10)
 */
export async function exportDocxReport(
  docId: string
): Promise<APIResponse<ReportExportData>> {
  return apiFetch<ReportExportData>(`/api/fs/${docId}/export/docx`);
}

// ── MCP Monitoring ────────────────────────────────────

export interface MCPSession {
  id: string;
  fs_id: string | null;
  target_stack: string;
  source: string;
  status: "RUNNING" | "PASSED" | "FAILED" | "CANCELLED";
  phase: number;
  total_phases: number;
  current_step: string;
  dry_run: boolean;
  meta_json: Record<string, unknown> | null;
  started_at: string;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MCPSessionEvent {
  id: string;
  session_id: string;
  event_type: string;
  phase: number;
  status: string;
  message: string;
  payload_json: Record<string, unknown> | null;
  created_at: string;
}

export interface MCPSessionListData {
  sessions: MCPSession[];
  total: number;
}

export interface MCPSessionEventListData {
  events: MCPSessionEvent[];
  total: number;
}

export async function listMcpSessions(
  limit: number = 50
): Promise<APIResponse<MCPSessionListData>> {
  return apiFetch<MCPSessionListData>(`/api/mcp/sessions?limit=${limit}`);
}

export async function getMcpSession(
  sessionId: string
): Promise<APIResponse<MCPSession>> {
  return apiFetch<MCPSession>(`/api/mcp/sessions/${sessionId}`);
}

export async function listMcpSessionEvents(
  sessionId: string,
  limit: number = 200
): Promise<APIResponse<MCPSessionEventListData>> {
  return apiFetch<MCPSessionEventListData>(
    `/api/mcp/sessions/${sessionId}/events?limit=${limit}`
  );
}
