"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listDocuments } from "@/lib/api";

interface DocSummary {
  id: string;
  filename: string;
  status: string;
  file_size: number | null;
  created_at: string;
  updated_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  UPLOADED: "#6366f1",
  PARSING: "#f59e0b",
  PARSED: "#10b981",
  ANALYZING: "#3b82f6",
  COMPLETE: "#10b981",
  ERROR: "#ef4444",
  PARSE_FAILED: "#ef4444",
};

const STATUS_ICONS: Record<string, string> = {
  UPLOADED: "⬆",
  PARSING: "⏳",
  PARSED: "📄",
  ANALYZING: "🔍",
  COMPLETE: "✅",
  ERROR: "❌",
  PARSE_FAILED: "❌",
};

const FEATURES = [
  {
    icon: "🔍",
    title: "Ambiguity Detection",
    description:
      "AI-powered detection of vague, contradictory, or incomplete requirements.",
  },
  {
    icon: "📋",
    title: "Task Decomposition",
    description:
      "Automatically break specs into developer-ready task lists with effort estimates.",
  },
  {
    icon: "⚡",
    title: "Change Impact Analysis",
    description:
      "Instantly understand what breaks when a spec changes — trace impacts everywhere.",
  },
  {
    icon: "🔗",
    title: "Full Traceability",
    description:
      "Requirements → Tasks → Test Cases — complete traceability with export.",
  },
  {
    icon: "📤",
    title: "JIRA & Confluence Export",
    description:
      "One-click export to JIRA (epic + stories) and Confluence documentation pages.",
  },
  {
    icon: "🤝",
    title: "Team Collaboration",
    description:
      "Comments, @mentions, approval workflows, and full audit trail.",
  },
];

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "Just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatSize(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export default function DashboardPage() {
  const [docs, setDocs] = useState<DocSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listDocuments()
      .then((res) => setDocs(res.data?.documents || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const statCounts = {
    total: docs.length,
    complete: docs.filter((d) => d.status === "COMPLETE").length,
    inProgress: docs.filter((d) =>
      ["UPLOADED", "PARSING", "PARSED", "ANALYZING"].includes(d.status)
    ).length,
    errors: docs.filter((d) => ["ERROR", "PARSE_FAILED"].includes(d.status)).length,
  };

  return (
    <>
      <section className="hero" id="hero-section">
        <div className="hero-badge">◈ AI-Powered FS Intelligence</div>
        <h1>
          Turn your <span className="gradient-text">Functional Specs</span>
          <br />
          into dev-ready tasks
        </h1>
        <p className="hero-subtitle">
          Bridge the gap between functional teams and developers. Detect
          ambiguities, decompose tasks, generate test cases, and export to
          JIRA — all powered by advanced AI.
        </p>
        <div className="hero-actions">
          <Link href="/upload" className="btn btn-primary" id="hero-upload-btn">
            ⬆ Upload FS Document
          </Link>
          <Link
            href="/documents"
            className="btn btn-secondary"
            id="hero-docs-btn"
          >
            📄 View Documents
          </Link>
          <Link
            href="/reverse"
            className="btn btn-secondary"
            id="hero-reverse-btn"
          >
            🔄 Reverse Generate FS
          </Link>
          <Link
            href="/monitoring"
            className="btn btn-secondary"
            id="hero-monitoring-btn"
          >
            📡 Live MCP Monitoring
          </Link>
        </div>
      </section>

      {/* Dashboard Stats */}
      {!loading && docs.length > 0 && (
        <section
          id="dashboard-stats"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: "1rem",
            marginBottom: "2.5rem",
          }}
        >
          <div className="card" style={{ textAlign: "center", padding: "1.5rem" }}>
            <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--color-primary)" }}>
              {statCounts.total}
            </div>
            <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Total Documents</div>
          </div>
          <div className="card" style={{ textAlign: "center", padding: "1.5rem" }}>
            <div style={{ fontSize: "2rem", fontWeight: 700, color: "#10b981" }}>
              {statCounts.complete}
            </div>
            <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Analyzed</div>
          </div>
          <div className="card" style={{ textAlign: "center", padding: "1.5rem" }}>
            <div style={{ fontSize: "2rem", fontWeight: 700, color: "#3b82f6" }}>
              {statCounts.inProgress}
            </div>
            <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>In Progress</div>
          </div>
          <div className="card" style={{ textAlign: "center", padding: "1.5rem" }}>
            <div style={{ fontSize: "2rem", fontWeight: 700, color: statCounts.errors > 0 ? "#ef4444" : "var(--text-muted)" }}>
              {statCounts.errors}
            </div>
            <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Errors</div>
          </div>
        </section>
      )}

      {/* Recent Documents */}
      {!loading && docs.length > 0 && (
        <section style={{ marginBottom: "2.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <h2 style={{ margin: 0, fontSize: "1.3rem" }}>📄 Recent Documents</h2>
            <Link href="/documents" className="btn btn-sm" style={{ fontSize: "0.8rem" }}>
              View All →
            </Link>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "1rem" }}>
            {docs.slice(0, 6).map((doc) => {
              const color = STATUS_COLORS[doc.status] || "#6b7280";
              const icon = STATUS_ICONS[doc.status] || "📄";
              return (
                <Link
                  key={doc.id}
                  href={`/documents/${doc.id}`}
                  style={{ textDecoration: "none", color: "inherit" }}
                >
                  <div
                    className="card"
                    id={`doc-card-${doc.id.substring(0, 8)}`}
                    style={{
                      cursor: "pointer",
                      transition: "all 0.2s ease",
                      borderLeft: `3px solid ${color}`,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                      <h4 style={{ margin: 0, fontSize: "0.95rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "70%" }}>
                        {doc.filename}
                      </h4>
                      <span
                        style={{
                          fontSize: "0.7rem",
                          padding: "2px 8px",
                          borderRadius: "12px",
                          background: `${color}22`,
                          color: color,
                          fontWeight: 600,
                        }}
                      >
                        {icon} {doc.status}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      <span>{formatSize(doc.file_size)}</span>
                      <span>{formatDate(doc.updated_at)}</span>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </section>
      )}

      <section className="feature-grid" id="features-section">
        {FEATURES.map((f, i) => (
          <div className="card feature-card" key={i}>
            <div className="feature-icon">{f.icon}</div>
            <h3>{f.title}</h3>
            <p>{f.description}</p>
          </div>
        ))}
      </section>
    </>
  );
}
