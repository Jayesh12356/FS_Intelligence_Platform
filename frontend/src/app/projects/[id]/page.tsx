"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  FolderOpen,
  Upload,
  FileText,
  Clock,
  CheckCircle2,
  Edit3,
  ChevronRight,
} from "lucide-react";
import {
  PageShell,
  KpiCard,
  FadeIn,
  StaggerList,
  StaggerItem,
  EmptyState,
  Badge,
} from "@/components/index";
import { useToast } from "@/components/Toaster";
import {
  getProject,
  updateProject,
  uploadFileToProject,
  assignDocumentToProject,
  listDocuments,
  type FSProjectDetail,
  type FSDocumentResponse,
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

type DocStatusVariant = "success" | "warning" | "error" | "neutral";

function documentStatusVariant(status: string): DocStatusVariant {
  const u = status.toUpperCase();
  if (u === "COMPLETE") return "success";
  if (u === "ANALYZING") return "warning";
  if (u === "PARSED" || u === "UPLOADED") return "neutral";
  if (u === "ERROR") return "error";
  return "neutral";
}

function DocumentStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={documentStatusVariant(status)} dot>
      {status}
    </Badge>
  );
}

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { error: toastError } = useToast();
  const projectId = typeof params.id === "string" ? params.id : params.id?.[0] ?? "";
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [project, setProject] = useState<FSProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);

  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState("");

  const loadProject = useCallback(async () => {
    if (!projectId) return;
    try {
      setLoading(true);
      setError(null);
      const [projRes, listRes] = await Promise.all([
        getProject(projectId),
        listDocuments(),
      ]);
      const byId = new Map(listRes.data.documents.map((d) => [d.id, d]));
      const merged: FSProjectDetail = {
        ...projRes.data,
        documents: projRes.data.documents.map((d) => byId.get(d.id) ?? d),
      };
      setProject(merged);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load project");
      setProject(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadProject();
  }, [loadProject]);

  const analyzedCount = useMemo(() => {
    if (!project) return 0;
    return project.documents.filter((d) => d.status.toUpperCase() === "COMPLETE").length;
  }, [project]);

  const latestActivityLabel = useMemo(() => {
    if (!project) return "—";
    const candidates = [project.updated_at, ...project.documents.map((d) => d.updated_at)];
    const latest = candidates.reduce((best, cur) =>
      new Date(cur) > new Date(best) ? cur : best
    );
    return formatDate(latest);
  }, [project]);

  const saveName = useCallback(async () => {
    if (!project || !projectId) return;
    const next = nameDraft.trim();
    if (!next || next === project.name) {
      setEditingName(false);
      setNameDraft(project.name);
      return;
    }
    try {
      await updateProject(projectId, { name: next });
      setProject((p) => (p ? { ...p, name: next, updated_at: new Date().toISOString() } : p));
      setEditingName(false);
      router.refresh();
    } catch (err: unknown) {
      toastError("Could not update name", err instanceof Error ? err.message : undefined);
      setNameDraft(project.name);
      setEditingName(false);
    }
  }, [project, projectId, nameDraft, router, toastError]);

  const saveDescription = useCallback(async () => {
    if (!project || !projectId) return;
    const next = descriptionDraft.trim();
    const prev = (project.description ?? "").trim();
    if (next === prev) {
      setEditingDescription(false);
      setDescriptionDraft(project.description ?? "");
      return;
    }
    try {
      await updateProject(projectId, { description: next || undefined });
      const stored = next.length ? next : null;
      setProject((p) =>
        p ? { ...p, description: stored, updated_at: new Date().toISOString() } : p
      );
      setEditingDescription(false);
      router.refresh();
    } catch (err: unknown) {
      toastError(
        "Could not update description",
        err instanceof Error ? err.message : undefined,
      );
      setDescriptionDraft(project.description ?? "");
      setEditingDescription(false);
    }
  }, [project, projectId, descriptionDraft, router, toastError]);

  const startEditName = useCallback(() => {
    if (!project) return;
    setNameDraft(project.name);
    setEditingName(true);
  }, [project]);

  const startEditDescription = useCallback(() => {
    if (!project) return;
    setDescriptionDraft(project.description ?? "");
    setEditingDescription(true);
  }, [project]);

  const onFileSelected = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file || !projectId || uploadBusy) return;
      setUploadBusy(true);
      try {
        const res = await uploadFileToProject(file, projectId);
        try {
          await assignDocumentToProject(projectId, res.data.id);
        } catch {
          /* may already be linked via upload query */
        }
        await loadProject();
        router.refresh();
      } catch (err: unknown) {
        toastError("Upload failed", err instanceof Error ? err.message : undefined);
      } finally {
        setUploadBusy(false);
      }
    },
    [projectId, uploadBusy, loadProject, router, toastError]
  );

  const titleNode = useMemo(() => {
    if (!project) return "Project";
    if (editingName) {
      return (
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            flexWrap: "wrap",
            maxWidth: "100%",
          }}
        >
          <input
            className="input"
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            onBlur={() => void saveName()}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void saveName();
              }
              if (e.key === "Escape") {
                setNameDraft(project.name);
                setEditingName(false);
              }
            }}
            autoFocus
            aria-label="Project name"
            style={{
              fontSize: "clamp(1.25rem, 2.5vw, 1.75rem)",
              fontWeight: 600,
              minWidth: "12rem",
              maxWidth: "min(100%, 28rem)",
            }}
          />
        </span>
      );
    }
    return (
      <span
        role="button"
        tabIndex={0}
        onClick={startEditName}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            startEditName();
          }
        }}
        style={{
          cursor: "pointer",
          display: "inline-flex",
          alignItems: "center",
          gap: "0.5rem",
          outline: "none",
        }}
      >
        {project.name}
        <Edit3 size={20} strokeWidth={1.5} aria-hidden style={{ opacity: 0.55 }} />
      </span>
    );
  }, [project, editingName, nameDraft, saveName, startEditName]);

  if (!projectId) {
    return (
      <PageShell title="Project" backHref="/projects" backLabel="Projects">
        <FadeIn>
          <EmptyState
            icon={<FolderOpen size={40} strokeWidth={1.25} aria-hidden />}
            title="Invalid project"
            description="No project id was provided in the URL."
            action={
              <Link href="/projects" className="btn btn-primary">
                Back to projects
              </Link>
            }
          />
        </FadeIn>
      </PageShell>
    );
  }

  if (loading) {
    return (
      <PageShell title="Project" backHref="/projects" backLabel="Projects">
        <div className="page-loading">
          <div className="spinner" />
          Loading project…
        </div>
      </PageShell>
    );
  }

  if (error || !project) {
    return (
      <PageShell title="Project" backHref="/projects" backLabel="Projects">
        <FadeIn>
          <div className="empty-state">
            <div className="empty-state-icon" aria-hidden>
              <FolderOpen size={40} strokeWidth={1.25} />
            </div>
            <h3>Failed to load project</h3>
            <p>{error ?? "Unknown error"}</p>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => void loadProject()}>
              Retry
            </button>
          </div>
        </FadeIn>
      </PageShell>
    );
  }

  return (
    <PageShell
      title={titleNode}
      backHref="/projects"
      backLabel="Projects"
      actions={
        <>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
            style={{ display: "none" }}
            aria-hidden
            onChange={onFileSelected}
          />
          <button
            type="button"
            className="btn btn-primary"
            id="project-upload-fs-btn"
            disabled={uploadBusy}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload size={18} aria-hidden />
            {uploadBusy ? "Uploading…" : "Upload FS"}
          </button>
        </>
      }
    >
      <FadeIn>
        <div style={{ marginBottom: "1.25rem" }}>
          {editingDescription ? (
            <textarea
              className="input"
              value={descriptionDraft}
              onChange={(e) => setDescriptionDraft(e.target.value)}
              onBlur={() => void saveDescription()}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setDescriptionDraft(project.description ?? "");
                  setEditingDescription(false);
                }
              }}
              rows={3}
              autoFocus
              aria-label="Project description"
              placeholder="Add a description…"
              style={{
                width: "100%",
                maxWidth: "42rem",
                resize: "vertical",
                fontSize: "0.9375rem",
                lineHeight: 1.5,
              }}
            />
          ) : (
            <button
              type="button"
              onClick={startEditDescription}
              style={{
                display: "block",
                width: "100%",
                maxWidth: "42rem",
                textAlign: "left",
                background: "var(--surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                padding: "0.75rem 1rem",
                cursor: "pointer",
                color: "var(--text-secondary)",
                fontSize: "0.9375rem",
                lineHeight: 1.5,
              }}
            >
              {project.description?.trim() ? (
                project.description
              ) : (
                <span style={{ fontStyle: "italic", opacity: 0.85 }}>
                  Click to add a description…
                </span>
              )}
            </button>
          )}
        </div>
      </FadeIn>

      <FadeIn delay={0.05}>
        <div className="kpi-row" style={{ marginBottom: "1.25rem" }}>
          <KpiCard
            label="Documents"
            value={project.documents.length}
            icon={<FileText size={20} aria-hidden />}
            iconBg="var(--well-blue)"
            delay={0}
          />
          <KpiCard
            label="Analyzed"
            value={analyzedCount}
            icon={<CheckCircle2 size={20} aria-hidden />}
            iconBg="var(--well-green)"
            delay={0.05}
          />
          <KpiCard
            label="Latest activity"
            valueText={latestActivityLabel}
            icon={<Clock size={20} aria-hidden />}
            iconBg="var(--well-amber)"
            delay={0.1}
          />
        </div>
      </FadeIn>

      {project.documents.length === 0 ? (
        <EmptyState
          icon={<FileText size={40} strokeWidth={1.25} aria-hidden />}
          title="No documents in this project"
          description="Upload a Functional Specification to get started."
          action={
            <button
              type="button"
              className="btn btn-primary"
              disabled={uploadBusy}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload size={18} aria-hidden style={{ marginRight: 6 }} />
              Upload FS
            </button>
          }
        />
      ) : (
        <div id="project-documents-list">
          <StaggerList className="documents-grid">
            {project.documents.map((doc: FSDocumentResponse) => (
              <StaggerItem key={doc.id}>
                <motion.div
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
                >
                  <Link
                    href={`/documents/${doc.id}`}
                    className="card doc-card"
                    id={`project-doc-${doc.id}`}
                  >
                    <div className="doc-icon">
                      <FileText size={22} strokeWidth={1.75} aria-hidden />
                    </div>
                    <div className="doc-info">
                      <div className="doc-name">{doc.filename}</div>
                      <div className="doc-meta">
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                          <Clock size={14} aria-hidden />
                          {formatDate(doc.created_at)}
                        </span>
                      </div>
                    </div>
                    <DocumentStatusBadge status={doc.status} />
                    <div className="doc-actions">
                      <ChevronRight
                        size={20}
                        style={{ color: "var(--text-muted)", flexShrink: 0 }}
                        aria-hidden
                      />
                    </div>
                  </Link>
                </motion.div>
              </StaggerItem>
            ))}
          </StaggerList>
        </div>
      )}
    </PageShell>
  );
}
