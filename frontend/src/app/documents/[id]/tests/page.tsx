"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  TestTube2,
  Download,
  AlertTriangle,
  ChevronDown,
  Loader2,
} from "lucide-react";
import { PageShell, KpiCard, FadeIn, EmptyState } from "@/components/index";
import Badge from "@/components/Badge";
import { motion, AnimatePresence } from "framer-motion";
import { listTestCases, type TestCase, type TestCaseListData } from "@/lib/api";

export default function TestCasesPage() {
  const params = useParams();
  const docId = params.id as string;
  const [data, setData] = useState<TestCaseListData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());

  const fetchTestCases = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listTestCases(docId);
      setData(res.data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load test cases");
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    if (docId) fetchTestCases();
  }, [docId, fetchTestCases]);

  const grouped = useMemo(() => {
    if (!data?.test_cases) return new Map<string, TestCase[]>();
    const map = new Map<string, TestCase[]>();
    for (const tc of data.test_cases) {
      const key = tc.task_id || "unassigned";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(tc);
    }
    return map;
  }, [data]);

  const toggleTask = (taskId: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  };

  const expandAll = () => setExpandedTasks(new Set(grouped.keys()));
  const collapseAll = () => setExpandedTasks(new Set());

  const handleExportCSV = () => {
    if (!data?.test_cases?.length) return;
    const headers = ["Task ID", "Title", "Type", "Preconditions", "Steps", "Expected Result", "Section"];
    const rows = data.test_cases.map((tc) => [
      tc.task_id,
      tc.title,
      tc.test_type,
      tc.preconditions,
      tc.steps.join(" -> "),
      tc.expected_result,
      tc.section_heading,
    ]);
    const csvContent = [headers, ...rows]
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `test-cases-${docId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <PageShell backHref={`/documents/${docId}`} backLabel="Document" title="Test Cases">
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 size={28} className="spin" style={{ color: "var(--text-tertiary)" }} />
        </div>
      </PageShell>
    );
  }

  if (error) {
    return (
      <PageShell backHref={`/documents/${docId}`} backLabel="Document" title="Test Cases">
        <EmptyState
          icon={<AlertTriangle size={40} strokeWidth={1.25} aria-hidden />}
          title="Failed to load test cases"
          description={error}
          action={
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => fetchTestCases()}
              >
                Retry
              </button>
              <Link href={`/documents/${docId}`} className="btn btn-secondary btn-sm">
                Back to Document
              </Link>
            </div>
          }
        />
      </PageShell>
    );
  }

  if (!data?.test_cases?.length) {
    return (
      <PageShell backHref={`/documents/${docId}`} backLabel="Document" title="Test Cases">
        <EmptyState
          icon={<TestTube2 size={40} strokeWidth={1.25} aria-hidden />}
          title="No test cases yet"
          description="Run analysis first to generate test cases from the task decomposition."
          action={
            <Link href={`/documents/${docId}`} className="btn btn-primary btn-sm">
              Back to Document
            </Link>
          }
        />
      </PageShell>
    );
  }

  return (
    <PageShell
      backHref={`/documents/${docId}`}
      backLabel="Document"
      title="Test Cases"
      subtitle={`${data.total} test cases across ${grouped.size} tasks`}
      actions={
        <button className="btn btn-secondary btn-sm" onClick={handleExportCSV} style={{ gap: "0.4rem" }}>
          <Download size={14} />
          Export CSV
        </button>
      }
    >
      {/* Type breakdown */}
      <FadeIn delay={0.04}>
        <div className="kpi-row">
          {Object.entries(data.by_type).map(([type, count], i) => (
            <KpiCard
              key={type}
              label={type}
              value={count}
              icon={<TestTube2 size={20} aria-hidden />}
              iconBg="var(--well-blue)"
              delay={i * 0.05}
            />
          ))}
        </div>
      </FadeIn>

      {/* Controls */}
      <FadeIn delay={0.08}>
        <div style={{ display: "flex", gap: "0.5rem", margin: "1rem 0" }}>
          <button type="button" onClick={expandAll} className="btn btn-secondary btn-sm">Expand all</button>
          <button type="button" onClick={collapseAll} className="btn btn-secondary btn-sm">Collapse all</button>
        </div>
      </FadeIn>

      {/* Grouped test cases */}
      <FadeIn delay={0.12}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {Array.from(grouped.entries()).map(([taskId, cases]) => {
            const expanded = expandedTasks.has(taskId);
            return (
              <div key={taskId} className="accordion-item">
                <button
                  type="button"
                  className="accordion-trigger"
                  onClick={() => toggleTask(taskId)}
                  aria-expanded={expanded}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontWeight: 600 }}>{taskId}</span>
                    <Badge variant="info">{cases.length} tests</Badge>
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
                      key="content"
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
                      style={{ overflow: "hidden" }}
                    >
                      <div className="accordion-content" style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                        {cases.map((tc, i) => (
                          <div key={tc.id || i} style={{
                            padding: "0.75rem", borderRadius: "var(--radius-md)",
                            background: "var(--bg-main)", border: "1px solid var(--border-subtle)",
                          }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                              <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>{tc.title}</span>
                              <Badge variant="info">{tc.test_type}</Badge>
                            </div>
                            {tc.preconditions && (
                              <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0 0 0.35rem" }}>
                                <strong>Preconditions:</strong> {tc.preconditions}
                              </p>
                            )}
                            {tc.steps.length > 0 && (
                              <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0 0 0.35rem" }}>
                                <strong>Steps:</strong>
                                <ol style={{ margin: "0.25rem 0 0", paddingLeft: "1.25rem" }}>
                                  {tc.steps.map((step, si) => <li key={si}>{step}</li>)}
                                </ol>
                              </div>
                            )}
                            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0.35rem 0 0" }}>
                              <strong>Expected:</strong> {tc.expected_result}
                            </p>
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </FadeIn>
    </PageShell>
  );
}
