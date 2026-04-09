"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import {
  uploadCodebase,
  listCodeUploads,
  generateFS,
  getGeneratedFS,
} from "@/lib/api";
import type {
  CodeUploadItem,
  GeneratedFSData,
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

function formatBytes(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const STATUS_COLORS: Record<string, string> = {
  UPLOADED: "#6b7280",
  PARSING: "#f59e0b",
  PARSED: "#3b82f6",
  GENERATING: "#a855f7",
  GENERATED: "#22c55e",
  ERROR: "#ef4444",
};

export default function ReverseFSPage() {
  const [uploads, setUploads] = useState<CodeUploadItem[]>([]);
  const [selectedUpload, setSelectedUpload] = useState<string | null>(null);
  const [generatedFS, setGeneratedFS] = useState<GeneratedFSData | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchUploads = useCallback(async () => {
    try {
      setLoading(true);
      const result = await listCodeUploads();
      setUploads(result.data.uploads || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load uploads");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUploads();
  }, [fetchUploads]);

  useEffect(() => {
    if (selectedUpload) {
      fetchGeneratedFS(selectedUpload);
    }
  }, [selectedUpload]);

  const fetchGeneratedFS = async (uploadId: string) => {
    try {
      const result = await getGeneratedFS(uploadId);
      setGeneratedFS(result.data);
    } catch {
      setGeneratedFS(null);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadError(null);

    try {
      const result = await uploadCodebase(file);
      await fetchUploads();
      setSelectedUpload(result.data.id);
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleGenerate = async () => {
    if (!selectedUpload) return;
    setGenerating(true);
    setError(null);
    try {
      const result = await generateFS(selectedUpload);
      setGeneratedFS(result.data);
      await fetchUploads();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGenerating(false);
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

  const selectedUploadData = uploads.find((u) => u.id === selectedUpload);
  const report = generatedFS?.report;

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        Loading...
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "960px" }}>
      <Link href="/" className="back-link">
        ← Home
      </Link>

      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.8rem", fontWeight: 700, marginBottom: "0.5rem" }}>
          🔄 Legacy Code → FS Generator
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem" }}>
          Upload a codebase zip to automatically generate a Functional Specification document
        </p>
      </div>

      {/* Upload Section */}
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
              Upload Codebase
            </h3>
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
              Upload a .zip archive of your codebase (.py, .js, .ts, .java, .go supported)
            </p>
          </div>
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              onChange={handleUpload}
              style={{ display: "none" }}
              id="code-upload"
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
                  Uploading & Parsing…
                </>
              ) : (
                <>📤 Upload .zip</>
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

      {/* Previous Uploads */}
      {uploads.length > 0 && (
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
            📁 Uploaded Codebases ({uploads.length})
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {uploads.map((u) => {
              const statusColor = STATUS_COLORS[u.status] || "#6b7280";
              return (
                <button
                  key={u.id}
                  onClick={() => setSelectedUpload(u.id)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "12px 16px",
                    borderRadius: "var(--radius-md)",
                    border: selectedUpload === u.id
                      ? "2px solid var(--accent-primary)"
                      : "1px solid var(--border-subtle)",
                    background: selectedUpload === u.id
                      ? "rgba(108, 92, 231, 0.08)"
                      : "var(--bg-secondary)",
                    cursor: "pointer",
                    color: "var(--text-primary)",
                    fontSize: "0.9rem",
                    fontWeight: selectedUpload === u.id ? 600 : 400,
                    textAlign: "left",
                    transition: "all 0.2s ease",
                    width: "100%",
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, marginBottom: "2px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {u.filename}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      {formatDate(u.created_at)} · {formatBytes(u.file_size)}
                    </div>
                  </div>
                  <span
                    style={{
                      padding: "3px 10px",
                      borderRadius: "4px",
                      fontSize: "0.7rem",
                      fontWeight: 700,
                      background: `${statusColor}22`,
                      color: statusColor,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                      whiteSpace: "nowrap",
                      flexShrink: 0,
                    }}
                  >
                    {u.status}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* No uploads hint */}
      {uploads.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">📦</div>
          <h3>No Codebases Uploaded</h3>
          <p>Upload a zip archive of your codebase to generate a Functional Specification.</p>
        </div>
      )}

      {/* Selected Upload Actions */}
      {selectedUpload && selectedUploadData && (
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
                {selectedUploadData.filename}
              </h3>
              <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                Status: {selectedUploadData.status}
              </p>
            </div>
            {(selectedUploadData.status === "PARSED" || selectedUploadData.status === "GENERATED") && (
              <button
                className="btn btn-primary"
                onClick={handleGenerate}
                disabled={generating}
                style={{ padding: "10px 24px", fontSize: "0.9rem" }}
              >
                {generating ? (
                  <>
                    <span className="spinner" style={{ width: "14px", height: "14px" }} />
                    Generating FS…
                  </>
                ) : selectedUploadData.status === "GENERATED" ? (
                  <>🔄 Regenerate FS</>
                ) : (
                  <>⚡ Generate FS Document</>
                )}
              </button>
            )}
          </div>
          {error && (
            <p style={{ color: "var(--error)", marginTop: "0.75rem", fontSize: "0.85rem" }}>
              ❌ {error}
            </p>
          )}
        </div>
      )}

      {/* Generated FS Results */}
      {generatedFS && generatedFS.status === "GENERATED" && (
        <>
          {/* Quality Report Card */}
          {report && (
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
                📊 Quality Report
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "1rem", marginBottom: "1rem" }}>
                <div style={{ textAlign: "center", padding: "1rem", background: "rgba(34, 197, 94, 0.1)", borderRadius: "var(--radius-md)", border: "1px solid rgba(34, 197, 94, 0.2)" }}>
                  <div style={{ fontSize: "2rem", fontWeight: 800, color: "#22c55e" }}>{Math.round(report.coverage * 100)}%</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Coverage</div>
                </div>
                <div style={{ textAlign: "center", padding: "1rem", background: "rgba(108, 92, 231, 0.1)", borderRadius: "var(--radius-md)", border: "1px solid rgba(108, 92, 231, 0.2)" }}>
                  <div style={{ fontSize: "2rem", fontWeight: 800, color: "var(--accent-primary)" }}>{Math.round(report.confidence * 100)}%</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Confidence</div>
                </div>
                <div style={{ textAlign: "center", padding: "1rem", background: "rgba(245, 158, 11, 0.1)", borderRadius: "var(--radius-md)", border: "1px solid rgba(245, 158, 11, 0.2)" }}>
                  <div style={{ fontSize: "2rem", fontWeight: 800, color: "#f59e0b" }}>{report.gaps.length}</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Gaps</div>
                </div>
                <div style={{ textAlign: "center", padding: "1rem", background: "rgba(59, 130, 246, 0.1)", borderRadius: "var(--radius-md)", border: "1px solid rgba(59, 130, 246, 0.2)" }}>
                  <div style={{ fontSize: "2rem", fontWeight: 800, color: "#3b82f6" }}>{generatedFS.sections.length}</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Sections</div>
                </div>
              </div>

              {/* Gaps List */}
              {report.gaps.length > 0 && (
                <div style={{ marginTop: "1rem" }}>
                  <h4 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.5rem", color: "#f59e0b" }}>
                    ⚠️ Knowledge Gaps ({report.gaps.length})
                  </h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    {report.gaps.slice(0, 10).map((gap, idx) => (
                      <div
                        key={idx}
                        style={{
                          padding: "6px 12px",
                          background: "rgba(245, 158, 11, 0.08)",
                          border: "1px solid rgba(245, 158, 11, 0.15)",
                          borderRadius: "var(--radius-sm)",
                          fontSize: "0.82rem",
                          color: "var(--text-secondary)",
                        }}
                      >
                        <span style={{ color: "#f59e0b", marginRight: "6px", fontSize: "0.7rem", fontWeight: 700, padding: "1px 6px", background: "rgba(245, 158, 11, 0.2)", borderRadius: "3px" }}>
                          LOW CONF
                        </span>
                        {gap}
                      </div>
                    ))}
                    {report.gaps.length > 10 && (
                      <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", padding: "4px" }}>
                        ...and {report.gaps.length - 10} more gaps
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Run Full Analysis Button */}
          {generatedFS.generated_fs_id && (
            <div
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-lg)",
                padding: "1.25rem",
                marginBottom: "1.5rem",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: "1rem",
              }}
            >
              <div>
                <h4 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.2rem" }}>
                  Run Full Analysis Pipeline
                </h4>
                <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                  Feed the generated FS into the forward pipeline (ambiguity detection, task decomposition, etc.)
                </p>
              </div>
              <Link
                href={`/documents/${generatedFS.generated_fs_id}`}
                className="btn btn-primary"
                style={{ padding: "10px 24px", fontSize: "0.9rem" }}
              >
                🚀 Analyze Generated FS
              </Link>
            </div>
          )}

          {/* Generated Sections */}
          {generatedFS.sections.length > 0 && (
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
                📄 Generated FS Sections ({generatedFS.sections.length})
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {generatedFS.sections.map((section, idx) => {
                  const isExpanded = expandedSections.has(idx);
                  return (
                    <div
                      key={idx}
                      style={{
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "var(--radius-md)",
                        overflow: "hidden",
                        transition: "all 0.2s ease",
                      }}
                    >
                      <button
                        onClick={() => toggleSection(idx)}
                        style={{
                          width: "100%",
                          padding: "12px 16px",
                          display: "flex",
                          alignItems: "center",
                          gap: "10px",
                          background: "var(--bg-secondary)",
                          border: "none",
                          cursor: "pointer",
                          color: "var(--text-primary)",
                          fontSize: "0.9rem",
                          fontWeight: 600,
                          textAlign: "left",
                        }}
                      >
                        <span style={{ fontSize: "0.75rem", color: "var(--accent-primary)", fontWeight: 700, flexShrink: 0 }}>
                          §{idx + 1}
                        </span>
                        <span style={{ flex: 1 }}>{section.heading}</span>
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
                        <div
                          style={{
                            padding: "1rem 16px",
                            borderTop: "1px solid var(--border-subtle)",
                            fontSize: "0.88rem",
                            lineHeight: 1.7,
                            color: "var(--text-secondary)",
                            whiteSpace: "pre-wrap",
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
        </>
      )}

      {/* Generating state */}
      {generating && (
        <div className="page-loading">
          <div className="spinner" />
          <div style={{ textAlign: "center" }}>
            <p style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Generating Functional Specification…</p>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
              Parsing code → Analysing modules → Generating FS → Quality check
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
