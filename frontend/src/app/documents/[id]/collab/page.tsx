"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  listComments,
  addComment,
  resolveComment,
  getApprovalStatus,
  submitForApproval,
  approveDocument,
  rejectDocument,
  getAuditLog,
  FSComment,
  FSApproval,
  AuditEvent,
} from "@/lib/api";

const EVENT_ICONS: Record<string, string> = {
  UPLOADED: "⬆️",
  PARSED: "📄",
  ANALYZED: "🔍",
  APPROVED: "✅",
  REJECTED: "❌",
  VERSION_ADDED: "📝",
  TASKS_GENERATED: "📋",
  EXPORTED: "📤",
  COMMENT_ADDED: "💬",
  COMMENT_RESOLVED: "☑️",
  SUBMITTED_FOR_APPROVAL: "📨",
};

export default function CollabPage() {
  const params = useParams();
  const docId = params?.id as string;

  // Comments state
  const [comments, setComments] = useState<FSComment[]>([]);
  const [commentText, setCommentText] = useState("");
  const [commentSection, setCommentSection] = useState(0);
  const [commentsLoading, setCommentsLoading] = useState(true);

  // Approval state
  const [approvalStatus, setApprovalStatus] = useState("NONE");
  const [approvalHistory, setApprovalHistory] = useState<FSApproval[]>([]);
  const [approvalLoading, setApprovalLoading] = useState(true);

  // Audit state
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditLoading, setAuditLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const loadData = useCallback(async () => {
    if (!docId) return;

    try {
      const [commentsRes, approvalRes, auditRes] = await Promise.all([
        listComments(docId),
        getApprovalStatus(docId),
        getAuditLog(docId),
      ]);

      setComments(commentsRes.data?.comments || []);
      setApprovalStatus(approvalRes.data?.current_status || "NONE");
      setApprovalHistory(approvalRes.data?.history || []);
      setAuditEvents(auditRes.data?.events || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setCommentsLoading(false);
      setApprovalLoading(false);
      setAuditLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAddComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!commentText.trim()) return;
    setActionLoading(true);
    try {
      await addComment(docId, commentSection, commentText.trim());
      setCommentText("");
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add comment");
    } finally {
      setActionLoading(false);
    }
  };

  const handleResolveComment = async (commentId: string) => {
    setActionLoading(true);
    try {
      await resolveComment(docId, commentId);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to resolve");
    } finally {
      setActionLoading(false);
    }
  };

  const handleSubmitForApproval = async () => {
    setActionLoading(true);
    try {
      await submitForApproval(docId);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to submit");
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprove = async () => {
    setActionLoading(true);
    try {
      await approveDocument(docId, "reviewer");
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to approve");
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    setActionLoading(true);
    try {
      await rejectDocument(docId, "reviewer", "Needs revision");
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to reject");
    } finally {
      setActionLoading(false);
    }
  };

  const resolvedCount = comments.filter((c) => c.resolved).length;

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto" }}>
      <div className="page-header">
        <h1 className="page-title">🤝 Collaboration</h1>
        <p className="page-subtitle">
          Comments, approval workflow, and audit trail for this document.
        </p>
      </div>

      {error && (
        <div className="alert alert-error" style={{ marginBottom: "1.5rem" }}>
          {error}
          <button onClick={() => setError(null)} style={{ float: "right", background: "none", border: "none", cursor: "pointer" }}>✕</button>
        </div>
      )}

      {/* ── Approval Status ── */}
      <section className="card" style={{ marginBottom: "1.5rem" }} id="approval-section">
        <h2 style={{ marginTop: 0 }}>📋 Approval Status</h2>
        {approvalLoading ? (
          <p>Loading…</p>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1rem" }}>
              <span style={{ fontSize: "1.2rem", fontWeight: 600 }}>Current:</span>
              <span
                className={`badge ${
                  approvalStatus === "APPROVED"
                    ? "badge-success"
                    : approvalStatus === "REJECTED"
                    ? "badge-error"
                    : approvalStatus === "PENDING"
                    ? "badge-warning"
                    : "badge-neutral"
                }`}
                id="approval-badge"
              >
                {approvalStatus === "APPROVED"
                  ? "✅ Approved"
                  : approvalStatus === "REJECTED"
                  ? "❌ Rejected"
                  : approvalStatus === "PENDING"
                  ? "⏳ Pending Review"
                  : "— Not Submitted"}
              </span>
            </div>

            <div style={{ display: "flex", gap: "0.75rem" }}>
              {approvalStatus === "NONE" || approvalStatus === "REJECTED" ? (
                <button
                  className="btn btn-primary"
                  onClick={handleSubmitForApproval}
                  disabled={actionLoading}
                  id="btn-submit-approval"
                >
                  📨 Submit for Approval
                </button>
              ) : null}
              {approvalStatus === "PENDING" && (
                <>
                  <button
                    className="btn btn-success"
                    onClick={handleApprove}
                    disabled={actionLoading}
                    id="btn-approve"
                  >
                    ✅ Approve
                  </button>
                  <button
                    className="btn btn-danger"
                    onClick={handleReject}
                    disabled={actionLoading}
                    id="btn-reject"
                  >
                    ❌ Reject
                  </button>
                </>
              )}
            </div>

            {approvalHistory.length > 0 && (
              <div style={{ marginTop: "1rem" }}>
                <h4>History</h4>
                {approvalHistory.map((a, i) => (
                  <div
                    key={a.id || i}
                    style={{
                      padding: "0.5rem",
                      borderLeft: `3px solid ${
                        a.status === "APPROVED"
                          ? "var(--color-success)"
                          : a.status === "REJECTED"
                          ? "var(--color-error)"
                          : "var(--color-warning)"
                      }`,
                      marginBottom: "0.5rem",
                      fontSize: "0.85rem",
                    }}
                  >
                    <strong>{a.status}</strong> by {a.approver_id}
                    {a.comment && <span> — &quot;{a.comment}&quot;</span>}
                    {a.created_at && (
                      <span style={{ color: "var(--text-muted)", marginLeft: "0.5rem" }}>
                        {new Date(a.created_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </section>

      {/* ── Comments ── */}
      <section className="card" style={{ marginBottom: "1.5rem" }} id="comments-section">
        <h2 style={{ marginTop: 0 }}>
          💬 Comments{" "}
          <span style={{ fontSize: "0.85rem", fontWeight: 400, color: "var(--text-muted)" }}>
            ({comments.length} total, {resolvedCount} resolved)
          </span>
        </h2>

        {/* Add comment form */}
        <form onSubmit={handleAddComment} style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
          <input
            type="number"
            value={commentSection}
            onChange={(e) => setCommentSection(Number(e.target.value))}
            placeholder="Section #"
            className="form-input"
            style={{ width: 80 }}
            min={0}
            id="comment-section-input"
          />
          <input
            type="text"
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            placeholder="Add a comment… (use @username to mention)"
            className="form-input"
            style={{ flex: 1 }}
            id="comment-text-input"
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={actionLoading || !commentText.trim()}
            id="btn-add-comment"
          >
            Add
          </button>
        </form>

        {commentsLoading ? (
          <p>Loading comments…</p>
        ) : comments.length === 0 ? (
          <p style={{ color: "var(--text-muted)" }}>No comments yet.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {comments.map((c, i) => (
              <div
                key={c.id || i}
                style={{
                  padding: "0.75rem",
                  borderRadius: "var(--radius-sm)",
                  background: c.resolved
                    ? "var(--bg-success-subtle, rgba(34,197,94,0.08))"
                    : "var(--bg-secondary)",
                  opacity: c.resolved ? 0.7 : 1,
                }}
                id={`comment-${i}`}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <strong>{c.user_id}</strong>
                    <span style={{ color: "var(--text-muted)", marginLeft: "0.5rem", fontSize: "0.8rem" }}>
                      Section {c.section_index}
                    </span>
                    {c.mentions.length > 0 && (
                      <span style={{ color: "var(--color-primary)", fontSize: "0.8rem", marginLeft: "0.5rem" }}>
                        @{c.mentions.join(" @")}
                      </span>
                    )}
                  </div>
                  {!c.resolved && c.id && (
                    <button
                      className="btn btn-sm"
                      onClick={() => handleResolveComment(c.id!)}
                      disabled={actionLoading}
                      style={{ fontSize: "0.75rem" }}
                    >
                      ☑ Resolve
                    </button>
                  )}
                  {c.resolved && <span className="badge badge-success">Resolved</span>}
                </div>
                <p style={{ margin: "0.5rem 0 0", fontSize: "0.9rem" }}>{c.text}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Audit Trail ── */}
      <section className="card" id="audit-section">
        <h2 style={{ marginTop: 0 }}>
          📜 Audit Trail{" "}
          <span style={{ fontSize: "0.85rem", fontWeight: 400, color: "var(--text-muted)" }}>
            ({auditEvents.length} events)
          </span>
        </h2>

        {auditLoading ? (
          <p>Loading audit trail…</p>
        ) : auditEvents.length === 0 ? (
          <p style={{ color: "var(--text-muted)" }}>No events recorded yet.</p>
        ) : (
          <div style={{ position: "relative", paddingLeft: "2rem" }}>
            {/* Timeline line */}
            <div
              style={{
                position: "absolute",
                left: "0.85rem",
                top: 0,
                bottom: 0,
                width: 2,
                background: "var(--border-color)",
              }}
            />
            {auditEvents.map((e, i) => (
              <div
                key={e.id || i}
                style={{
                  position: "relative",
                  paddingBottom: "1rem",
                  paddingLeft: "1rem",
                }}
                id={`audit-event-${i}`}
              >
                {/* Timeline dot */}
                <div
                  style={{
                    position: "absolute",
                    left: "-1.35rem",
                    top: "0.25rem",
                    width: 20,
                    height: 20,
                    borderRadius: "50%",
                    background: "var(--bg-primary)",
                    border: "2px solid var(--color-primary)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "0.6rem",
                  }}
                >
                  {EVENT_ICONS[e.event_type] || "•"}
                </div>
                <div style={{ fontSize: "0.9rem" }}>
                  <strong>{e.event_type.replace(/_/g, " ")}</strong>
                  <span style={{ color: "var(--text-muted)", marginLeft: "0.5rem", fontSize: "0.8rem" }}>
                    by {e.user_id}
                  </span>
                </div>
                {e.created_at && (
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {new Date(e.created_at).toLocaleString()}
                  </div>
                )}
                {e.payload_json && Object.keys(e.payload_json).length > 0 && (
                  <div
                    style={{
                      fontSize: "0.75rem",
                      color: "var(--text-secondary)",
                      marginTop: "0.25rem",
                      fontFamily: "monospace",
                    }}
                  >
                    {Object.entries(e.payload_json)
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(" · ")}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
