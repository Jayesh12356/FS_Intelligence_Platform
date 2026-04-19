/**
 * Typed API client for the FS Intelligence Platform backend.
 *
 * All calls go through the backend API at NEXT_PUBLIC_API_URL.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Typed API error raised by `apiFetch` on non-2xx responses. */
export class APIError extends Error {
  status: number;
  code: string;
  requestId?: string;
  detail?: unknown;
  constructor(message: string, init: { status: number; code?: string; requestId?: string; detail?: unknown }) {
    super(message);
    this.name = "APIError";
    this.status = init.status;
    this.code = init.code ?? `http_${init.status}`;
    this.requestId = init.requestId;
    this.detail = init.detail;
  }
}

export function isApiError(err: unknown): err is APIError {
  return err instanceof APIError;
}

/** Shallow helper to extract a user-facing message from any thrown value. */
export function errorMessage(err: unknown, fallback = "Something went wrong"): string {
  if (isApiError(err)) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

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
  /**
   * True when the FS body changed (refine / accept-suggestion / accept-edge-case
   * / accept-contradiction) after the last successful analyze. The Build CTA
   * stays available; the document detail page surfaces a soft "Re-analyze
   * to refresh metrics" banner so the user can re-run analysis on demand.
   */
  analysis_stale?: boolean;
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
  resolution_text?: string | null;
  resolved_at?: string | null;
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

export interface RefinementSuggestion {
  issue: string;
  original: string;
  refined: string;
}

export interface RefinementDiffLine {
  line: string;
}

export interface RefinementResponse {
  original_score: number;
  refined_score: number;
  changes_made: number;
  refined_text: string;
  diff: RefinementDiffLine[];
  suggestions: RefinementSuggestion[];
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

export async function apiFetch<T>(
  path: string,
  options?: RequestInit & { signal?: AbortSignal }
): Promise<APIResponse<T>> {
  const url = `${API_BASE}${path}`;

  let res: Response;
  try {
    res = await fetch(url, {
      ...options,
      headers: {
        ...options?.headers,
      },
    });
  } catch (err) {
    if ((err as { name?: string })?.name === "AbortError") throw err;
    throw new APIError(
      `Network error contacting ${url}`,
      { status: 0, code: "network_error", detail: String(err) }
    );
  }

  const requestId = res.headers.get("X-Request-ID") ?? undefined;

  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as
      | { error?: string; detail?: unknown; code?: string; request_id?: string }
      | null;
    const detailText =
      typeof body?.detail === "string"
        ? body.detail
        : Array.isArray(body?.detail)
        ? (body!.detail as Array<{ msg?: string }>)
            .map((d) => d?.msg)
            .filter(Boolean)
            .join("; ")
        : undefined;
    const message =
      detailText || body?.error || `API error: ${res.status} ${res.statusText}`;
    throw new APIError(message, {
      status: res.status,
      code: body?.code,
      requestId: body?.request_id ?? requestId,
      detail: body?.detail,
    });
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
export async function listDocuments(
  opts?: { limit?: number; offset?: number; signal?: AbortSignal },
): Promise<APIResponse<DocumentListData>> {
  const params = new URLSearchParams();
  if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts?.offset !== undefined) params.set("offset", String(opts.offset));
  const qs = params.toString();
  const path = qs ? `/api/fs/?${qs}` : "/api/fs/";
  return apiFetch<DocumentListData>(path, { signal: opts?.signal });
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
 * Reset a stuck document status back to PARSED (or UPLOADED).
 */
export async function resetDocumentStatus(
  id: string
): Promise<APIResponse<{ id: string; old_status: string; new_status: string }>> {
  return apiFetch<{ id: string; old_status: string; new_status: string }>(`/api/fs/${id}/reset-status`, {
    method: "POST",
  });
}

/**
 * Trigger document analysis (L3+L4).
 * Runs the LangGraph pipeline to detect ambiguities, contradictions,
 * edge cases, and compute quality scores.
 */
export async function analyzeDocument(
  id: string,
): Promise<APIResponse<AnalysisResponse | CursorTaskEnvelope>> {
  return apiFetch<AnalysisResponse | CursorTaskEnvelope>(
    `/api/fs/${id}/analyze`,
    { method: "POST" },
  );
}

// ── Analysis Progress ──────────────────────────────────

export interface AnalysisProgress {
  status: string;
  current_node: string | null;
  completed_nodes: string[];
  total_nodes: number;
  node_labels: Record<string, string>;
  logs: string[];
}

export async function getAnalysisProgress(
  id: string
): Promise<APIResponse<AnalysisProgress>> {
  return apiFetch<AnalysisProgress>(`/api/fs/${id}/analysis-progress`);
}

export async function cancelAnalysis(
  docId: string
): Promise<
  APIResponse<{ cancelled: boolean; document_id?: string; reason?: string }>
> {
  return apiFetch<{ cancelled: boolean; document_id?: string; reason?: string }>(
    `/api/fs/${docId}/cancel-analysis`,
    {
      method: "POST",
    }
  );
}

export async function editSection(
  docId: string,
  sectionIndex: number,
  body: { heading?: string; content?: string }
): Promise<APIResponse<FSSection>> {
  return apiFetch<FSSection>(`/api/fs/${docId}/sections/${sectionIndex}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function addSection(
  docId: string,
  body: { heading: string; content: string; insert_after?: number }
): Promise<APIResponse<FSSection>> {
  return apiFetch<FSSection>(`/api/fs/${docId}/sections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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
  flagId: string,
  body?: { resolution_text?: string; resolved?: boolean }
): Promise<APIResponse<AmbiguityFlag>> {
  return apiFetch<AmbiguityFlag>(`/api/fs/${docId}/ambiguities/${flagId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
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

export async function acceptEdgeCaseSuggestion(
  docId: string,
  edgeCaseId: string
): Promise<APIResponse<EdgeCaseGap>> {
  return apiFetch<EdgeCaseGap>(`/api/fs/${docId}/edge-cases/${edgeCaseId}/accept`, {
    method: "POST",
  });
}

export async function acceptContradictionSuggestion(
  docId: string,
  contradictionId: string
): Promise<APIResponse<Contradiction>> {
  return apiFetch<Contradiction>(`/api/fs/${docId}/contradictions/${contradictionId}/accept`, {
    method: "POST",
  });
}

export interface BulkResult {
  accepted?: number;
  resolved: number;
}

export async function bulkAcceptEdgeCases(docId: string): Promise<APIResponse<BulkResult>> {
  return apiFetch<BulkResult>(`/api/fs/${docId}/edge-cases/bulk-accept`, { method: "POST" });
}

export async function bulkResolveEdgeCases(docId: string): Promise<APIResponse<BulkResult>> {
  return apiFetch<BulkResult>(`/api/fs/${docId}/edge-cases/bulk-resolve`, { method: "POST" });
}

export async function bulkAcceptContradictions(docId: string): Promise<APIResponse<BulkResult>> {
  return apiFetch<BulkResult>(`/api/fs/${docId}/contradictions/bulk-accept`, { method: "POST" });
}

export async function bulkResolveContradictions(docId: string): Promise<APIResponse<BulkResult>> {
  return apiFetch<BulkResult>(`/api/fs/${docId}/contradictions/bulk-resolve`, { method: "POST" });
}

export async function bulkResolveAmbiguities(docId: string): Promise<APIResponse<BulkResult>> {
  return apiFetch<BulkResult>(`/api/fs/${docId}/ambiguities/bulk-resolve`, { method: "POST" });
}

/**
 * Get complete quality dashboard data for a document. (L4)
 */
export async function getQualityDashboard(
  id: string
): Promise<APIResponse<QualityDashboardResponse>> {
  return apiFetch<QualityDashboardResponse>(`/api/fs/${id}/quality-score`);
}

export async function refineDocument(
  id: string
): Promise<APIResponse<RefinementResponse | CursorTaskEnvelope>> {
  return apiFetch<RefinementResponse | CursorTaskEnvelope>(
    `/api/fs/${id}/refine`,
    {
      method: "POST",
    },
  );
}

export async function acceptRefinedDocument(
  id: string,
  refinedText: string
): Promise<APIResponse<{ accepted: boolean; version_id: string; version_number: number }>> {
  return apiFetch<{ accepted: boolean; version_id: string; version_number: number }>(
    `/api/fs/${id}/refine/accept`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refined_text: refinedText }),
    }
  );
}

/** Alias for UI copy: POST refine (suggestions + refined text). */
export const getRefinementSuggestions = refineDocument;

/** Alias for UI copy: accept refined version. */
export const applyRefinement = acceptRefinedDocument;

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
): Promise<APIResponse<FSVersionItem | CursorTaskEnvelope>> {
  const formData = new FormData();
  formData.append("file", file);

  return apiFetch<FSVersionItem | CursorTaskEnvelope>(
    `/api/fs/${docId}/version`,
    {
      method: "POST",
      body: formData,
    },
  );
}

/**
 * List all versions for a document. (L7)
 */
export async function listVersions(
  id: string
): Promise<APIResponse<VersionListData>> {
  return apiFetch<VersionListData>(`/api/fs/${id}/versions`);
}

export interface VersionTextData {
  id: string;
  version_number: number;
  parsed_text: string;
}

export async function getVersionText(
  docId: string,
  versionId: string
): Promise<APIResponse<VersionTextData>> {
  return apiFetch<VersionTextData>(`/api/fs/${docId}/versions/${versionId}/text`);
}

export async function revertToVersion(
  docId: string,
  versionId: string
): Promise<APIResponse<{ reverted: boolean; version_number: number }>> {
  return apiFetch<{ reverted: boolean; version_number: number }>(
    `/api/fs/${docId}/versions/${versionId}/revert`,
    { method: "POST" }
  );
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
export async function listCodeUploads(
  opts?: { limit?: number; offset?: number; signal?: AbortSignal },
): Promise<APIResponse<CodeUploadListData>> {
  const params = new URLSearchParams();
  if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts?.offset !== undefined) params.set("offset", String(opts.offset));
  const qs = params.toString();
  const path = qs ? `/api/code/uploads?${qs}` : "/api/code/uploads";
  return apiFetch<CodeUploadListData>(path, { signal: opts?.signal });
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
  id: string,
): Promise<APIResponse<GeneratedFSData | CursorTaskEnvelope>> {
  return apiFetch<GeneratedFSData | CursorTaskEnvelope>(
    `/api/code/${id}/generate-fs`,
    { method: "POST" },
  );
}

/**
 * Get generated FS for a code upload. (L8)
 */
export async function getGeneratedFS(
  id: string
): Promise<APIResponse<GeneratedFSData>> {
  return apiFetch<GeneratedFSData>(`/api/code/${id}/generated-fs`);
}

/** Reverse FS UI aliases (same endpoints as codebase upload / generated FS). */
export type ReverseUploadItem = CodeUploadItem;
export const uploadCodeZip = uploadCodebase;
export const listReverseUploads = listCodeUploads;
export const getReverseStatus = getGeneratedFS;

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

// ── Activity Log (Global) ─────────────────────────────

export interface ActivityLogEntry {
  id: string | null;
  fs_id: string;
  document_name: string;
  event_type: string;
  event_label: string;
  detail: string | null;
  user_id: string;
  created_at: string | null;
  /** "document" | "analysis" | "build" | "collab" — used for color chips. */
  category?: string;
  /** Raw payload — only present when called with include_payload=true. */
  payload?: Record<string, unknown> | null;
}

export interface ActivityLogData {
  events: ActivityLogEntry[];
  total: number;
}

/**
 * Fetch the activity-log timeline. The legacy positional signature is
 * preserved for callers that pass numbers/strings directly; new callers
 * are encouraged to use the options-object form so they can target a
 * single document via ``fsId`` (powers the per-doc Lifecycle strip).
 */
export async function getActivityLog(
  arg1?:
    | number
    | {
        limit?: number;
        offset?: number;
        eventType?: string;
        documentName?: string;
        fsId?: string;
        category?: string;
        includePayload?: boolean;
      },
  offset: number = 0,
  eventType?: string,
  documentName?: string,
): Promise<APIResponse<ActivityLogData>> {
  let limit = 50;
  let off = offset;
  let evt = eventType;
  let docName = documentName;
  let fsId: string | undefined;
  let category: string | undefined;
  let includePayload = false;
  if (typeof arg1 === "object" && arg1 !== null) {
    limit = arg1.limit ?? 50;
    off = arg1.offset ?? 0;
    evt = arg1.eventType;
    docName = arg1.documentName;
    fsId = arg1.fsId;
    category = arg1.category;
    includePayload = !!arg1.includePayload;
  } else if (typeof arg1 === "number") {
    limit = arg1;
  }
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(off));
  if (evt) params.set("event_type", evt);
  if (docName) params.set("document_name", docName);
  if (fsId) params.set("fs_id", fsId);
  if (category) params.set("category", category);
  if (includePayload) params.set("include_payload", "true");
  return apiFetch<ActivityLogData>(`/api/activity-log?${params.toString()}`);
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

// ── Project Types & Functions ─────────────────────────

export interface FSProject {
  id: string;
  name: string;
  description: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface FSProjectDetail extends FSProject {
  documents: FSDocumentResponse[];
}

export interface ProjectListData {
  projects: FSProject[];
  total: number;
}

export async function createProject(
  name: string,
  description?: string
): Promise<APIResponse<FSProject>> {
  return apiFetch<FSProject>("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
}

export async function listProjects(): Promise<APIResponse<ProjectListData>> {
  return apiFetch<ProjectListData>("/api/projects");
}

export async function getProject(
  id: string
): Promise<APIResponse<FSProjectDetail>> {
  return apiFetch<FSProjectDetail>(`/api/projects/${id}`);
}

export async function updateProject(
  id: string,
  body: { name?: string; description?: string }
): Promise<APIResponse<FSProject>> {
  return apiFetch<FSProject>(`/api/projects/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function deleteProject(
  id: string
): Promise<APIResponse<{ id: string; deleted: boolean }>> {
  return apiFetch<{ id: string; deleted: boolean }>(`/api/projects/${id}`, {
    method: "DELETE",
  });
}

export async function assignDocumentToProject(
  projectId: string,
  docId: string
): Promise<APIResponse<{ document_id: string; project_id: string; order_in_project: number }>> {
  return apiFetch<{ document_id: string; project_id: string; order_in_project: number }>(
    `/api/projects/${projectId}/documents/${docId}`,
    { method: "POST" }
  );
}

export async function uploadFileToProject(
  file: File,
  projectId: string
): Promise<APIResponse<UploadResponse>> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<UploadResponse>(`/api/fs/upload?project_id=${projectId}`, {
    method: "POST",
    body: formData,
  });
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

/** Aliases for monitoring UI */
export const getMCPSessions = listMcpSessions;
export const getMCPSessionEvents = listMcpSessionEvents;
export const getMCPSession = getMcpSession;

// ── Phase 2: Idea-to-FS ──────────────────────────────

export interface IdeaGenerateResponse {
  document_id: string;
  filename: string;
  fs_text: string;
  section_count: number;
}

export interface GuidedQuestion {
  id: string;
  question: string;
  dimension: string;
  options: string[];
}

export interface GuidedQuestionsResponse {
  session_id: string;
  step: number;
  questions: GuidedQuestion[];
}

export async function generateFSFromIdea(
  idea: string,
  industry?: string,
  complexity?: string,
): Promise<APIResponse<IdeaGenerateResponse | CursorTaskEnvelope>> {
  return apiFetch<IdeaGenerateResponse | CursorTaskEnvelope>(
    "/api/idea/generate",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idea, industry, complexity }),
    },
  );
}

export async function guidedIdeaStep(
  params: {
    session_id?: string;
    idea?: string;
    step: number;
    answers?: Record<string, string>;
    industry?: string;
    complexity?: string;
  },
): Promise<
  APIResponse<
    GuidedQuestionsResponse | IdeaGenerateResponse | CursorTaskEnvelope
  >
> {
  return apiFetch("/api/idea/guided", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

/** Narrowing helper: returns true if backend returned a Cursor paste task envelope. */
export function isCursorTaskEnvelope(
  v: unknown,
): v is CursorTaskEnvelope {
  return (
    !!v &&
    typeof v === "object" &&
    (v as { mode?: string }).mode === "cursor_task"
  );
}

// ── Phase 2: Tool Orchestration ──────────────────────

export interface ProviderInfo {
  name: string;
  display_name: string;
  capabilities: string[];
  healthy: boolean | null;
  /** When false, hidden from the automatic LLM picker (build/MCP-only tools). */
  llm_selectable?: boolean;
  /** Extra context for health checks (e.g. MCP vs CLI). */
  health_note?: string;
}

export interface ToolConfig {
  id: string;
  llm_provider: string;
  build_provider: string;
  frontend_provider: string;
  fallback_chain: string[];
  cursor_config: Record<string, unknown>;
  claude_code_config: Record<string, unknown>;
}

export interface ProviderTestResult {
  provider: string;
  display_name?: string;
  healthy: boolean;
  capabilities?: string[];
  error?: string;
}

export async function listProviders(): Promise<APIResponse<ProviderInfo[]>> {
  return apiFetch<ProviderInfo[]>("/api/orchestration/providers");
}

export async function getToolConfig(): Promise<APIResponse<ToolConfig>> {
  return apiFetch<ToolConfig>("/api/orchestration/config");
}

export async function updateToolConfig(
  config: Partial<ToolConfig>,
): Promise<APIResponse<ToolConfig>> {
  return apiFetch<ToolConfig>("/api/orchestration/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
}

export async function testProvider(
  providerName: string,
): Promise<APIResponse<ProviderTestResult>> {
  return apiFetch<ProviderTestResult>(
    `/api/orchestration/test/${providerName}`,
    { method: "POST" },
  );
}

export async function getProviderCapabilities(): Promise<APIResponse<Record<string, string[]>>> {
  return apiFetch<Record<string, string[]>>("/api/orchestration/capabilities");
}

export interface MCPConfigSnippet {
  path: string;
  snippet: Record<string, unknown>;
  install_steps: string[];
  agent_prompt?: string;
  cli_command?: string;
}

export interface MCPConfigBundle {
  cursor: MCPConfigSnippet;
  claude_code: MCPConfigSnippet;
  notes: string;
  document_id?: string | null;
  stack?: string;
  output_folder?: string;
}

export async function getMcpConfig(
  params: { document_id?: string; stack?: string; output_folder?: string } = {},
): Promise<APIResponse<MCPConfigBundle>> {
  const search = new URLSearchParams();
  if (params.document_id) search.set("document_id", params.document_id);
  if (params.stack) search.set("stack", params.stack);
  if (params.output_folder) search.set("output_folder", params.output_folder);
  const qs = search.toString();
  const path = qs ? `/api/orchestration/mcp-config?${qs}` : "/api/orchestration/mcp-config";
  return apiFetch<MCPConfigBundle>(path);
}

// ── Build Engine ──────────────────────────────────────

export interface BuildState {
  id: string;
  document_id: string;
  status: "PENDING" | "RUNNING" | "PAUSED" | "COMPLETE" | "FAILED" | "CANCELLED" | "PASSED";
  current_phase: number;
  current_task_index: number;
  completed_task_ids: string[];
  failed_task_ids: string[];
  total_tasks: number;
  stack: string | null;
  output_folder: string | null;
  started_at: string | null;
  last_updated: string | null;
}

export interface FileRegistryEntry {
  id: string;
  document_id: string;
  task_id: string | null;
  section_id: string | null;
  file_path: string;
  file_type: string | null;
  status: string | null;
  created_at: string | null;
}

export async function getBuildState(
  docId: string,
  opts?: { signal?: AbortSignal },
): Promise<APIResponse<BuildState | null>> {
  return apiFetch<BuildState | null>(`/api/fs/${docId}/build-state`, { signal: opts?.signal });
}

export interface BuildPromptSummary {
  quality: number;
  tasks: number;
  sections: number;
  blockers: number;
  high_ambiguities: number;
  contradictions: number;
  edge_cases: number;
  status: string;
}

export interface BuildPromptResponse {
  prompt: string;
  mcp_config: Record<string, unknown>;
  summary: BuildPromptSummary;
}

/** Fetch the rich, analysis-aware agent prompt for a document. Used by the
 * Build page so Cursor / Claude Code receive a single comprehensive
 * instruction (quality, task count, blockers, key MCP tools, …) rather
 * than the bare one-liner served by `/api/orchestration/mcp-config`. */
export async function getBuildPrompt(
  docId: string,
  params: { stack?: string; output_folder?: string } = {},
  opts?: { signal?: AbortSignal },
): Promise<APIResponse<BuildPromptResponse>> {
  const search = new URLSearchParams();
  if (params.stack) search.set("stack", params.stack);
  if (params.output_folder) search.set("output_folder", params.output_folder);
  const qs = search.toString();
  const path = qs
    ? `/api/fs/${docId}/build-prompt?${qs}`
    : `/api/fs/${docId}/build-prompt`;
  return apiFetch<BuildPromptResponse>(path, { signal: opts?.signal });
}

export interface RunBuildResponse {
  build_state_id: string;
  document_id: string;
  status: string;
  stack: string;
  output_folder: string;
  provider: string;
}

/** Kick off a headless Claude Code build for the document. */
export async function runBuild(
  docId: string,
  params: {
    provider?: "claude_code";
    stack?: string;
    output_folder?: string;
  } = {},
): Promise<APIResponse<RunBuildResponse>> {
  return apiFetch<RunBuildResponse>(`/api/fs/${docId}/build/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider: params.provider ?? "claude_code",
      stack: params.stack ?? "Next.js + FastAPI",
      output_folder: params.output_folder ?? "./output",
    }),
  });
}

export async function listFileRegistry(
  docId: string,
  opts?: { signal?: AbortSignal },
): Promise<APIResponse<{ files: FileRegistryEntry[]; total: number }>> {
  return apiFetch<{ files: FileRegistryEntry[]; total: number }>(
    `/api/fs/${docId}/file-registry`,
    { signal: opts?.signal },
  );
}

export interface PreBuildCheckResult {
  go: boolean;
  checks: Record<string, { pass: boolean; [k: string]: unknown }>;
  blockers: string[];
  warnings: string[];
}

export async function getPreBuildCheck(
  docId: string,
  opts?: { signal?: AbortSignal },
): Promise<APIResponse<PreBuildCheckResult>> {
  return apiFetch<PreBuildCheckResult>(`/api/fs/${docId}/pre-build-check`, {
    signal: opts?.signal,
  });
}


// ── Cursor paste-per-action tasks ────────────────────────────────

export type CursorTaskKind =
  | "generate_fs"
  | "analyze"
  | "reverse_fs"
  | "refine"
  | "impact";
export type CursorTaskStatus =
  | "pending"
  | "claimed"
  | "done"
  | "failed"
  | "expired";

export interface CursorTaskEnvelope {
  mode: "cursor_task";
  task_id: string;
  kind: CursorTaskKind;
  prompt: string;
  mcp_snippet: string;
  status: CursorTaskStatus;
}

export interface CursorTaskPoll {
  id: string;
  kind: CursorTaskKind;
  status: CursorTaskStatus;
  result_ref: string | null;
  error: string | null;
  created_at: string;
  claimed_at: string | null;
  completed_at: string | null;
}

const JSON_HEADERS = { "Content-Type": "application/json" } as const;

export async function createCursorTaskGenerateFS(body: {
  idea: string;
  industry?: string;
  complexity?: string;
}): Promise<APIResponse<CursorTaskEnvelope>> {
  return apiFetch<CursorTaskEnvelope>("/api/cursor-tasks/generate-fs", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export async function createCursorTaskAnalyze(
  docId: string,
): Promise<APIResponse<CursorTaskEnvelope>> {
  return apiFetch<CursorTaskEnvelope>(
    `/api/cursor-tasks/analyze/${docId}`,
    { method: "POST", headers: JSON_HEADERS, body: "{}" },
  );
}

export async function createCursorTaskReverseFS(
  uploadId: string,
): Promise<APIResponse<CursorTaskEnvelope>> {
  return apiFetch<CursorTaskEnvelope>(
    `/api/cursor-tasks/reverse-fs/${uploadId}`,
    { method: "POST", headers: JSON_HEADERS, body: "{}" },
  );
}

export async function createCursorTaskRefine(
  docId: string,
): Promise<APIResponse<CursorTaskEnvelope>> {
  return apiFetch<CursorTaskEnvelope>(
    `/api/cursor-tasks/refine/${docId}`,
    { method: "POST", headers: JSON_HEADERS, body: "{}" },
  );
}

export async function createCursorTaskImpact(
  versionId: string,
): Promise<APIResponse<CursorTaskEnvelope>> {
  return apiFetch<CursorTaskEnvelope>(
    `/api/cursor-tasks/impact/${versionId}`,
    { method: "POST", headers: JSON_HEADERS, body: "{}" },
  );
}

export async function pollCursorTask(
  taskId: string,
  opts?: { signal?: AbortSignal },
): Promise<APIResponse<CursorTaskPoll>> {
  return apiFetch<CursorTaskPoll>(`/api/cursor-tasks/${taskId}`, {
    signal: opts?.signal,
  });
}

export async function cancelCursorTask(
  taskId: string,
): Promise<APIResponse<CursorTaskPoll>> {
  return apiFetch<CursorTaskPoll>(`/api/cursor-tasks/${taskId}/cancel`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: "{}",
  });
}
