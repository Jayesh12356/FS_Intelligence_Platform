"use client";

import { useState, useEffect, useCallback, type FormEvent } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
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
import {
  PageShell,
  KpiCard,
  Tabs,
  FadeIn,
  StaggerList,
  StaggerItem,
  EmptyState,
} from "@/components/index";
import Badge from "@/components/Badge";
import { motion, AnimatePresence } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import {
  Users,
  MessageSquare,
  Shield,
  Clock,
  CheckCircle2,
  XCircle,
  Send,
  Upload,
  FileText,
  Search,
  ListTodo,
  Download,
  MessageCircle,
  CheckSquare,
} from "lucide-react";

const EVENT_ICONS: Record<string, LucideIcon> = {
  UPLOADED: Upload,
  PARSED: FileText,
  ANALYZED: Search,
  APPROVED: CheckCircle2,
  REJECTED: XCircle,
  VERSION_ADDED: FileText,
  TASKS_GENERATED: ListTodo,
  EXPORTED: Download,
  COMMENT_ADDED: MessageCircle,
  COMMENT_RESOLVED: CheckSquare,
  SUBMITTED_FOR_APPROVAL: Send,
};

function approvalStatusLabel(status: string): string {
  if (status === "APPROVED") return "Approved";
  if (status === "REJECTED") return "Rejected";
  if (status === "PENDING") return "Pending review";
  return "Not submitted";
}

function approvalBadgeVariant(
  status: string
): "success" | "error" | "warning" | "neutral" {
  if (status === "APPROVED") return "success";
  if (status === "REJECTED") return "error";
  if (status === "PENDING") return "warning";
  return "neutral";
}

function historyDotClass(status: string): string {
  if (status === "APPROVED") return "timeline-dot success";
  if (status === "REJECTED") return "timeline-dot error";
  return "timeline-dot warning";
}

