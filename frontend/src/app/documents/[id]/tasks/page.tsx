"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { listTasks, getDependencyGraph, getTraceability } from "@/lib/api";
import type { FSTaskItem, DependencyGraphData, TraceabilityData } from "@/lib/api";
import {
  PageShell,
  KpiCard,
  Tabs,
  FadeIn,
  StaggerList,
  StaggerItem,
  EmptyState,
} from "@/components/index";
import Badge from "@/components/Badge";
import { motion, AnimatePresence } from "framer-motion";
import {
  ListTodo,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ChevronDown,
  Zap,
  Flame,
  HelpCircle,
  GitBranch,
  Table,
} from "lucide-react";

type EffortKey = "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";

const effortConfig: Record<
  EffortKey,
  {
    color: string;
    bg: string;
    label: string;
    border: string;
    variant: "success" | "warning" | "error" | "neutral";
    Icon: typeof Zap;
  }
> = {
  LOW: { color: "#15803d", bg: "#22c55e18", label: "Low", border: "#22c55e44", variant: "success", Icon: Zap },
  MEDIUM: { color: "#b45309", bg: "#f59e0b18", label: "Medium", border: "#f59e0b44", variant: "warning", Icon: Clock },
  HIGH: { color: "#b91c1c", bg: "#ef444418", label: "High", border: "#ef444444", variant: "error", Icon: Flame },
  UNKNOWN: { color: "#374151", bg: "#6b728018", label: "Unknown", border: "#6b728044", variant: "neutral", Icon: HelpCircle },
};

// AA-compliant ~700-shade text on the matching ~9%-tinted backgrounds.
// We keep the lighter ~500 token only for borders/icons; small caption
// text uses the darker shade so axe color-contrast passes (>= 4.5:1).
const tagColors: Record<string, { bg: string; color: string }> = {
  frontend: { bg: "#3b82f618", color: "#1d4ed8" },
  backend: { bg: "#22c55e18", color: "#15803d" },
  db: { bg: "#8b5cf618", color: "#6d28d9" },
  auth: { bg: "#ef444418", color: "#b91c1c" },
  api: { bg: "#f59e0b18", color: "#b45309" },
  testing: { bg: "#06b6d418", color: "#0e7490" },
  security: { bg: "#ec489918", color: "#be185d" },
  devops: { bg: "#6366f118", color: "#4338ca" },
  integration: { bg: "#14b8a618", color: "#0f766e" },
  ui: { bg: "#a855f718", color: "#7e22ce" },
  performance: { bg: "#f4735618", color: "#c2410c" },
};

