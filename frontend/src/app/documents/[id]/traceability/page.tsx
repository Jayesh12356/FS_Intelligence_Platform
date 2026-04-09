"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  getTraceability,
  listTasks,
  TraceabilityEntry,
} from "@/lib/api";
import type { FSTaskItem } from "@/lib/api";

interface TaskInfo {
  task_id: string;
  title: string;
  section_index: number;
  section_heading: string;
}

export default function TraceabilityPage() {
  const params = useParams();
  const docId = params?.id as string;

  const [entries, setEntries] = useState<TraceabilityEntry[]>([]);
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!docId) return;
    try {
      setLoading(true);
      const [traceRes, taskRes] = await Promise.all([
        getTraceability(docId),
        listTasks(docId),
      ]);
      setEntries(traceRes.data?.entries || []);
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
    loadData();
  }, [loadData]);

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
      <div className="empty-state">
        <div className="empty-state-icon">⚠️</div>
        <h3>Error</h3>
        <p>{error}</p>
      </div>
    );
  }

  // Build matrix data: unique sections (rows) and tasks (columns)
  const sectionSet = new Map<number, string>();
  const taskSet = new Map<string, string>();

  // Add all tasks
  tasks.forEach((t) => taskSet.set(t.task_id, t.title));

  // Add all sections from entries and tasks
  entries.forEach((e) => sectionSet.set(e.section_index, e.section_heading));
  tasks.forEach((t) => {
    if (!sectionSet.has(t.section_index)) {
      sectionSet.set(t.section_index, t.section_heading);
    }
  });

  const sectionRows = Array.from(sectionSet.entries()).sort((a, b) => a[0] - b[0]);
  const taskCols = Array.from(taskSet.entries());

  // Build lookup set for linked cells
  const linkedSet = new Set<string>();
  entries.forEach((e) => linkedSet.add(`${e.section_index}-${e.task_id}`));

  // Find orphaned tasks (tasks with no traceability entry)
  const tracedTaskIds = new Set(entries.map((e) => e.task_id));
  const orphanedTasks = taskCols.filter(([tid]) => !tracedTaskIds.has(tid));

  // Find uncovered sections (sections with no tasks)
  const tracedSections = new Set(entries.map((e) => e.section_index));
  const uncoveredSections = sectionRows.filter(([idx]) => !tracedSections.has(idx));

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <Link href={`/documents/${docId}`} className="back-link">
        ← Back to Document
      </Link>

      <div className="page-header">
        <h1 className="page-title">🔗 Traceability Matrix</h1>
        <p className="page-subtitle">
          Rows = FS Sections, Columns = Tasks. Linked cells show requirement-to-task mapping.
        </p>
      </div>

      {/* Summary Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
        <div className="card" style={{ textAlign: "center" }}>
          <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--color-primary)" }}>{sectionRows.length}</div>
          <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Sections</div>
        </div>
        <div className="card" style={{ textAlign: "center" }}>
          <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--color-primary)" }}>{taskCols.length}</div>
          <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Tasks</div>
        </div>
        <div className="card" style={{ textAlign: "center" }}>
          <div style={{ fontSize: "2rem", fontWeight: 700, color: orphanedTasks.length > 0 ? "#f59e0b" : "#10b981" }}>
            {orphanedTasks.length}
          </div>
          <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Orphaned Tasks</div>
        </div>
        <div className="card" style={{ textAlign: "center" }}>
          <div style={{ fontSize: "2rem", fontWeight: 700, color: uncoveredSections.length > 0 ? "#ef4444" : "#10b981" }}>
            {uncoveredSections.length}
          </div>
          <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Uncovered Sections</div>
        </div>
      </div>

      {/* Warnings */}
      {orphanedTasks.length > 0 && (
        <div
          id="orphaned-warning"
          style={{
            padding: "0.75rem 1rem",
            borderRadius: "8px",
            background: "rgba(245, 158, 11, 0.1)",
            border: "1px solid rgba(245, 158, 11, 0.3)",
            marginBottom: "1rem",
            fontSize: "0.85rem",
          }}
        >
          <strong style={{ color: "#f59e0b" }}>⚠ Orphaned Tasks:</strong>{" "}
          {orphanedTasks.map(([tid, title]) => `${tid} (${title})`).join(", ")}
        </div>
      )}
      {uncoveredSections.length > 0 && (
        <div
          id="uncovered-warning"
          style={{
            padding: "0.75rem 1rem",
            borderRadius: "8px",
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            marginBottom: "1rem",
            fontSize: "0.85rem",
          }}
        >
          <strong style={{ color: "#ef4444" }}>❌ Uncovered Sections:</strong>{" "}
          {uncoveredSections.map(([idx, heading]) => `§${idx}: ${heading}`).join(", ")}
        </div>
      )}

      {/* Matrix table */}
      {sectionRows.length > 0 && taskCols.length > 0 ? (
        <div style={{ overflowX: "auto" }}>
          <table
            id="traceability-table"
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "0.8rem",
            }}
          >
            <thead>
              <tr>
                <th
                  style={{
                    padding: "8px 12px",
                    background: "var(--glass-bg)",
                    border: "1px solid var(--glass-border)",
                    position: "sticky",
                    left: 0,
                    zIndex: 1,
                    textAlign: "left",
                    minWidth: 180,
                  }}
                >
                  Section ↓ / Task →
                </th>
                {taskCols.map(([tid, title]) => (
                  <th
                    key={tid}
                    style={{
                      padding: "6px 8px",
                      background: "var(--glass-bg)",
                      border: "1px solid var(--glass-border)",
                      writingMode: "vertical-rl",
                      textOrientation: "mixed",
                      transform: "rotate(180deg)",
                      maxHeight: 120,
                      fontSize: "0.7rem",
                      whiteSpace: "nowrap",
                    }}
                    title={title}
                  >
                    {tid}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sectionRows.map(([sIdx, sHeading]) => {
                const isUncovered = !tracedSections.has(sIdx);
                return (
                  <tr key={sIdx}>
                    <td
                      style={{
                        padding: "6px 12px",
                        border: "1px solid var(--glass-border)",
                        position: "sticky",
                        left: 0,
                        background: isUncovered
                          ? "rgba(239, 68, 68, 0.08)"
                          : "var(--bg-primary)",
                        fontWeight: 500,
                        whiteSpace: "nowrap",
                      }}
                    >
                      §{sIdx}: {sHeading.substring(0, 30)}{sHeading.length > 30 ? "…" : ""}
                    </td>
                    {taskCols.map(([tid]) => {
                      const isLinked = linkedSet.has(`${sIdx}-${tid}`);
                      return (
                        <td
                          key={`${sIdx}-${tid}`}
                          style={{
                            padding: "4px",
                            border: "1px solid var(--glass-border)",
                            textAlign: "center",
                            background: isLinked
                              ? "rgba(139, 92, 246, 0.2)"
                              : "transparent",
                            cursor: "default",
                          }}
                          title={isLinked ? `${sHeading} → ${tid}` : "Not linked"}
                        >
                          {isLinked ? "✓" : ""}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-state">
          <div className="empty-state-icon">🔗</div>
          <h3>No traceability data</h3>
          <p>Run analysis first to generate the traceability matrix.</p>
        </div>
      )}
    </div>
  );
}
