"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  FolderOpen,
  Plus,
  Trash2,
  FileText,
  Clock,
} from "lucide-react";
import {
  PageShell,
  KpiCard,
  FadeIn,
  StaggerList,
  StaggerItem,
  EmptyState,
  Badge,
  Modal,
} from "@/components/index";
import { useToast } from "@/components/Toaster";
import {
  listProjects,
  createProject,
  deleteProject,
  type FSProject,
  type ProjectListData,
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

export default function ProjectsPage() {
  const router = useRouter();
  const { error: toastError } = useToast();
  const [projects, setProjects] = useState<ProjectListData["projects"]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [createBusy, setCreateBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<FSProject | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await listProjects();
      setProjects(result.data.projects);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchProjects();
  }, [fetchProjects]);

  const totalDocuments = useMemo(
    () => projects.reduce((sum, p) => sum + (p.document_count ?? 0), 0),
    [projects]
  );

  const resetCreateForm = useCallback(() => {
    setNewName("");
    setNewDescription("");
    setShowCreateForm(false);
  }, []);

  const handleCreate = useCallback(async () => {
    const name = newName.trim();
    if (!name || createBusy) return;
    setCreateBusy(true);
    try {
      const desc = newDescription.trim();
      const result = await createProject(name, desc || undefined);
      setProjects((prev) => [result.data, ...prev]);
      resetCreateForm();
      router.refresh();
    } catch (err: unknown) {
      toastError(
        "Could not create project",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setCreateBusy(false);
    }
  }, [newName, newDescription, createBusy, resetCreateForm, router, toastError]);

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget || deleteBusy) return;
    const id = deleteTarget.id;
    setDeleteBusy(true);
    setDeleteTarget(null);
    try {
      await deleteProject(id);
      setRemovingId(id);
      await new Promise((r) => setTimeout(r, 300));
      setProjects((prev) => prev.filter((p) => p.id !== id));
      setRemovingId(null);
      router.refresh();
    } catch (err: unknown) {
      toastError("Delete failed", err instanceof Error ? err.message : undefined);
    } finally {
      setDeleteBusy(false);
    }
  }, [deleteTarget, deleteBusy, router, toastError]);

  const requestDelete = (e: React.MouseEvent, project: FSProject) => {
    e.preventDefault();
    e.stopPropagation();
    setDeleteTarget(project);
  };

  if (loading) {
    return (
      <PageShell title="Projects">
        <div className="page-loading">
          <div className="spinner" />
          Loading projects…
        </div>
      </PageShell>
    );
  }

  if (error) {
    return (
      <PageShell title="Projects">
        <FadeIn>
          <div className="empty-state">
            <div className="empty-state-icon" aria-hidden>
              <FolderOpen size={40} strokeWidth={1.25} />
            </div>
            <h3>Failed to load projects</h3>
            <p>{error}</p>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => void fetchProjects()}>
              Retry
            </button>
          </div>
        </FadeIn>
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Projects"
      actions={
        <button
          type="button"
          className="btn btn-primary"
          id="new-project-btn"
          onClick={() => setShowCreateForm((v) => !v)}
          aria-expanded={showCreateForm}
        >
          <Plus size={18} aria-hidden />
          New Project
        </button>
      }
    >
      <AnimatePresence initial={false}>
        {showCreateForm && (
          <motion.div
            key="create-form"
            initial={{ opacity: 0, height: 0, marginBottom: 0 }}
            animate={{ opacity: 1, height: "auto", marginBottom: 20 }}
            exit={{ opacity: 0, height: 0, marginBottom: 0 }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: "hidden" }}
          >
            <div className="card" style={{ padding: "1.25rem 1.5rem" }}>
              <h3 style={{ margin: "0 0 1rem", fontSize: "1rem", fontWeight: 600 }}>
                Create project
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div>
                  <label className="form-label" htmlFor="project-name">
                    Name
                  </label>
                  <input
                    id="project-name"
                    className="form-input"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g. Mobile app rollout"
                    autoComplete="off"
                  />
                </div>
                <div>
                  <label className="form-label" htmlFor="project-description">
                    Description <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(optional)</span>
                  </label>
                  <textarea
                    id="project-description"
                    className="form-input"
                    rows={3}
                    value={newDescription}
                    onChange={(e) => setNewDescription(e.target.value)}
                    placeholder="Short summary for your team…"
                    style={{ resize: "vertical", minHeight: "4.5rem" }}
                  />
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={!newName.trim() || createBusy}
                    onClick={() => void handleCreate()}
                  >
                    {createBusy ? "Creating…" : "Create"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={createBusy}
                    onClick={resetCreateForm}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <FadeIn delay={0.04}>
        <div className="kpi-row" style={{ marginBottom: "1.25rem" }}>
          <KpiCard
            label="Total projects"
            value={projects.length}
            icon={<FolderOpen size={20} aria-hidden />}
            iconBg="var(--well-blue)"
            delay={0}
          />
          <KpiCard
            label="Total documents"
            value={totalDocuments}
            icon={<FileText size={20} aria-hidden />}
            iconBg="var(--well-green)"
            delay={0.05}
          />
        </div>
      </FadeIn>

      {projects.length === 0 ? (
        <EmptyState
          icon={<FolderOpen size={40} strokeWidth={1.25} aria-hidden />}
          title="No projects yet"
          description="Create a project to group specifications and track document counts in one place."
          action={
            <button type="button" className="btn btn-primary" onClick={() => setShowCreateForm(true)}>
              <Plus size={18} aria-hidden style={{ marginRight: 6 }} />
              New project
            </button>
          }
        />
      ) : (
        <div id="projects-grid">
          <StaggerList className="documents-grid">
            {projects.map((project) => (
              <StaggerItem key={project.id}>
                <motion.div
                  layout
                  initial={false}
                  animate={{
                    opacity: removingId === project.id ? 0 : 1,
                    x: removingId === project.id ? -20 : 0,
                  }}
                  transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
                >
                  <Link
                    href={`/projects/${project.id}`}
                    className="card doc-card"
                    id={`project-${project.id}`}
                  >
                    <div className="doc-icon">
                      <FolderOpen size={22} strokeWidth={1.75} aria-hidden />
                    </div>
                    <div className="doc-info">
                      <div className="doc-name">{project.name}</div>
                      <p
                        style={{
                          margin: "0.25rem 0 0",
                          fontSize: "0.8125rem",
                          color: "var(--text-muted)",
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                          lineHeight: 1.45,
                        }}
                      >
                        {project.description?.trim() || "No description"}
                      </p>
                      <div className="doc-meta" style={{ marginTop: "0.5rem" }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                          <FileText size={14} aria-hidden />
                          {project.document_count === 1 ? "1 document" : `${project.document_count} documents`}
                        </span>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                          <Clock size={14} aria-hidden />
                          {formatDate(project.created_at)}
                        </span>
                      </div>
                    </div>
                    <Badge variant="accent">{project.document_count}</Badge>
                    <div className="doc-actions">
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={(e) => requestDelete(e, project)}
                        id={`delete-project-${project.id}`}
                        aria-label={`Delete ${project.name}`}
                      >
                        <Trash2 size={16} aria-hidden />
                      </button>
                    </div>
                  </Link>
                </motion.div>
              </StaggerItem>
            ))}
          </StaggerList>
        </div>
      )}

      <Modal
        open={deleteTarget !== null}
        onClose={() => !deleteBusy && setDeleteTarget(null)}
        title="Delete project?"
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteBusy}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              onClick={() => void confirmDelete()}
              disabled={deleteBusy}
            >
              {deleteBusy ? "Deleting…" : "Delete"}
            </button>
          </>
        }
      >
        <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
          {deleteTarget
            ? `This will remove “${deleteTarget.name}” and its associations. This action cannot be undone.`
            : null}
        </p>
      </Modal>
    </PageShell>
  );
}
