"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listDocuments, deleteDocument } from "@/lib/api";
import type { FSDocumentResponse } from "@/lib/api";

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

function getFileIcon(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "pdf":
      return "📕";
    case "docx":
      return "📘";
    case "txt":
      return "📝";
    default:
      return "📄";
  }
}

function statusClass(status: string): string {
  return status.toLowerCase();
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<FSDocumentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDocs = async () => {
    try {
      setLoading(true);
      const result = await listDocuments();
      setDocuments(result.data.documents);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocs();
  }, []);

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("Delete this document?")) return;

    try {
      await deleteDocument(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        Loading documents…
      </div>
    );
  }

  if (error) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">⚠️</div>
        <h3>Failed to load documents</h3>
        <p>{error}</p>
        <button className="btn btn-primary btn-sm" onClick={fetchDocs}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="documents-header">
        <h1>My Documents</h1>
        <Link href="/upload" className="btn btn-primary btn-sm" id="upload-new-btn">
          ⬆ Upload New
        </Link>
      </div>

      {documents.length === 0 ? (
        <div className="empty-state" id="empty-state">
          <div className="empty-state-icon">📂</div>
          <h3>No documents yet</h3>
          <p>Upload your first Functional Specification to get started.</p>
          <Link href="/upload" className="btn btn-primary">
            ⬆ Upload FS Document
          </Link>
        </div>
      ) : (
        <div className="documents-grid" id="documents-grid">
          {documents.map((doc) => (
            <Link
              href={`/documents/${doc.id}`}
              key={doc.id}
              className="card doc-card"
              id={`doc-${doc.id}`}
            >
              <div className="doc-icon">{getFileIcon(doc.filename)}</div>
              <div className="doc-info">
                <div className="doc-name">{doc.filename}</div>
                <div className="doc-meta">
                  <span>{formatSize(doc.file_size)}</span>
                  <span>{formatDate(doc.created_at)}</span>
                </div>
              </div>
              <span
                className={`status-badge ${statusClass(doc.status)}`}
              >
                {doc.status}
              </span>
              <div className="doc-actions">
                <button
                  className="btn btn-danger btn-sm"
                  onClick={(e) => handleDelete(doc.id, e)}
                  id={`delete-${doc.id}`}
                >
                  🗑
                </button>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
