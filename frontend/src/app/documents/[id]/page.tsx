"use client";

import { useEffect, useState, useCallback, type ReactNode } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  getDocument,
  parseDocument,
  analyzeDocument,
  cancelAnalysis,
  listDuplicates,
  getApprovalStatus,
  editSection,
  addSection,
  getQualityDashboard,
  listAmbiguities,
  listTasks,
  exportToJira,
  exportToConfluence,
  exportPdfReport,
  exportDocxReport,
  isCursorTaskEnvelope,
} from "@/lib/api";
import { useToolConfig, normalizeProvider } from "@/lib/toolConfig";
import type {
  CursorTaskEnvelope,
  FSDocumentDetail,
  FSSection,
  DuplicateFlag,
  QualityDashboardResponse,
  AmbiguityFlag,
  TaskListData,
} from "@/lib/api";
import {
  CursorTaskModal,
  PageShell,
  KpiCard,
  FadeIn,
  EmptyState,
} from "@/components/index";
import { StatusBadge } from "@/components/Badge";
import { DocumentLifecycle } from "./_components/DocumentLifecycle";
import CopyButton from "@/components/CopyButton";
import { AnalysisProgress } from "@/components/AnalysisProgress";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  Layers,
  AlertTriangle,
  CheckCircle2,
  Zap,
  BarChart3,
  ListTodo,
  GitCompare,
  Users,
  Link2,
  Sparkles,
  Play,
  ChevronDown,
  ChevronRight,
  Hash,
  HardDrive,
  Type,
  Clock,
  RotateCcw,
  Edit3,
  Plus,
  Save,
  X,
  Download,
  TestTube2,
} from "lucide-react";

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatSize(bytes: number | null): string {
  if (!bytes) return "\u2014";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function qualityLabel(status: string, complete: boolean): string {
  if (complete) return "Complete";
  if (status === "PARSED") return "Ready to analyze";
  if (status === "ANALYZING" || status === "PARSING") return "In progress";
  if (status === "UPLOADED") return "Awaiting parse";
  if (status === "ERROR" || status === "PARSE_FAILED") return "Needs attention";
  return status;
}

function approvalLabel(s: string): string {
  if (s === "APPROVED") return "Approved";
  if (s === "REJECTED") return "Rejected";
  if (s === "PENDING") return "Pending";
  return "Not set";
}

const SEPARATOR_RE = /^[-=~*]{3,}$/;
const REFINED_TAG_RE = /\s*\[REFINED\]/g;

function cleanLine(line: string): string {
  return line.replace(REFINED_TAG_RE, "");
}

function renderRichContent(content: string): ReactNode {
  if (!content) return null;
  const lines = content.split("\n");
  return (
    <div className="section-content-rich">
      {lines.map((line, i) => {
        if (SEPARATOR_RE.test(line.trim())) return null;
        const cleaned = cleanLine(line);
        const trimmed = cleaned.trimStart();
        if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
          return (
            <div key={i} className="req-line req-bullet">
              {trimmed.slice(2)}
            </div>
          );
        }
        if (cleaned.trim() === "") {
          return <div key={i} style={{ height: "0.5rem" }} />;
        }
        return (
          <div key={i} className="req-line">
            {cleaned}
          </div>
        );
      })}
    </div>
  );
}

function contentPreview(content: string, maxLen = 120): string {
  if (!content) return "";
  const clean = content
    .replace(REFINED_TAG_RE, "")
    .split("\n")
    .filter((l) => !SEPARATOR_RE.test(l.trim()))
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
  if (clean.length <= maxLen) return clean;
  return clean.slice(0, maxLen) + "\u2026";
}

type TabId = "sections" | "analysis";

