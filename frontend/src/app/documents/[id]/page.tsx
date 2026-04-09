"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getDocument, parseDocument, listDuplicates, getApprovalStatus } from "@/lib/api";
import type { FSDocumentDetail, FSSection, DuplicateFlag } from "@/lib/api";

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
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    UPLOADED: "#6366f1",
    PARSING: "#f59e0b",
    PARSED: "#10b981",
    ANALYZING: "#3b82f6",
    COMPLETE: "#10b981",
    ERROR: "#ef4444",
    PARSE_FAILED: "#ef4444",
  };
  const color = colors[status] || "#6b7280";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "4px 12px",
        borderRadius: "20px",
        fontSize: "0.75rem",
        fontWeight: 600,
        letterSpacing: "0.05em",
        background: `${color}22`,
        color: color,
        border: `1px solid ${color}44`,
      }}
    >
      <span
        style={{
          width: "6px",
          height: "6px",
          borderRadius: "50%",
          background: color,
          animation: status === "PARSING" ? "pulse 1.5s infinite" : "none",
        }}
      />
      {status}
    </span>
  );
}

export default function DocumentDetailPage() {
  const params = useParams();
  const docId = params.id as string;
  const [doc, setDoc] = useState<FSDocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [sections, setSections] = useState<FSSection[]>([]);
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set());
  const [duplicates, setDuplicates] = useState<DuplicateFlag[]>([]);
  const [approvalStatus, setApprovalStatus] = useState<string>("NONE");

  const fetchDoc = useCallback(async () => {
    try {
      setLoading(true);
      const result = await getDocument(docId);
      setDoc(result.data);
      if (result.data.sections) {
        setSections(result.data.sections);
      }
      // L9: Load duplicates and approval status
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
      setError(
        err instanceof Error ? err.message : "Failed to load document"
      );
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    if (docId) fetchDoc();
  }, [docId, fetchDoc]);

  const handleParse = async () => {
    setParsing(true);
    setParseError(null);
    try {
      const result = await parseDocument(docId);
      setSections(result.data.sections);
      // Refresh document to get updated status
      await fetchDoc();
    } catch (err: unknown) {
      setParseError(
        err instanceof Error ? err.message : "Parsing failed"
      );
    } finally {
      setParsing(false);
    }
  };

  const toggleSection = (index: number) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedSections(new Set(sections.map((_, i) => i)));
  };

  const collapseAll = () => {
    setExpandedSections(new Set());
  };

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        Loading document…
      </div>
    );
  }

  if (error || !doc) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">⚠️</div>
        <h3>Document not found</h3>
        <p>{error || "The requested document could not be found."}</p>
        <Link href="/documents" className="btn btn-primary btn-sm">
          ← Back to Documents
        </Link>
      </div>
    );
  }

  const canParse = doc.status === "UPLOADED" || doc.status === "ERROR";
  const isParsed = doc.status === "PARSED" || doc.status === "ANALYZING" || doc.status === "COMPLETE";

  return (
    <div className="doc-detail">
      <Link href="/documents" className="back-link">
        ← Back to Documents
      </Link>

      <div className="doc-detail-header">
        <h1>{doc.filename}</h1>
        <div className="doc-detail-meta">
          <StatusBadge status={doc.status} />
          {approvalStatus !== "NONE" && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
                padding: "4px 12px",
                borderRadius: "20px",
                fontSize: "0.75rem",
                fontWeight: 600,
                background: approvalStatus === "APPROVED" ? "#10b98122" : approvalStatus === "REJECTED" ? "#ef444422" : "#f59e0b22",
                color: approvalStatus === "APPROVED" ? "#10b981" : approvalStatus === "REJECTED" ? "#ef4444" : "#f59e0b",
                border: `1px solid ${approvalStatus === "APPROVED" ? "#10b98144" : approvalStatus === "REJECTED" ? "#ef444444" : "#f59e0b44"}`,
              }}
              id="approval-status-badge"
            >
              {approvalStatus === "APPROVED" ? "✅ Approved" : approvalStatus === "REJECTED" ? "❌ Rejected" : "⏳ Pending"}
            </span>
          )}
          <span>Uploaded {formatDate(doc.created_at)}</span>
          <span>Updated {formatDate(doc.updated_at)}</span>
        </div>
      </div>

      {/* L9: Duplicate Warning Banner */}
      {duplicates.length > 0 && (
        <div
          id="duplicate-warning-banner"
          style={{
            padding: "1rem 1.25rem",
            borderRadius: "12px",
            background: "rgba(245, 158, 11, 0.1)",
            border: "1px solid rgba(245, 158, 11, 0.3)",
            marginBottom: "1.5rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
            <span style={{ fontSize: "1.2rem" }}>⚠️</span>
            <strong style={{ color: "#f59e0b" }}>
              {duplicates.length} potential duplicate{duplicates.length !== 1 ? "s" : ""} found
            </strong>
          </div>
          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", margin: 0 }}>
            Similar requirements were detected in other FS documents.
          </p>
          <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {duplicates.slice(0, 3).map((d, i) => (
              <div key={i} style={{ fontSize: "0.8rem", padding: "0.5rem", background: "rgba(245, 158, 11, 0.05)", borderRadius: "8px" }}>
                <strong>§{d.section_index}: {d.section_heading}</strong>
                <span style={{ color: "var(--text-muted)", marginLeft: "0.5rem" }}>
                  {(d.similarity_score * 100).toFixed(0)}% similar to &quot;{d.similar_section_heading}&quot;
                </span>
              </div>
            ))}
            {duplicates.length > 3 && (
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                …and {duplicates.length - 3} more
              </p>
            )}
          </div>
        </div>
      )}

      <div className="info-grid">
        <div className="info-item">
          <div className="info-label">File Size</div>
          <div className="info-value">{formatSize(doc.file_size)}</div>
        </div>
        <div className="info-item">
          <div className="info-label">Content Type</div>
          <div className="info-value">{doc.content_type || "—"}</div>
        </div>
        <div className="info-item">
          <div className="info-label">Document ID</div>
          <div className="info-value" style={{ fontSize: "0.78rem", fontFamily: "var(--font-mono)" }}>
            {doc.id}
          </div>
        </div>
        <div className="info-item">
          <div className="info-label">Sections</div>
          <div className="info-value">{sections.length || "—"}</div>
        </div>
      </div>

      {/* Parse Action */}
      {canParse && (
        <div style={{ margin: "2rem 0" }}>
          <button
            className="btn btn-primary"
            onClick={handleParse}
            disabled={parsing}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "12px 28px",
              fontSize: "1rem",
            }}
          >
            {parsing ? (
              <>
                <span className="spinner" style={{ width: "16px", height: "16px" }} />
                Parsing Document…
              </>
            ) : (
              <>⚡ Parse Document</>
            )}
          </button>
          {parseError && (
            <p style={{ color: "var(--color-error, #ef4444)", marginTop: "0.75rem", fontSize: "0.9rem" }}>
              ❌ {parseError}
            </p>
          )}
        </div>
      )}

      {/* Parsed Sections */}
      {sections.length > 0 && (
        <div style={{ marginTop: "2rem" }}>
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "1rem",
          }}>
            <h2 style={{ margin: 0, fontSize: "1.25rem" }}>
              📄 Parsed Sections ({sections.length})
            </h2>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                onClick={expandAll}
                className="btn btn-sm"
                style={{
                  padding: "4px 12px",
                  fontSize: "0.75rem",
                  background: "var(--glass-bg)",
                  border: "1px solid var(--glass-border)",
                  borderRadius: "6px",
                  color: "var(--text-secondary)",
                  cursor: "pointer",
                }}
              >
                Expand All
              </button>
              <button
                onClick={collapseAll}
                className="btn btn-sm"
                style={{
                  padding: "4px 12px",
                  fontSize: "0.75rem",
                  background: "var(--glass-bg)",
                  border: "1px solid var(--glass-border)",
                  borderRadius: "6px",
                  color: "var(--text-secondary)",
                  cursor: "pointer",
                }}
              >
                Collapse All
              </button>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {sections.map((section, idx) => {
              const isExpanded = expandedSections.has(idx);
              return (
                <div
                  key={idx}
                  style={{
                    background: "var(--glass-bg)",
                    border: "1px solid var(--glass-border)",
                    borderRadius: "12px",
                    overflow: "hidden",
                    transition: "all 0.2s ease",
                  }}
                >
                  <button
                    onClick={() => toggleSection(idx)}
                    style={{
                      width: "100%",
                      padding: "14px 18px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      color: "var(--text-primary)",
                      fontSize: "0.95rem",
                      fontWeight: 600,
                      textAlign: "left",
                    }}
                  >
                    <span style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <span style={{
                        width: "24px",
                        height: "24px",
                        borderRadius: "6px",
                        background: "var(--color-primary-alpha, rgba(139, 92, 246, 0.15))",
                        color: "var(--color-primary, #8b5cf6)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: "0.7rem",
                        fontWeight: 700,
                        flexShrink: 0,
                      }}>
                        {section.section_index + 1}
                      </span>
                      {section.heading}
                    </span>
                    <span style={{
                      transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
                      transition: "transform 0.2s ease",
                      opacity: 0.5,
                    }}>
                      ▼
                    </span>
                  </button>

                  {isExpanded && (
                    <div
                      style={{
                        padding: "0 18px 16px 52px",
                        fontSize: "0.88rem",
                        lineHeight: 1.7,
                        color: "var(--text-secondary)",
                        whiteSpace: "pre-wrap",
                        borderTop: "1px solid var(--glass-border)",
                        paddingTop: "14px",
                      }}
                    >
                      {section.content}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Already parsed indicator */}
      {isParsed && sections.length === 0 && (
        <div style={{ margin: "2rem 0" }}>
          <button
            className="btn btn-primary"
            onClick={handleParse}
            disabled={parsing}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "12px 28px",
              fontSize: "1rem",
              opacity: 0.8,
            }}
          >
            {parsing ? (
              <>
                <span className="spinner" style={{ width: "16px", height: "16px" }} />
                Re-parsing…
              </>
            ) : (
              <>🔄 Re-parse Document</>
            )}
          </button>
        </div>
      )}

      {/* Analyze Actions (L3 + L4 + L5) */}
      {(doc.status === "PARSED" || doc.status === "COMPLETE") && (
        <div style={{ margin: "2rem 0", display: "flex", gap: "12px", flexWrap: "wrap", alignItems: "center" }}>
          <Link
            href={`/documents/${doc.id}/ambiguities`}
            className="btn btn-secondary"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "12px 28px",
              fontSize: "1rem",
            }}
          >
            🔍 View Ambiguity Analysis
          </Link>
          <Link
            href={`/documents/${doc.id}/quality`}
            className="btn btn-secondary"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "12px 28px",
              fontSize: "1rem",
            }}
          >
            📊 Quality Dashboard
          </Link>
          <Link
            href={`/documents/${doc.id}/tasks`}
            className="btn btn-secondary"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "12px 28px",
              fontSize: "1rem",
            }}
          >
            📋 Task Board
          </Link>
          <Link
            href={`/documents/${doc.id}/impact`}
            className="btn btn-secondary"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "12px 28px",
              fontSize: "1rem",
            }}
          >
            🔄 Impact Analysis
          </Link>
          <Link
            href={`/documents/${doc.id}/collab`}
            className="btn btn-secondary"
            id="btn-collab-link"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "12px 28px",
              fontSize: "1rem",
            }}
          >
            🤝 Collaboration
          </Link>
          <Link
            href={`/documents/${doc.id}/traceability`}
            className="btn btn-secondary"
            id="btn-traceability-link"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "12px 28px",
              fontSize: "1rem",
            }}
          >
            🔗 Traceability Matrix
          </Link>
        </div>
      )}
    </div>
  );
}

