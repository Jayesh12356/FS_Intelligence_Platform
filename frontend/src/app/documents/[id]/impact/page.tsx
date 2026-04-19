"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { listVersions, getImpactAnalysis, uploadVersion, isCursorTaskEnvelope } from "@/lib/api";
import type { FSVersionItem, ImpactAnalysisData, CursorTaskEnvelope } from "@/lib/api";
import CursorTaskModal from "@/components/CursorTaskModal";
import {
  PageShell,
  KpiCard,
  FadeIn,
  StaggerList,
  StaggerItem,
  EmptyState,
} from "@/components/index";
import Badge from "@/components/Badge";
import { motion, AnimatePresence } from "framer-motion";
import {
  GitCompare,
  Upload,
  Clock,
  XCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Plus,
  Minus,
  PenLine,
} from "lucide-react";

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const CHANGE_BORDER: Record<string, string> = {
  ADDED: "var(--success-border, #22c55e)",
  MODIFIED: "var(--warning-border, #f59e0b)",
  DELETED: "var(--error-border, #ef4444)",
};

const CHANGE_BADGE_VARIANT: Record<string, "success" | "warning" | "error"> = {
  ADDED: "success",
  MODIFIED: "warning",
  DELETED: "error",
};

const CHANGE_ICON: Record<string, typeof Plus> = {
  ADDED: Plus,
  MODIFIED: PenLine,
  DELETED: Minus,
};

const IMPACT_BORDER: Record<string, string> = {
  INVALIDATED: "var(--error-border, #ef4444)",
  REQUIRES_REVIEW: "var(--warning-border, #f59e0b)",
  UNAFFECTED: "var(--success-border, #22c55e)",
};

const IMPACT_BADGE_VARIANT: Record<string, "error" | "warning" | "success"> = {
  INVALIDATED: "error",
  REQUIRES_REVIEW: "warning",
  UNAFFECTED: "success",
};

const IMPACT_LABELS: Record<string, string> = {
  INVALIDATED: "Invalidated",
  REQUIRES_REVIEW: "Needs Review",
  UNAFFECTED: "Unaffected",
};

const IMPACT_ICON: Record<string, typeof XCircle> = {
  INVALIDATED: XCircle,
  REQUIRES_REVIEW: AlertTriangle,
  UNAFFECTED: CheckCircle2,
};