export default function DocumentDetailPage() {
  const params = useParams();
  const docId = params.id as string;
  const [doc, setDoc] = useState<FSDocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [cursorTask, setCursorTask] = useState<CursorTaskEnvelope | null>(null);
  const { config: toolConfig } = useToolConfig();
  const [sections, setSections] = useState<FSSection[]>([]);
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set());
  const [editingSection, setEditingSection] = useState<number | null>(null);
  const [editHeading, setEditHeading] = useState("");
  const [editContent, setEditContent] = useState("");
  const [savingSection, setSavingSection] = useState(false);
  const [showAddSection, setShowAddSection] = useState(false);
  const [newSectionHeading, setNewSectionHeading] = useState("");
  const [newSectionContent, setNewSectionContent] = useState("");
  const [addingSection, setAddingSection] = useState(false);
  const [duplicates, setDuplicates] = useState<DuplicateFlag[]>([]);
  const [approvalStatus, setApprovalStatus] = useState<string>("NONE");
  const [activeTab, setActiveTab] = useState<TabId>("sections");

  // Analysis summary data
  const [qualityData, setQualityData] = useState<QualityDashboardResponse | null>(null);
  const [ambiguities, setAmbiguities] = useState<AmbiguityFlag[]>([]);
  const [taskData, setTaskData] = useState<TaskListData | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  const fetchDoc = useCallback(async () => {
    try {
      setLoading(true);
      const result = await getDocument(docId);
      setDoc(result.data);
      if (result.data.sections) {
        setSections(result.data.sections);
      }
      try {
        const [dupRes, appRes] = await Promise.all([
          listDuplicates(docId),
          getApprovalStatus(docId),
        ]);
        setDuplicates(dupRes.data?.duplicates || []);
        setApprovalStatus(appRes.data?.current_status || "NONE");
      } catch {
        // Non-fatal
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load document");
    } finally {
      setLoading(false);
    }
  }, [docId]);

  const fetchAnalysisSummary = useCallback(async () => {
    try {
      const [qRes, aRes, tRes] = await Promise.all([
        getQualityDashboard(docId),
        listAmbiguities(docId),
        listTasks(docId),
      ]);
      if (qRes.data) setQualityData(qRes.data);
      if (aRes.data) setAmbiguities(Array.isArray(aRes.data) ? aRes.data : []);
      if (tRes.data) setTaskData(tRes.data);
    } catch {
      // Non-fatal — analysis data may not exist yet
    }
  }, [docId]);

  useEffect(() => {
    if (docId) fetchDoc();
  }, [docId, fetchDoc]);

  useEffect(() => {
    const status = doc?.status;
    if (!status) return;
    if (status === "COMPLETE" || status === "PARSED" || status === "ANALYZING") {
      fetchAnalysisSummary();
    }
    if (status === "COMPLETE") {
      setActiveTab("analysis");
    }
  }, [doc?.status, fetchAnalysisSummary]);

  // (removed) The legacy ?autoAnalyze=1 redirect from the refine page is no
  // longer needed: refinement keeps the document at COMPLETE and only flips
  // ``analysis_stale`` so the user can re-run analysis explicitly via the
  // banner below.

  // Refetch analysis data when user returns to this tab (back from subpages)
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "visible" && doc?.status === "COMPLETE") {
        fetchAnalysisSummary();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [doc?.status, fetchAnalysisSummary]);

  const handleParse = async () => {
    setParsing(true);
    setParseError(null);
    try {
      const result = await parseDocument(docId);
      setSections(result.data.sections);
      await fetchDoc();
    } catch (err: unknown) {
      setParseError(err instanceof Error ? err.message : "Parsing failed");
    } finally {
      setParsing(false);
    }
  };

  const handleAnalyze = async () => {
    setAnalyzeError(null);
    setAnalyzing(true);
    try {
      const res = await analyzeDocument(docId);
      if (isCursorTaskEnvelope(res.data)) {
        setCursorTask(res.data);
      } else {
        await fetchDoc();
      }
    } catch (err: unknown) {
      setAnalyzeError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await cancelAnalysis(docId);
      const refreshed = await getDocument(docId);
      if (refreshed.data) {
        setDoc(refreshed.data);
        setSections(refreshed.data.sections || []);
      }
    } catch (err: unknown) {
      setAnalyzeError(err instanceof Error ? err.message : "Cancel failed");
    } finally {
      setCancelling(false);
    }
  };

  const toggleSection = (index: number) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const expandAll = () => setExpandedSections(new Set(sections.map((_, i) => i)));
  const collapseAll = () => setExpandedSections(new Set());

  const handleEditSection = (idx: number) => {
    const s = sections[idx];
    setEditingSection(idx);
    setEditHeading(s.heading);
    setEditContent(s.content);
    setExpandedSections((prev) => new Set(prev).add(idx));
  };

  const handleSaveSection = async () => {
    if (editingSection === null) return;
    setSavingSection(true);
    try {
      await editSection(docId, editingSection, {
        heading: editHeading,
        content: editContent,
      });
      const refreshed = await getDocument(docId);
      if (refreshed.data) {
        setDoc(refreshed.data);
        setSections(refreshed.data.sections || []);
      }
      setEditingSection(null);
    } catch (err: unknown) {
      setParseError(err instanceof Error ? err.message : "Save section failed");
    } finally {
      setSavingSection(false);
    }
  };

  const handleCancelEdit = () => {
    setEditingSection(null);
    setEditHeading("");
    setEditContent("");
  };

  const handleAddSection = async () => {
    if (!newSectionHeading.trim()) return;
    setAddingSection(true);
    try {
      await addSection(docId, {
        heading: newSectionHeading,
        content: newSectionContent,
      });
      const refreshed = await getDocument(docId);
      if (refreshed.data) {
        setDoc(refreshed.data);
        setSections(refreshed.data.sections || []);
      }
      setShowAddSection(false);
      setNewSectionHeading("");
      setNewSectionContent("");
    } catch (err: unknown) {
      setParseError(err instanceof Error ? err.message : "Add section failed");
    } finally {
      setAddingSection(false);
    }
  };

  const handleExport = async (type: string) => {
    setExporting(type);
    setExportMsg(null);
    try {
      let result;
      switch (type) {
        case "jira":
          result = await exportToJira(docId);
          setExportMsg(`Exported ${result.data.total} stories to JIRA`);
          break;
        case "confluence":
          result = await exportToConfluence(docId);
          setExportMsg(`Exported to Confluence: ${result.data.title}`);
          break;
        case "pdf":
          result = await exportPdfReport(docId);
          if (result.data.download_url) window.open(result.data.download_url, "_blank");
          setExportMsg(`PDF report generated: ${result.data.filename}`);
          break;
        case "docx":
          result = await exportDocxReport(docId);
          if (result.data.download_url) window.open(result.data.download_url, "_blank");
          setExportMsg(`DOCX report generated: ${result.data.filename}`);
          break;
      }
    } catch (err: unknown) {
      setExportMsg(err instanceof Error ? err.message : `Export failed`);
    } finally {
      setExporting(null);
      setTimeout(() => setExportMsg(null), 5000);
    }
  };

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        Loading document\u2026
      </div>
    );
  }

  if (error || !doc) {
    return (
      <EmptyState
        icon={<AlertTriangle size={40} strokeWidth={1.25} aria-hidden />}
        title="Document not found"
        description={error || "The requested document could not be found."}
        action={
          <Link href="/documents" className="btn btn-primary btn-sm">
            Back to Documents
          </Link>
        }
      />
    );
  }

  const canParse = doc.status === "UPLOADED" || doc.status === "ERROR";
  const canAnalyze = doc.status === "PARSED";
  const isAnalyzing = doc.status === "ANALYZING" || analyzing;
  const isComplete = doc.status === "COMPLETE";
  const isParsed = doc.status === "PARSED" || doc.status === "ANALYZING" || doc.status === "COMPLETE";
  const hasAnalysisData = isComplete || qualityData !== null;
  const pipelineBadgeStatus = isAnalyzing ? "ANALYZING" : doc.status;

  const approvalIcon =
    approvalStatus === "APPROVED" ? <CheckCircle2 size={20} aria-hidden /> :
    approvalStatus === "REJECTED" ? <AlertTriangle size={20} aria-hidden /> :
    approvalStatus === "PENDING" ? <Clock size={20} aria-hidden /> :
    <Hash size={20} aria-hidden />;

  const approvalWell =
    approvalStatus === "APPROVED" ? "var(--well-green)" :
    approvalStatus === "REJECTED" ? "var(--well-red)" :
    approvalStatus === "PENDING" ? "var(--well-amber)" :
    "var(--well-gray)";

  const analysisLinks: { href: string; title: string; icon: ReactNode; well: string; id?: string }[] = [
    { href: `/documents/${doc.id}/ambiguities`, title: "Ambiguity Analysis", icon: <AlertTriangle size={20} aria-hidden />, well: "var(--well-amber)" },
    { href: `/documents/${doc.id}/quality`, title: "Quality Dashboard", icon: <BarChart3 size={20} aria-hidden />, well: "var(--well-blue)" },
    { href: `/documents/${doc.id}/tasks`, title: "Task Board", icon: <ListTodo size={20} aria-hidden />, well: "var(--well-purple)" },
    { href: `/documents/${doc.id}/impact`, title: "Impact Analysis", icon: <GitCompare size={20} aria-hidden />, well: "var(--well-peach)" },
    { href: `/documents/${doc.id}/collab`, title: "Collaboration", icon: <Users size={20} aria-hidden />, well: "var(--well-gray)", id: "btn-collab-link" },
    { href: `/documents/${doc.id}/traceability`, title: "Traceability Matrix", icon: <Link2 size={20} aria-hidden />, well: "var(--well-blue)", id: "btn-traceability-link" },
    { href: `/documents/${doc.id}/refine`, title: "Refine FS", icon: <Sparkles size={20} aria-hidden />, well: "var(--well-purple)" },
    { href: `/documents/${doc.id}/tests`, title: "Test Cases", icon: <TestTube2 size={20} aria-hidden />, well: "var(--well-peach)" },
  ];

  const ambiguityCount = ambiguities.filter((a) => !a.resolved).length;
  const contradictionCount = qualityData?.contradictions?.length ?? 0;
  const edgeCaseCount = qualityData?.edge_cases?.length ?? 0;
  const qualityScore = qualityData?.quality_score?.overall ?? null;
  const taskCount = taskData?.total ?? 0;

  return (
    <PageShell
      backHref="/documents"
      backLabel="Documents"
      title={doc.filename}
      badge={<StatusBadge status={pipelineBadgeStatus} />}
      subtitle={`Uploaded ${formatDate(doc.created_at)} \u00b7 Updated ${formatDate(doc.updated_at)}`}
    >
      {/* ── KPI Row ──────────────────────────────────────── */}
      <FadeIn delay={0.04}>
        <div className="kpi-row">
          <KpiCard
            label="Sections"
            value={sections.length}
            icon={<Layers size={20} aria-hidden />}
            iconBg="var(--well-blue)"
            delay={0}
          />
          <KpiCard
            label="File size"
            valueText={formatSize(doc.file_size)}
            icon={<HardDrive size={20} aria-hidden />}
            iconBg="var(--well-purple)"
            delay={0.05}
          />
          <KpiCard
            label="Quality status"
            valueText={qualityLabel(doc.status, isComplete)}
            icon={isComplete ? <CheckCircle2 size={20} aria-hidden /> : <Zap size={20} aria-hidden />}
            iconBg={isComplete ? "var(--well-green)" : "var(--well-amber)"}
            delay={0.1}
          />
          <div id="approval-status-badge">
            <KpiCard
              label="Approval status"
              valueText={approvalLabel(approvalStatus)}
              icon={approvalIcon}
              iconBg={approvalWell}
              delay={0.15}
            />
          </div>
        </div>
        <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginTop: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
            <Type size={14} aria-hidden />
            {doc.content_type || "\u2014"}
          </span>
          <span aria-hidden style={{ opacity: 0.4 }}>\u00b7</span>
          <span style={{ fontFamily: "var(--font-mono)", wordBreak: "break-all" }}>{doc.id}</span>
          <CopyButton text={doc.id} label="Copy ID" className="btn btn-secondary btn-sm" />
        </p>
        <DocumentLifecycle fsId={doc.id} />
      </FadeIn>

      {/* ── Duplicate Warning ────────────────────────────── */}
      {duplicates.length > 0 && (
        <FadeIn delay={0.08} style={{ marginTop: "1.5rem" }}>
          <div className="alert alert-warning" id="duplicate-warning-banner">
            <AlertTriangle size={20} style={{ flexShrink: 0 }} aria-hidden />
            <div style={{ flex: 1, minWidth: 0 }}>
              <strong>
                {duplicates.length} potential duplicate{duplicates.length !== 1 ? "s" : ""} found
              </strong>
              <p style={{ margin: "0.35rem 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                Similar requirements were detected in other FS documents.
              </p>
              <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {duplicates.slice(0, 3).map((d, i) => (
                  <div key={i} style={{ fontSize: "0.8125rem", padding: "0.5rem 0.65rem", background: "var(--bg-card)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
                    <strong>Section {d.section_index}: {d.section_heading}</strong>
                    <span style={{ color: "var(--text-muted)", marginLeft: "0.5rem" }}>
                      {(d.similarity_score * 100).toFixed(0)}% similar to &quot;{d.similar_section_heading}&quot;
                    </span>
                  </div>
                ))}
                {duplicates.length > 3 && (
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", margin: 0 }}>
                    \u2026and {duplicates.length - 3} more
                  </p>
                )}
              </div>
            </div>
          </div>
        </FadeIn>
      )}

      {/* ── Pipeline Actions ─────────────────────────────── */}
      <FadeIn delay={0.1} style={{ marginTop: "1.5rem" }}>
        {canParse && (
          <div style={{ marginBottom: "1.25rem" }}>
            <button type="button" className="btn btn-primary" onClick={handleParse} disabled={parsing} style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
              {parsing ? (
                <><span className="spinner" style={{ width: 16, height: 16 }} />Parsing document\u2026</>
              ) : (
                <><Zap size={18} aria-hidden />Parse Document</>
              )}
            </button>
            {parseError && <p className="alert alert-error" style={{ marginTop: "0.75rem", display: "block" }}>{parseError}</p>}
          </div>
        )}

        {canAnalyze && !analyzing && (
          <div style={{ marginBottom: "1.25rem" }}>
            <button type="button" className="btn btn-primary" onClick={handleAnalyze} style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
              <BarChart3 size={18} aria-hidden />
              Analyze Document
            </button>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginTop: "0.5rem", maxWidth: "42rem" }}>
              Runs the full pipeline: ambiguities, contradictions, edge cases, quality scoring, task decomposition, and more.
            </p>
          </div>
        )}

        {isAnalyzing && (
          <AnalysisProgress
            docId={docId}
            isAnalyzing={isAnalyzing}
            onCancel={handleCancel}
            cancelling={cancelling}
          />
        )}

        {analyzeError && (
          <p className="alert alert-error" style={{ marginBottom: "1.25rem", display: "block" }}>{analyzeError}</p>
        )}

        {isComplete && doc.analysis_stale && (
          <div
            className="card alert-warning"
            role="status"
            style={{
              marginBottom: "1.25rem",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "1rem",
              flexWrap: "wrap",
              borderColor: "var(--warning, #f59e0b)",
              background: "var(--bg-warning-subtle, rgba(245,158,11,0.08))",
            }}
          >
            <div style={{ display: "flex", gap: "0.65rem", alignItems: "flex-start" }}>
              <Zap size={18} aria-hidden style={{ marginTop: "0.15rem" }} />
              <div>
                <strong>FS was refined since the last analysis.</strong>
                <p style={{ margin: "0.2rem 0 0", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                  Re-analyze to refresh metrics. The build CTA stays available so you can ship now or after.
                </p>
              </div>
            </div>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleAnalyze}
              disabled={analyzing}
            >
              {analyzing ? "Re-analyzing…" : "Re-analyze"}
            </button>
          </div>
        )}

        {isComplete && (() => {
          const buildPref = normalizeProvider(toolConfig?.build_provider);
          if (buildPref !== "cursor" && buildPref !== "claude_code") return null;
          const isClaude = buildPref === "claude_code";
          const ctaLabel = isClaude ? "Build with Claude" : "Build with Cursor";
          const ctaSub = isClaude
            ? "Spawns Claude Code with the rich, analysis-aware prompt and the MCP server wired in."
            : "Opens the Cursor kickoff page with the MCP snippet and the rich, analysis-aware agent prompt.";
          return (
            <div className="card" style={{ marginBottom: "1.5rem" }} data-testid="build-cta-card">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
                  <div className="kpi-icon" style={{ background: "var(--bg-success-subtle)", color: "var(--success)" }}>
                    <CheckCircle2 size={22} aria-hidden />
                  </div>
                  <div>
                    <h3 className="page-title" style={{ fontSize: "1.05rem", marginBottom: "0.25rem" }}>Analysis complete</h3>
                    <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: 0 }}>{ctaSub}</p>
                  </div>
                </div>
                <Link
                  href={`/documents/${doc.id}/build`}
                  className="btn btn-primary"
                  style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}
                  aria-label={ctaLabel}
                  data-testid="build-cta-link"
                >
                  <Play size={18} aria-hidden />
                  {ctaLabel}
                </Link>
              </div>
            </div>
          );
        })()}
      </FadeIn>

      {/* ── Re-parse fallback ────────────────────────────── */}
      {isParsed && sections.length === 0 && (
        <FadeIn delay={0.1} style={{ marginTop: "1.5rem" }}>
          <button type="button" className="btn btn-primary" onClick={handleParse} disabled={parsing} style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
            {parsing ? (
              <><span className="spinner" style={{ width: 16, height: 16 }} />Re-parsing\u2026</>
            ) : (
              <><RotateCcw size={18} aria-hidden />Re-parse Document</>
            )}
          </button>
        </FadeIn>
      )}

      {/* ── Tab Bar ──────────────────────────────────────── */}
      {sections.length > 0 && (
        <FadeIn delay={0.12} style={{ marginTop: "1.5rem" }}>
          <div className="detail-tabs">
            <button
              type="button"
              className={`detail-tab${activeTab === "sections" ? " active" : ""}`}
              onClick={() => setActiveTab("sections")}
            >
              <FileText size={16} aria-hidden />
              Sections
              <span className="tab-count">{sections.length}</span>
            </button>
            {hasAnalysisData && (
              <button
                type="button"
                className={`detail-tab${activeTab === "analysis" ? " active" : ""}`}
                onClick={() => setActiveTab("analysis")}
              >
                <BarChart3 size={16} aria-hidden />
                Analysis
                {qualityScore !== null && (
                  <span className="tab-count">{qualityScore.toFixed(0)}</span>
                )}
              </button>
            )}
          </div>

          {/* ── Sections Tab ─────────────────────────────── */}
          {activeTab === "sections" && (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem", marginBottom: "1rem" }}>
                <h2 className="page-title" style={{ fontSize: "1.1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  Parsed sections ({sections.length})
                </h2>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button type="button" onClick={expandAll} className="btn btn-secondary btn-sm">Expand all</button>
                  <button type="button" onClick={collapseAll} className="btn btn-secondary btn-sm">Collapse all</button>
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {sections.map((section, idx) => {
                  const isExpanded = expandedSections.has(idx) || editingSection === idx;
                  const preview = contentPreview(section.content);
                  return (
                    <div key={idx} className="accordion-item">
                      <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", minWidth: 0 }}>
                        <button
                          type="button"
                          className="accordion-trigger"
                          onClick={() => toggleSection(idx)}
                          aria-expanded={isExpanded}
                          style={{ flex: 1, minWidth: 0 }}
                        >
                          <span style={{ display: "flex", flexDirection: "column", gap: "0.1rem", minWidth: 0 }}>
                            <span style={{ display: "flex", alignItems: "center", gap: "0.65rem", minWidth: 0 }}>
                              <span className="badge badge-accent" style={{ flexShrink: 0 }}>
                                {section.section_index + 1}
                              </span>
                              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {section.heading}
                              </span>
                            </span>
                            {!isExpanded && preview && (
                              <span className="section-preview" style={{ paddingLeft: "2.15rem" }}>
                                {preview}
                              </span>
                            )}
                          </span>
                          <ChevronDown
                            size={18}
                            className={`accordion-chevron${isExpanded ? " open" : ""}`}
                            aria-hidden
                          />
                        </button>
                        {editingSection !== idx && (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={(e) => { e.stopPropagation(); handleEditSection(idx); }}
                            aria-label="Edit section"
                            style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", flexShrink: 0, marginTop: "0.65rem" }}
                          >
                            <Edit3 size={16} aria-hidden />
                            Edit
                          </button>
                        )}
                      </div>
                      <AnimatePresence initial={false}>
                        {isExpanded && (
                          <motion.div
                            key="content"
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
                            style={{ overflow: "hidden" }}
                          >
                            <div className="accordion-content" style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "0.75rem" }}>
                              {editingSection === idx ? (
                                <>
                                  <input type="text" className="form-input" value={editHeading} onChange={(e) => setEditHeading(e.target.value)} aria-label="Section heading" style={{ width: "100%", marginBottom: "0.5rem" }} />
                                  <textarea className="form-input" style={{ minHeight: "120px", fontFamily: "inherit", width: "100%" }} value={editContent} onChange={(e) => setEditContent(e.target.value)} aria-label="Section content" />
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.75rem" }}>
                                    <button type="button" className="btn btn-primary btn-sm" onClick={handleSaveSection} disabled={savingSection} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                                      {savingSection ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Save size={16} aria-hidden />}
                                      Save
                                    </button>
                                    <button type="button" className="btn btn-secondary btn-sm" onClick={handleCancelEdit} disabled={savingSection} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                                      <X size={16} aria-hidden />Cancel
                                    </button>
                                  </div>
                                </>
                              ) : (
                                renderRichContent(section.content)
                              )}
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  );
                })}
              </div>

              <div style={{ marginTop: "1rem" }}>
                {!showAddSection ? (
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowAddSection(true)} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                    <Plus size={16} aria-hidden />Add Section
                  </button>
                ) : (
                  <div className="card" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "0.65rem" }}>
                    <input type="text" className="form-input" value={newSectionHeading} onChange={(e) => setNewSectionHeading(e.target.value)} placeholder="Section heading" aria-label="New section heading" />
                    <textarea className="form-input" style={{ minHeight: "120px", fontFamily: "inherit" }} value={newSectionContent} onChange={(e) => setNewSectionContent(e.target.value)} placeholder="Section content" aria-label="New section content" />
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                      <button type="button" className="btn btn-primary btn-sm" onClick={handleAddSection} disabled={addingSection || !newSectionHeading.trim()} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                        {addingSection ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Plus size={16} aria-hidden />}
                        Add
                      </button>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setShowAddSection(false); setNewSectionHeading(""); setNewSectionContent(""); }} disabled={addingSection} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                        <X size={16} aria-hidden />Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {/* ── Analysis Tab ─────────────────────────────── */}
          {activeTab === "analysis" && hasAnalysisData && (
            <>
              <div className="analysis-summary-grid" style={{ marginTop: "0.25rem" }}>
                <div className="analysis-summary-stat">
                  <span className="stat-value">{qualityScore !== null ? qualityScore.toFixed(1) : "\u2014"}</span>
                  <span className="stat-label">Quality Score</span>
                </div>
                <div className="analysis-summary-stat">
                  <span className="stat-value">{ambiguityCount}</span>
                  <span className="stat-label">Ambiguities</span>
                </div>
                <div className="analysis-summary-stat">
                  <span className="stat-value">{contradictionCount}</span>
                  <span className="stat-label">Contradictions</span>
                </div>
                <div className="analysis-summary-stat">
                  <span className="stat-value">{edgeCaseCount}</span>
                  <span className="stat-label">Edge Cases</span>
                </div>
                <div className="analysis-summary-stat">
                  <span className="stat-value">{taskCount}</span>
                  <span className="stat-label">Tasks</span>
                </div>
              </div>

              {qualityData?.quality_score && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem", marginBottom: "1.5rem" }}>
                  {(["completeness", "clarity", "consistency"] as const).map((key) => (
                    <div key={key} style={{ padding: "0.75rem", background: "var(--bg-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-lg)", textAlign: "center" }}>
                      <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>
                        {qualityData.quality_score[key].toFixed(1)}
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "capitalize" }}>
                        {key}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.75rem", color: "var(--text-primary)" }}>
                Explore Analysis
              </h3>
              <div className="analysis-links-grid">
                {analysisLinks.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    id={item.id}
                    className="card analysis-link-card"
                  >
                    <div className="kpi-icon" style={{ background: item.well, flexShrink: 0 }}>
                      {item.icon}
                    </div>
                    <span style={{ flex: 1, fontWeight: 600, fontSize: "0.9375rem" }}>
                      {item.title}
                    </span>
                    <ChevronRight size={20} style={{ flexShrink: 0, color: "var(--text-muted)" }} aria-hidden />
                  </Link>
                ))}
              </div>

              {/* Export Section */}
              <h3 style={{ fontSize: "1rem", fontWeight: 700, margin: "1.5rem 0 0.75rem", color: "var(--text-primary)" }}>
                Export
              </h3>
              {exportMsg && (
                <div style={{
                  padding: "0.5rem 0.75rem", borderRadius: "0.5rem", marginBottom: "0.75rem",
                  background: exportMsg.includes("fail") ? "var(--error-bg)" : "var(--success-bg, rgba(34,197,94,0.1))",
                  color: exportMsg.includes("fail") ? "var(--error)" : "var(--success)",
                  fontSize: "0.8125rem",
                }}>
                  {exportMsg}
                </div>
              )}
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                {([
                  { key: "jira", label: "Export to JIRA" },
                  { key: "confluence", label: "Export to Confluence" },
                  { key: "pdf", label: "PDF Report" },
                  { key: "docx", label: "DOCX Report" },
                ] as const).map((exp) => (
                  <button
                    key={exp.key}
                    className="btn btn-secondary btn-sm"
                    disabled={exporting !== null}
                    onClick={() => handleExport(exp.key)}
                    style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
                  >
                    <Download size={14} aria-hidden />
                    {exporting === exp.key ? "Exporting..." : exp.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </FadeIn>
      )}

      <CursorTaskModal
        envelope={cursorTask}
        onClose={() => setCursorTask(null)}
        onDone={async () => {
          setCursorTask(null);
          await fetchDoc();
        }}
      />
    </PageShell>
  );
}
