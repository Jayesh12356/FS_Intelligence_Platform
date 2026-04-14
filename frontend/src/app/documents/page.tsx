"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  FileText,
  Trash2,
  Plus,
  Clock,
  ChevronRight,
} from "lucide-react";
import {
  PageShell,
  FadeIn,
  StaggerList,
  StaggerItem,
  EmptyState,
  SearchInput,
} from "@/components/index";
import { StatusBadge } from "@/components/Badge";
import Modal from "@/components/Modal";
import { listDocuments, deleteDocument, type FSDocumentResponse } from "@/lib/api";

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
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

export default function DocumentsPage() {
  const router = useRouter();
  const [documents, setDocuments] = useState<FSDocumentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<FSDocumentResponse | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const fetchDocs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await listDocuments();
      setDocuments(result.data.documents);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchDocs();
  }, [fetchDocs]);

  const filteredDocuments = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return documents;
    return documents.filter((d) => d.filename.toLowerCase().includes(q));
  }, [documents, search]);

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget || deleteBusy) return;
    const id = deleteTarget.id;
    setDeleteBusy(true);
    setDeleteTarget(null);

    try {
      await deleteDocument(id);
      setRemovingId(id);
      await new Promise((r) => setTimeout(r, 300));
      setDocuments((prev) => prev.filter((d) => d.id !== id));
      setRemovingId(null);
      router.refresh();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleteBusy(false);
    }
  }, [deleteTarget, deleteBusy, router]);

  const requestDelete = (e: React.MouseEvent, doc: FSDocumentResponse) => {
    e.preventDefault();
    e.stopPropagation();
    setDeleteTarget(doc);
  };

  if (loading) {
    return (
      <PageShell title="My Documents">
        <div className="page-loading">
          <div className="spinner" />
          Loading documents…
        </div>
      </PageShell>
    );
  }

  if (error) {
    return (
      <PageShell title="My Documents">
        <FadeIn>
          <div className="empty-state">
            <div className="empty-state-icon" aria-hidden>
              <FileText size={40} strokeWidth={1.25} />
            </div>
            <h3>Failed to load documents</h3>
            <p>{error}</p>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => void fetchDocs()}>
              Retry
            </button>
          </div>
        </FadeIn>
      </PageShell>
    );
  }

  return (
    <PageShell
      title="My Documents"
      actions={
        <Link href="/upload" className="btn btn-primary" id="upload-new-btn">
          <Plus size={18} aria-hidden />
          Upload
        </Link>
      }
    >
      <FadeIn>
        <div style={{ marginBottom: "1.25rem" }}>
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Filter by file name…"
          />
        </div>
      </FadeIn>

      {documents.length === 0 ? (
        <EmptyState
          icon={<FileText size={40} strokeWidth={1.25} aria-hidden />}
          title="Upload your first document"
          description="Add a Functional Specification (PDF, DOCX, or TXT) to start analysis."
          action={
            <Link href="/upload" className="btn btn-primary">
              <Plus size={18} aria-hidden style={{ marginRight: 6 }} />
              Go to upload
            </Link>
          }
        />
      ) : filteredDocuments.length === 0 ? (
        <EmptyState
          icon={<FileText size={40} strokeWidth={1.25} aria-hidden />}
          title="No matches"
          description="Try a different search term."
          action={
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSearch("")}>
              Clear search
            </button>
          }
        />
      ) : (
        <div id="documents-grid">
          <StaggerList className="documents-grid">
          {filteredDocuments.map((doc) => (
            <StaggerItem key={doc.id}>
              <motion.div
                layout
                initial={false}
                animate={{
                  opacity: removingId === doc.id ? 0 : 1,
                  x: removingId === doc.id ? -20 : 0,
                }}
                transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
              >
                <Link
                  href={`/documents/${doc.id}`}
                  className="card doc-card"
                  id={`doc-${doc.id}`}
                >
                  <div className="doc-icon">
                    <FileText size={22} strokeWidth={1.75} aria-hidden />
                  </div>
                  <div className="doc-info">
                    <div className="doc-name">{doc.filename}</div>
                    <div className="doc-meta">
                      <span>{formatSize(doc.file_size)}</span>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <Clock size={14} aria-hidden />
                        {formatDate(doc.created_at)}
                      </span>
                    </div>
                  </div>
                  <StatusBadge status={doc.status} />
                  <div className="doc-actions">
                    <ChevronRight
                      size={20}
                      style={{ color: "var(--text-muted)", flexShrink: 0 }}
                      aria-hidden
                    />
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={(e) => requestDelete(e, doc)}
                      id={`delete-${doc.id}`}
                      aria-label={`Delete ${doc.filename}`}
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
        title="Delete document?"
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
            ? `This will remove “${deleteTarget.filename}” from your library. This action cannot be undone.`
            : null}
        </p>
      </Modal>
    </PageShell>
  );
}
