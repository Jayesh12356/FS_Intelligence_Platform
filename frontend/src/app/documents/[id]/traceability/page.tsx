"use client";

import { useEffect, useState, useCallback, type CSSProperties } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getTraceability, listTasks } from "@/lib/api";
import type { TraceabilityData, TraceabilityEntry, FSTaskItem } from "@/lib/api";
import { PageShell, KpiCard, FadeIn, EmptyState } from "@/components/index";
import { motion } from "framer-motion";
import { Link2, CheckCircle2, AlertTriangle, Layers } from "lucide-react";

interface TaskInfo {
  task_id: string;
  title: string;
  section_index: number;
  section_heading: string;
}

function truncateHeading(s: string, max = 48) {
  if (s.length <= max) return s;
  return `${s.slice(0, max)}…`;
}

export default function TraceabilityPage() {
  const params = useParams();
  const docId = params?.id as string;

  const [entries, setEntries] = useState<TraceabilityEntry[]>([]);
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTraceability = useCallback(async () => {
    if (!docId) return;
    try {
      setLoading(true);
      const [traceRes, taskRes] = await Promise.all([
        getTraceability(docId),
        listTasks(docId),
      ]);
      const data: TraceabilityData | undefined = traceRes.data;
      setEntries(data?.entries || []);
      const taskInfos: TaskInfo[] = (taskRes.data?.tasks || []).map((t: FSTaskItem) => ({
        task_id: t.task_id,
        title: t.title,
        section_index: t.section_index,
        section_heading: t.section_heading,
      }));
      setTasks(taskInfos);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    fetchTraceability();
  }, [fetchTraceability]);

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        Loading traceability matrix…
      </div>
    );
  }

  if (error) {
    return (
      <PageShell
        backHref={`/documents/${docId}`}
        backLabel="Back to Document"
        title="Traceability Matrix"
        maxWidth={1200}
      >
        <FadeIn>
          <EmptyState
            icon={<AlertTriangle size={40} strokeWidth={1.25} aria-hidden />}
            title="Error"
            description={error}
            action={
              <Link href={`/documents/${docId}`} className="btn btn-primary btn-sm">
                Back to Document
              </Link>
            }
          />
        </FadeIn>
      </PageShell>
    );
  }

  const sectionSet = new Map<number, string>();
  const taskSet = new Map<string, string>();

  tasks.forEach((t) => taskSet.set(t.task_id, t.title));

  entries.forEach((e) => sectionSet.set(e.section_index, e.section_heading));
  tasks.forEach((t) => {
    if (!sectionSet.has(t.section_index)) {
      sectionSet.set(t.section_index, t.section_heading);
    }
  });

  const sectionRows = Array.from(sectionSet.entries()).sort((a, b) => a[0] - b[0]);
  const taskCols = Array.from(taskSet.entries());

  const linkedSet = new Set<string>();
  entries.forEach((e) => linkedSet.add(`${e.section_index}-${e.task_id}`));

  const tracedTaskIds = new Set(entries.map((e) => e.task_id));
  const orphanedTasks = taskCols.filter(([tid]) => !tracedTaskIds.has(tid));

  const tracedSections = new Set(entries.map((e) => e.section_index));
  const uncoveredSections = sectionRows.filter(([idx]) => !tracedSections.has(idx));

  void orphanedTasks;

  const totalSections = sectionRows.length;
  const sectionsWithMappings = tracedSections.size;
  const coveragePct =
    totalSections > 0 ? Math.round((sectionsWithMappings / totalSections) * 100) : 0;
  const totalMappings = entries.length;
  const orphanSectionCount = uncoveredSections.length;

  const stickyCornerTh: CSSProperties = {
    position: "sticky",
    left: 0,
    top: 0,
    zIndex: 4,
    minWidth: 200,
    background: "var(--bg-tertiary)",
    boxShadow: "1px 0 0 var(--border-subtle)",
  };

  const stickyFirstTd = (isUncovered: boolean): CSSProperties => ({
    position: "sticky",
    left: 0,
    zIndex: 2,
    fontWeight: 500,
    background: isUncovered ? "var(--bg-warning-subtle)" : "var(--bg-card)",
    boxShadow: "1px 0 0 var(--border-subtle)",
  });

  return (
    <PageShell
      backHref={`/documents/${docId}`}
      backLabel="Back to Document"
      title="Traceability Matrix"
      subtitle="Rows are FS sections, columns are tasks. A green check means that section is linked to that task in the traceability data."
      maxWidth={1200}
    >
      <>
        <div className="kpi-row" style={{ marginBottom: "1.25rem" }}>
          <KpiCard
            label="Coverage"
            valueText={totalSections > 0 ? `${coveragePct}%` : "—"}
            icon={<CheckCircle2 size={20} aria-hidden />}
            iconBg="var(--well-green)"
            delay={0}
          />
          <KpiCard
            label="Sections"
            value={totalSections}
            icon={<Layers size={20} aria-hidden />}
            iconBg="var(--well-blue)"
            delay={0.05}
          />
          <KpiCard
            label="Total mappings"
            value={totalMappings}
            icon={<Link2 size={20} aria-hidden />}
            iconBg="var(--well-purple)"
            delay={0.1}
          />
          <KpiCard
            label="Orphan sections"
            value={orphanSectionCount}
            icon={<AlertTriangle size={20} aria-hidden />}
            iconBg={orphanSectionCount > 0 ? "var(--well-amber)" : "var(--well-green)"}
            delay={0.15}
          />
        </div>

        {uncoveredSections.length > 0 && (
          <motion.div
            className="alert alert-warning"
            role="alert"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
            style={{ marginBottom: "1.25rem" }}
          >
            <AlertTriangle size={20} aria-hidden style={{ flexShrink: 0, marginTop: "0.125rem" }} />
            <div>
              <strong>Orphan sections</strong>
              <p style={{ margin: "0.35rem 0 0", fontSize: "0.8125rem", lineHeight: 1.5 }}>
                These sections have no task mappings yet:{" "}
                {uncoveredSections.map(([idx, heading]) => `${idx}: ${heading}`).join("; ")}
              </p>
            </div>
          </motion.div>
        )}

        {sectionRows.length > 0 && taskCols.length > 0 ? (
          <FadeIn delay={0.06}>
            <div className="table-wrap">
              <table id="traceability-table">
                <thead>
                  <tr>
                    <th scope="col" style={stickyCornerTh}>
                      Section
                    </th>
                    {taskCols.map(([tid, title]) => (
                      <th
                        key={tid}
                        scope="col"
                        title={title}
                        style={{
                          maxWidth: "11rem",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          verticalAlign: "bottom",
                        }}
                      >
                        {truncateHeading(title, 56)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sectionRows.map(([sIdx, sHeading]) => {
                    const isUncovered = !tracedSections.has(sIdx);
                    return (
                      <tr key={sIdx}>
                        <td style={stickyFirstTd(isUncovered)} title={`${sIdx}: ${sHeading}`}>
                          {truncateHeading(`${sIdx}: ${sHeading}`, 64)}
                        </td>
                        {taskCols.map(([tid]) => {
                          const isLinked = linkedSet.has(`${sIdx}-${tid}`);
                          return (
                            <td
                              key={`${sIdx}-${tid}`}
                              style={{ textAlign: "center", verticalAlign: "middle" }}
                              title={
                                isLinked
                                  ? `${sHeading} mapped to ${tid}`
                                  : "Not linked"
                              }
                            >
                              {isLinked ? (
                                <CheckCircle2
                                  size={18}
                                  aria-label="Mapped"
                                  style={{ color: "var(--success)", display: "inline-block", flexShrink: 0 }}
                                />
                              ) : null}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </FadeIn>
        ) : (
          <FadeIn delay={0.06}>
            <EmptyState
              icon={<Link2 size={40} strokeWidth={1.25} aria-hidden />}
              title="No traceability data"
              description="Run analysis first to generate the traceability matrix."
            />
          </FadeIn>
        )}
      </>
    </PageShell>
  );
}
