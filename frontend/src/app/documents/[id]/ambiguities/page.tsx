"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  analyzeDocument,
  listAmbiguities,
  resolveAmbiguity,
  getDebateResults,
} from "@/lib/api";
import type { AmbiguityFlag, DebateResult } from "@/lib/api";

const severityConfig = {
  HIGH: { color: "#ef4444", bg: "#ef444418", label: "🔴 HIGH", border: "#ef444444" },
  MEDIUM: { color: "#f59e0b", bg: "#f59e0b18", label: "🟡 MEDIUM", border: "#f59e0b44" },
  LOW: { color: "#3b82f6", bg: "#3b82f618", label: "🔵 LOW", border: "#3b82f644" },
};

function DebateTranscript({ debate }: { debate: DebateResult }) {
  const [expanded, setExpanded] = useState(false);
  const isCleared = debate.verdict === "CLEAR";

  return (
    <div
      style={{
        marginTop: "12px",
        background: isCleared
          ? "rgba(34, 197, 94, 0.06)"
          : "rgba(139, 92, 246, 0.06)",
        border: `1px solid ${isCleared ? "rgba(34, 197, 94, 0.25)" : "rgba(139, 92, 246, 0.25)"}`,
        borderRadius: "10px",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: "100%",
          padding: "10px 14px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--text-primary)",
          fontSize: "0.82rem",
          fontWeight: 600,
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span>⚔️ Adversarial Debate</span>
          <span
            style={{
              padding: "2px 8px",
              borderRadius: "6px",
              fontSize: "0.7rem",
              fontWeight: 700,
              background: isCleared ? "rgba(34, 197, 94, 0.15)" : "rgba(239, 68, 68, 0.15)",
              color: isCleared ? "#22c55e" : "#ef4444",
              border: `1px solid ${isCleared ? "rgba(34, 197, 94, 0.3)" : "rgba(239, 68, 68, 0.3)"}`,
            }}
          >
            {isCleared ? "✓ CLEARED" : "✗ CONFIRMED AMBIGUOUS"}
          </span>
          <span
            style={{
              padding: "2px 8px",
              borderRadius: "6px",
              fontSize: "0.7rem",
              fontWeight: 600,
              background: "rgba(139, 92, 246, 0.1)",
              color: "#8b5cf6",
            }}
          >
            {debate.confidence}% confidence
          </span>
        </span>
        <span
          style={{
            transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s ease",
            opacity: 0.5,
          }}
        >
          ▼
        </span>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div
          style={{
            padding: "0 14px 14px",
            borderTop: "1px solid var(--border-subtle)",
          }}
        >
          {/* Red Agent */}
          <div
            style={{
              margin: "12px 0 8px",
              padding: "10px 12px",
              borderRadius: "8px",
              background: "rgba(239, 68, 68, 0.06)",
              borderLeft: "3px solid #ef4444",
            }}
          >
            <div
              style={{
                fontSize: "0.75rem",
                fontWeight: 700,
                color: "#ef4444",
                marginBottom: "6px",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              🔴 Red Agent — &quot;It IS ambiguous&quot;
            </div>
            <div
              style={{
                fontSize: "0.82rem",
                lineHeight: 1.7,
                color: "var(--text-secondary)",
                whiteSpace: "pre-wrap",
              }}
            >
              {debate.red_argument}
            </div>
          </div>

          {/* Blue Agent */}
          <div
            style={{
              margin: "8px 0",
              padding: "10px 12px",
              borderRadius: "8px",
              background: "rgba(59, 130, 246, 0.06)",
              borderLeft: "3px solid #3b82f6",
            }}
          >
            <div
              style={{
                fontSize: "0.75rem",
                fontWeight: 700,
                color: "#3b82f6",
                marginBottom: "6px",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              🔵 Blue Agent — &quot;It IS clear&quot;
            </div>
            <div
              style={{
                fontSize: "0.82rem",
                lineHeight: 1.7,
                color: "var(--text-secondary)",
                whiteSpace: "pre-wrap",
              }}
            >
              {debate.blue_argument}
            </div>
          </div>

          {/* Arbiter */}
          <div
            style={{
              margin: "8px 0 0",
              padding: "10px 12px",
              borderRadius: "8px",
              background: "rgba(139, 92, 246, 0.08)",
              borderLeft: "3px solid #8b5cf6",
            }}
          >
            <div
              style={{
                fontSize: "0.75rem",
                fontWeight: 700,
                color: "#8b5cf6",
                marginBottom: "6px",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              ⚖️ Arbiter Verdict
            </div>
            <div
              style={{
                fontSize: "0.82rem",
                lineHeight: 1.7,
                color: "var(--text-secondary)",
                whiteSpace: "pre-wrap",
              }}
            >
              {debate.arbiter_reasoning}
            </div>

            {/* Confidence bar */}
            <div style={{ marginTop: "8px" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: "0.7rem",
                  color: "var(--text-muted)",
                  marginBottom: "4px",
                }}
              >
                <span>Confidence</span>
                <span>{debate.confidence}%</span>
              </div>
              <div
                style={{
                  height: "4px",
                  background: "var(--bg-tertiary)",
                  borderRadius: "2px",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${debate.confidence}%`,
                    background:
                      debate.confidence >= 80
                        ? "#22c55e"
                        : debate.confidence >= 50
                          ? "#f59e0b"
                          : "#ef4444",
                    borderRadius: "2px",
                    transition: "width 0.3s ease",
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AmbiguitiesPage() {
  const params = useParams();
  const docId = params.id as string;
  const [flags, setFlags] = useState<AmbiguityFlag[]>([]);
  const [debates, setDebates] = useState<DebateResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasAnalyzed, setHasAnalyzed] = useState(false);

  const fetchFlags = useCallback(async () => {
    try {
      const result = await listAmbiguities(docId);
      setFlags(result.data || []);
      setHasAnalyzed(result.data && result.data.length > 0);

      // Also fetch debate results
      try {
        const debateResult = await getDebateResults(docId);
        setDebates(debateResult.data?.results || []);
      } catch {
        setDebates([]);
      }
    } catch {
      setFlags([]);
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    if (docId) fetchFlags();
  }, [docId, fetchFlags]);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setError(null);
    try {
      const result = await analyzeDocument(docId);
      setFlags(result.data.ambiguities);
      setHasAnalyzed(true);

      // Refresh debate results
      try {
        const debateResult = await getDebateResults(docId);
        setDebates(debateResult.data?.results || []);
      } catch {
        setDebates([]);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleResolve = async (flagId: string) => {
    try {
      await resolveAmbiguity(docId, flagId);
      setFlags((prev) =>
        prev.map((f) => (f.id === flagId ? { ...f, resolved: true } : f))
      );
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to resolve");
    }
  };

  // Find debate result for a specific flag
  const getDebateForFlag = (flag: AmbiguityFlag): DebateResult | undefined => {
    return debates.find(
      (d) =>
        d.section_index === flag.section_index &&
        d.flagged_text === flag.flagged_text
    );
  };

  // Count cleared flags (exist in debates with CLEAR verdict)
  const clearedDebates = debates.filter((d) => d.verdict === "CLEAR");

  const total = flags.length;
  const resolved = flags.filter((f) => f.resolved).length;
  const highCount = flags.filter((f) => f.severity === "HIGH").length;
  const mediumCount = flags.filter((f) => f.severity === "MEDIUM").length;
  const lowCount = flags.filter((f) => f.severity === "LOW").length;
  const unresolvedHigh = flags.filter(
    (f) => f.severity === "HIGH" && !f.resolved
  ).length;
  const progressPct = total > 0 ? Math.round((resolved / total) * 100) : 0;

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        Loading ambiguity analysis…
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "900px" }}>
      <Link href={`/documents/${docId}`} className="back-link">
        ← Back to Document
      </Link>

      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.8rem", fontWeight: 700, marginBottom: "0.5rem" }}>
          🔍 Ambiguity Analysis
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem" }}>
          AI-detected ambiguities, vague language, and incomplete requirements
        </p>
      </div>

      {/* Action button */}
      <div style={{ marginBottom: "2rem" }}>
        <button
          className="btn btn-primary"
          onClick={handleAnalyze}
          disabled={analyzing}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            padding: "12px 28px",
            fontSize: "1rem",
          }}
        >
          {analyzing ? (
            <>
              <span className="spinner" style={{ width: "16px", height: "16px" }} />
              Analyzing…
            </>
          ) : hasAnalyzed ? (
            <>🔄 Re-analyze Document</>
          ) : (
            <>⚡ Run Analysis</>
          )}
        </button>
        {error && (
          <p style={{ color: "#ef4444", marginTop: "0.75rem", fontSize: "0.9rem" }}>
            ❌ {error}
          </p>
        )}
      </div>

      {/* Debate Summary Banner */}
      {debates.length > 0 && (
        <div
          style={{
            marginBottom: "1.5rem",
            padding: "14px 18px",
            borderRadius: "12px",
            background: "linear-gradient(135deg, rgba(139, 92, 246, 0.08), rgba(59, 130, 246, 0.08))",
            border: "1px solid rgba(139, 92, 246, 0.2)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "12px",
          }}
        >
          <div>
            <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "4px" }}>
              ⚔️ Adversarial Validation (L6)
            </div>
            <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
              {debates.length} HIGH severity flag{debates.length !== 1 ? "s" : ""} challenged
              by Red vs Blue agent debate
            </div>
          </div>
          <div style={{ display: "flex", gap: "12px" }}>
            <div
              style={{
                textAlign: "center",
                padding: "6px 14px",
                borderRadius: "8px",
                background: "rgba(239, 68, 68, 0.1)",
              }}
            >
              <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#ef4444" }}>
                {debates.filter((d) => d.verdict === "AMBIGUOUS").length}
              </div>
              <div style={{ fontSize: "0.68rem", color: "#ef4444", fontWeight: 600 }}>Confirmed</div>
            </div>
            <div
              style={{
                textAlign: "center",
                padding: "6px 14px",
                borderRadius: "8px",
                background: "rgba(34, 197, 94, 0.1)",
              }}
            >
              <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#22c55e" }}>
                {clearedDebates.length}
              </div>
              <div style={{ fontSize: "0.68rem", color: "#22c55e", fontWeight: 600 }}>Cleared</div>
            </div>
          </div>
        </div>
      )}

      {/* Stats + Progress */}
      {flags.length > 0 && (
        <>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: "1rem",
            marginBottom: "1.5rem",
          }}>
            <div className="info-item">
              <div className="info-label">Total</div>
              <div className="info-value">{total}</div>
            </div>
            <div className="info-item" style={{ borderLeft: "3px solid #ef4444" }}>
              <div className="info-label">High</div>
              <div className="info-value" style={{ color: "#ef4444" }}>{highCount}</div>
            </div>
            <div className="info-item" style={{ borderLeft: "3px solid #f59e0b" }}>
              <div className="info-label">Medium</div>
              <div className="info-value" style={{ color: "#f59e0b" }}>{mediumCount}</div>
            </div>
            <div className="info-item" style={{ borderLeft: "3px solid #3b82f6" }}>
              <div className="info-label">Low</div>
              <div className="info-value" style={{ color: "#3b82f6" }}>{lowCount}</div>
            </div>
            <div className="info-item">
              <div className="info-label">Resolved</div>
              <div className="info-value" style={{ color: "#22c55e" }}>
                {resolved}/{total}
              </div>
            </div>
          </div>

          {/* Progress bar */}
          <div style={{ marginBottom: "2rem" }}>
            <div style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: "0.8rem",
              color: "var(--text-secondary)",
              marginBottom: "6px",
            }}>
              <span>Resolution Progress</span>
              <span>{progressPct}%</span>
            </div>
            <div style={{
              height: "8px",
              background: "var(--bg-tertiary)",
              borderRadius: "4px",
              overflow: "hidden",
            }}>
              <div style={{
                height: "100%",
                width: `${progressPct}%`,
                background: progressPct === 100
                  ? "linear-gradient(135deg, #22c55e, #10b981)"
                  : "var(--accent-gradient)",
                borderRadius: "4px",
                transition: "width 0.3s ease",
              }} />
            </div>
            {unresolvedHigh > 0 && (
              <p style={{
                color: "#ef4444",
                fontSize: "0.82rem",
                marginTop: "8px",
                fontWeight: 600,
              }}>
                ⚠ {unresolvedHigh} HIGH severity issue{unresolvedHigh > 1 ? "s" : ""} require resolution
              </p>
            )}
          </div>

          {/* Cleared by debate section */}
          {clearedDebates.length > 0 && (
            <div style={{ marginBottom: "2rem" }}>
              <h3 style={{
                fontSize: "1rem",
                fontWeight: 600,
                marginBottom: "12px",
                color: "#22c55e",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}>
                ✓ Overridden by Debate ({clearedDebates.length})
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {clearedDebates.map((debate, idx) => (
                  <div
                    key={idx}
                    style={{
                      background: "var(--bg-card)",
                      border: "1px solid rgba(34, 197, 94, 0.3)",
                      borderRadius: "12px",
                      padding: "16px",
                      opacity: 0.7,
                      borderLeft: "4px solid #22c55e",
                    }}
                  >
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      marginBottom: "8px",
                    }}>
                      <span style={{
                        padding: "2px 10px",
                        borderRadius: "8px",
                        fontSize: "0.72rem",
                        fontWeight: 700,
                        background: "rgba(34, 197, 94, 0.12)",
                        color: "#22c55e",
                        border: "1px solid rgba(34, 197, 94, 0.3)",
                      }}>
                        OVERRIDDEN BY DEBATE
                      </span>
                      <span style={{
                        fontSize: "0.78rem",
                        color: "var(--text-muted)",
                        fontWeight: 500,
                      }}>
                        §{debate.section_index + 1} · {debate.section_heading}
                      </span>
                    </div>
                    <div style={{
                      background: "rgba(34, 197, 94, 0.06)",
                      padding: "8px 12px",
                      borderRadius: "6px",
                      fontSize: "0.85rem",
                      fontFamily: "var(--font-mono)",
                      color: "var(--text-secondary)",
                      textDecoration: "line-through",
                      marginBottom: "8px",
                    }}>
                      &ldquo;{debate.flagged_text}&rdquo;
                    </div>
                    <DebateTranscript debate={debate} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Active flags list */}
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {flags.map((flag) => {
              const sev = severityConfig[flag.severity] || severityConfig.MEDIUM;
              const debate = getDebateForFlag(flag);

              return (
                <div
                  key={flag.id}
                  style={{
                    background: "var(--bg-card)",
                    border: `1px solid ${flag.resolved ? "var(--border-subtle)" : sev.border}`,
                    borderRadius: "12px",
                    padding: "20px",
                    opacity: flag.resolved ? 0.6 : 1,
                    transition: "all 0.2s ease",
                    borderLeft: `4px solid ${flag.resolved ? "#22c55e" : sev.color}`,
                  }}
                >
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
                      <span style={{
                        fontSize: "0.82rem",
                        color: "var(--text-muted)",
                        fontWeight: 500,
                      }}>
                        §{flag.section_index + 1} · {flag.section_heading}
                      </span>
                      {debate && debate.verdict === "AMBIGUOUS" && (
                        <span style={{
                          padding: "2px 8px",
                          borderRadius: "6px",
                          fontSize: "0.68rem",
                          fontWeight: 700,
                          background: "rgba(239, 68, 68, 0.1)",
                          color: "#ef4444",
                          border: "1px solid rgba(239, 68, 68, 0.25)",
                        }}>
                          ⚔️ Debate Confirmed
                        </span>
                      )}
                    </div>
                    {flag.resolved ? (
                      <span style={{
                        fontSize: "0.78rem",
                        color: "#22c55e",
                        fontWeight: 600,
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                      }}>
                        ✓ Resolved
                      </span>
                    ) : (
                      <button
                        onClick={() => flag.id && handleResolve(flag.id)}
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
                    )}
                  </div>

                  <div style={{
                    background: sev.bg,
                    padding: "10px 14px",
                    borderRadius: "8px",
                    fontSize: "0.88rem",
                    lineHeight: 1.6,
                    fontFamily: "var(--font-mono)",
                    marginBottom: "10px",
                    color: "var(--text-primary)",
                    borderLeft: `3px solid ${sev.color}`,
                  }}>
                    &ldquo;{flag.flagged_text}&rdquo;
                  </div>

                  <p style={{
                    fontSize: "0.88rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.6,
                    marginBottom: "10px",
                  }}>
                    <strong>Why:</strong> {flag.reason}
                  </p>

                  <div style={{
                    background: "var(--bg-tertiary)",
                    padding: "10px 14px",
                    borderRadius: "8px",
                    fontSize: "0.88rem",
                    lineHeight: 1.6,
                    color: "var(--accent-primary)",
                    fontWeight: 500,
                  }}>
                    💬 {flag.clarification_question}
                  </div>

                  {/* Debate transcript for HIGH flags */}
                  {debate && <DebateTranscript debate={debate} />}
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Empty state */}
      {!loading && flags.length === 0 && hasAnalyzed && (
        <div className="empty-state">
          <div className="empty-state-icon">✅</div>
          <h3>No ambiguities detected</h3>
          <p>The document appears to have clear, well-defined requirements.</p>
        </div>
      )}
    </div>
  );
}
