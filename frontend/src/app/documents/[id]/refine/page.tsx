"use client";

import { useEffect, useState, useCallback, useMemo, type CSSProperties } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  getRefinementSuggestions,
  applyRefinement,
  getDocument,
  listVersions,
  getVersionText,
  revertToVersion,
} from "@/lib/api";
import type {
  FSDocumentDetail,
  RefinementResponse,
  RefinementDiffLine,
  FSVersionItem,
} from "@/lib/api";
import { PageShell, KpiCard, FadeIn, EmptyState } from "@/components/index";
import QualityGauge from "@/components/QualityGauge";
import Badge from "@/components/Badge";
import { motion, AnimatePresence } from "framer-motion";
import {
  Sparkles,
  CheckCircle2,
  XCircle,
  ArrowRight,
  RefreshCw,
  TrendingUp,
  ListChecks,
  History,
  RotateCcw,
  Eye,
  ChevronDown,
} from "lucide-react";

function computeSplitPaneLineClasses(
  originalLines: string[],
  refinedLines: string[],
  diff: RefinementDiffLine[]
): { origClass: string[]; refClass: string[] } {
  const minusCounts = new Map<string, number>();
  const plusCounts = new Map<string, number>();
  for (const { line: raw } of diff) {
    if (raw.startsWith("-") && !raw.startsWith("---")) {
      const t = raw.slice(1);
      minusCounts.set(t, (minusCounts.get(t) ?? 0) + 1);
    } else if (raw.startsWith("+") && !raw.startsWith("+++")) {
      const t = raw.slice(1);
      plusCounts.set(t, (plusCounts.get(t) ?? 0) + 1);
    }
  }
  const origClass = originalLines.map((l) => {
    const c = minusCounts.get(l) ?? 0;
    if (c > 0) {
      minusCounts.set(l, c - 1);
      return "diff-remove";
    }
    return "";
  });
  const refClass = refinedLines.map((l) => {
    const c = plusCounts.get(l) ?? 0;
    if (c > 0) {
      plusCounts.set(l, c - 1);
      return l.includes("[REFINED]") ? "diff-refined" : "diff-add";
    }
    if (l.includes("[REFINED]")) return "diff-refined";
    return "";
  });
  return { origClass, refClass };
}

