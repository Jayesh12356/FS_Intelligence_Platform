"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  listVersions,
  getImpactAnalysis,
  uploadVersion,
} from "@/lib/api";
import type {
  FSVersionItem,
  ImpactAnalysisData,
} from "@/lib/api";

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const CHANGE_COLORS: Record<string, string> = {
  ADDED: "#22c55e",
  MODIFIED: "#f59e0b",
  DELETED: "#ef4444",
};

const CHANGE_ICONS: Record<string, string> = {
  ADDED: "+",
  MODIFIED: "~",
  DELETED: "−",
};

const IMPACT_COLORS: Record<string, string> = {
  INVALIDATED: "#ef4444",
  REQUIRES_REVIEW: "#f59e0b",
  UNAFFECTED: "#22c55e",
};

const IMPACT_LABELS: Record<string, string> = {
  INVALIDATED: "Invalidated",
  REQUIRES_REVIEW: "Needs Review",
  UNAFFECTED: "Unaffected",
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
  const [error, setError] = useState<string | null>(null);
  const [expandedChanges, setExpandedChanges] = useState<Set<number>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchVersions = useCallback(async () => {
    try {
      setLoading(true);
      const result = await listVersions(docId);
      setVersions(result.data.versions || []);
      // Auto-select latest version (if > 1)
      if (result.data.versions.length > 1) {
        const latest = result.data.versions[result.data.versions.length - 1];
        setSelectedVersion(latest.id);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load versions");
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    if (docId) fetchVersions();
  }, [docId, fetchVersions]);

  const fetchImpactData = useCallback(async (versionId: string) => {
    try {
      setImpactLoading(true);
      const result = await getImpactAnalysis(docId, versionId);
      setImpactData(result.data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load impact data");
    } finally {
      setImpactLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    if (selectedVersion) {
      fetchImpactData(selectedVersion);
    }
  }, [selectedVersion, fetchImpactData]);

  const handleUploadVersion = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadError(null);

    try {
      await uploadVersion(docId, file);
      await fetchVersions();
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const toggleChange = (index: number) => {
    setExpandedChanges((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
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
      <div className="empty-state">
        <div className="empty-state-icon">⚠️</div>
        <h3>Error</h3>
        <p>{error}</p>
        <Link href={`/documents/${docId}`} className="btn btn-primary btn-sm">
          ← Back to Document
        </Link>
      </div>
    );
  }

  const rework = impactData?.rework_estimate;

  return (
    <div style={{ maxWidth: "960px" }}>
      <Link href={`/documents/${docId}`} className="back-link">
        ← Back to Document
      </Link>

      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.8rem", fontWeight: 700, marginBottom: "0.5rem" }}>
          🔄 Change Impact Analysis
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem" }}>
          Upload a new version of the FS document to see what tasks are affected
        </p>
      </div>

      {/* Upload New Version */}
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "1.5rem",
          marginBottom: "1.5rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>
              Upload New Version
            </h3>
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
              Upload an updated FS document to trigger impact analysis
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={handleUploadVersion}
              style={{ display: "none" }}
              id="version-upload"
            />
            <button
              className="btn btn-primary"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              style={{ padding: "10px 24px", fontSize: "0.9rem" }}
            >
              {uploading ? (
                <>
                  <span className="spinner" style={{ width: "14px", height: "14px" }} />
                  Uploading…
                </>
              ) : (
                <>📤 Upload Version {versions.length > 0 ? `v${versions.length + 1}` : "v2"}</>
              )}
            </button>
          </div>
        </div>
        {uploadError && (
          <p style={{ color: "var(--error)", marginTop: "0.75rem", fontSize: "0.85rem" }}>
            ❌ {uploadError}
          </p>
        )}
      </div>

      {/* Version Selector */}
      {versions.length > 0 && (
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-lg)",
            padding: "1.5rem",
            marginBottom: "1.5rem",
          }}
        >
          <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem" }}>
            📑 Version History ({versions.length})
          </h3>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {versions.map((v) => (
              <button
                key={v.id}
                onClick={() => setSelectedVersion(v.id)}
                style={{
                  padding: "8px 16px",
                  borderRadius: "var(--radius-sm)",
                  border: selectedVersion === v.id
                    ? "2px solid var(--accent-primary)"
                    : "1px solid var(--border-subtle)",
                  background: selectedVersion === v.id
                    ? "rgba(108, 92, 231, 0.15)"
                    : "var(--bg-secondary)",
                  color: selectedVersion === v.id
                    ? "var(--accent-primary)"
                    : "var(--text-secondary)",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                  fontWeight: selectedVersion === v.id ? 700 : 500,
                  transition: "all 0.2s ease",
                }}
              >
                v{v.version_number}
                <span style={{ display: "block", fontSize: "0.72rem", opacity: 0.6, marginTop: "2px" }}>
                  {formatDate(v.created_at)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* No versions yet hint */}
      {versions.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">📋</div>
          <h3>No Versions Yet</h3>
          <p>Upload a new version of the FS document to begin impact analysis.</p>
        </div>
      )}

      {/* Impact Analysis Loading */}
      {impactLoading && (
        <div className="page-loading">
          <div className="spinner" />
          Loading impact analysis…
        </div>
      )}

      {/* Impact Results */}
      {impactData && !impactLoading && (
        <>
          {/* Rework Summary Card */}
          {rework && (
            <div
              style={{
                background: "linear-gradient(135deg, rgba(108, 92, 231, 0.1), rgba(168, 85, 247, 0.05))",
                border: "1px solid rgba(108, 92, 231, 0.25)",
                borderRadius: "var(--radius-lg)",
                padding: "1.5rem",
                marginBottom: "1.5rem",
              }}
            >
              <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "1rem" }}>
                📊 Rework Estimate — v{impactData.version_number}
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "1rem", marginBottom: "1rem" }}>
                <div style={{ textAlign: "center", padding: "1rem", background: "rgba(239, 68, 68, 0.1)", borderRadius: "var(--radius-md)", border: "1px solid rgba(239, 68, 68, 0.2)" }}>
                  <div style={{ fontSize: "2rem", fontWeight: 800, color: "#ef4444" }}>{rework.invalidated_count}</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Invalidated</div>
                </div>
                <div style={{ textAlign: "center", padding: "1rem", background: "rgba(245, 158, 11, 0.1)", borderRadius: "var(--radius-md)", border: "1px solid rgba(245, 158, 11, 0.2)" }}>
                  <div style={{ fontSize: "2rem", fontWeight: 800, color: "#f59e0b" }}>{rework.review_count}</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Need Review</div>
                </div>
                <div style={{ textAlign: "center", padding: "1rem", background: "rgba(34, 197, 94, 0.1)", borderRadius: "var(--radius-md)", border: "1px solid rgba(34, 197, 94, 0.2)" }}>
                  <div style={{ fontSize: "2rem", fontWeight: 800, color: "#22c55e" }}>{rework.unaffected_count}</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Unaffected</div>
                </div>
                <div style={{ textAlign: "center", padding: "1rem", background: "rgba(108, 92, 231, 0.1)", borderRadius: "var(--radius-md)", border: "1px solid rgba(108, 92, 231, 0.2)" }}>
                  <div style={{ fontSize: "2rem", fontWeight: 800, color: "var(--accent-primary)" }}>{rework.total_rework_days}d</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Est. Rework</div>
                </div>
              </div>
              {rework.changes_summary && (
                <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem", lineHeight: 1.6, margin: 0 }}>
                  {rework.changes_summary}
                </p>
              )}
            </div>
          )}

          {/* What Changed? */}
          {impactData.changes.length > 0 && (
            <div
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-lg)",
                padding: "1.5rem",
                marginBottom: "1.5rem",
              }}
            >
              <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem" }}>
                📝 What Changed? ({impactData.changes.length} section{impactData.changes.length === 1 ? "" : "s"})
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {impactData.changes.map((change, idx) => {
                  const isExpanded = expandedChanges.has(idx);
                  const color = CHANGE_COLORS[change.change_type] || "#6b7280";
                  return (
                    <div
                      key={idx}
                      style={{
                        border: `1px solid ${color}33`,
                        borderRadius: "var(--radius-md)",
                        overflow: "hidden",
                        transition: "all 0.2s ease",
                      }}
                    >
                      <button
                        onClick={() => toggleChange(idx)}
                        style={{
                          width: "100%",
                          padding: "12px 16px",
                          display: "flex",
                          alignItems: "center",
                          gap: "10px",
                          background: `${color}0a`,
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
                            width: "24px",
                            height: "24px",
                            borderRadius: "6px",
                            background: `${color}22`,
                            color: color,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: "0.85rem",
                            fontWeight: 800,
                            flexShrink: 0,
                          }}
                        >
                          {CHANGE_ICONS[change.change_type]}
                        </span>
                        <span style={{ flex: 1 }}>{change.section_heading || `Section ${change.section_index + 1}`}</span>
                        <span
                          style={{
                            padding: "2px 8px",
                            borderRadius: "4px",
                            fontSize: "0.7rem",
                            fontWeight: 700,
                            background: `${color}22`,
                            color: color,
                            textTransform: "uppercase",
                            letterSpacing: "0.05em",
                          }}
                        >
                          {change.change_type}
                        </span>
                        <span
                          style={{
                            transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
                            transition: "transform 0.2s ease",
                            opacity: 0.4,
                            fontSize: "0.75rem",
                          }}
                        >
                          ▼
                        </span>
                      </button>
                      {isExpanded && (
                        <div style={{ padding: "1rem 16px", borderTop: `1px solid ${color}22` }}>
                          {change.change_type === "MODIFIED" && (
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                              <div>
                                <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.5rem" }}>
                                  Previous
                                </div>
                                <div style={{
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
                                }}>
                                  {change.old_text || "(empty)"}
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "#22c55e", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.5rem" }}>
                                  New
                                </div>
                                <div style={{
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
                                }}>
                                  {change.new_text || "(empty)"}
                                </div>
                              </div>
                            </div>
                          )}
                          {change.change_type === "ADDED" && (
                            <div style={{
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
                            }}>
                              {change.new_text || "(empty)"}
                            </div>
                          )}
                          {change.change_type === "DELETED" && (
                            <div style={{
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
                            }}>
                              {change.old_text || "(empty)"}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Affected Tasks */}
          {impactData.task_impacts.length > 0 && (
            <div
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-lg)",
                padding: "1.5rem",
                marginBottom: "1.5rem",
              }}
            >
              <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem" }}>
                🎯 Affected Tasks ({impactData.task_impacts.filter(t => t.impact_type !== "UNAFFECTED").length} of {impactData.task_impacts.length})
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {impactData.task_impacts
                  .sort((a, b) => {
                    const priority: Record<string, number> = { INVALIDATED: 0, REQUIRES_REVIEW: 1, UNAFFECTED: 2 };
                    return (priority[a.impact_type] ?? 9) - (priority[b.impact_type] ?? 9);
                  })
                  .map((impact, idx) => {
                    const color = IMPACT_COLORS[impact.impact_type] || "#6b7280";
                    const label = IMPACT_LABELS[impact.impact_type] || impact.impact_type;
                    return (
                      <div
                        key={idx}
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: "12px",
                          padding: "12px 16px",
                          background: `${color}08`,
                          border: `1px solid ${color}22`,
                          borderRadius: "var(--radius-md)",
                          transition: "all 0.2s ease",
                        }}
                      >
                        <span
                          style={{
                            padding: "3px 10px",
                            borderRadius: "4px",
                            fontSize: "0.7rem",
                            fontWeight: 700,
                            background: `${color}22`,
                            color: color,
                            textTransform: "uppercase",
                            letterSpacing: "0.04em",
                            whiteSpace: "nowrap",
                            flexShrink: 0,
                            marginTop: "2px",
                          }}
                        >
                          {label}
                        </span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 600, fontSize: "0.9rem", marginBottom: "3px" }}>
                            {impact.task_title || impact.task_id}
                          </div>
                          {impact.reason && (
                            <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                              {impact.reason}
                            </div>
                          )}
                          {impact.change_section && (
                            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "4px" }}>
                              Changed section: {impact.change_section}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}

          {/* No changes */}
          {impactData.changes.length === 0 && (
            <div className="empty-state">
              <div className="empty-state-icon">✅</div>
              <h3>No Changes Detected</h3>
              <p>This version is identical to the previous one.</p>
            </div>
          )}
        </>
      )}

      {/* Show message when version 1 selected */}
      {selectedVersion && !impactLoading && !impactData && versions.length > 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">📄</div>
          <h3>Original Version</h3>
          <p>This is the first version. Upload a new version to see change impact analysis.</p>
        </div>
      )}
    </div>
  );
}
