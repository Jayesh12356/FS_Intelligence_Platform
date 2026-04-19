"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  analyzeDocument,
  listAmbiguities,
  resolveAmbiguity,
  getDebateResults,
  bulkResolveAmbiguities,
  getDocument,
  isCursorTaskEnvelope,
} from "@/lib/api";
import type { AmbiguityFlag, CursorTaskEnvelope, DebateResult } from "@/lib/api";
import {
  PageShell,
  KpiCard,
  Tabs,
  FadeIn,
  StaggerList,
  StaggerItem,
  ScoreBar,
  EmptyState,
  CursorTaskModal,
} from "@/components/index";
import Badge from "@/components/Badge";
import { useToast } from "@/components/Toaster";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  AlertTriangle,
  CheckCircle2,
  Shield,
  Swords,
  ChevronDown,
  RefreshCw,
  Zap,
} from "lucide-react";

const severityBorder: Record<AmbiguityFlag["severity"], string> = {
  HIGH: "var(--error)",
  MEDIUM: "var(--warning)",
  LOW: "var(--info)",
};

function severityBadgeVariant(
  sev: AmbiguityFlag["severity"]
): "error" | "warning" | "info" {
  if (sev === "HIGH") return "error";
  if (sev === "MEDIUM") return "warning";
  return "info";
}