export default function CollabPage() {
  const params = useParams();
  const docId = params?.id as string;

  const [comments, setComments] = useState<FSComment[]>([]);
  const [commentText, setCommentText] = useState("");
  const [commentSection, setCommentSection] = useState(0);
  const [commentsLoading, setCommentsLoading] = useState(true);

  const [approvalStatus, setApprovalStatus] = useState("NONE");
  const [approvalHistory, setApprovalHistory] = useState<FSApproval[]>([]);
  const [approvalLoading, setApprovalLoading] = useState(true);

  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditLoading, setAuditLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const [activeTab, setActiveTab] = useState<"approval" | "comments" | "audit">(
    "approval"
  );

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

  const handleAddComment = async (e: FormEvent) => {
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

  const handleSubmitApproval = async () => {
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
  const pageBooting = commentsLoading && approvalLoading && auditLoading;

  return (
    <PageShell
      backHref={docId ? `/documents/${docId}` : "/documents"}
      backLabel="Document"
      title="Collaboration"
      subtitle="Review, approve, and track document changes"
      maxWidth={1000}
    >
      {pageBooting ? (
        <div className="page-loading">
          <div className="spinner" />
        </div>
      ) : (
        <FadeIn delay={0.04}>
          {error && (
            <div className="alert alert-error" style={{ marginBottom: "1.5rem" }}>
              {error}
              <button
                type="button"
                onClick={() => setError(null)}
                className="btn btn-sm"
                style={{ float: "right", marginTop: -2 }}
                aria-label="Dismiss error"
              >
                ×
              </button>
            </div>
          )}

          <div className="kpi-row">
            <KpiCard
              label="Total comments"
              value={comments.length}
              icon={<MessageSquare size={20} aria-hidden />}
              iconBg="var(--well-blue)"
              delay={0}
            />
            <KpiCard
              label="Resolved"
              value={resolvedCount}
              icon={<CheckSquare size={20} aria-hidden />}
              iconBg="var(--well-green)"
              delay={0.04}
            />
            <KpiCard
              label="Approval status"
              valueText={approvalStatusLabel(approvalStatus)}
              icon={<Shield size={20} aria-hidden />}
              iconBg="var(--well-purple)"
              delay={0.08}
            />
            <KpiCard
              label="Audit events"
              value={auditEvents.length}
              icon={<Clock size={20} aria-hidden />}
              iconBg="var(--well-amber)"
              delay={0.12}
            />
          </div>

          <div style={{ marginBottom: "1.25rem" }}>
            <Tabs
              active={activeTab}
              onChange={(k) => setActiveTab(k as "approval" | "comments" | "audit")}
              items={[
                { key: "approval", label: "Approval" },
                { key: "comments", label: "Comments", count: comments.length },
                { key: "audit", label: "Audit Trail", count: auditEvents.length },
              ]}
            />
          </div>

          <AnimatePresence mode="wait">
            {activeTab === "approval" && (
              <motion.div
                key="approval"
                id="approval-section"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
              >
                {approvalLoading ? (
                  <p style={{ color: "var(--text-muted)" }}>Loading…</p>
                ) : (
                  <>
                    <div
                      className="card"
                      style={{
                        marginBottom: "1.5rem",
                        padding: "1.5rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "1.25rem",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          flexWrap: "wrap",
                          alignItems: "center",
                          gap: "1rem",
                          justifyContent: "space-between",
                        }}
                      >
                        <div>
                          <p
                            style={{
                              margin: "0 0 0.5rem",
                              fontSize: "0.8125rem",
                              fontWeight: 600,
                              color: "var(--text-secondary)",
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                            }}
                          >
                            <Users size={16} aria-hidden />
                            Current status
                          </p>
                          <Badge
                            variant={approvalBadgeVariant(approvalStatus)}
                            id="approval-badge"
                            className="collab-status-badge"
                            style={{
                              fontSize: "1.0625rem",
                              padding: "0.5rem 1rem",
                              fontWeight: 600,
                            }}
                          >
                            {approvalStatusLabel(approvalStatus)}
                          </Badge>
                        </div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
                          {approvalStatus === "NONE" || approvalStatus === "REJECTED" ? (
                            <button
                              type="button"
                              className="btn btn-primary"
                              onClick={handleSubmitApproval}
                              disabled={actionLoading}
                              id="btn-submit-approval"
                              style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
                            >
                              <Send size={18} aria-hidden />
                              Submit for approval
                            </button>
                          ) : null}
                          {approvalStatus === "PENDING" && (
                            <>
                              <button
                                type="button"
                                className="btn btn-success"
                                onClick={handleApprove}
                                disabled={actionLoading}
                                id="btn-approve"
                                style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
                              >
                                <CheckCircle2 size={18} aria-hidden />
                                Approve
                              </button>
                              <button
                                type="button"
                                className="btn btn-danger"
                                onClick={handleReject}
                                disabled={actionLoading}
                                id="btn-reject"
                                style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
                              >
                                <XCircle size={18} aria-hidden />
                                Reject
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    {approvalHistory.length > 0 && (
                      <div className="card" style={{ padding: "1.5rem" }}>
                        <h3
                          style={{
                            margin: "0 0 1rem",
                            fontSize: "1rem",
                            fontWeight: 600,
                          }}
                        >
                          Approval history
                        </h3>
                        <div className="timeline">
                          {approvalHistory.map((a, i) => (
                            <div key={a.id || i} className="timeline-item">
                              <div className={historyDotClass(a.status)} aria-hidden />
                              <div className="timeline-content">
                                <div className="timeline-title">
                                  <strong>{a.status}</strong>
                                  {" "}
                                  <span style={{ fontWeight: 400 }}>by {a.approver_id}</span>
                                </div>
                                {a.comment ? (
                                  <div className="timeline-desc">&quot;{a.comment}&quot;</div>
                                ) : null}
                                {a.created_at ? (
                                  <div className="timeline-time">
                                    {new Date(a.created_at).toLocaleString()}
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </motion.div>
            )}

            {activeTab === "comments" && (
              <motion.div
                key="comments"
                id="comments-section"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
              >
                <form
                  onSubmit={handleAddComment}
                  className="card"
                  style={{ padding: "1.5rem", marginBottom: "1.5rem" }}
                >
                  <div className="form-group">
                    <label className="form-label" htmlFor="comment-section-input">
                      Section number
                    </label>
                    <input
                      id="comment-section-input"
                      type="number"
                      value={commentSection}
                      onChange={(e) => setCommentSection(Number(e.target.value))}
                      placeholder="0"
                      className="form-input"
                      style={{ maxWidth: 120 }}
                      min={0}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="comment-text-input">
                      Comment
                    </label>
                    <textarea
                      id="comment-text-input"
                      value={commentText}
                      onChange={(e) => setCommentText(e.target.value)}
                      placeholder="Add a comment… (use @username to mention)"
                      className="form-textarea"
                      rows={4}
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={actionLoading || !commentText.trim()}
                    id="btn-add-comment"
                    style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
                  >
                    <Send size={18} aria-hidden />
                    Send
                  </button>
                </form>

                {commentsLoading ? (
                  <p style={{ color: "var(--text-muted)" }}>Loading comments…</p>
                ) : comments.length === 0 ? (
                  <EmptyState
                    icon={<MessageSquare size={40} strokeWidth={1.25} aria-hidden />}
                    title="No comments yet"
                    description="Start the conversation with your team on this specification."
                    action={
                      <Link href={docId ? `/documents/${docId}` : "/documents"} className="btn btn-sm">
                        Back to document
                      </Link>
                    }
                  />
                ) : (
                  <StaggerList style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                    {comments.map((c, i) => (
                      <StaggerItem key={c.id || i}>
                        <div
                          className="card"
                          id={`comment-${i}`}
                          style={{
                            padding: "1rem 1.25rem",
                            opacity: c.resolved ? 0.72 : 1,
                            background: c.resolved
                              ? "var(--bg-success-subtle, rgba(34,197,94,0.08))"
                              : undefined,
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "flex-start",
                              gap: "0.75rem",
                              flexWrap: "wrap",
                            }}
                          >
                            <div style={{ flex: "1 1 200px" }}>
                              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                                <Badge variant="accent">Section {c.section_index}</Badge>
                                <strong style={{ fontSize: "0.875rem" }}>{c.user_id}</strong>
                                {c.mentions.length > 0 && (
                                  <span
                                    style={{
                                      color: "var(--color-primary)",
                                      fontSize: "0.8125rem",
                                    }}
                                  >
                                    @{c.mentions.join(" @")}
                                  </span>
                                )}
                              </div>
                              <p style={{ margin: "0.75rem 0 0", fontSize: "0.9rem", lineHeight: 1.5 }}>
                                {c.text}
                              </p>
                            </div>
                            <div style={{ flexShrink: 0 }}>
                              {!c.resolved && c.id && (
                                <button
                                  type="button"
                                  className="btn btn-success btn-sm"
                                  onClick={() => handleResolveComment(c.id!)}
                                  disabled={actionLoading}
                                  style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                                >
                                  <CheckSquare size={14} aria-hidden />
                                  Resolve
                                </button>
                              )}
                              {c.resolved && (
                                <Badge variant="success">Resolved</Badge>
                              )}
                            </div>
                          </div>
                        </div>
                      </StaggerItem>
                    ))}
                  </StaggerList>
                )}
              </motion.div>
            )}

            {activeTab === "audit" && (
              <motion.div
                key="audit"
                id="audit-section"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
              >
                {auditLoading ? (
                  <p style={{ color: "var(--text-muted)" }}>Loading audit trail…</p>
                ) : auditEvents.length === 0 ? (
                  <EmptyState
                    icon={<Clock size={40} strokeWidth={1.25} aria-hidden />}
                    title="No events recorded yet"
                    description="Activity on this document will appear here."
                  />
                ) : (
                  <div className="card" style={{ padding: "1.5rem" }}>
                    <div className="timeline">
                      {auditEvents.map((e, i) => {
                        const Icon = EVENT_ICONS[e.event_type] ?? FileText;
                        return (
                          <div key={e.id || i} className="timeline-item" id={`audit-event-${i}`}>
                            <div
                              className="timeline-dot active"
                              style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                width: 22,
                                height: 22,
                                left: "calc(-1.75rem + 3px)",
                                top: 1,
                                background: "var(--bg-card)",
                                borderWidth: 2,
                              }}
                              aria-hidden
                            >
                              <Icon size={11} strokeWidth={2.25} />
                            </div>
                            <div className="timeline-content">
                              <div className="timeline-title">
                                {e.event_type.replace(/_/g, " ")}
                                <span
                                  style={{
                                    fontWeight: 400,
                                    color: "var(--text-secondary)",
                                    marginLeft: "0.5rem",
                                    fontSize: "0.8125rem",
                                  }}
                                >
                                  by {e.user_id}
                                </span>
                              </div>
                              {e.created_at && (
                                <div className="timeline-time">
                                  {new Date(e.created_at).toLocaleString()}
                                </div>
                              )}
                              {e.payload_json && Object.keys(e.payload_json).length > 0 && (
                                <div
                                  className="timeline-desc"
                                  style={{ fontFamily: "monospace", marginTop: "0.35rem" }}
                                >
                                  {Object.entries(e.payload_json)
                                    .map(([k, v]) => `${k}: ${String(v)}`)
                                    .join(" · ")}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </FadeIn>
      )}
    </PageShell>
  );
}
