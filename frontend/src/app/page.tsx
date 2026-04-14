"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  Award,
  Boxes,
  CheckCircle2,
  Clock,
  FileText,
  GitCompare,
  ListTodo,
  Loader2,
  ScanSearch,
  Upload,
  FolderOpen,
} from "lucide-react";
import {
  FadeIn,
  KpiCard,
  PageMotion,
  StaggerItem,
  StaggerList,
  StatusBadge,
} from "@/components/index";
import { listDocuments, type FSDocumentResponse } from "@/lib/api";

const STATUS_BORDER: Record<string, string> = {
  UPLOADED: "var(--info)",
  PARSING: "var(--warning)",
  PARSED: "var(--success)",
  ANALYZING: "var(--warning)",
  COMPLETE: "var(--success)",
  ERROR: "var(--error)",
  PARSE_FAILED: "var(--error)",
};

const FEATURES = [
  {
    title: "Ambiguity Detection",
    description:
      "Surface vague or incomplete requirements with AI-assisted clarification prompts.",
    icon: ScanSearch,
    well: "var(--well-blue)" as const,
  },
  {
    title: "Contradiction Finder",
    description:
      "Cross-check sections to flag conflicting statements before they reach development.",
    icon: GitCompare,
    well: "var(--well-peach)" as const,
  },
  {
    title: "Edge Case Analysis",
    description:
      "Identify missing scenarios and gaps so acceptance criteria hold up in production.",
    icon: AlertTriangle,
    well: "var(--well-amber)" as const,
  },
  {
    title: "Task Decomposition",
    description:
      "Break functional specs into structured, traceable work items ready for delivery.",
    icon: ListTodo,
    well: "var(--well-purple)" as const,
  },
  {
    title: "Quality Scoring",
    description:
      "Quantify completeness, clarity, and consistency to prioritize spec hardening.",
    icon: Award,
    well: "var(--well-green)" as const,
  },
  {
    title: "Autonomous Build",
    description:
      "Orchestrate analysis, refinement, and build steps through an automated pipeline.",
    icon: Boxes,
    well: "var(--well-gray)" as const,
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
  if (bytes == null || bytes === 0) return "—";
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function recentUploadsCount(docs: FSDocumentResponse[]): number {
  const cutoff = Date.now() - 7 * 24 * 3600000;
  return docs.filter((d) => new Date(d.created_at).getTime() >= cutoff).length;
}

export default function HomePage() {
  const [docs, setDocs] = useState<FSDocumentResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listDocuments()
      .then((res) => setDocs(res.data?.documents ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const sortedRecent = useMemo(() => {
    return [...docs].sort(
      (a, b) =>
        new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );
  }, [docs]);

  const stats = useMemo(() => {
    const complete = docs.filter((d) => d.status === "COMPLETE").length;
    const analyzing = docs.filter((d) => d.status === "ANALYZING").length;
    const recent = recentUploadsCount(docs);
    return {
      total: docs.length,
      complete,
      analyzing,
      recent,
    };
  }, [docs]);

  return (
    <PageMotion>
      <section className="hero" id="hero-section">
        <div className="hero-badge">Functional specification intelligence</div>
        <h1>
          FS <span className="gradient-text">Intelligence</span> Platform
        </h1>
        <p className="hero-subtitle">
          Upload functional specs, run deep analysis, and move from ambiguous
          prose to structured tasks, quality scores, and build-ready output.
        </p>
        <div className="hero-actions">
          <Link href="/upload" className="btn btn-primary" id="hero-upload-btn">
            <Upload size={20} />
            Upload FS
          </Link>
          <Link
            href="/documents"
            className="btn btn-secondary"
            id="hero-docs-btn"
          >
            <FolderOpen size={20} />
            View Documents
          </Link>
        </div>
      </section>

      {!loading && docs.length > 0 && (
        <FadeIn delay={0.08}>
          <div className="kpi-row" id="dashboard-stats">
            <KpiCard
              label="Total Documents"
              value={stats.total}
              icon={<FileText size={20} />}
              iconBg="var(--well-blue)"
              delay={0}
            />
            <KpiCard
              label="Complete"
              value={stats.complete}
              icon={<CheckCircle2 size={20} />}
              iconBg="var(--well-green)"
              delay={0.05}
            />
            <KpiCard
              label="Analyzing"
              value={stats.analyzing}
              icon={<Loader2 size={20} />}
              iconBg="var(--well-amber)"
              delay={0.1}
            />
            <KpiCard
              label="Recent uploads"
              value={stats.recent}
              icon={<Clock size={20} />}
              iconBg="var(--well-peach)"
              delay={0.15}
            />
          </div>
        </FadeIn>
      )}

      {!loading && docs.length > 0 && (
        <FadeIn delay={0.14}>
          <div className="documents-header">
            <h2 className="page-title" style={{ fontSize: "1.25rem" }}>
              Recent documents
            </h2>
            <Link href="/documents" className="btn btn-secondary btn-sm">
              View all
            </Link>
          </div>
          <div
            style={{
              display: "flex",
              gap: "1rem",
              overflowX: "auto",
              paddingBottom: "0.25rem",
              marginBottom: "1.5rem",
              scrollbarGutter: "stable",
            }}
          >
            {sortedRecent.slice(0, 6).map((doc, i) => {
              const border =
                STATUS_BORDER[doc.status] ?? "var(--border-strong)";
              return (
                <motion.div
                  key={doc.id}
                  initial={{ opacity: 0, x: 16 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{
                    duration: 0.3,
                    delay: 0.12 + i * 0.04,
                    ease: [0.4, 0, 0.2, 1],
                  }}
                  style={{ flex: "0 0 auto", minWidth: "min(280px, 85vw)" }}
                >
                  <Link
                    href={`/documents/${doc.id}`}
                    className="card doc-card"
                    id={`doc-card-${doc.id.substring(0, 8)}`}
                    style={{
                      borderLeft: `3px solid ${border}`,
                      flexDirection: "column",
                      alignItems: "stretch",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: "1rem",
                        width: "100%",
                      }}
                    >
                      <div className="doc-icon">
                        <FileText size={20} />
                      </div>
                      <div className="doc-info" style={{ minWidth: 0, flex: 1 }}>
                        <div className="doc-name">{doc.filename}</div>
                        <div style={{ marginTop: "0.5rem" }}>
                          <StatusBadge status={doc.status} />
                        </div>
                      </div>
                    </div>
                    <div
                      className="doc-meta"
                      style={{ marginTop: "0.75rem", paddingLeft: "58px" }}
                    >
                      <span>{formatSize(doc.file_size)}</span>
                      <span>{formatDate(doc.updated_at)}</span>
                    </div>
                  </Link>
                </motion.div>
              );
            })}
          </div>
        </FadeIn>
      )}

      <FadeIn delay={0.2}>
        <h2
          className="page-title"
          style={{
            fontSize: "1.25rem",
            marginBottom: "1rem",
            textAlign: "center",
          }}
        >
          Capabilities
        </h2>
        <div id="features-section">
          <StaggerList className="feature-grid">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <StaggerItem key={f.title}>
                  <div className="card feature-card">
                    <div
                      className="feature-icon"
                      style={{
                        background: f.well,
                        color: "var(--accent-primary)",
                      }}
                    >
                      <Icon size={20} />
                    </div>
                    <h3>{f.title}</h3>
                    <p>{f.description}</p>
                  </div>
                </StaggerItem>
              );
            })}
          </StaggerList>
        </div>
      </FadeIn>
    </PageMotion>
  );
}