export default function ImpactDashboardPage() {
  const params = useParams();
  const docId = params.id as string;

  const [versions, setVersions] = useState<FSVersionItem[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [impactData, setImpactData] = useState<ImpactAnalysisData | null>(null);
  const [loading, setLoading] = useState(true);
  const [impactLoading, setImpactLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedChanges, setExpandedChanges] = useState<Set<number>>(new Set());
  const [cursorTask, setCursorTask] = useState<CursorTaskEnvelope | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchVersions = useCallback(async () => {
    try {
      setLoading(true);
      const result = await listVersions(docId);
      const vers = result.data.versions || [];
      setVersions(vers);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load versions");
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    setVersions([]);
    setSelectedVersion(null);
    setImpactData(null);
  }, [docId]);

  useEffect(() => {
    if (docId) fetchVersions();
  }, [docId, fetchVersions]);

  useEffect(() => {
    if (versions.length === 0) return;
    const ids = new Set(versions.map((v) => v.id));
    if (selectedVersion == null || !ids.has(selectedVersion)) {
      setSelectedVersion(versions[versions.length - 1].id);
    }
  }, [versions, selectedVersion]);

  const [impactError, setImpactError] = useState<string | null>(null);

  const fetchImpactData = useCallback(
    async (versionId: string) => {
      try {
        setImpactLoading(true);
        setImpactError(null);
        const result = await getImpactAnalysis(docId, versionId);
        setImpactData(result.data);
      } catch (err: unknown) {
        setImpactError(err instanceof Error ? err.message : "Failed to load impact data");
      } finally {
        setImpactLoading(false);
      }
    },
    [docId]
  );

  useEffect(() => {
    if (selectedVersion) {
      fetchImpactData(selectedVersion);
    }
  }, [selectedVersion, fetchImpactData]);

  const uploadImpl = useCallback(
    async (file: File) => {
      const ext = file.name.toLowerCase().slice(file.name.lastIndexOf("."));
      if (![".pdf", ".docx", ".txt"].includes(ext)) {
        setUploadError(`Unsupported file type '${ext}'. Allowed: .pdf, .docx, .txt`);
        return;
      }
      if (file.size > 20 * 1024 * 1024) {
        setUploadError(`File is ${(file.size / 1024 / 1024).toFixed(1)} MB — exceeds 20 MB limit.`);
        return;
      }

      setUploading(true);
      setUploadError(null);
      try {
        const res = await uploadVersion(docId, file);
        if (res.data && isCursorTaskEnvelope(res.data)) {
          setCursorTask(res.data);
          await fetchVersions();
        } else {
          await fetchVersions();
        }
      } catch (err: unknown) {
        setUploadError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [docId, fetchVersions],
  );

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void uploadImpl(file);
  };

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (uploading) return;
      const file = e.dataTransfer.files[0];
      if (file) void uploadImpl(file);
    },
    [uploading, uploadImpl],
  );

  const onDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (!uploading) setDragOver(true);
    },
    [uploading],
  );

  const onDragLeave = useCallback(() => setDragOver(false), []);

  const handleCompare = (versionId: string) => {
    setSelectedVersion(versionId);
  };

  const toggleChange = (index: number) => {
    setExpandedChanges((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const openFilePicker = () => fileInputRef.current?.click();

  const onZoneKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openFilePicker();
    }
  };

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        Loading version history…
      </div>
    );
  }

  if (error) {
    return (
      <PageShell
        backHref={`/documents/${docId}`}
        title="Impact Analysis"
        maxWidth={960}
      >
        <FadeIn>
          <EmptyState
            icon={<AlertTriangle size={40} strokeWidth={1.25} aria-hidden />}
            title="Error"
            description={error}
            action={
              <Link href={`/documents/${docId}`} className="btn btn-primary btn-sm">
                Back to Document
              </Link>
            }
          />
        </FadeIn>
      </PageShell>
    );
  }

  const rework = impactData?.rework_estimate;

  return (
    <PageShell
      backHref={`/documents/${docId}`}
      title="Impact Analysis"
      subtitle="Upload a new version of the FS document to see what tasks are affected"
      maxWidth={960}
    >
      <FadeIn>
        <div className="card" style={{ marginBottom: "1.5rem" }}>
          <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            Upload new version
          </h3>
          <p className="page-subtitle" style={{ marginBottom: "1rem", fontSize: "0.875rem" }}>
            Upload an updated FS document to trigger impact analysis
          </p>
          <motion.div
            className={`upload-zone ${dragOver ? "drag-over" : ""}`}
            onClick={uploading ? undefined : openFilePicker}
            onKeyDown={uploading ? undefined : onZoneKeyDown}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            role="button"
            tabIndex={uploading ? -1 : 0}
            aria-disabled={uploading}
            whileHover={uploading ? undefined : { scale: 1.01 }}
            animate={{ scale: dragOver ? 1.02 : 1 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            style={{ cursor: uploading ? "not-allowed" : "pointer", opacity: uploading ? 0.7 : 1 }}
          >
            <div className="upload-icon">
              <Upload size={40} strokeWidth={1.5} aria-hidden />
            </div>
            <h3>
              {uploading
                ? "Uploading…"
                : "Drop a file here or click to browse"}
            </h3>
            <p>PDF, DOCX, or TXT — triggers parse, diff, and impact analysis</p>
            <div className="file-types">
              <span className="file-type-badge">.PDF</span>
              <span className="file-type-badge">.DOCX</span>
              <span className="file-type-badge">.TXT</span>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={handleUpload}
              style={{ display: "none" }}
              id="version-upload"
              disabled={uploading}
            />
          </motion.div>
          {uploadError && (
            <p style={{ color: "var(--error)", marginTop: "0.75rem", fontSize: "0.85rem" }}>
              {uploadError}
            </p>
          )}
        </div>
      </FadeIn>

      {versions.length > 0 && (
        <FadeIn delay={0.05}>
          <div style={{ marginBottom: "1.5rem" }}>
            <h3
              style={{
                fontSize: "0.95rem",
                fontWeight: 600,
                marginBottom: "0.75rem",
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              <GitCompare size={18} aria-hidden />
              Version timeline ({versions.length})
            </h3>
            <div
              style={{
                display: "flex",
                flexDirection: "row",
                flexWrap: "nowrap",
                gap: "0.75rem",
                overflowX: "auto",
                paddingBottom: "0.25rem",
                WebkitOverflowScrolling: "touch",
              }}
            >
              {versions.map((v) => {
                const selected = selectedVersion === v.id;
                return (
                  <button
                    key={v.id}
                    type="button"
                    onClick={() => handleCompare(v.id)}
                    className="card card-flat"
                    style={{
                      flex: "0 0 auto",
                      minWidth: "140px",
                      textAlign: "left",
                      cursor: "pointer",
                      padding: "1rem 1.125rem",
                      borderWidth: selected ? 2 : 1,
                      borderColor: selected ? "var(--accent-primary)" : "var(--border-subtle)",
                      background: selected ? "rgba(108, 92, 231, 0.12)" : "var(--bg-card)",
                      boxShadow: selected ? "var(--shadow-sm)" : undefined,
                    }}
                  >
                    <div
                      style={{
                        fontWeight: 700,
                        fontSize: "0.95rem",
                        color: selected ? "var(--accent-primary)" : "var(--text-primary)",
                        marginBottom: "0.35rem",
                      }}
                    >
                      v{v.version_number}
                    </div>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.35rem",
                        fontSize: "0.75rem",
                        color: "var(--text-muted)",
                      }}
                    >
                      <Clock size={12} aria-hidden />
                      {formatDate(v.created_at)}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </FadeIn>
      )}

      {versions.length === 0 && (
        <EmptyState
          icon={<GitCompare size={40} strokeWidth={1.25} aria-hidden />}
          title="No versions yet"
          description="Upload a new version of the FS document to begin impact analysis."
        />
      )}

      {impactLoading && (
        <div className="page-loading" style={{ minHeight: "120px", marginTop: "1rem" }}>
          <div className="spinner" />
          Loading impact analysis…
        </div>
      )}

      {impactError && !impactLoading && (
        <div className="alert alert-error" style={{ marginTop: "1rem", marginBottom: "1rem" }}>
          {impactError}
        </div>
      )}

      {impactData && !impactLoading && (
        <>
          <FadeIn>
            <div className="kpi-row" style={{ marginBottom: "1.5rem" }}>
              <KpiCard
                label="Total changes"
                value={impactData.changes.length}
                icon={<GitCompare size={22} aria-hidden />}
                iconBg="rgba(108, 92, 231, 0.2)"
                delay={0}
              />
              <KpiCard
                label="Invalidated tasks"
                value={impactData.invalidated_count}
                icon={<XCircle size={22} aria-hidden />}
                iconBg="rgba(239, 68, 68, 0.2)"
                delay={0.05}
              />
              <KpiCard
                label="Needs review tasks"
                value={impactData.review_count}
                icon={<AlertTriangle size={22} aria-hidden />}
                iconBg="rgba(245, 158, 11, 0.2)"
                delay={0.1}
              />
              <KpiCard
                label="Unaffected tasks"
                value={impactData.unaffected_count}
                icon={<CheckCircle2 size={22} aria-hidden />}
                iconBg="rgba(34, 197, 94, 0.2)"
                delay={0.15}
              />
            </div>
          </FadeIn>

          {rework && (
            <FadeIn delay={0.08}>
              <div style={{ marginBottom: "1.5rem" }}>
                <h3
                  style={{
                    fontSize: "0.95rem",
                    fontWeight: 600,
                    marginBottom: "0.75rem",
                  }}
                >
                  Rework estimate — v{impactData.version_number}
                </h3>
                <div className="kpi-row" style={{ marginBottom: rework.changes_summary ? "1rem" : 0 }}>
                  <KpiCard
                    label="Est. rework (days)"
                    value={rework.total_rework_days}
                    suffix="d"
                    decimals={rework.total_rework_days % 1 !== 0 ? 1 : 0}
                    icon={<Clock size={22} aria-hidden />}
                    iconBg="rgba(108, 92, 231, 0.25)"
                    delay={0}
                  />
                </div>
                {rework.changes_summary && (
                  <p
                    style={{
                      color: "var(--text-secondary)",
                      fontSize: "0.88rem",
                      lineHeight: 1.6,
                      margin: 0,
                    }}
                  >
                    {rework.changes_summary}
                  </p>
                )}
              </div>
            </FadeIn>
          )}

          {impactData.changes.length > 0 && (
            <FadeIn>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem" }}>
                What changed ({impactData.changes.length} section
                {impactData.changes.length === 1 ? "" : "s"})
              </h3>
              <StaggerList style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "1.5rem" }}>
                {impactData.changes.map((change, idx) => {
                  const isExpanded = expandedChanges.has(idx);
                  const borderColor = CHANGE_BORDER[change.change_type] ?? "var(--border-subtle)";
                  const Icon = CHANGE_ICON[change.change_type] ?? Plus;
                  const badgeVariant: "success" | "warning" | "error" | "neutral" =
                    CHANGE_BADGE_VARIANT[change.change_type] ?? "neutral";

                  return (
                    <StaggerItem key={idx}>
                      <div
                        className="card card-flat"
                        style={{
                          padding: 0,
                          overflow: "hidden",
                          borderLeftWidth: 4,
                          borderLeftStyle: "solid",
                          borderLeftColor: borderColor,
                        }}
                      >
                        <button
                          type="button"
                          onClick={() => toggleChange(idx)}
                          style={{
                            width: "100%",
                            padding: "12px 16px",
                            display: "flex",
                            alignItems: "center",
                            gap: "10px",
                            background: "transparent",
                            border: "none",
                            cursor: "pointer",
                            color: "var(--text-primary)",
                            fontSize: "0.9rem",
                            fontWeight: 600,
                            textAlign: "left",
                          }}
                        >
                          <span
                            style={{
                              width: "28px",
                              height: "28px",
                              borderRadius: "8px",
                              background: `${borderColor}22`,
                              color: borderColor,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              flexShrink: 0,
                            }}
                          >
                            <Icon size={16} strokeWidth={2.5} aria-hidden />
                          </span>
                          <span style={{ flex: 1, minWidth: 0 }}>
                            {change.section_heading || `Section ${change.section_index + 1}`}
                          </span>
                          <Badge variant={badgeVariant}>{change.change_type}</Badge>
                          <ChevronDown
                            size={18}
                            aria-hidden
                            style={{
                              flexShrink: 0,
                              opacity: 0.45,
                              transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
                              transition: "transform 0.2s ease",
                            }}
                          />
                        </button>
                        <AnimatePresence initial={false}>
                          {isExpanded && (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
                              style={{ overflow: "hidden" }}
                            >
                              <div
                                style={{
                                  padding: "0 16px 16px",
                                  borderTop: "1px solid var(--border-subtle)",
                                }}
                              >
                                {change.change_type === "MODIFIED" && (
                                  <div
                                    style={{
                                      display: "grid",
                                      gridTemplateColumns: "1fr 1fr",
                                      gap: "1rem",
                                      marginTop: "1rem",
                                    }}
                                  >
                                    <div>
                                      <div
                                        style={{
                                          fontSize: "0.72rem",
                                          fontWeight: 700,
                                          color: "#b91c1c",
                                          textTransform: "uppercase",
                                          letterSpacing: "0.06em",
                                          marginBottom: "0.5rem",
                                        }}
                                      >
                                        Previous
                                      </div>
                                      <div
                                        style={{
                                          background: "rgba(239, 68, 68, 0.05)",
                                          border: "1px solid rgba(239, 68, 68, 0.15)",
                                          borderRadius: "var(--radius-sm)",
                                          padding: "12px",
                                          fontSize: "0.82rem",
                                          lineHeight: 1.6,
                                          color: "var(--text-secondary)",
                                          whiteSpace: "pre-wrap",
                                          maxHeight: "300px",
                                          overflow: "auto",
                                        }}
                                      >
                                        {change.old_text || "(empty)"}
                                      </div>
                                    </div>
                                    <div>
                                      <div
                                        style={{
                                          fontSize: "0.72rem",
                                          fontWeight: 700,
                                          color: "#15803d",
                                          textTransform: "uppercase",
                                          letterSpacing: "0.06em",
                                          marginBottom: "0.5rem",
                                        }}
                                      >
                                        New
                                      </div>
                                      <div
                                        style={{
                                          background: "rgba(34, 197, 94, 0.05)",
                                          border: "1px solid rgba(34, 197, 94, 0.15)",
                                          borderRadius: "var(--radius-sm)",
                                          padding: "12px",
                                          fontSize: "0.82rem",
                                          lineHeight: 1.6,
                                          color: "var(--text-secondary)",
                                          whiteSpace: "pre-wrap",
                                          maxHeight: "300px",
                                          overflow: "auto",
                                        }}
                                      >
                                        {change.new_text || "(empty)"}
                                      </div>
                                    </div>
                                  </div>
                                )}
                                {change.change_type === "ADDED" && (
                                  <div
                                    style={{
                                      background: "rgba(34, 197, 94, 0.05)",
                                      border: "1px solid rgba(34, 197, 94, 0.15)",
                                      borderRadius: "var(--radius-sm)",
                                      padding: "12px",
                                      fontSize: "0.82rem",
                                      lineHeight: 1.6,
                                      color: "var(--text-secondary)",
                                      whiteSpace: "pre-wrap",
                                      maxHeight: "300px",
                                      overflow: "auto",
                                      marginTop: "1rem",
                                    }}
                                  >
                                    {change.new_text || "(empty)"}
                                  </div>
                                )}
                                {change.change_type === "DELETED" && (
                                  <div
                                    style={{
                                      background: "rgba(239, 68, 68, 0.05)",
                                      border: "1px solid rgba(239, 68, 68, 0.15)",
                                      borderRadius: "var(--radius-sm)",
                                      padding: "12px",
                                      fontSize: "0.82rem",
                                      lineHeight: 1.6,
                                      color: "var(--text-secondary)",
                                      whiteSpace: "pre-wrap",
                                      textDecoration: "line-through",
                                      opacity: 0.7,
                                      maxHeight: "300px",
                                      overflow: "auto",
                                      marginTop: "1rem",
                                    }}
                                  >
                                    {change.old_text || "(empty)"}
                                  </div>
                                )}
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    </StaggerItem>
                  );
                })}
              </StaggerList>
            </FadeIn>
          )}

          {impactData.task_impacts.length > 0 && (
            <FadeIn>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem" }}>
                Affected tasks (
                {impactData.task_impacts.filter((t) => t.impact_type !== "UNAFFECTED").length} of{" "}
                {impactData.task_impacts.length})
              </h3>
              <StaggerList style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "1.5rem" }}>
                {[...impactData.task_impacts]
                  .sort((a, b) => {
                    const priority: Record<string, number> = {
                      INVALIDATED: 0,
                      REQUIRES_REVIEW: 1,
                      UNAFFECTED: 2,
                    };
                    return (priority[a.impact_type] ?? 9) - (priority[b.impact_type] ?? 9);
                  })
                  .map((impact, idx) => {
                    const borderColor = IMPACT_BORDER[impact.impact_type] ?? "var(--border-subtle)";
                    const label = IMPACT_LABELS[impact.impact_type] ?? impact.impact_type;
                    const badgeVariant: "error" | "warning" | "success" | "neutral" =
                      IMPACT_BADGE_VARIANT[impact.impact_type] ?? "neutral";
                    const ImpactIcon = IMPACT_ICON[impact.impact_type] ?? CheckCircle2;

                    return (
                      <StaggerItem key={`${impact.task_id}-${idx}`}>
                        <div
                          className="card card-flat"
                          style={{
                            display: "flex",
                            alignItems: "flex-start",
                            gap: "12px",
                            borderLeftWidth: 4,
                            borderLeftStyle: "solid",
                            borderLeftColor: borderColor,
                          }}
                        >
                          <span
                            style={{
                              width: "32px",
                              height: "32px",
                              borderRadius: "8px",
                              background: `${borderColor}22`,
                              color: borderColor,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              flexShrink: 0,
                              marginTop: "2px",
                            }}
                          >
                            <ImpactIcon size={18} strokeWidth={2} aria-hidden />
                          </span>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "0.5rem",
                                flexWrap: "wrap",
                                marginBottom: "0.35rem",
                              }}
                            >
                              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                                {impact.task_title || impact.task_id}
                              </span>
                              <Badge variant={badgeVariant}>{label}</Badge>
                            </div>
                            {impact.reason && (
                              <div
                                style={{
                                  fontSize: "0.82rem",
                                  color: "var(--text-secondary)",
                                  lineHeight: 1.5,
                                }}
                              >
                                {impact.reason}
                              </div>
                            )}
                            {impact.change_section && (
                              <div
                                style={{
                                  fontSize: "0.75rem",
                                  color: "var(--text-muted)",
                                  marginTop: "4px",
                                }}
                              >
                                Changed section: {impact.change_section}
                              </div>
                            )}
                          </div>
                        </div>
                      </StaggerItem>
                    );
                  })}
              </StaggerList>
            </FadeIn>
          )}

          {impactData.changes.length === 0 && (
            <EmptyState
              icon={<CheckCircle2 size={40} strokeWidth={1.25} aria-hidden />}
              title="No changes detected"
              description="This version is identical to the previous one."
            />
          )}
        </>
      )}

      {selectedVersion && !impactLoading && !impactData && versions.length > 0 && (
        <EmptyState
          icon={<GitCompare size={40} strokeWidth={1.25} aria-hidden />}
          title="Original version"
          description="This is the first version. Upload a new version to see change impact analysis."
        />
      )}

      <CursorTaskModal
        envelope={cursorTask}
        onClose={() => setCursorTask(null)}
        onDone={() => {
          setCursorTask(null);
          void fetchVersions();
          if (selectedVersion) void fetchImpactData(selectedVersion);
        }}
      />
    </PageShell>
  );
}
