"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { getAnalysisProgress } from "@/lib/api";
import type { AnalysisProgress as ProgressData } from "@/lib/api";
import {
  CheckCircle2,
  Loader2,
  Circle,
  ChevronDown,
  Terminal,
  XCircle,
} from "lucide-react";

const NODE_ORDER = [
  "parse_node",
  "ambiguity_node",
  "debate_node",
  "contradiction_node",
  "edge_case_node",
  "quality_node",
  "task_decomposition_node",
  "dependency_node",
  "traceability_node",
  "duplicate_node",
  "testcase_node",
];

const FALLBACK_LABELS: Record<string, string> = {
  parse_node: "Loading Sections",
  ambiguity_node: "Detecting Ambiguities",
  debate_node: "Adversarial Debate",
  contradiction_node: "Cross-Reference Contradictions",
  edge_case_node: "Edge Case Analysis",
  quality_node: "Quality Scoring",
  task_decomposition_node: "Task Decomposition",
  dependency_node: "Dependency Mapping",
  traceability_node: "Traceability Matrix",
  duplicate_node: "Duplicate Detection",
  testcase_node: "Test Case Generation",
};

interface Props {
  docId: string;
  isAnalyzing: boolean;
  onCancel?: () => void;
  cancelling?: boolean;
}

export function AnalysisProgress({ docId, isAnalyzing, onCancel, cancelling }: Props) {
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [hiding, setHiding] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const prevAnalyzing = useRef(isAnalyzing);

  const poll = useCallback(async () => {
    try {
      const res = await getAnalysisProgress(docId);
      if (res.data) setProgress(res.data);
    } catch {
      // silently retry next interval
    }
  }, [docId]);

  useEffect(() => {
    if (!isAnalyzing) return;
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, [isAnalyzing, poll]);

  // When isAnalyzing transitions from true to false, clear progress after brief delay
  useEffect(() => {
    if (prevAnalyzing.current && !isAnalyzing && progress) {
      setHiding(true);
      const t = setTimeout(() => {
        setProgress(null);
        setHiding(false);
      }, 1500);
      prevAnalyzing.current = isAnalyzing;
      return () => clearTimeout(t);
    }
    prevAnalyzing.current = isAnalyzing;
  }, [isAnalyzing, progress]);

  // When all nodes complete during active analysis, also trigger cleanup
  const allComplete = progress && progress.completed_nodes &&
    progress.completed_nodes.length >= (progress.total_nodes || NODE_ORDER.length);
  useEffect(() => {
    if (!allComplete || !isAnalyzing) return;
    const t = setTimeout(() => {
      setProgress(null);
      setHiding(false);
    }, 2000);
    return () => clearTimeout(t);
  }, [allComplete, isAnalyzing]);

  useEffect(() => {
    if (logsOpen && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [progress?.logs?.length, logsOpen]);

  if (!isAnalyzing && !progress) return null;

  const labels = progress?.node_labels || FALLBACK_LABELS;
  const completed = new Set(progress?.completed_nodes || []);
  const currentNode = progress?.current_node;
  const total = progress?.total_nodes || NODE_ORDER.length;
  const completedCount = completed.size;
  const pct = Math.round((completedCount / total) * 100);
  const logs = progress?.logs || [];

  return (
    <div className="analysis-progress-card">
      <div className="analysis-progress-header">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="analysis-progress-title-row">
            <h3 className="analysis-progress-title">
              {hiding || (completedCount === total && completedCount > 0) ? "Analysis Complete" : "Analysis Pipeline"}
            </h3>
            <span className="analysis-progress-counter">
              {completedCount}/{total} nodes
            </span>
          </div>
          <div className="analysis-progress-bar-track">
            <div
              className="analysis-progress-bar-fill"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
        {onCancel && (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onCancel}
            disabled={cancelling}
            style={{ flexShrink: 0, display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
          >
            {cancelling ? (
              <Loader2 size={14} className="analysis-spinner-icon" />
            ) : (
              <XCircle size={14} />
            )}
            {cancelling ? "Cancelling…" : "Cancel"}
          </button>
        )}
      </div>

      <div className="analysis-stepper">
        {NODE_ORDER.map((node, idx) => {
          const isCompleted = completed.has(node);
          const isRunning = currentNode === node;
          const label = labels[node] || FALLBACK_LABELS[node] || node;

          let stateClass = "pending";
          if (isCompleted) stateClass = "complete";
          else if (isRunning) stateClass = "running";

          return (
            <div key={node} className={`analysis-step ${stateClass}`}>
              <div className="analysis-step-icon">
                {isCompleted ? (
                  <CheckCircle2 size={16} />
                ) : isRunning ? (
                  <Loader2 size={16} className="analysis-spinner-icon" />
                ) : (
                  <Circle size={16} />
                )}
              </div>
              {idx < NODE_ORDER.length - 1 && (
                <div className={`analysis-step-line ${isCompleted ? "complete" : ""}`} />
              )}
              <span className="analysis-step-label">{label}</span>
            </div>
          );
        })}
      </div>

      {logs.length > 0 && (
        <div className="analysis-logs-section">
          <button
            type="button"
            className="analysis-logs-toggle"
            onClick={() => setLogsOpen((v) => !v)}
          >
            <Terminal size={14} />
            <span>Live Logs ({logs.length})</span>
            <ChevronDown
              size={14}
              style={{
                transform: logsOpen ? "rotate(180deg)" : "rotate(0deg)",
                transition: "transform 0.2s",
              }}
            />
          </button>
          {logsOpen && (
            <div className="analysis-logs-panel">
              {logs.map((line, i) => (
                <div key={i} className="analysis-log-line">{line}</div>
              ))}
              <div ref={logsEndRef} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
