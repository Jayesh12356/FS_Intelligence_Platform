"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  listTasks,
  getDependencyGraph,
  getTraceability,
} from "@/lib/api";
import type {
  FSTaskItem,
  DependencyGraphData,
  TraceabilityData,
} from "@/lib/api";

// ── Config ─────────────────────────────────────────────

const effortConfig = {
  LOW: { color: "#22c55e", bg: "#22c55e18", label: "⚡ Low", border: "#22c55e44" },
  MEDIUM: { color: "#f59e0b", bg: "#f59e0b18", label: "⏱️ Medium", border: "#f59e0b44" },
  HIGH: { color: "#ef4444", bg: "#ef444418", label: "🔥 High", border: "#ef444444" },
  UNKNOWN: { color: "#6b7280", bg: "#6b728018", label: "❓ Unknown", border: "#6b728044" },
};

const tagColors: Record<string, { bg: string; color: string }> = {
  frontend: { bg: "#3b82f618", color: "#3b82f6" },
  backend: { bg: "#22c55e18", color: "#22c55e" },
  db: { bg: "#8b5cf618", color: "#8b5cf6" },
  auth: { bg: "#ef444418", color: "#ef4444" },
  api: { bg: "#f59e0b18", color: "#f59e0b" },
  testing: { bg: "#06b6d418", color: "#06b6d4" },
  security: { bg: "#ec489918", color: "#ec4899" },
  devops: { bg: "#6366f118", color: "#6366f1" },
  integration: { bg: "#14b8a618", color: "#14b8a6" },
  ui: { bg: "#a855f718", color: "#a855f7" },
  performance: { bg: "#f4735618", color: "#f47356" },
};

