"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import {
  uploadCodeZip,
  getReverseStatus,
  listReverseUploads,
  generateFS,
  isCursorTaskEnvelope,
  type CursorTaskEnvelope,
  type ReverseUploadItem,
  type GeneratedFSData,
} from "@/lib/api";
import { useToolConfig } from "@/lib/toolConfig";
import {
  CursorTaskModal,
  PageShell,
  KpiCard,
  FadeIn,
  StaggerList,
  StaggerItem,
  EmptyState,
} from "@/components/index";
import QualityGauge from "@/components/QualityGauge";
import Badge from "@/components/Badge";
import CopyButton from "@/components/CopyButton";
import { motion, AnimatePresence } from "framer-motion";
import {
  RotateCcw,
  Upload,
  FileText,
  CheckCircle2,
  Clock,
  ChevronDown,
  Download,
  Layers,
  BarChart3,
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

function formatBytes(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function uploadStatusBadgeVariant(
  status: string
): "success" | "warning" | "error" | "info" | "neutral" | "accent" {
  switch (status) {
    case "GENERATED":
      return "success";
    case "GENERATING":
    case "PARSING":
      return "accent";
    case "PARSED":
      return "info";
    case "ERROR":
      return "error";
    case "UPLOADED":
    default:
      return "neutral";
  }
}

function compositeQualityScore(report: NonNullable<GeneratedFSData["report"]>): number {
  return Math.round((report.coverage * 0.5 + report.confidence * 0.5) * 100);
}

export default function ReverseFSPage() {
  const [uploads, setUploads] = useState<ReverseUploadItem[]>([]);
  const [selectedUpload, setSelectedUpload] = useState<string | null>(null);
  const [generatedFS, setGeneratedFS] = useState<GeneratedFSData | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set());
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [cursorTask, setCursorTask] = useState<CursorTaskEnvelope | null>(null);
  useToolConfig();

  const fetchUploads = useCallback(async () => {
    try {
      setLoading(true);
      const result = await listReverseUploads();
      setUploads(result.data.uploads || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load uploads");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchGeneratedFS = useCallback(async (uploadId: string) => {
    try {
      const result = await getReverseStatus(uploadId);
      setGeneratedFS(result.data);
    } catch {
      setGeneratedFS(null);
    }
  }, []);

  useEffect(() => {
    void fetchUploads();
  }, [fetchUploads]);

  useEffect(() => {
    if (selectedUpload) {
      void fetchGeneratedFS(selectedUpload);
    }
  }, [selectedUpload, fetchGeneratedFS]);

  const processZipFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith(".zip")) {
        setUploadError("Please upload a .zip archive.");
        return;
      }
      setUploading(true);
      setUploadError(null);
      try {
        const result = await uploadCodeZip(file);
        await fetchUploads();
        setSelectedUpload(result.data.id);
      } catch (err: unknown) {
        setUploadError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [fetchUploads]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) void processZipFile(file);
    },
    [processZipFile]
  );

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const onDragLeave = () => setDragOver(false);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void processZipFile(file);
  };

  const openFilePicker = () => fileInputRef.current?.click();

  const onZoneKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openFilePicker();
    }
  };

  const handleGenerate = async () => {
    if (!selectedUpload) return;
    setError(null);

    setGenerating(true);
    try {
      const result = await generateFS(selectedUpload);
      if (isCursorTaskEnvelope(result.data)) {
        setCursorTask(result.data);
      } else {
        setGeneratedFS(result.data as GeneratedFSData);
        await fetchUploads();
      }
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
      <PageShell title="Reverse FS Engineering" subtitle="Upload your codebase to generate a Functional Specification">
        <div className="page-loading" style={{ minHeight: "40vh" }}>
          <div className="spinner" aria-hidden />
          <p style={{ color: "var(--text-secondary)", marginTop: "0.75rem" }}>Loading uploads…</p>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell title="Reverse FS Engineering" subtitle="Upload your codebase to generate a Functional Specification">
      <AnimatePresence>
        {error && !selectedUploadData && (
          <motion.div
            key="global-error"
            role="alert"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="upload-status error"
            style={{ marginBottom: "1.25rem" }}
          >
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      <FadeIn>
        <div className="upload-container" style={{ maxWidth: "min(560px, 100%)", paddingTop: 0 }}>
          <motion.div
            className={`upload-zone ${dragOver ? "drag-over" : ""} ${uploading ? "drag-over" : ""}`}
            onDrop={uploading ? undefined : onDrop}
            onDragOver={uploading ? undefined : onDragOver}
            onDragLeave={uploading ? undefined : onDragLeave}
            onClick={uploading ? undefined : openFilePicker}
            onKeyDown={uploading ? undefined : onZoneKeyDown}
            role="button"
            tabIndex={uploading ? -1 : 0}
            aria-disabled={uploading}
            aria-label="Upload codebase zip"
            animate={{ scale: dragOver && !uploading ? 1.02 : 1 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
          >
            <div className="upload-icon">
              {uploading ? (
                <Clock size={40} strokeWidth={1.5} aria-hidden />
              ) : dragOver ? (
                <Upload size={40} strokeWidth={1.5} aria-hidden />
              ) : (
                <Upload size={40} strokeWidth={1.5} aria-hidden />
              )}
            </div>
            <h3>
              {uploading
                ? "Uploading and parsing…"
                : "Drop your codebase .zip here or click to browse"}
            </h3>
            <p>Python, JavaScript, TypeScript, Java, Go sources supported inside the archive</p>
            <div className="file-types">
              <span className="file-type-badge">.ZIP</span>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              onChange={handleFileInput}
              style={{ display: "none" }}
              id="code-upload-zip"
              disabled={uploading}
            />
          </motion.div>
        </div>
      </FadeIn>

      <AnimatePresence mode="wait">
        {uploadError && (
          <motion.div
            key="upload-err"
            role="alert"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            className="upload-status error"
            style={{ marginTop: "1rem" }}
          >
            {uploadError}
          </motion.div>
        )}
      </AnimatePresence>

      {uploads.length > 0 && (
        <FadeIn>
          <div style={{ marginTop: "2rem" }}>
            <h2 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.75rem" }}>
              Previous uploads
            </h2>
            <StaggerList style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {uploads.map((u) => {
                const selected = selectedUpload === u.id;
                return (
                  <StaggerItem key={u.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedUpload(u.id)}
                      className="card"
                      style={{
                        width: "100%",
                        textAlign: "left",
                        cursor: "pointer",
                        padding: "1rem 1.15rem",
                        borderRadius: "var(--radius-lg)",
                        border: selected
                          ? "2px solid var(--accent-primary)"
                          : "1px solid var(--border-subtle)",
                        background: selected ? "rgba(108, 92, 231, 0.06)" : "var(--bg-card)",
                        boxShadow: selected ? "0 0 0 1px rgba(108, 92, 231, 0.12)" : undefined,
                        transition: "border-color 0.2s ease, background 0.2s ease",
                        color: "var(--text-primary)",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div
                            style={{
                              fontWeight: 600,
                              fontSize: "0.9rem",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {u.filename}
                          </div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                            {formatDate(u.created_at)} · {formatBytes(u.file_size)}
                          </div>
                        </div>
                        <Badge variant={uploadStatusBadgeVariant(u.status)}>{u.status}</Badge>
                      </div>
                    </button>
                  </StaggerItem>
                );
              })}
            </StaggerList>
          </div>
        </FadeIn>
      )}

      {uploads.length === 0 && !error && (
        <EmptyState
          icon={<Layers size={36} strokeWidth={1.25} aria-hidden />}
          title="No codebases yet"
          description="Upload a zip archive of your codebase to generate a Functional Specification."
        />
      )}

      {selectedUpload && selectedUploadData && (
        <FadeIn>
          <div
            className="card"
            style={{
              marginTop: "1.5rem",
              padding: "1.25rem 1.35rem",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
              <div style={{ minWidth: 0 }}>
                <h2 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.35rem" }}>{selectedUploadData.filename}</h2>
                <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                  Status: <Badge variant={uploadStatusBadgeVariant(selectedUploadData.status)}>{selectedUploadData.status}</Badge>
                </p>
              </div>
              {(selectedUploadData.status === "PARSED" || selectedUploadData.status === "GENERATED") && (
                <button type="button" className="btn btn-primary" onClick={handleGenerate} disabled={generating}>
                  {generating ? (
                    <>
                      <span className="spinner" style={{ width: 14, height: 14 }} aria-hidden />
                      Generating FS…
                    </>
                  ) : selectedUploadData.status === "GENERATED" ? (
                    <>
                      <RotateCcw size={16} aria-hidden style={{ marginRight: 6 }} />
                      Regenerate FS
                    </>
                  ) : (
                    <>
                      <FileText size={16} aria-hidden style={{ marginRight: 6 }} />
                      Generate FS document
                    </>
                  )}
                </button>
              )}
            </div>
            {error && (
              <p role="alert" style={{ color: "var(--error)", marginTop: "0.85rem", fontSize: "0.85rem" }}>
                {error}
              </p>
            )}
          </div>
        </FadeIn>
      )}

      {generatedFS && generatedFS.status === "GENERATED" && (
        <FadeIn>
          <div style={{ marginTop: "1.5rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            {report && (
              <div
                className="card"
                style={{
                  padding: "1.35rem",
                  borderRadius: "var(--radius-lg)",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
                  <BarChart3 size={20} strokeWidth={1.75} aria-hidden />
                  <h3 style={{ fontSize: "1rem", fontWeight: 600 }}>Quality report</h3>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                    gap: "0.75rem",
                    marginBottom: "1.25rem",
                  }}
                >
                  <KpiCard
                    label="Coverage"
                    value={Math.round(report.coverage * 100)}
                    suffix="%"
                    icon={<CheckCircle2 size={18} aria-hidden />}
                    iconBg="rgba(34, 197, 94, 0.15)"
                    delay={0}
                  />
                  <KpiCard
                    label="Confidence"
                    value={Math.round(report.confidence * 100)}
                    suffix="%"
                    icon={<BarChart3 size={18} aria-hidden />}
                    iconBg="rgba(108, 92, 231, 0.15)"
                    delay={0.05}
                  />
                  <KpiCard
                    label="Gaps"
                    value={report.gaps.length}
                    icon={<Clock size={18} aria-hidden />}
                    iconBg="rgba(245, 158, 11, 0.15)"
                    delay={0.1}
                  />
                  <KpiCard
                    label="Sections"
                    value={generatedFS.sections.length}
                    icon={<Layers size={18} aria-hidden />}
                    iconBg="rgba(59, 130, 246, 0.15)"
                    delay={0.15}
                  />
                </div>

                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "1rem", justifyContent: "center" }}>
                  <QualityGauge score={compositeQualityScore(report)} label="FS quality" size={152} strokeWidth={10} />
                  {generatedFS.raw_text ? (
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <Download size={20} strokeWidth={1.5} aria-hidden style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                      <CopyButton text={generatedFS.raw_text} label="Copy full FS" />
                    </div>
                  ) : null}
                </div>

                {report.gaps.length > 0 && (
                  <div style={{ marginTop: "1.25rem" }}>
                    <h4 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.5rem", color: "var(--warning)" }}>
                      Knowledge gaps ({report.gaps.length})
                    </h4>
                    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                      {report.gaps.slice(0, 10).map((gap, idx) => (
                        <li
                          key={idx}
                          style={{
                            padding: "0.5rem 0.75rem",
                            background: "rgba(245, 158, 11, 0.08)",
                            border: "1px solid rgba(245, 158, 11, 0.15)",
                            borderRadius: "var(--radius-sm)",
                            fontSize: "0.82rem",
                            color: "var(--text-secondary)",
                          }}
                        >
                          <Badge variant="warning" style={{ marginRight: "0.5rem", fontSize: "0.65rem" }}>
                            Low conf
                          </Badge>
                          {gap}
                        </li>
                      ))}
                    </ul>
                    {report.gaps.length > 10 && (
                      <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.35rem" }}>
                        …and {report.gaps.length - 10} more
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {generatedFS.generated_fs_id && (
              <div
                className="card"
                style={{
                  padding: "1.15rem 1.35rem",
                  borderRadius: "var(--radius-lg)",
                  border: "1px solid var(--border-subtle)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "1rem",
                }}
              >
                <div>
                  <h4 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.2rem" }}>Run full analysis pipeline</h4>
                  <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                    Feed the generated FS into the forward pipeline (ambiguity detection, task decomposition, and more).
                  </p>
                </div>
                <Link href={`/documents/${generatedFS.generated_fs_id}`} className="btn btn-primary">
                  <Layers size={16} aria-hidden style={{ marginRight: 6, verticalAlign: "middle" }} />
                  Analyze generated FS
                </Link>
              </div>
            )}

            {generatedFS.sections.length > 0 && (
              <div
                className="card"
                style={{
                  padding: "1.25rem",
                  borderRadius: "var(--radius-lg)",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
                  <FileText size={20} strokeWidth={1.75} aria-hidden />
                  <h3 style={{ fontSize: "1rem", fontWeight: 600 }}>Generated FS sections ({generatedFS.sections.length})</h3>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {generatedFS.sections.map((section, idx) => {
                    const isExpanded = expandedSections.has(idx);
                    return (
                      <div key={idx} className="accordion-item">
                        <button
                          type="button"
                          className="accordion-trigger"
                          onClick={() => toggleSection(idx)}
                          aria-expanded={isExpanded}
                        >
                          <span style={{ display: "flex", alignItems: "center", gap: "0.65rem", minWidth: 0 }}>
                            <span className="badge badge-accent" style={{ flexShrink: 0 }}>
                              {section.section_index + 1}
                            </span>
                            <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{section.heading}</span>
                          </span>
                          <ChevronDown
                            size={18}
                            className={`accordion-chevron${isExpanded ? " open" : ""}`}
                            aria-hidden
                          />
                        </button>
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
                              <div
                                className="accordion-content"
                                style={{
                                  fontSize: "0.875rem",
                                  lineHeight: 1.65,
                                  color: "var(--text-secondary)",
                                  whiteSpace: "pre-wrap",
                                  paddingLeft: "0.25rem",
                                  borderTop: "1px solid var(--border-subtle)",
                                  paddingTop: "0.75rem",
                                }}
                              >
                                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.5rem" }}>
                                  <CopyButton text={section.content} label="Copy section" />
                                </div>
                                {section.content}
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </FadeIn>
      )}

      <AnimatePresence>
        {generating && (
          <motion.div
            key="generating"
            className="page-loading"
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0,0,0,0.45)",
              zIndex: 50,
              flexDirection: "column",
              gap: "0.75rem",
              padding: "2rem",
            }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div className="card" style={{ padding: "1.5rem 2rem", maxWidth: 400, textAlign: "center" }}>
              <div className="spinner" style={{ margin: "0 auto 0.75rem" }} aria-hidden />
              <p style={{ fontWeight: 600, marginBottom: "0.35rem" }}>Generating Functional Specification…</p>
              <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                Parsing code, analyzing modules, generating FS, running quality checks
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <CursorTaskModal
        envelope={cursorTask}
        onClose={() => setCursorTask(null)}
        onDone={async () => {
          setCursorTask(null);
          if (selectedUpload) await fetchGeneratedFS(selectedUpload);
          await fetchUploads();
        }}
      />
    </PageShell>
  );
}