export default function RefinePage() {
  const params = useParams();
  const router = useRouter();
  const docId = params.id as string;

  const [doc, setDoc] = useState<FSDocumentDetail | null>(null);
  const [result, setResult] = useState<RefinementResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [versions, setVersions] = useState<FSVersionItem[]>([]);
  const [showVersions, setShowVersions] = useState(false);
  const [previewVersionId, setPreviewVersionId] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [reverting, setReverting] = useState(false);

  const fetchVersions = useCallback(async () => {
    try {
      const res = await listVersions(docId);
      if (res.data) setVersions(res.data.versions);
    } catch { /* non-fatal */ }
  }, [docId]);

  useEffect(() => {
    const run = async () => {
      try {
        const d = await getDocument(docId);
        setDoc(d.data);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to load document");
      }
    };
    if (docId) {
      run();
      fetchVersions();
    }
  }, [docId, fetchVersions]);

  const onRefine = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getRefinementSuggestions(docId);
      setResult(res.data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Refinement failed");
    } finally {
      setLoading(false);
    }
  }, [docId]);

  const onAccept = useCallback(async () => {
    if (!result) return;
    setSaving(true);
    setError(null);
    try {
      await applyRefinement(docId, result.refined_text);
      router.push(`/documents/${docId}?autoAnalyze=1`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save refined version");
    } finally {
      setSaving(false);
    }
  }, [docId, result, router]);

  const onPreviewVersion = useCallback(async (versionId: string) => {
    if (previewVersionId === versionId) {
      setPreviewVersionId(null);
      setPreviewText(null);
      return;
    }
    try {
      const res = await getVersionText(docId, versionId);
      setPreviewVersionId(versionId);
      setPreviewText(res.data.parsed_text);
    } catch { /* non-fatal */ }
  }, [docId, previewVersionId]);

  const onRevertVersion = useCallback(async (versionId: string) => {
    setReverting(true);
    try {
      await revertToVersion(docId, versionId);
      const d = await getDocument(docId);
      setDoc(d.data);
      await fetchVersions();
      setPreviewVersionId(null);
      setPreviewText(null);
      setResult(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Revert failed");
    } finally {
      setReverting(false);
    }
  }, [docId, fetchVersions]);

  const onReject = useCallback(() => {
    setResult(null);
  }, []);

  const originalText = useMemo(
    () => doc?.parsed_text || doc?.original_text || "",
    [doc]
  );

  const originalScore = result?.original_score ?? 0;
  const refinedScore = result?.refined_score ?? 0;
  const changes = result?.changes_made ?? 0;
  const improvementDelta = refinedScore - originalScore;

  const refinedText = result?.refined_text ?? "";
  const originalLines = useMemo(() => originalText.split(/\r?\n/), [originalText]);
  const refinedLines = useMemo(() => refinedText.split(/\r?\n/), [refinedText]);
  const { origClass, refClass } = useMemo(
    () =>
      result?.diff?.length
        ? computeSplitPaneLineClasses(originalLines, refinedLines, result.diff)
        : {
            origClass: originalLines.map(() => ""),
            refClass: refinedLines.map((l) => (l.includes("[REFINED]") ? "diff-refined" : "")),
          },
    [result?.diff, originalLines, refinedLines]
  );

  const docLoading = Boolean(docId) && doc === null && error === null;
  const documentFailed = Boolean(docId) && doc === null && error !== null;
  const showEmpty = doc !== null && !loading && !result;

  const panelStyle: CSSProperties = {
    border: "1px solid var(--glass-border)",
    borderRadius: 12,
    padding: "1rem",
    minHeight: 320,
    overflow: "hidden",
  };

  return (
    <PageShell
      backHref={`/documents/${docId}`}
      title="FS Refinement"
      subtitle="Run the refinement engine to propose an improved FS, compare quality, then accept or reject."
      actions={
        <button
          type="button"
          className="btn btn-primary"
          onClick={onRefine}
          disabled={loading || saving || docLoading}
        >
          {loading ? (
            <>
              <span className="spinner" style={{ display: "inline-block", verticalAlign: "middle" }} />
              <span style={{ marginLeft: 8 }}>Refining</span>
            </>
          ) : (
            <>
              <Sparkles size={18} style={{ marginRight: 8, verticalAlign: "middle" }} />
              Get suggestions
            </>
          )}
        </button>
      }
    >
      {error && doc !== null && (
        <FadeIn>
          <div className="badge badge-error" style={{ marginBottom: "1rem", display: "inline-block" }}>
            {error}
          </div>
        </FadeIn>
      )}

      <AnimatePresence mode="wait">
        {documentFailed ? (
          <motion.div
            key="doc-error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <FadeIn>
              <EmptyState
                icon={<XCircle size={40} strokeWidth={1.25} />}
                title="Document unavailable"
                description={error ?? undefined}
                action={
                  <Link href="/documents" className="btn btn-secondary">
                    Browse documents
                  </Link>
                }
              />
            </FadeIn>
          </motion.div>
        ) : docLoading ? (
          <motion.div
            key="doc-loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="page-loading"
          >
            <span className="spinner" />
            <span>Loading document</span>
          </motion.div>
        ) : showEmpty ? (
          <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <FadeIn>
              <EmptyState
                icon={<RefreshCw size={40} strokeWidth={1.25} />}
                title="No refinement yet"
                description="Load suggestions to see before/after quality scores, a side-by-side diff, and accept or reject the proposed FS."
                action={
                  <Link href={`/documents/${docId}`} className="btn btn-secondary">
                    Back to document
                  </Link>
                }
              />
            </FadeIn>
          </motion.div>
        ) : result ? (
          <motion.div
            key="result"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            style={{ display: "grid", gap: "1.5rem" }}
          >
            <FadeIn>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "1rem",
                  flexWrap: "wrap",
                }}
              >
                <div style={{ textAlign: "center" }}>
                  <QualityGauge score={originalScore} size={140} label="Before" />
                  <div className="page-subtitle" style={{ marginTop: 8 }}>
                    Before
                  </div>
                </div>
                <ArrowRight size={28} className="text-muted" style={{ color: "var(--text-muted)" }} />
                <div style={{ textAlign: "center" }}>
                  <QualityGauge score={refinedScore} size={140} label="After" />
                  <div className="page-subtitle" style={{ marginTop: 8 }}>
                    After
                  </div>
                </div>
              </div>
            </FadeIn>

            <FadeIn delay={0.05}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                  gap: "1rem",
                }}
              >
                <KpiCard
                  label="Overall improvement"
                  valueText={`${improvementDelta >= 0 ? "+" : ""}${improvementDelta.toFixed(1)} pts`}
                  icon={<TrendingUp size={20} />}
                  iconBg="var(--well-blue)"
                />
                <KpiCard
                  label="Changes (diff additions)"
                  value={changes}
                  icon={<ListChecks size={20} />}
                  iconBg="var(--well-purple)"
                />
              </div>
            </FadeIn>

            <FadeIn delay={0.1}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                <span className="page-subtitle" style={{ margin: 0 }}>
                  Proposed text
                </span>
                <Badge variant="accent">{changes} line changes</Badge>
              </div>
            </FadeIn>

            <FadeIn delay={0.12}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "1rem",
                  alignItems: "stretch",
                }}
              >
                <div style={panelStyle}>
                  <h3 className="page-subtitle" style={{ marginTop: 0, marginBottom: "0.75rem" }}>
                    Original
                  </h3>
                  <div
                    style={{
                      fontFamily: "var(--font-mono, monospace)",
                      fontSize: "0.8125rem",
                      lineHeight: 1.55,
                      maxHeight: 520,
                      overflow: "auto",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}
                  >
                    {originalLines.map((line, i) => (
                      <div key={`o-${i}`} className={origClass[i] || undefined}>
                        {line || " "}
                      </div>
                    ))}
                  </div>
                </div>
                <div style={panelStyle}>
                  <h3 className="page-subtitle" style={{ marginTop: 0, marginBottom: "0.75rem" }}>
                    Refined
                  </h3>
                  <div
                    style={{
                      fontFamily: "var(--font-mono, monospace)",
                      fontSize: "0.8125rem",
                      lineHeight: 1.55,
                      maxHeight: 520,
                      overflow: "auto",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}
                  >
                    {refinedLines.length === 0 ? (
                      <span className="text-muted" style={{ color: "var(--text-muted)" }}>
                        No refined text.
                      </span>
                    ) : (
                      refinedLines.map((line, i) => (
                        <div key={`r-${i}`} className={refClass[i] || undefined}>
                          {line || " "}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </FadeIn>

            <FadeIn delay={0.15}>
              <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={onReject}
                  disabled={saving}
                >
                  <XCircle size={18} style={{ marginRight: 8, verticalAlign: "middle" }} />
                  Reject
                </button>
                <button
                  type="button"
                  className="btn btn-success"
                  onClick={onAccept}
                  disabled={!result || saving}
                >
                  {saving ? (
                    <>
                      <span className="spinner" style={{ display: "inline-block", verticalAlign: "middle" }} />
                      <span style={{ marginLeft: 8 }}>Saving</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 size={18} style={{ marginRight: 8, verticalAlign: "middle" }} />
                      Accept and save
                    </>
                  )}
                </button>
              </div>
            </FadeIn>
          </motion.div>
        ) : (
          <motion.div
            key="loaded-waiting"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{ display: "grid", gap: "1rem" }}
          >
            {loading && (
              <div className="page-loading">
                <span className="spinner" />
                <span>Fetching suggestions</span>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {versions.length > 0 && (
        <FadeIn delay={0.18} style={{ marginTop: "2rem" }}>
          <button
            type="button"
            className="accordion-trigger"
            onClick={() => setShowVersions((v) => !v)}
            style={{ width: "100%", marginBottom: showVersions ? "0.75rem" : 0 }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <History size={18} aria-hidden />
              Version History ({versions.length})
            </span>
            <ChevronDown
              size={18}
              className={`accordion-chevron${showVersions ? " open" : ""}`}
              aria-hidden
            />
          </button>
          <AnimatePresence initial={false}>
            {showVersions && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.22 }}
                style={{ overflow: "hidden" }}
              >
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {versions.map((v) => (
                    <div
                      key={v.id}
                      className="card card-flat"
                      style={{
                        padding: "0.75rem 1rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.5rem",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap" }}>
                        <div>
                          <span style={{ fontWeight: 600, fontSize: "0.9375rem" }}>
                            Version {v.version_number}
                          </span>
                          <span style={{ color: "var(--text-muted)", fontSize: "0.8125rem", marginLeft: "0.5rem" }}>
                            {new Date(v.created_at).toLocaleString()}
                          </span>
                          {v.diff_summary && (
                            <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "0.15rem" }}>
                              {v.diff_summary}
                            </div>
                          )}
                        </div>
                        <div style={{ display: "flex", gap: "0.35rem", flexShrink: 0 }}>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => onPreviewVersion(v.id)}
                            style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                          >
                            <Eye size={14} aria-hidden />
                            {previewVersionId === v.id ? "Hide" : "View"}
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => onRevertVersion(v.id)}
                            disabled={reverting}
                            style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                          >
                            <RotateCcw size={14} aria-hidden />
                            Revert
                          </button>
                        </div>
                      </div>
                      {previewVersionId === v.id && previewText !== null && (
                        <div
                          style={{
                            fontFamily: "var(--font-mono, monospace)",
                            fontSize: "0.8rem",
                            lineHeight: 1.5,
                            maxHeight: 300,
                            overflow: "auto",
                            background: "var(--bg-main, #f8fafc)",
                            borderRadius: "var(--radius-sm)",
                            padding: "0.75rem",
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                            border: "1px solid var(--border-subtle)",
                          }}
                        >
                          {previewText || "(empty)"}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </FadeIn>
      )}
    </PageShell>
  );
}