// ── Task Card Component ────────────────────────────────

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

  // Resolve dependency titles
  const depTitles = task.depends_on
    .map((id) => allTasks.find((t) => t.task_id === id))
    .filter(Boolean);

  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "12px",
        overflow: "hidden",
        transition: "all 0.2s ease",
        borderLeft: `4px solid ${eff.color}`,
      }}
    >
      {/* Header */}
      <div
        onClick={onToggle}
        style={{
          padding: "16px 20px",
          cursor: "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "12px",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            marginBottom: "6px",
            flexWrap: "wrap",
          }}>
            <span style={{
              fontSize: "0.72rem",
              fontWeight: 700,
              color: "var(--text-muted)",
              background: "var(--bg-tertiary)",
              padding: "2px 8px",
              borderRadius: "4px",
              fontFamily: "monospace",
            }}>
              #{task.order + 1}
            </span>
            <h3 style={{
              fontSize: "0.95rem",
              fontWeight: 600,
              color: "var(--text-primary)",
              margin: 0,
            }}>
              {task.title}
            </h3>
          </div>
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            flexWrap: "wrap",
          }}>
            {/* Effort badge */}
            <span style={{
              padding: "2px 10px",
              borderRadius: "8px",
              fontSize: "0.72rem",
              fontWeight: 600,
              background: eff.bg,
              color: eff.color,
              border: `1px solid ${eff.border}`,
            }}>
              {eff.label}
            </span>
            {/* Source section */}
            <span style={{
              fontSize: "0.75rem",
              color: "var(--text-muted)",
              fontWeight: 500,
            }}>
              §{task.section_index + 1} · {task.section_heading}
            </span>
            {/* Parallel badge */}
            {task.can_parallel && (
              <span style={{
                padding: "2px 8px",
                borderRadius: "8px",
                fontSize: "0.68rem",
                fontWeight: 600,
                background: "rgba(99, 102, 241, 0.1)",
                color: "#6366f1",
                border: "1px solid rgba(99, 102, 241, 0.3)",
              }}>
                ∥ Parallel
              </span>
            )}
            {/* Dependency count */}
            {task.depends_on.length > 0 && (
              <span style={{
                fontSize: "0.72rem",
                color: "var(--text-muted)",
              }}>
                🔗 {task.depends_on.length} dep{task.depends_on.length > 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
        {/* Tags */}
        <div style={{
          display: "flex",
          gap: "4px",
          flexWrap: "wrap",
          justifyContent: "flex-end",
          maxWidth: "200px",
        }}>
          {task.tags.slice(0, 4).map((tag) => {
            const tc = tagColors[tag] || { bg: "var(--bg-tertiary)", color: "var(--text-muted)" };
            return (
              <span
                key={tag}
                style={{
                  padding: "2px 8px",
                  borderRadius: "6px",
                  fontSize: "0.68rem",
                  fontWeight: 600,
                  background: tc.bg,
                  color: tc.color,
                }}
              >
                {tag}
              </span>
            );
          })}
        </div>
        {/* Expand icon */}
        <span style={{
          fontSize: "1.2rem",
          color: "var(--text-muted)",
          transition: "transform 0.2s ease",
          transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
        }}>
          ▾
        </span>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div style={{
          padding: "0 20px 20px",
          borderTop: "1px solid var(--border-subtle)",
          paddingTop: "16px",
        }}>
          {/* Description */}
          <div style={{ marginBottom: "16px" }}>
            <h4 style={{
              fontSize: "0.78rem",
              fontWeight: 700,
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "6px",
            }}>
              Description
            </h4>
            <p style={{
              fontSize: "0.88rem",
              color: "var(--text-secondary)",
              lineHeight: 1.7,
              margin: 0,
            }}>
              {task.description}
            </p>
          </div>

          {/* Acceptance Criteria */}
          {task.acceptance_criteria.length > 0 && (
            <div style={{ marginBottom: "16px" }}>
              <h4 style={{
                fontSize: "0.78rem",
                fontWeight: 700,
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: "8px",
              }}>
                Acceptance Criteria
              </h4>
              <ul style={{
                margin: 0,
                paddingLeft: "20px",
                display: "flex",
                flexDirection: "column",
                gap: "6px",
              }}>
                {task.acceptance_criteria.map((ac, i) => (
                  <li key={i} style={{
                    fontSize: "0.85rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.5,
                  }}>
                    {ac}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Dependencies */}
          {depTitles.length > 0 && (
            <div>
              <h4 style={{
                fontSize: "0.78rem",
                fontWeight: 700,
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: "8px",
              }}>
                Depends On
              </h4>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                {depTitles.map((dep) =>
                  dep ? (
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
                      <span style={{
                        fontFamily: "monospace",
                        fontSize: "0.72rem",
                        color: "var(--text-muted)",
                        background: "var(--bg-card)",
                        padding: "1px 6px",
                        borderRadius: "4px",
                      }}>
                        #{dep.order + 1}
                      </span>
                      {dep.title}
                    </div>
                  ) : null
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Dependency Tree Component ──────────────────────────

function DependencyTree({
  graph,
  tasks,
}: {
  graph: DependencyGraphData;
  tasks: FSTaskItem[];
}) {
  const taskMap = new Map(tasks.map((t) => [t.task_id, t]));

  // Group by depth level
  const depths = new Map<string, number>();

  function getDepth(nodeId: string): number {
    if (depths.has(nodeId)) return depths.get(nodeId)!;
    const deps = graph.adjacency[nodeId] || [];
    const validDeps = deps.filter((d) => graph.nodes.includes(d));
    const d = validDeps.length === 0 ? 0 : Math.max(...validDeps.map(getDepth)) + 1;
    depths.set(nodeId, d);
    return d;
  }

  graph.nodes.forEach(getDepth);

  // Group nodes by depth
  const levels = new Map<number, string[]>();
  depths.forEach((depth, nodeId) => {
    if (!levels.has(depth)) levels.set(depth, []);
    levels.get(depth)!.push(nodeId);
  });

  const sortedLevels = Array.from(levels.entries()).sort((a, b) => a[0] - b[0]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {sortedLevels.map(([level, nodeIds]) => (
        <div key={level}>
          <div style={{
            fontSize: "0.72rem",
            fontWeight: 700,
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            marginBottom: "8px",
          }}>
            Level {level + 1}
            {level === 0 && " (No dependencies)"}
          </div>
          <div style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "8px",
          }}>
            {nodeIds.map((nodeId) => {
              const task = taskMap.get(nodeId);
              if (!task) return null;
              const eff = effortConfig[task.effort] || effortConfig.UNKNOWN;
              return (
                <div
                  key={nodeId}
                  style={{
                    background: "var(--bg-card)",
                    border: `1px solid ${eff.border}`,
                    borderRadius: "10px",
                    padding: "10px 14px",
                    minWidth: "200px",
                    maxWidth: "320px",
                    borderLeft: `3px solid ${eff.color}`,
                  }}
                >
                  <div style={{
                    fontSize: "0.82rem",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    marginBottom: "4px",
                  }}>
                    #{task.order + 1} · {task.title}
                  </div>
                  <div style={{
                    display: "flex",
                    gap: "6px",
                    alignItems: "center",
                    fontSize: "0.72rem",
                    color: "var(--text-muted)",
                  }}>
                    <span style={{
                      padding: "1px 6px",
                      borderRadius: "4px",
                      background: eff.bg,
                      color: eff.color,
                      fontWeight: 600,
                    }}>
                      {eff.label}
                    </span>
                    {task.depends_on.length > 0 && (
                      <span>→ depends on {task.depends_on.length}</span>
                    )}
                    {task.can_parallel && <span>∥</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main Page Component ────────────────────────────────

export default function TaskBoardPage() {
  const params = useParams();
  const docId = params.id as string;
  const [tasks, setTasks] = useState<FSTaskItem[]>([]);
  const [graph, setGraph] = useState<DependencyGraphData | null>(null);
  const [traceability, setTraceability] = useState<TraceabilityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"tasks" | "dependencies" | "traceability">("tasks");

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [taskRes, graphRes, traceRes] = await Promise.all([
        listTasks(docId),
        getDependencyGraph(docId),
        getTraceability(docId),
      ]);
      setTasks(taskRes.data.tasks);
      setGraph(graphRes.data);
      setTraceability(traceRes.data);
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

  if (error || tasks.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">📋</div>
        <h3>Task Board</h3>
        <p>{error || "Run analysis first to generate dev tasks."}</p>
        <Link href={`/documents/${docId}`} className="btn btn-secondary btn-sm">
          ← Back to Document
        </Link>
      </div>
    );
  }

  // Stats
  const effortCounts = { LOW: 0, MEDIUM: 0, HIGH: 0, UNKNOWN: 0 };
  tasks.forEach((t) => {
    effortCounts[t.effort] = (effortCounts[t.effort] || 0) + 1;
  });
  const withDeps = tasks.filter((t) => t.depends_on.length > 0).length;
  const parallelCount = tasks.filter((t) => t.can_parallel).length;

  // Group traceability by section
  const traceBySection = new Map<number, { heading: string; tasks: string[] }>();
  if (traceability) {
    traceability.entries.forEach((e) => {
      if (!traceBySection.has(e.section_index)) {
        traceBySection.set(e.section_index, { heading: e.section_heading, tasks: [] });
      }
      traceBySection.get(e.section_index)!.tasks.push(e.task_title);
    });
  }

  return (
    <div style={{ maxWidth: "960px" }}>
      <Link href={`/documents/${docId}`} className="back-link">
        ← Back to Document
      </Link>

      {/* Header */}
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.8rem", fontWeight: 700, marginBottom: "0.25rem" }}>
          📋 Task Board
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem" }}>
          {tasks.length} dev tasks decomposed from FS requirements
        </p>
      </div>

      {/* Summary Stats */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
        gap: "1rem",
        marginBottom: "2rem",
      }}>
        <div className="info-item" style={{ borderLeft: "3px solid #6366f1" }}>
          <div className="info-label">Total Tasks</div>
          <div className="info-value" style={{ color: "#6366f1" }}>{tasks.length}</div>
        </div>
        <div className="info-item" style={{ borderLeft: "3px solid #22c55e" }}>
          <div className="info-label">Low Effort</div>
          <div className="info-value" style={{ color: "#22c55e" }}>{effortCounts.LOW}</div>
        </div>
        <div className="info-item" style={{ borderLeft: "3px solid #f59e0b" }}>
          <div className="info-label">Medium Effort</div>
          <div className="info-value" style={{ color: "#f59e0b" }}>{effortCounts.MEDIUM}</div>
        </div>
        <div className="info-item" style={{ borderLeft: "3px solid #ef4444" }}>
          <div className="info-label">High Effort</div>
          <div className="info-value" style={{ color: "#ef4444" }}>{effortCounts.HIGH}</div>
        </div>
        <div className="info-item" style={{ borderLeft: "3px solid #8b5cf6" }}>
          <div className="info-label">With Deps</div>
          <div className="info-value" style={{ color: "#8b5cf6" }}>{withDeps}</div>
        </div>
        <div className="info-item" style={{ borderLeft: "3px solid #06b6d4" }}>
          <div className="info-label">Parallel</div>
          <div className="info-value" style={{ color: "#06b6d4" }}>{parallelCount}</div>
        </div>
      </div>

      {/* Export Placeholder */}
      <div style={{
        display: "flex",
        gap: "10px",
        marginBottom: "1.5rem",
      }}>
        <button
          disabled
          style={{
            padding: "8px 20px",
            borderRadius: "8px",
            fontSize: "0.85rem",
            fontWeight: 600,
            background: "var(--bg-tertiary)",
            color: "var(--text-muted)",
            border: "1px solid var(--border-subtle)",
            cursor: "not-allowed",
            opacity: 0.6,
          }}
        >
          📤 Export to JIRA (L10)
        </button>
      </div>

      {/* Tabs */}
      <div style={{
        display: "flex",
        gap: "0",
        borderBottom: "1px solid var(--border-subtle)",
        marginBottom: "1.5rem",
      }}>
        {[
          { key: "tasks" as const, label: `📋 Tasks (${tasks.length})` },
          { key: "dependencies" as const, label: `🔗 Dependencies` },
          { key: "traceability" as const, label: `🗺️ Traceability` },
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

      {/* Tasks Tab */}
      {activeTab === "tasks" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {tasks.map((task) => (
            <TaskCard
              key={task.task_id}
              task={task}
              isExpanded={expandedId === task.task_id}
              onToggle={() =>
                setExpandedId(expandedId === task.task_id ? null : task.task_id)
              }
              allTasks={tasks}
            />
          ))}
        </div>
      )}

      {/* Dependencies Tab */}
      {activeTab === "dependencies" && graph && (
        <div>
          {graph.edges.length === 0 ? (
            <div className="empty-state" style={{ padding: "2rem" }}>
              <div className="empty-state-icon">🔗</div>
              <h3>No dependencies detected</h3>
              <p>All tasks can be worked on independently.</p>
            </div>
          ) : (
            <DependencyTree graph={graph} tasks={tasks} />
          )}
        </div>
      )}

      {/* Traceability Tab */}
      {activeTab === "traceability" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {traceBySection.size === 0 ? (
            <div className="empty-state" style={{ padding: "2rem" }}>
              <div className="empty-state-icon">🗺️</div>
              <h3>No traceability data</h3>
              <p>Run analysis to generate the traceability matrix.</p>
            </div>
          ) : (
            Array.from(traceBySection.entries())
              .sort((a, b) => a[0] - b[0])
              .map(([sectionIdx, data]) => (
                <div
                  key={sectionIdx}
                  style={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "12px",
                    padding: "16px 20px",
                    borderLeft: "3px solid var(--accent-primary)",
                  }}
                >
                  <h3 style={{
                    fontSize: "0.9rem",
                    fontWeight: 700,
                    marginBottom: "10px",
                    color: "var(--text-primary)",
                  }}>
                    §{sectionIdx + 1} · {data.heading}
                  </h3>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    {data.tasks.map((title, i) => (
                      <div
                        key={i}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                          padding: "6px 12px",
                          background: "var(--bg-tertiary)",
                          borderRadius: "8px",
                          fontSize: "0.84rem",
                          color: "var(--text-secondary)",
                        }}
                      >
                        <span style={{ color: "var(--text-muted)" }}>→</span>
                        {title}
                      </div>
                    ))}
                  </div>
                  <div style={{
                    marginTop: "8px",
                    fontSize: "0.72rem",
                    color: "var(--text-muted)",
                  }}>
                    {data.tasks.length} task{data.tasks.length > 1 ? "s" : ""} from this section
                  </div>
                </div>
              ))
          )}
        </div>
      )}
    </div>
  );
}