function DebateTranscript({ debate }: { debate: DebateResult }) {
  const [expanded, setExpanded] = useState(false);
  const isCleared = debate.verdict === "CLEAR";

  return (
    <div
      className="accordion-item"
      style={{
        marginTop: "0.75rem",
        background: isCleared ? "var(--bg-success-subtle)" : "var(--bg-accent-subtle)",
        borderColor: isCleared ? "rgba(22, 163, 74, 0.2)" : "var(--border-subtle)",
      }}
    >
      <button
        type="button"
        className="accordion-trigger"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
          <Swords size={16} style={{ opacity: 0.85 }} />
          <span>Adversarial Debate</span>
          <Badge variant={isCleared ? "success" : "error"}>
            {isCleared ? "Cleared" : "Confirmed ambiguous"}
          </Badge>
        </span>
        <ChevronDown
          size={18}
          className={`accordion-chevron${expanded ? " open" : ""}`}
          aria-hidden
        />
      </button>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="debate-body"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: "hidden" }}
          >
            <div className="accordion-content">
              <div
                style={{
                  marginBottom: "0.5rem",
                  padding: "0.625rem 0.75rem",
                  borderRadius: "var(--radius-md)",
                  background: "var(--bg-error-subtle)",
                  borderLeft: "3px solid var(--error)",
                }}
              >
                <div
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    color: "var(--error)",
                    marginBottom: "0.375rem",
                  }}
                >
                  Red Agent — &quot;It IS ambiguous&quot;
                </div>
                <div
                  style={{
                    fontSize: "0.8125rem",
                    lineHeight: 1.7,
                    color: "var(--text-secondary)",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {debate.red_argument}
                </div>
              </div>

              <div
                style={{
                  marginBottom: "0.5rem",
                  padding: "0.625rem 0.75rem",
                  borderRadius: "var(--radius-md)",
                  background: "var(--bg-info-subtle)",
                  borderLeft: "3px solid var(--info)",
                }}
              >
                <div
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    color: "var(--info)",
                    marginBottom: "0.375rem",
                  }}
                >
                  Blue Agent — &quot;It IS clear&quot;
                </div>
                <div
                  style={{
                    fontSize: "0.8125rem",
                    lineHeight: 1.7,
                    color: "var(--text-secondary)",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {debate.blue_argument}
                </div>
              </div>

              <div
                style={{
                  padding: "0.625rem 0.75rem",
                  borderRadius: "var(--radius-md)",
                  background: "var(--bg-accent-subtle)",
                  borderLeft: "3px solid var(--accent-primary)",
                }}
              >
                <div
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    color: "var(--accent-primary)",
                    marginBottom: "0.375rem",
                  }}
                >
                  Arbiter Verdict
                </div>
                <div
                  style={{
                    fontSize: "0.8125rem",
                    lineHeight: 1.7,
                    color: "var(--text-secondary)",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {debate.arbiter_reasoning}
                </div>
                <div style={{ marginTop: "0.75rem" }}>
                  <ScoreBar
                    label="Confidence"
                    value={debate.confidence}
                    max={100}
                    color={
                      debate.confidence >= 80
                        ? "var(--success)"
                        : debate.confidence >= 50
                          ? "var(--warning)"
                          : "var(--error)"
                    }
                  />
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function AmbiguitiesPage() {
  const params = useParams();
  const docId = params.id as string;
  const { error: toastError, success: toastSuccess } = useToast();
  const [flags, setFlags] = useState<AmbiguityFlag[]>([]);
  const [debates, setDebates] = useState<DebateResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasAnalyzed, setHasAnalyzed] = useState(false);
  const [filterTab, setFilterTab] = useState<string>("all");
  const [cursorTask, setCursorTask] = useState<CursorTaskEnvelope | null>(null);

  const fetchFlags = useCallback(async () => {
    setError(null);
    try {
      let analyzedByStatus = false;
      try {
        const docResp = await getDocument(docId);
        const status = docResp.data?.status;
        analyzedByStatus = status === "COMPLETE";
      } catch {
        // non-fatal; fall back to flag count heuristic below
      }

      const result = await listAmbiguities(docId);
      const list = result.data || [];
      setFlags(list);
      setHasAnalyzed(analyzedByStatus || list.length > 0);

      try {
        const debateResult = await getDebateResults(docId);
        setDebates(debateResult.data?.results || []);
      } catch {
        setDebates([]);
      }
    } catch (err: unknown) {
      setFlags([]);
      setError(err instanceof Error ? err.message : "Could not load ambiguities.");
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
      const res = await analyzeDocument(docId);
      if (isCursorTaskEnvelope(res.data)) {
        setCursorTask(res.data);
      } else {
        await fetchFlags();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleResolve = async (flagId: string, resolutionText?: string) => {
    try {
      const res = await resolveAmbiguity(
        docId,
        flagId,
        resolutionText !== undefined
          ? { resolution_text: resolutionText, resolved: true }
          : undefined
      );
      const updated = res.data;
      setFlags((prev) =>
        prev.map((f) =>
          f.id === flagId
            ? {
                ...f,
                resolved: true,
                resolution_text: updated?.resolution_text ?? resolutionText ?? f.resolution_text,
                resolved_at: updated?.resolved_at ?? new Date().toISOString(),
              }
            : f
        )
      );
    } catch (err: unknown) {
      toastError("Failed to resolve", err instanceof Error ? err.message : undefined);
    }
  };

  const [bulkLoading, setBulkLoading] = useState(false);
  const handleBulkResolve = async () => {
    setBulkLoading(true);
    try {
      await bulkResolveAmbiguities(docId);
      setFlags((prev) => prev.map((f) => ({ ...f, resolved: true })));
      toastSuccess("Ambiguities resolved", "All outstanding flags marked as resolved.");
    } catch (err: unknown) {
      toastError("Bulk resolve failed", err instanceof Error ? err.message : undefined);
    } finally {
      setBulkLoading(false);
    }
  };

  const getDebateForFlag = (flag: AmbiguityFlag): DebateResult | undefined => {
    return debates.find(
      (d) =>
        d.section_index === flag.section_index &&
        d.flagged_text === flag.flagged_text
    );
  };

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

  const filteredFlags = useMemo(() => {
    switch (filterTab) {
      case "high":
        return flags.filter((f) => f.severity === "HIGH");
      case "medium":
        return flags.filter((f) => f.severity === "MEDIUM");
      case "low":
        return flags.filter((f) => f.severity === "LOW");
      case "resolved":
        return flags.filter((f) => f.resolved);
      default:
        return flags;
    }
  }, [flags, filterTab]);

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        Loading ambiguity analysis…
      </div>
    );
  }

  const unresolvedCount = flags.filter((f) => !f.resolved).length;

  const actionButtons = (
    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
      {unresolvedCount > 0 && (
        <button
          type="button"
          className="btn btn-success"
          onClick={handleBulkResolve}
          disabled={bulkLoading}
          style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
        >
          <CheckCircle2 size={18} />
          {bulkLoading ? "Resolving…" : `Resolve All (${unresolvedCount})`}
        </button>
      )}
      <button
        type="button"
        className="btn btn-primary"
        onClick={handleAnalyze}
        disabled={analyzing}
      >
        {analyzing ? (
          <>
            <span className="spinner" style={{ width: 16, height: 16 }} />
            Analyzing…
          </>
        ) : hasAnalyzed ? (
          <>
            <RefreshCw size={18} />
            Re-analyze Document
          </>
        ) : (
          <>
            <Zap size={18} />
            Run Analysis
          </>
        )}
      </button>
    </div>
  );

  return (
    <PageShell
      backHref={`/documents/${docId}`}
      backLabel="Back to Document"
      title="Ambiguity Analysis"
      subtitle="AI-detected ambiguities, vague language, and incomplete requirements"
      actions={actionButtons}
      maxWidth={900}
    >
      {error && (
        <div
          className="alert alert-error"
          style={{
            marginBottom: "1.25rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "1rem",
          }}
        >
          <span>{error}</span>
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={() => {
              setError(null);
              setLoading(true);
              fetchFlags();
            }}
          >
            Retry
          </button>
        </div>
      )}

      {flags.length === 0 && !hasAnalyzed && (
        <EmptyState
          icon={<AlertTriangle size={40} strokeWidth={1.25} aria-hidden />}
          title="No ambiguity data yet"
          description="Run the analysis pipeline first to detect ambiguities, contradictions, and edge cases in your document."
          action={
            <button type="button" className="btn btn-primary" onClick={handleAnalyze} disabled={analyzing} style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
              {analyzing ? <><span className="spinner" style={{ width: 16, height: 16 }} />Analyzing…</> : <><Zap size={18} />Run Analysis</>}
            </button>
          }
        />
      )}

      {flags.length > 0 && (
        <>
          <FadeIn delay={0.04}>
            <div className="kpi-row">
              <KpiCard
                label="Total flags"
                value={total}
                icon={<AlertTriangle size={20} />}
                iconBg="var(--well-amber)"
                delay={0}
              />
              <KpiCard
                label="HIGH severity"
                value={highCount}
                icon={<Shield size={20} />}
                iconBg="var(--well-red)"
                delay={0.05}
              />
              <KpiCard
                label="Resolved"
                value={resolved}
                icon={<CheckCircle2 size={20} />}
                iconBg="var(--well-green)"
                delay={0.1}
              />
              <KpiCard
                label="Debate coverage"
                value={debates.length}
                icon={<Swords size={20} />}
                iconBg="var(--well-purple)"
                delay={0.15}
              />
            </div>
          </FadeIn>

          <FadeIn delay={0.08} style={{ marginBottom: "1.5rem" }}>
            <ScoreBar
              label="Resolution Progress"
              value={progressPct}
              max={100}
              color={
                progressPct === 100
                  ? "var(--success)"
                  : progressPct >= 70
                    ? "var(--accent-primary)"
                    : progressPct >= 40
                      ? "var(--warning)"
                      : "var(--error)"
              }
            />
            {unresolvedHigh > 0 && (
              <p
                className="alert alert-warning"
                style={{
                  marginTop: "0.75rem",
                  marginBottom: 0,
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                }}
              >
                <AlertTriangle size={16} />
                {unresolvedHigh} HIGH severity issue{unresolvedHigh > 1 ? "s" : ""} still open
              </p>
            )}
          </FadeIn>
        </>
      )}

      {debates.length > 0 && (
        <FadeIn delay={0.06} style={{ marginBottom: "1.5rem" }}>
          <div className="section-card">
            <div className="section-card-header">Adversarial Validation</div>
            <div className="section-card-body">
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                {debates.length} HIGH severity flag{debates.length !== 1 ? "s" : ""} challenged by Red vs
                Blue agent debate.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
                <Badge variant="error">
                  Confirmed: {debates.filter((d) => d.verdict === "AMBIGUOUS").length}
                </Badge>
                <Badge variant="success">
                  Cleared: {clearedDebates.length}
                </Badge>
              </div>
            </div>
          </div>
        </FadeIn>
      )}

      {flags.length > 0 && (
        <>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
              flexWrap: "wrap",
              marginBottom: "1rem",
            }}
          >
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.35rem",
                fontSize: "0.8125rem",
                color: "var(--text-muted)",
                fontWeight: 600,
              }}
            >
              <Search size={16} aria-hidden />
              Filter
            </span>
            <Tabs
              items={[
                { key: "all", label: "All", count: flags.length },
                { key: "high", label: "HIGH", count: highCount },
                { key: "medium", label: "MEDIUM", count: mediumCount },
                { key: "low", label: "LOW", count: lowCount },
                { key: "resolved", label: "Resolved", count: resolved },
              ]}
              active={filterTab}
              onChange={setFilterTab}
            />
          </div>

          <StaggerList style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {filteredFlags.map((flag) => {
              const leftColor = flag.resolved ? "var(--success)" : severityBorder[flag.severity];
              const debate = getDebateForFlag(flag);

              return (
                <StaggerItem key={flag.id ?? `${flag.section_index}-${flag.flagged_text.slice(0, 24)}`}>
                  <motion.div
                    className="card"
                    whileHover={{ y: -3 }}
                    transition={{ type: "spring", stiffness: 420, damping: 28 }}
                    style={{
                      borderLeft: `4px solid ${leftColor}`,
                      opacity: flag.resolved ? 0.72 : 1,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: "0.75rem",
                        marginBottom: "0.75rem",
                        flexWrap: "wrap",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                        <Badge variant={severityBadgeVariant(flag.severity)}>{flag.severity}</Badge>
                        <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", fontWeight: 500 }}>
                          Section {flag.section_index + 1} · {flag.section_heading}
                        </span>
                        {debate && debate.verdict === "AMBIGUOUS" && (
                          <Badge variant="error">Debate Confirmed</Badge>
                        )}
                      </div>
                      {flag.resolved ? (
                        <Badge variant="success">Resolved</Badge>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-success btn-sm"
                          onClick={() => {
                            if (!flag.id) return;
                            const note = window.prompt(
                              "How was this resolved? (optional)",
                              ""
                            );
                            // Cancel == null → bail; empty string still resolves without a note
                            if (note === null) return;
                            handleResolve(flag.id, note.trim());
                          }}
                          disabled={!flag.id}
                        >
                          <CheckCircle2 size={14} />
                          Mark Resolved
                        </button>
                      )}
                    </div>

                    <div
                      style={{
                        padding: "0.625rem 0.875rem",
                        borderRadius: "var(--radius-md)",
                        fontSize: "0.875rem",
                        lineHeight: 1.6,
                        marginBottom: "0.625rem",
                        borderLeft: `3px solid ${leftColor}`,
                        background: "var(--bg-tertiary)",
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      &ldquo;{flag.flagged_text}&rdquo;
                    </div>

                    <p
                      style={{
                        fontSize: "0.875rem",
                        color: "var(--text-secondary)",
                        lineHeight: 1.6,
                        marginBottom: "0.625rem",
                      }}
                    >
                      <strong>Why:</strong> {flag.reason}
                    </p>

                    <div
                      style={{
                        background: "var(--bg-accent-subtle)",
                        padding: "0.625rem 0.875rem",
                        borderRadius: "var(--radius-md)",
                        fontSize: "0.875rem",
                        lineHeight: 1.6,
                        color: "var(--accent-primary)",
                        fontWeight: 500,
                      }}
                    >
                      {flag.clarification_question}
                    </div>

                    {flag.resolved && flag.resolution_text && (
                      <div
                        style={{
                          marginTop: "0.5rem",
                          padding: "0.5rem 0.75rem",
                          borderRadius: "var(--radius-md)",
                          fontSize: "0.8125rem",
                          color: "var(--text-secondary)",
                          background: "var(--bg-success-subtle, rgba(34,197,94,0.08))",
                          borderLeft: "3px solid var(--success, #16a34a)",
                        }}
                      >
                        <strong style={{ color: "var(--success, #16a34a)" }}>Resolution:</strong>{" "}
                        {flag.resolution_text}
                      </div>
                    )}

                    {debate && <DebateTranscript debate={debate} />}
                  </motion.div>
                </StaggerItem>
              );
            })}
          </StaggerList>

          {clearedDebates.length > 0 && (
            <FadeIn delay={0.05} style={{ marginTop: "2rem" }}>
              <h2
                className="page-title"
                style={{ fontSize: "1.05rem", marginBottom: "0.75rem", color: "var(--success)" }}
              >
                <CheckCircle2 size={18} style={{ verticalAlign: "text-bottom", marginRight: "0.35rem" }} />
                Cleared by debate ({clearedDebates.length})
              </h2>
              <StaggerList style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {clearedDebates.map((debate, idx) => (
                  <StaggerItem key={`cleared-${idx}-${debate.section_index}-${debate.flagged_text.slice(0, 16)}`}>
                    <motion.div
                      className="card"
                      whileHover={{ y: -2 }}
                      transition={{ type: "spring", stiffness: 400, damping: 26 }}
                      style={{
                        borderLeft: "4px solid var(--success)",
                        opacity: 0.88,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
                        <Badge variant="success">Overridden by debate</Badge>
                        <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", fontWeight: 500 }}>
                          Section {debate.section_index + 1} · {debate.section_heading}
                        </span>
                      </div>
                      <div
                        style={{
                          padding: "0.5rem 0.75rem",
                          borderRadius: "var(--radius-md)",
                          fontSize: "0.875rem",
                          color: "var(--text-secondary)",
                          textDecoration: "line-through",
                          marginBottom: "0.5rem",
                          background: "var(--bg-tertiary)",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        &ldquo;{debate.flagged_text}&rdquo;
                      </div>
                      <DebateTranscript debate={debate} />
                    </motion.div>
                  </StaggerItem>
                ))}
              </StaggerList>
            </FadeIn>
          )}
        </>
      )}

      {!loading && flags.length === 0 && hasAnalyzed && (
        <EmptyState
          icon={<CheckCircle2 size={40} strokeWidth={1.25} />}
          title="No ambiguities detected"
          description="The document appears to have clear, well-defined requirements."
          action={
            <Link href={`/documents/${docId}`} className="btn btn-secondary btn-sm" style={{ marginTop: "0.75rem" }}>
              Back to document
            </Link>
          }
        />
      )}

      <CursorTaskModal
        envelope={cursorTask}
        onClose={() => setCursorTask(null)}
        onDone={async () => {
          setCursorTask(null);
          await fetchFlags();
        }}
      />
    </PageShell>
  );
}
