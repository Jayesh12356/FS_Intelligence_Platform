"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  getQualityDashboard,
  resolveContradiction,
  resolveEdgeCase,
} from "@/lib/api";
import type {
  QualityDashboardResponse,
  ComplianceTag,
} from "@/lib/api";

// ── Config ─────────────────────────────────────────────

const severityConfig = {
  HIGH: { color: "#ef4444", bg: "#ef444418", label: "🔴 HIGH", border: "#ef444444" },
  MEDIUM: { color: "#f59e0b", bg: "#f59e0b18", label: "🟡 MEDIUM", border: "#f59e0b44" },
  LOW: { color: "#3b82f6", bg: "#3b82f618", label: "🔵 LOW", border: "#3b82f644" },
};

const complianceColors: Record<string, { bg: string; color: string; border: string }> = {
  payments: { bg: "#22c55e18", color: "#22c55e", border: "#22c55e44" },
  auth: { bg: "#6366f118", color: "#6366f1", border: "#6366f144" },
  pii: { bg: "#ef444418", color: "#ef4444", border: "#ef444444" },
  external_api: { bg: "#f59e0b18", color: "#f59e0b", border: "#f59e0b44" },
  security: { bg: "#ec489918", color: "#ec4899", border: "#ec489944" },
  data_retention: { bg: "#8b5cf618", color: "#8b5cf6", border: "#8b5cf644" },
};

const complianceLabels: Record<string, string> = {
  payments: "💳 Payments",
  auth: "🔐 Auth",
  pii: "🛡️ PII",
  external_api: "🔗 External API",
  security: "🔒 Security",
  data_retention: "📦 Data Retention",
};

// ── Quality Gauge Component ────────────────────────────

function QualityGauge({ score, label }: { score: number; label: string }) {
  const getColor = (s: number) => {
    if (s >= 80) return "#22c55e";
    if (s >= 60) return "#f59e0b";
    return "#ef4444";
  };

  const color = getColor(score);
  const circumference = 2 * Math.PI * 54;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ position: "relative", width: "140px", height: "140px", margin: "0 auto" }}>
        <svg viewBox="0 0 120 120" width="140" height="140">
          {/* Background circle */}
          <circle
            cx="60"
            cy="60"
            r="54"
            fill="none"
            stroke="var(--bg-tertiary)"
            strokeWidth="8"
          />
          {/* Progress circle */}
          <circle
            cx="60"
            cy="60"
            r="54"
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            transform="rotate(-90 60 60)"
            style={{ transition: "stroke-dashoffset 1s ease, stroke 0.5s ease" }}
          />
        </svg>
        <div style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          textAlign: "center",
        }}>
          <div style={{
            fontSize: "2rem",
            fontWeight: 800,
            color: color,
            lineHeight: 1,
          }}>
            {Math.round(score)}
          </div>
          <div style={{
            fontSize: "0.65rem",
            color: "var(--text-muted)",
            fontWeight: 600,
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            marginTop: "2px",
          }}>
            / 100
          </div>
        </div>
      </div>
      <div style={{
        marginTop: "8px",
        fontSize: "0.85rem",
        fontWeight: 600,
        color: "var(--text-secondary)",
      }}>
        {label}
      </div>
    </div>
  );
}

// ── Sub Score Bar Component ────────────────────────────

function SubScoreBar({ label, score, icon }: { label: string; score: number; icon: string }) {
  const getColor = (s: number) => {
    if (s >= 80) return "#22c55e";
    if (s >= 60) return "#f59e0b";
    return "#ef4444";
  };

  const color = getColor(score);

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-subtle)",
      borderRadius: "12px",
      padding: "16px 20px",
    }}>
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "10px",
      }}>
        <span style={{
          fontSize: "0.88rem",
          fontWeight: 600,
          color: "var(--text-primary)",
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}>
          {icon} {label}
        </span>
        <span style={{
          fontSize: "1.1rem",
          fontWeight: 700,
          color: color,
        }}>
          {score.toFixed(1)}%
        </span>
      </div>
      <div style={{
        height: "6px",
        background: "var(--bg-tertiary)",
        borderRadius: "3px",
        overflow: "hidden",
      }}>
        <div style={{
          height: "100%",
          width: `${Math.min(score, 100)}%`,
          background: color,
          borderRadius: "3px",
          transition: "width 0.8s ease",
        }} />
      </div>
    </div>
  );
}

// ── Resolve Button Component ───────────────────────────

function ResolveButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "4px 14px",
        borderRadius: "6px",
        fontSize: "0.78rem",
        fontWeight: 600,
        background: "rgba(34, 197, 94, 0.1)",
        color: "#22c55e",
        border: "1px solid rgba(34, 197, 94, 0.3)",
        cursor: "pointer",
        transition: "all 0.15s ease",
      }}
      onMouseEnter={(e) => {
        (e.target as HTMLButtonElement).style.background = "rgba(34, 197, 94, 0.2)";
      }}
      onMouseLeave={(e) => {
        (e.target as HTMLButtonElement).style.background = "rgba(34, 197, 94, 0.1)";
      }}
    >
      ✓ Mark Resolved
    </button>
  );
}

// ── Main Page Component ────────────────────────────────

export default function QualityDashboardPage() {
  const params = useParams();
  const docId = params.id as string;
  const [dashboard, setDashboard] = useState<QualityDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"contradictions" | "edge_cases" | "compliance">("contradictions");

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
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to resolve");
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
      <div className="empty-state">
        <div className="empty-state-icon">📊</div>
        <h3>Quality Dashboard</h3>
        <p>{error || "Run analysis first to see quality metrics."}</p>
        <Link href={`/documents/${docId}`} className="btn btn-secondary btn-sm">
          ← Back to Document
        </Link>
      </div>
    );
  }

  const { quality_score, contradictions, edge_cases, compliance_tags } = dashboard;

  // Group compliance tags by tag
  const tagGroups: Record<string, ComplianceTag[]> = {};
  for (const ct of compliance_tags) {
    if (!tagGroups[ct.tag]) tagGroups[ct.tag] = [];
    tagGroups[ct.tag].push(ct);
  }

  return (
    <div style={{ maxWidth: "960px" }}>
      <Link href={`/documents/${docId}`} className="back-link">
        ← Back to Document
      </Link>

      {/* Header */}
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.8rem", fontWeight: 700, marginBottom: "0.25rem" }}>
          📊 Quality Dashboard
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem" }}>
          {dashboard.filename} — Deep analysis results
        </p>
      </div>

      {/* Overall Score + Sub-scores */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "1.5rem",
        marginBottom: "2rem",
      }}>
        {/* Large Overall Gauge */}
        <div style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "16px",
          padding: "2rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "var(--shadow-glow)",
        }}>
          <QualityGauge score={quality_score.overall} label="Overall Quality" />
        </div>

        {/* Sub-scores */}
        <div style={{
          display: "flex",
          flexDirection: "column",
          gap: "12px",
        }}>
          <SubScoreBar label="Completeness" score={quality_score.completeness} icon="📋" />
          <SubScoreBar label="Clarity" score={quality_score.clarity} icon="💡" />
          <SubScoreBar label="Consistency" score={quality_score.consistency} icon="🔗" />
        </div>
      </div>

      {/* Summary Stats */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
        gap: "1rem",
        marginBottom: "2rem",
      }}>
        <div className="info-item" style={{ borderLeft: "3px solid #ef4444" }}>
          <div className="info-label">Contradictions</div>
          <div className="info-value" style={{ color: contradictions.length > 0 ? "#ef4444" : "#22c55e" }}>
            {contradictions.length}
          </div>
        </div>
        <div className="info-item" style={{ borderLeft: "3px solid #f59e0b" }}>
          <div className="info-label">Edge Case Gaps</div>
          <div className="info-value" style={{ color: edge_cases.length > 0 ? "#f59e0b" : "#22c55e" }}>
            {edge_cases.length}
          </div>
        </div>
        <div className="info-item" style={{ borderLeft: "3px solid #6366f1" }}>
          <div className="info-label">Compliance Tags</div>
          <div className="info-value" style={{ color: "#6366f1" }}>
            {compliance_tags.length}
          </div>
        </div>
      </div>

      {/* Compliance Tag Pills */}
      {compliance_tags.length > 0 && (
        <div style={{ marginBottom: "2rem" }}>
          <h2 style={{
            fontSize: "1.1rem",
            fontWeight: 700,
            marginBottom: "12px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}>
            🏷️ Compliance Areas Detected
          </h2>
          <div style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "8px",
          }}>
            {Object.entries(tagGroups).map(([tag, items]) => {
              const cfg = complianceColors[tag] || complianceColors.security;
              const label = complianceLabels[tag] || tag;
              return (
                <span
                  key={tag}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "6px 14px",
                    borderRadius: "20px",
                    fontSize: "0.82rem",
                    fontWeight: 600,
                    background: cfg.bg,
                    color: cfg.color,
                    border: `1px solid ${cfg.border}`,
                  }}
                >
                  {label}
                  <span style={{
                    background: cfg.color,
                    color: "#fff",
                    borderRadius: "10px",
                    padding: "0 6px",
                    fontSize: "0.7rem",
                    fontWeight: 700,
                    minWidth: "18px",
                    textAlign: "center",
                  }}>
                    {items.length}
                  </span>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Tabbed Content */}
      <div style={{ marginBottom: "1rem" }}>
        <div style={{
          display: "flex",
          gap: "0",
          borderBottom: "1px solid var(--border-subtle)",
          marginBottom: "1.5rem",
        }}>
          {[
            { key: "contradictions" as const, label: `⚔️ Contradictions (${contradictions.length})` },
            { key: "edge_cases" as const, label: `🔍 Edge Cases (${edge_cases.length})` },
            { key: "compliance" as const, label: `🏷️ Compliance (${compliance_tags.length})` },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: "10px 20px",
                fontSize: "0.88rem",
                fontWeight: 600,
                background: "none",
                border: "none",
                borderBottom: activeTab === tab.key ? "2px solid var(--accent-primary)" : "2px solid transparent",
                color: activeTab === tab.key ? "var(--accent-primary)" : "var(--text-secondary)",
                cursor: "pointer",
                transition: "all 0.2s ease",
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Contradictions Tab */}
        {activeTab === "contradictions" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {contradictions.length === 0 ? (
              <div className="empty-state" style={{ padding: "2rem" }}>
                <div className="empty-state-icon">✅</div>
                <h3>No contradictions detected</h3>
                <p>All sections are consistent with each other.</p>
              </div>
            ) : (
              contradictions.map((c) => {
                const sev = severityConfig[c.severity] || severityConfig.MEDIUM;
                return (
                  <div
                    key={c.id}
                    style={{
                      background: "var(--bg-card)",
                      border: `1px solid ${c.resolved ? "var(--border-subtle)" : sev.border}`,
                      borderRadius: "12px",
                      padding: "20px",
                      opacity: c.resolved ? 0.6 : 1,
                      transition: "all 0.2s ease",
                      borderLeft: `4px solid ${c.resolved ? "#22c55e" : sev.color}`,
                    }}
                  >
                    {/* Header */}
                    <div style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      marginBottom: "12px",
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                        <span style={{
                          padding: "3px 10px",
                          borderRadius: "8px",
                          fontSize: "0.72rem",
                          fontWeight: 700,
                          background: sev.bg,
                          color: sev.color,
                          border: `1px solid ${sev.border}`,
                        }}>
                          {sev.label}
                        </span>
                        <span style={{ fontSize: "0.82rem", color: "var(--text-muted)", fontWeight: 500 }}>
                          §{c.section_a_index + 1} ↔ §{c.section_b_index + 1}
                        </span>
                      </div>
                      {c.resolved ? (
                        <span style={{ fontSize: "0.78rem", color: "#22c55e", fontWeight: 600 }}>
                          ✓ Resolved
                        </span>
                      ) : (
                        c.id && <ResolveButton onClick={() => handleResolveContradiction(c.id!)} />
                      )}
                    </div>

                    {/* Conflicting sections side-by-side */}
                    <div style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: "8px",
                      marginBottom: "12px",
                    }}>
                      <div style={{
                        background: "var(--bg-tertiary)",
                        padding: "10px 14px",
                        borderRadius: "8px",
                        borderLeft: "3px solid var(--accent-primary)",
                      }}>
                        <div style={{
                          fontSize: "0.72rem",
                          color: "var(--text-muted)",
                          fontWeight: 600,
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                          marginBottom: "4px",
                        }}>
                          Section A
                        </div>
                        <div style={{ fontSize: "0.88rem", fontWeight: 600, color: "var(--text-primary)" }}>
                          §{c.section_a_index + 1} · {c.section_a_heading}
                        </div>
                      </div>
                      <div style={{
                        background: "var(--bg-tertiary)",
                        padding: "10px 14px",
                        borderRadius: "8px",
                        borderLeft: "3px solid var(--accent-secondary, #a855f7)",
                      }}>
                        <div style={{
                          fontSize: "0.72rem",
                          color: "var(--text-muted)",
                          fontWeight: 600,
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                          marginBottom: "4px",
                        }}>
                          Section B
                        </div>
                        <div style={{ fontSize: "0.88rem", fontWeight: 600, color: "var(--text-primary)" }}>
                          §{c.section_b_index + 1} · {c.section_b_heading}
                        </div>
                      </div>
                    </div>

                    {/* Description */}
                    <p style={{
                      fontSize: "0.88rem",
                      color: "var(--text-secondary)",
                      lineHeight: 1.6,
                      marginBottom: "10px",
                    }}>
                      <strong>Conflict:</strong> {c.description}
                    </p>

                    {/* Suggested resolution */}
                    <div style={{
                      background: "rgba(34, 197, 94, 0.08)",
                      padding: "10px 14px",
                      borderRadius: "8px",
                      fontSize: "0.85rem",
                      lineHeight: 1.6,
                      color: "#22c55e",
                      fontWeight: 500,
                    }}>
                      💡 {c.suggested_resolution}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* Edge Cases Tab */}
        {activeTab === "edge_cases" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {edge_cases.length === 0 ? (
              <div className="empty-state" style={{ padding: "2rem" }}>
                <div className="empty-state-icon">✅</div>
                <h3>No edge case gaps detected</h3>
                <p>All scenarios appear to be well-covered.</p>
              </div>
            ) : (
              edge_cases.map((ec) => {
                const sev = severityConfig[ec.impact] || severityConfig.MEDIUM;
                return (
                  <div
                    key={ec.id}
                    style={{
                      background: "var(--bg-card)",
                      border: `1px solid ${ec.resolved ? "var(--border-subtle)" : sev.border}`,
                      borderRadius: "12px",
                      padding: "20px",
                      opacity: ec.resolved ? 0.6 : 1,
                      transition: "all 0.2s ease",
                      borderLeft: `4px solid ${ec.resolved ? "#22c55e" : sev.color}`,
                    }}
                  >
                    <div style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      marginBottom: "12px",
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <span style={{
                          padding: "3px 10px",
                          borderRadius: "8px",
                          fontSize: "0.72rem",
                          fontWeight: 700,
                          background: sev.bg,
                          color: sev.color,
                          border: `1px solid ${sev.border}`,
                        }}>
                          {sev.label}
                        </span>
                        <span style={{ fontSize: "0.82rem", color: "var(--text-muted)", fontWeight: 500 }}>
                          §{ec.section_index + 1} · {ec.section_heading}
                        </span>
                      </div>
                      {ec.resolved ? (
                        <span style={{ fontSize: "0.78rem", color: "#22c55e", fontWeight: 600 }}>
                          ✓ Resolved
                        </span>
                      ) : (
                        ec.id && <ResolveButton onClick={() => handleResolveEdgeCase(ec.id!)} />
                      )}
                    </div>

                    <p style={{
                      fontSize: "0.88rem",
                      color: "var(--text-secondary)",
                      lineHeight: 1.6,
                      marginBottom: "10px",
                    }}>
                      <strong>Missing scenario:</strong> {ec.scenario_description}
                    </p>

                    <div style={{
                      background: "var(--bg-tertiary)",
                      padding: "10px 14px",
                      borderRadius: "8px",
                      fontSize: "0.85rem",
                      lineHeight: 1.6,
                      color: "var(--accent-primary)",
                      fontWeight: 500,
                    }}>
                      ➕ {ec.suggested_addition}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* Compliance Tags Tab */}
        {activeTab === "compliance" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {compliance_tags.length === 0 ? (
              <div className="empty-state" style={{ padding: "2rem" }}>
                <div className="empty-state-icon">🏷️</div>
                <h3>No compliance areas detected</h3>
                <p>No sections flagged for payments, auth, PII, or external APIs.</p>
              </div>
            ) : (
              Object.entries(tagGroups).map(([tag, items]) => {
                const cfg = complianceColors[tag] || complianceColors.security;
                const label = complianceLabels[tag] || tag;
                return (
                  <div key={tag}>
                    <h3 style={{
                      fontSize: "0.95rem",
                      fontWeight: 700,
                      marginBottom: "10px",
                      color: cfg.color,
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                    }}>
                      {label}
                      <span style={{
                        background: cfg.bg,
                        border: `1px solid ${cfg.border}`,
                        borderRadius: "10px",
                        padding: "1px 8px",
                        fontSize: "0.72rem",
                      }}>
                        {items.length} section{items.length > 1 ? "s" : ""}
                      </span>
                    </h3>
                    <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "16px" }}>
                      {items.map((ct) => (
                        <div
                          key={ct.id}
                          style={{
                            background: "var(--bg-card)",
                            border: `1px solid ${cfg.border}`,
                            borderRadius: "10px",
                            padding: "14px 18px",
                            borderLeft: `3px solid ${cfg.color}`,
                          }}
                        >
                          <div style={{
                            fontSize: "0.85rem",
                            fontWeight: 600,
                            marginBottom: "6px",
                            color: "var(--text-primary)",
                          }}>
                            §{ct.section_index + 1} · {ct.section_heading}
                          </div>
                          <div style={{
                            fontSize: "0.82rem",
                            color: "var(--text-secondary)",
                            lineHeight: 1.5,
                          }}>
                            {ct.reason}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
}