function TaskCard({
  task,
  isExpanded,
  onToggle,
  allTasks,
}: {
  task: FSTaskItem;
  isExpanded: boolean;
  onToggle: () => void;
  allTasks: FSTaskItem[];
}) {
  const eff = effortConfig[task.effort] || effortConfig.UNKNOWN;
  const EffIcon = eff.Icon;
  const depTitles = task.depends_on
    .map((id) => allTasks.find((t) => t.task_id === id))
    .filter(Boolean) as FSTaskItem[];

  return (
    <div
      className="card overflow-hidden"
      style={{
        padding: 0,
        borderLeft: `4px solid ${eff.color}`,
      }}
    >
      <button
        type="button"
        onClick={onToggle}
        style={{
          width: "100%",
          textAlign: "left",
          padding: "16px 20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "12px",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          color: "inherit",
          font: "inherit",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              marginBottom: "6px",
              flexWrap: "wrap",
            }}
          >
            <span
              style={{
                fontSize: "0.72rem",
                fontWeight: 700,
                color: "var(--text-muted)",
                background: "var(--bg-tertiary)",
                padding: "2px 8px",
                borderRadius: "4px",
                fontFamily: "monospace",
              }}
            >
              #{task.order + 1}
            </span>
            <h3
              style={{
                fontSize: "0.95rem",
                fontWeight: 600,
                color: "var(--text-primary)",
                margin: 0,
              }}
            >
              {task.title}
            </h3>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              flexWrap: "wrap",
            }}
          >
            <Badge
              variant={eff.variant}
              style={{
                background: eff.bg,
                color: eff.color,
                border: `1px solid ${eff.border}`,
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              <EffIcon size={12} strokeWidth={2.5} aria-hidden />
              {eff.label}
            </Badge>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 500 }}>
              Section {task.section_index + 1} · {task.section_heading}
            </span>
            {task.can_parallel && (
              <Badge variant="accent">Parallel</Badge>
            )}
            {task.depends_on.length > 0 && (
              <span
                style={{
                  fontSize: "0.72rem",
                  color: "var(--text-muted)",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                <GitBranch size={12} aria-hidden />
                {task.depends_on.length} dep{task.depends_on.length > 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
        <div
          style={{
            display: "flex",
            gap: "4px",
            flexWrap: "wrap",
            justifyContent: "flex-end",
            maxWidth: "200px",
          }}
        >
          {task.tags.slice(0, 4).map((tag) => {
            const tc = tagColors[tag] || {
              bg: "var(--bg-tertiary)",
              color: "var(--text-muted)",
            };
            return (
              <Badge
                key={tag}
                variant="neutral"
                style={{
                  background: tc.bg,
                  color: tc.color,
                  border: `1px solid ${tc.color}33`,
                }}
              >
                {tag}
              </Badge>
            );
          })}
        </div>
        <motion.span
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          style={{ display: "flex", color: "var(--text-muted)", flexShrink: 0 }}
          aria-hidden
        >
          <ChevronDown size={20} />
        </motion.span>
      </button>

      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            key="expanded"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: "hidden", borderTop: "1px solid var(--border-subtle)" }}
          >
            <div style={{ padding: "16px 20px 20px" }}>
              <div style={{ marginBottom: "16px" }}>
                <h4
                  style={{
                    fontSize: "0.78rem",
                    fontWeight: 700,
                    color: "var(--text-muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    marginBottom: "6px",
                  }}
                >
                  Description
                </h4>
                <p
                  style={{
                    fontSize: "0.88rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.7,
                    margin: 0,
                  }}
                >
                  {task.description}
                </p>
              </div>

              {task.acceptance_criteria.length > 0 && (
                <div style={{ marginBottom: "16px" }}>
                  <h4
                    style={{
                      fontSize: "0.78rem",
                      fontWeight: 700,
                      color: "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      marginBottom: "8px",
                    }}
                  >
                    Acceptance Criteria
                  </h4>
                  <ul
                    style={{
                      margin: 0,
                      paddingLeft: "20px",
                      display: "flex",
                      flexDirection: "column",
                      gap: "6px",
                    }}
                  >
                    {task.acceptance_criteria.map((ac, i) => (
                      <li
                        key={i}
                        style={{
                          fontSize: "0.85rem",
                          color: "var(--text-secondary)",
                          lineHeight: 1.5,
                        }}
                      >
                        {ac}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {depTitles.length > 0 && (
                <div>
                  <h4
                    style={{
                      fontSize: "0.78rem",
                      fontWeight: 700,
                      color: "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      marginBottom: "8px",
                    }}
                  >
                    Depends On
                  </h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    {depTitles.map((dep) => (
                      <div
                        key={dep.task_id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                          padding: "6px 12px",
                          background: "var(--bg-tertiary)",
                          borderRadius: "8px",
                          fontSize: "0.82rem",
                          color: "var(--text-secondary)",
                        }}
                      >
                        <span
                          style={{
                            fontFamily: "monospace",
                            fontSize: "0.72rem",
                            color: "var(--text-muted)",
                            background: "var(--bg-card)",
                            padding: "1px 6px",
                            borderRadius: "4px",
                          }}
                        >
                          #{dep.order + 1}
                        </span>
                        {dep.title}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function DependencyGraphList({
  graph,
  tasks,
}: {
  graph: DependencyGraphData;
  tasks: FSTaskItem[];
}) {
  const taskMap = new Map(tasks.map((t) => [t.task_id, t]));
  const nodeSet = new Set(graph.nodes);
  const rows = graph.nodes
    .map((id) => taskMap.get(id))
    .filter((t): t is FSTaskItem => Boolean(t))
    .sort((a, b) => a.order - b.order);

  return (
    <ul
      style={{
        listStyle: "none",
        padding: 0,
        margin: 0,
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
    >
      {rows.map((task) => {
        const depIds = (graph.adjacency[task.task_id] || []).filter((id) => nodeSet.has(id));
        const depTasks = depIds
          .map((id) => taskMap.get(id))
          .filter((t): t is FSTaskItem => Boolean(t));

        return (
          <li key={task.task_id}>
            <div className="card" style={{ padding: "1rem 1.25rem" }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: "10px" }}>
                <div
                  style={{
                    width: 3,
                    alignSelf: "stretch",
                    minHeight: 24,
                    borderRadius: 2,
                    background: "var(--accent-primary)",
                    opacity: 0.45,
                    flexShrink: 0,
                  }}
                  aria-hidden
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    #{task.order + 1} · {task.title}
                  </div>
                  {depTasks.length > 0 ? (
                    <div
                      style={{
                        marginTop: "12px",
                        paddingLeft: "14px",
                        borderLeft: "2px solid var(--border-subtle)",
                      }}
                    >
                      <div
                        style={{
                          fontSize: "0.72rem",
                          fontWeight: 700,
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                          color: "var(--text-muted)",
                          marginBottom: "8px",
                        }}
                      >
                        Dependencies
                      </div>
                      <ul
                        style={{
                          listStyle: "none",
                          padding: 0,
                          margin: 0,
                          display: "flex",
                          flexDirection: "column",
                          gap: "6px",
                        }}
                      >
                        {depTasks.map((d) => (
                          <li
                            key={d.task_id}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "8px",
                              fontSize: "0.84rem",
                              color: "var(--text-secondary)",
                              paddingLeft: 4,
                              borderLeft: "2px solid var(--border-subtle)",
                              marginLeft: 2,
                            }}
                          >
                            <GitBranch size={14} style={{ opacity: 0.55, flexShrink: 0 }} aria-hidden />
                            <span style={{ fontFamily: "monospace", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                              #{d.order + 1}
                            </span>
                            {d.title}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <p style={{ margin: "8px 0 0", fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                      No dependencies
                    </p>
                  )}
                </div>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export default function TaskBoardPage() {
  const params = useParams();
  const docId = params.id as string;
  const [tasks, setTasks] = useState<FSTaskItem[]>([]);
  const [depGraph, setDepGraph] = useState<DependencyGraphData | null>(null);
  const [traceability, setTraceability] = useState<TraceabilityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedTasks, setExpandedTasks] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"tasks" | "dependencies" | "traceability">("tasks");

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [tasksSettled, graphSettled, traceSettled] = await Promise.allSettled([
        listTasks(docId),
        getDependencyGraph(docId),
        getTraceability(docId),
      ]);

      if (tasksSettled.status === "rejected") {
        const err = tasksSettled.reason;
        setError(err instanceof Error ? err.message : "Failed to load task data");
        setTasks([]);
        setDepGraph(null);
        setTraceability(null);
        return;
      }

      setTasks(tasksSettled.value.data.tasks ?? []);
      if (graphSettled.status === "fulfilled") {
        setDepGraph(graphSettled.value.data);
      } else {
        setDepGraph(null);
      }
      if (traceSettled.status === "fulfilled") {
        setTraceability(traceSettled.value.data);
      } else {
        setTraceability(null);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load task data");
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    if (docId) fetchData();
  }, [docId, fetchData]);

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        Loading task board…
      </div>
    );
  }

  if (error) {
    return (
      <PageShell backHref={`/documents/${docId}`} title="Task Board" maxWidth={960}>
        <FadeIn>
          <EmptyState
            icon={<AlertTriangle size={40} strokeWidth={1.5} />}
            title="Couldn’t load tasks"
            description={error}
            action={
              <Link href={`/documents/${docId}`} className="btn btn-secondary btn-sm">
                Back to Document
              </Link>
            }
          />
        </FadeIn>
      </PageShell>
    );
  }

  if (tasks.length === 0) {
    return (
      <PageShell backHref={`/documents/${docId}`} title="Task Board" maxWidth={960}>
        <FadeIn>
          <EmptyState
            icon={<ListTodo size={40} strokeWidth={1.5} />}
            title="No tasks found"
            description="Run analysis on this document first to generate tasks."
            action={
              <Link href={`/documents/${docId}`} className="btn btn-secondary btn-sm">
                Go to document
              </Link>
            }
          />
        </FadeIn>
      </PageShell>
    );
  }

  const readyCount = tasks.filter((t) => t.depends_on.length === 0).length;
  const highEffortCount = tasks.filter((t) => t.effort === "HIGH").length;
  const depEdgeCount = depGraph?.edges.length ?? 0;

  const traceRows =
    traceability?.entries.slice().sort((a, b) => {
      if (a.section_index !== b.section_index) return a.section_index - b.section_index;
      return a.task_title.localeCompare(b.task_title);
    }) ?? [];

  return (
    <PageShell
      backHref={`/documents/${docId}`}
      title="Task Board"
      subtitle={`${tasks.length} dev tasks decomposed from FS requirements`}
      maxWidth={960}
    >
      <div className="kpi-row">
        <KpiCard
          label="Total Tasks"
          value={tasks.length}
          icon={<ListTodo size={22} />}
          iconBg="rgba(99, 102, 241, 0.2)"
          delay={0}
        />
        <KpiCard
          label="Completed (where task has no blockers)"
          value={readyCount}
          icon={<CheckCircle2 size={22} />}
          iconBg="rgba(34, 197, 94, 0.2)"
          delay={0.05}
        />
        <KpiCard
          label="High Effort"
          value={highEffortCount}
          icon={<Flame size={22} />}
          iconBg="rgba(239, 68, 68, 0.2)"
          delay={0.1}
        />
        <KpiCard
          label="Dependencies"
          value={depEdgeCount}
          icon={<GitBranch size={22} />}
          iconBg="rgba(139, 92, 246, 0.2)"
          delay={0.15}
        />
      </div>

      <div style={{ marginBottom: "1.5rem" }}>
        <Tabs
          items={[
            { key: "tasks", label: "All Tasks", count: tasks.length },
            { key: "dependencies", label: "Dependencies" },
            { key: "traceability", label: "Traceability" },
          ]}
          active={activeTab}
          onChange={(key) => setActiveTab(key as typeof activeTab)}
        />
      </div>

      {activeTab === "tasks" && (
        <FadeIn>
          <StaggerList style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {tasks.map((task) => (
              <StaggerItem key={task.task_id}>
                <TaskCard
                  task={task}
                  isExpanded={expandedTasks === task.task_id}
                  onToggle={() =>
                    setExpandedTasks(expandedTasks === task.task_id ? null : task.task_id)
                  }
                  allTasks={tasks}
                />
              </StaggerItem>
            ))}
          </StaggerList>
        </FadeIn>
      )}

      {activeTab === "dependencies" && depGraph && (
        <FadeIn>
          {depGraph.edges.length === 0 ? (
            <EmptyState
              icon={<GitBranch size={40} strokeWidth={1.5} />}
              title="No dependencies detected"
              description="All tasks can be worked on independently."
            />
          ) : (
            <DependencyGraphList graph={depGraph} tasks={tasks} />
          )}
        </FadeIn>
      )}

      {activeTab === "traceability" && (
        <FadeIn>
          {traceRows.length === 0 ? (
            <EmptyState
              icon={<Table size={40} strokeWidth={1.5} />}
              title="No traceability data"
              description="Run analysis to generate the traceability matrix."
            />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Section</th>
                    <th>Section heading</th>
                    <th>Task</th>
                  </tr>
                </thead>
                <tbody>
                  {traceRows.map((row) => (
                    <tr key={`${row.task_id}-${row.section_index}`}>
                      <td style={{ fontFamily: "monospace", fontSize: "0.8125rem" }}>{row.section_index + 1}</td>
                      <td>{row.section_heading}</td>
                      <td>{row.task_title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </FadeIn>
      )}
    </PageShell>
  );
}
