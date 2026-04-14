"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  getQualityDashboard,
  resolveContradiction,
  resolveEdgeCase,
  acceptEdgeCaseSuggestion,
  acceptContradictionSuggestion,
  bulkAcceptEdgeCases,
  bulkResolveEdgeCases,
  bulkAcceptContradictions,
  bulkResolveContradictions,
} from "@/lib/api";
import type { QualityDashboardResponse, ComplianceTag } from "@/lib/api";
import {
  PageShell,
  KpiCard,
  Tabs,
  QualityGauge,
  ScoreBar,
  FadeIn,
  StaggerList,
  StaggerItem,
} from "@/components/index";
import Badge from "@/components/Badge";
import EmptyState from "@/components/EmptyState";
import { motion, AnimatePresence } from "framer-motion";
import {
  BarChart3,
  GitCompare,
  AlertTriangle,
  Tag,
  CheckCircle2,
  ChevronDown,
  Shield,
  CreditCard,
  Lock,
  Database,
  Globe,
  Key,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const severityStyle: Record<
  string,
  { color: string; bg: string; border: string }
> = {
  HIGH: { color: "#ef4444", bg: "#ef444418", border: "#ef444444" },
  MEDIUM: { color: "#f59e0b", bg: "#f59e0b18", border: "#f59e0b44" },
  LOW: { color: "#3b82f6", bg: "#3b82f618", border: "#3b82f644" },
};

const complianceLabels: Record<string, string> = {
  payments: "Payments",
  auth: "Authentication",
  pii: "PII",
  external_api: "External API",
  security: "Security",
  data_retention: "Data Retention",
};

const complianceIcons: Record<string, LucideIcon> = {
  payments: CreditCard,
  auth: Key,
  pii: Shield,
  external_api: Globe,
  security: Lock,
  data_retention: Database,
};

function sectionRef(index: number) {
  return `Section ${index + 1}`;
}

function severityVariant(
  level: string
): "error" | "warning" | "info" {
  if (level === "HIGH") return "error";
  if (level === "LOW") return "info";
  return "warning";
}

export default function QualityDashboardPage() {
  const params = useParams();
  const docId = params.id as string;
  const [dashboard, setDashboard] = useState<QualityDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"contradictions" | "edge_cases" | "compliance">(
    "contradictions"
  );

  const fetchDashboard = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await getQualityDashboard(docId);
      setDashboard(result.data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load quality dashboard");
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    if (docId) fetchDashboard();
  }, [docId, fetchDashboard]);

  const handleResolveContradiction = async (contradictionId: string) => {
    try {
      await resolveContradiction(docId, contradictionId);
      setDashboard((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          contradictions: prev.contradictions.map((c) =>
            c.id === contradictionId ? { ...c, resolved: true } : c
          ),
        };
      });
      fetchDashboard();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to resolve");
    }
  };

  const handleResolveEdgeCase = async (edgeCaseId: string) => {
    try {
      await resolveEdgeCase(docId, edgeCaseId);
      setDashboard((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          edge_cases: prev.edge_cases.map((e) =>
            e.id === edgeCaseId ? { ...e, resolved: true } : e
          ),
        };
      });
      fetchDashboard();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to resolve");
    }
  };

  const handleAcceptEdgeCase = async (edgeCaseId: string) => {
    try {
      await acceptEdgeCaseSuggestion(docId, edgeCaseId);
      setDashboard((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          edge_cases: prev.edge_cases.map((e) =>
            e.id === edgeCaseId ? { ...e, resolved: true } : e
          ),
        };
      });
      fetchDashboard();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to accept suggestion");
    }
  };

  const handleAcceptContradiction = async (contradictionId: string) => {
    try {
      await acceptContradictionSuggestion(docId, contradictionId);
      setDashboard((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          contradictions: prev.contradictions.map((c) =>
            c.id === contradictionId ? { ...c, resolved: true } : c
          ),
        };
      });
      fetchDashboard();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to accept resolution");
    }
  };

  const [bulkLoading, setBulkLoading] = useState(false);

  const handleBulkAcceptEdgeCases = async () => {
    setBulkLoading(true);
    try {
      await bulkAcceptEdgeCases(docId);
      await fetchDashboard();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Bulk accept failed");
    } finally {
      setBulkLoading(false);
    }
  };

  const handleBulkResolveEdgeCases = async () => {
    setBulkLoading(true);
    try {
      await bulkResolveEdgeCases(docId);
      await fetchDashboard();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Bulk resolve failed");
    } finally {
      setBulkLoading(false);
    }
  };

  const handleBulkAcceptContradictions = async () => {
    setBulkLoading(true);
    try {
      await bulkAcceptContradictions(docId);
      await fetchDashboard();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Bulk accept failed");
    } finally {
      setBulkLoading(false);
    }
  };

  const handleBulkResolveContradictions = async () => {
    setBulkLoading(true);
    try {
      await bulkResolveContradictions(docId);
      await fetchDashboard();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Bulk resolve failed");
    } finally {
      setBulkLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        Loading quality dashboard…
      </div>
    );
  }

  if (error || !dashboard) {
    return (
      <PageShell backHref={`/documents/${docId}`} title="Quality Dashboard" maxWidth={960}>
        <FadeIn>
          <EmptyStateWrap
            title="Unable to load dashboard"
            description={error || "Run analysis first to see quality metrics."}
            docId={docId}
          />
        </FadeIn>
      </PageShell>
    );
  }

  const { quality_score, contradictions, edge_cases, compliance_tags } = dashboard;

  const tagGroups: Record<string, ComplianceTag[]> = {};
  for (const ct of compliance_tags) {
    if (!tagGroups[ct.tag]) tagGroups[ct.tag] = [];
    tagGroups[ct.tag].push(ct);
  }

  const tabItems = [
    { key: "contradictions", label: "Contradictions", count: contradictions.length },
    { key: "edge_cases", label: "Edge Cases", count: edge_cases.length },
    { key: "compliance", label: "Compliance", count: compliance_tags.length },
  ];

  return (
    <PageShell
      backHref={`/documents/${docId}`}
      title="Quality Dashboard"
      subtitle={`${dashboard.filename} — Deep analysis results`}
      maxWidth={960}
    >
      <StaggerList className="quality-dashboard-stagger">
        <StaggerItem>
          <FadeIn>
            <div className="section-card" style={{ marginBottom: "1.5rem" }}>
              <div className="section-card-header">
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <BarChart3 size={18} aria-hidden />
                  Scores
                </span>
              </div>
              <div className="section-card-body">
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: "1.5rem",
                    alignItems: "center",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      minHeight: 200,
                    }}
                  >
                    <QualityGauge
                      score={quality_score.overall}
                      size={180}
                      label="Overall Quality"
                    />
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                    <ScoreBar label="Completeness" value={quality_score.completeness} />
                    <ScoreBar label="Clarity" value={quality_score.clarity} />
                    <ScoreBar label="Consistency" value={quality_score.consistency} />
                  </div>
                </div>
              </div>
            </div>
          </FadeIn>
        </StaggerItem>

        <StaggerItem>
          <FadeIn delay={0.05}>
            <div className="kpi-row">
              <KpiCard
                label="Contradictions"
                value={contradictions.length}
                icon={<GitCompare size={22} strokeWidth={2} aria-hidden />}
                iconBg={contradictions.length > 0 ? "var(--well-red)" : "var(--well-green)"}
                delay={0}
              />
              <KpiCard
                label="Edge Case Gaps"
                value={edge_cases.length}
                icon={<AlertTriangle size={22} strokeWidth={2} aria-hidden />}
                iconBg={edge_cases.length > 0 ? "var(--well-amber)" : "var(--well-green)"}
                delay={0.05}
              />
              <KpiCard
                label="Compliance Tags"
                value={compliance_tags.length}
                icon={<Tag size={22} strokeWidth={2} aria-hidden />}
                iconBg="var(--well-blue)"
                delay={0.1}
              />
            </div>
          </FadeIn>
        </StaggerItem>

        {compliance_tags.length > 0 && (
          <StaggerItem>
            <FadeIn delay={0.1}>
              <div className="section-card" style={{ marginBottom: "1.5rem" }}>
                <div className="section-card-header">
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Tag size={18} aria-hidden />
                    Compliance Areas
                  </span>
                  <ChevronDown size={16} style={{ opacity: 0.45 }} aria-hidden />
                </div>
                <div className="section-card-body">
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {Object.entries(tagGroups).map(([tag, items]) => {
                      const label = complianceLabels[tag] ?? tag.replace(/_/g, " ");
                      return (
                        <Badge key={tag} variant="neutral" className="compliance-tag-pill">
                          {label}
                          <span style={{ opacity: 0.85, fontWeight: 700 }}>{items.length}</span>
                        </Badge>
                      );
                    })}
                  </div>
                </div>
              </div>
            </FadeIn>
          </StaggerItem>
        )}

        <StaggerItem>
          <FadeIn delay={0.12}>
            <Tabs
              items={tabItems}
              active={activeTab}
              onChange={(key) =>
                setActiveTab(key as "contradictions" | "edge_cases" | "compliance")
              }
              className="quality-tabs"
            />
            <div style={{ marginTop: "1.25rem" }}>
              <AnimatePresence mode="wait">
                {activeTab === "contradictions" && (
                  <motion.div
                    key="contradictions"
                    role="tabpanel"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.2 }}
                  >
                    {contradictions.length === 0 ? (
                      <EmptyState
                        icon={<CheckCircle2 size={40} strokeWidth={1.5} aria-hidden />}
                        title="No contradictions detected"
                        description="All sections are consistent with each other."
                      />
                    ) : (
                      <>
                        {contradictions.some((c) => !c.resolved) && (
                          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
                            <button type="button" className="btn btn-sm btn-primary" onClick={handleBulkAcceptContradictions} disabled={bulkLoading}>
                              {bulkLoading ? "Processing…" : "Accept All Resolutions"}
                            </button>
                            <button type="button" className="btn btn-sm btn-success" onClick={handleBulkResolveContradictions} disabled={bulkLoading}>
                              {bulkLoading ? "Processing…" : "Mark All Resolved"}
                            </button>
                          </div>
                        )}
                      <StaggerList>
                        {contradictions.map((c) => {
                          const sev = severityStyle[c.severity] ?? severityStyle.MEDIUM;
                          return (
                            <StaggerItem key={c.id ?? `${c.section_a_index}-${c.section_b_index}`}>
                              <div
                                className="card card-flat quality-issue-card"
                                style={{
                                  marginBottom: "0.75rem",
                                  borderLeft: `4px solid ${c.resolved ? "var(--success)" : sev.color}`,
                                  borderColor: c.resolved ? "var(--border-subtle)" : sev.border,
                                  opacity: c.resolved ? 0.72 : 1,
                                }}
                              >
                                <div
                                  style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "flex-start",
                                    gap: 12,
                                    marginBottom: 12,
                                    flexWrap: "wrap",
                                  }}
                                >
                                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                                    <Badge variant={severityVariant(c.severity)}>{c.severity}</Badge>
                                    <span
                                      style={{
                                        fontSize: "0.8125rem",
                                        color: "var(--text-muted)",
                                        fontWeight: 500,
                                      }}
                                    >
                                      {sectionRef(c.section_a_index)} ↔ {sectionRef(c.section_b_index)}
                                    </span>
                                  </div>
                                  {c.resolved ? (
                                    <Badge variant="success">
                                      <CheckCircle2 size={12} aria-hidden />
                                      Resolved
                                    </Badge>
                                  ) : (
                                    c.id && (
                                      <div style={{ display: "flex", gap: "0.35rem", flexShrink: 0 }}>
                                        {c.suggested_resolution && (
                                          <button
                                            type="button"
                                            className="btn btn-sm btn-primary"
                                            onClick={() => handleAcceptContradiction(c.id!)}
                                          >
                                            Accept resolution
                                          </button>
                                        )}
                                        <button
                                          type="button"
                                          className="btn btn-sm btn-success"
                                          onClick={() => handleResolveContradiction(c.id!)}
                                        >
                                          Mark resolved
                                        </button>
                                      </div>
                                    )
                                  )}
                                </div>

                                <div
                                  style={{
                                    display: "grid",
                                    gridTemplateColumns: "1fr 1fr",
                                    gap: 10,
                                    marginBottom: 12,
                                  }}
                                >
                                  <div
                                    style={{
                                      background: "var(--bg-tertiary)",
                                      padding: "10px 14px",
                                      borderRadius: "var(--radius-md)",
                                      borderLeft: "3px solid var(--accent-primary)",
                                    }}
                                  >
                                    <div
                                      style={{
                                        fontSize: "0.6875rem",
                                        color: "var(--text-muted)",
                                        fontWeight: 600,
                                        textTransform: "uppercase",
                                        letterSpacing: "0.06em",
                                        marginBottom: 4,
                                      }}
                                    >
                                      Section A
                                    </div>
                                    <div
                                      style={{
                                        fontSize: "0.875rem",
                                        fontWeight: 600,
                                        color: "var(--text-primary)",
                                      }}
                                    >
                                      {sectionRef(c.section_a_index)} · {c.section_a_heading}
                                    </div>
                                  </div>
                                  <div
                                    style={{
                                      background: "var(--bg-tertiary)",
                                      padding: "10px 14px",
                                      borderRadius: "var(--radius-md)",
                                      borderLeft: "3px solid var(--accent-secondary, #a855f7)",
                                    }}
                                  >
                                    <div
                                      style={{
                                        fontSize: "0.6875rem",
                                        color: "var(--text-muted)",
                                        fontWeight: 600,
                                        textTransform: "uppercase",
                                        letterSpacing: "0.06em",
                                        marginBottom: 4,
                                      }}
                                    >
                                      Section B
                                    </div>
                                    <div
                                      style={{
                                        fontSize: "0.875rem",
                                        fontWeight: 600,
                                        color: "var(--text-primary)",
                                      }}
                                    >
                                      {sectionRef(c.section_b_index)} · {c.section_b_heading}
                                    </div>
                                  </div>
                                </div>

                                <p
                                  style={{
                                    fontSize: "0.875rem",
                                    color: "var(--text-secondary)",
                                    lineHeight: 1.6,
                                    marginBottom: 10,
                                  }}
                                >
                                  <strong>Conflict:</strong> {c.description}
                                </p>

                                <div
                                  style={{
                                    background: "var(--bg-success-subtle)",
                                    padding: "10px 14px",
                                    borderRadius: "var(--radius-md)",
                                    fontSize: "0.8125rem",
                                    lineHeight: 1.6,
                                    color: "var(--success)",
                                    fontWeight: 500,
                                  }}
                                >
                                  {c.suggested_resolution}
                                </div>
                              </div>
                            </StaggerItem>
                          );
                        })}
                      </StaggerList>
                      </>
                    )}
                  </motion.div>
                )}

                {activeTab === "edge_cases" && (
                  <motion.div
                    key="edge_cases"
                    role="tabpanel"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.2 }}
                  >
                    {edge_cases.length === 0 ? (
                      <EmptyState
                        icon={<CheckCircle2 size={40} strokeWidth={1.5} aria-hidden />}
                        title="No edge case gaps detected"
                        description="All scenarios appear to be well-covered."
                      />
                    ) : (
                      <>
                        {edge_cases.some((ec) => !ec.resolved) && (
                          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
                            <button type="button" className="btn btn-sm btn-primary" onClick={handleBulkAcceptEdgeCases} disabled={bulkLoading}>
                              {bulkLoading ? "Processing…" : "Accept All Suggestions"}
                            </button>
                            <button type="button" className="btn btn-sm btn-success" onClick={handleBulkResolveEdgeCases} disabled={bulkLoading}>
                              {bulkLoading ? "Processing…" : "Mark All Resolved"}
                            </button>
                          </div>
                        )}
                      <StaggerList>
                        {edge_cases.map((ec) => {
                          const sev = severityStyle[ec.impact] ?? severityStyle.MEDIUM;
                          return (
                            <StaggerItem key={ec.id ?? `${ec.section_index}-${ec.scenario_description.slice(0, 24)}`}>
                              <div
                                className="card card-flat quality-issue-card"
                                style={{
                                  marginBottom: "0.75rem",
                                  borderLeft: `4px solid ${ec.resolved ? "var(--success)" : sev.color}`,
                                  borderColor: ec.resolved ? "var(--border-subtle)" : sev.border,
                                  opacity: ec.resolved ? 0.72 : 1,
                                }}
                              >
                                <div
                                  style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "flex-start",
                                    gap: 12,
                                    marginBottom: 12,
                                    flexWrap: "wrap",
                                  }}
                                >
                                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                                    <Badge variant={severityVariant(ec.impact)}>{ec.impact} impact</Badge>
                                    <span
                                      style={{
                                        fontSize: "0.8125rem",
                                        color: "var(--text-muted)",
                                        fontWeight: 500,
                                      }}
                                    >
                                      {sectionRef(ec.section_index)} · {ec.section_heading}
                                    </span>
                                  </div>
                                  {ec.resolved ? (
                                    <Badge variant="success">
                                      <CheckCircle2 size={12} aria-hidden />
                                      Resolved
                                    </Badge>
                                  ) : (
                                    ec.id && (
                                      <div style={{ display: "flex", gap: "0.35rem", flexShrink: 0 }}>
                                        {ec.suggested_addition && (
                                          <button
                                            type="button"
                                            className="btn btn-sm btn-primary"
                                            onClick={() => handleAcceptEdgeCase(ec.id!)}
                                          >
                                            Accept suggestion
                                          </button>
                                        )}
                                        <button
                                          type="button"
                                          className="btn btn-sm btn-success"
                                          onClick={() => handleResolveEdgeCase(ec.id!)}
                                        >
                                          Mark resolved
                                        </button>
                                      </div>
                                    )
                                  )}
                                </div>

                                <p
                                  style={{
                                    fontSize: "0.875rem",
                                    color: "var(--text-secondary)",
                                    lineHeight: 1.6,
                                    marginBottom: 10,
                                  }}
                                >
                                  <strong>Missing scenario:</strong> {ec.scenario_description}
                                </p>

                                <div
                                  style={{
                                    background: "var(--bg-accent-subtle)",
                                    padding: "10px 14px",
                                    borderRadius: "var(--radius-md)",
                                    fontSize: "0.8125rem",
                                    lineHeight: 1.6,
                                    color: "var(--accent-primary)",
                                    fontWeight: 500,
                                  }}
                                >
                                  {ec.suggested_addition}
                                </div>
                              </div>
                            </StaggerItem>
                          );
                        })}
                      </StaggerList>
                      </>
                    )}
                  </motion.div>
                )}

                {activeTab === "compliance" && (
                  <motion.div
                    key="compliance"
                    role="tabpanel"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.2 }}
                  >
                    {compliance_tags.length === 0 ? (
                      <EmptyState
                        icon={<Tag size={40} strokeWidth={1.5} aria-hidden />}
                        title="No compliance areas detected"
                        description="No sections flagged for payments, auth, PII, or external APIs."
                      />
                    ) : (
                      <StaggerList>
                        {Object.entries(tagGroups).map(([tag, items]) => {
                          const Icon = complianceIcons[tag] ?? Shield;
                          const label = complianceLabels[tag] ?? tag.replace(/_/g, " ");
                          return (
                            <StaggerItem key={tag}>
                              <div style={{ marginBottom: "1.25rem" }}>
                                <div
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 10,
                                    marginBottom: 12,
                                    flexWrap: "wrap",
                                  }}
                                >
                                  <Icon size={18} aria-hidden style={{ color: "var(--accent-primary)" }} />
                                  <h3
                                    style={{
                                      fontSize: "0.9375rem",
                                      fontWeight: 700,
                                      margin: 0,
                                      color: "var(--text-primary)",
                                    }}
                                  >
                                    {label}
                                  </h3>
                                  <Badge variant="neutral">{items.length}</Badge>
                                </div>
                                <StaggerList>
                                  {items.map((ct) => (
                                    <StaggerItem key={ct.id ?? `${tag}-${ct.section_index}`}>
                                      <div
                                        className="card card-flat"
                                        style={{
                                          marginBottom: 8,
                                          borderLeft: "3px solid var(--accent-primary)",
                                        }}
                                      >
                                        <div
                                          style={{
                                            fontSize: "0.8125rem",
                                            fontWeight: 600,
                                            marginBottom: 6,
                                            color: "var(--text-primary)",
                                          }}
                                        >
                                          {sectionRef(ct.section_index)} · {ct.section_heading}
                                        </div>
                                        <div
                                          style={{
                                            fontSize: "0.8125rem",
                                            color: "var(--text-secondary)",
                                            lineHeight: 1.5,
                                          }}
                                        >
                                          {ct.reason}
                                        </div>
                                      </div>
                                    </StaggerItem>
                                  ))}
                                </StaggerList>
                              </div>
                            </StaggerItem>
                          );
                        })}
                      </StaggerList>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </FadeIn>
        </StaggerItem>
      </StaggerList>
    </PageShell>
  );
}

function EmptyStateWrap({
  title,
  description,
  docId,
}: {
  title: string;
  description: string;
  docId: string;
}) {
  return (
    <EmptyState
      icon={<BarChart3 size={40} strokeWidth={1.5} aria-hidden />}
      title={title}
      description={description}
      action={
        <Link href={`/documents/${docId}`} className="btn btn-secondary btn-sm">
          Back to document
        </Link>
      }
    />
  );
}
