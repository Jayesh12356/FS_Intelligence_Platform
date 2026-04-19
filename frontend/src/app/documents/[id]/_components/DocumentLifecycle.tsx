"use client";

/**
 * DocumentLifecycle — compact horizontal timeline rendered just under
 * the document title on /documents/[id]. Shows only the events that
 * actually happened for this document, in chronological order. The
 * data source is the existing /api/activity-log endpoint (filtered by
 * fs_id) so we never need a second backend pipe.
 *
 * Design intent: the user said "no need to show actually run time
 * logs we can take time to show". Each chip is a friendly label + an
 * optional one-line detail and a hover tooltip with the raw payload
 * (when fetched with include_payload=true). No raw HTTP traffic, no
 * stack traces, no debug noise.
 */

import { useEffect, useState, type ReactNode } from "react";
import {
  Upload,
  FileText,
  Sparkles,
  Wand2,
  Layers,
  RotateCcw,
  Rocket,
  CheckCircle2,
  XCircle,
  Activity,
  ListChecks,
  FilePlus2,
  ListPlus,
  Eye,
  GitBranch,
  ShieldCheck,
} from "lucide-react";
import { getActivityLog, type ActivityLogEntry } from "@/lib/api";

const ICON_BY_TYPE: Record<string, ReactNode> = {
  UPLOADED: <Upload size={14} aria-hidden />,
  PARSED: <FileText size={14} aria-hidden />,
  ANALYZED: <Sparkles size={14} aria-hidden />,
  TASKS_GENERATED: <ListChecks size={14} aria-hidden />,
  ANALYSIS_REFINED: <Wand2 size={14} aria-hidden />,
  AMBIGUITY_RESOLVED: <ShieldCheck size={14} aria-hidden />,
  CONTRADICTION_ACCEPTED: <ShieldCheck size={14} aria-hidden />,
  EDGE_CASE_ACCEPTED: <ShieldCheck size={14} aria-hidden />,
  VERSION_ADDED: <Layers size={14} aria-hidden />,
  VERSION_REVERTED: <RotateCcw size={14} aria-hidden />,
  SECTION_EDITED: <FileText size={14} aria-hidden />,
  SECTION_ADDED: <FilePlus2 size={14} aria-hidden />,
  SUBMITTED_FOR_APPROVAL: <Eye size={14} aria-hidden />,
  APPROVED: <CheckCircle2 size={14} aria-hidden />,
  REJECTED: <XCircle size={14} aria-hidden />,
  COMMENT_ADDED: <ListPlus size={14} aria-hidden />,
  COMMENT_RESOLVED: <CheckCircle2 size={14} aria-hidden />,
  EXPORTED: <FileText size={14} aria-hidden />,
  ANALYSIS_CANCELLED: <XCircle size={14} aria-hidden />,
  BUILD_STARTED: <Rocket size={14} aria-hidden />,
  BUILD_PHASE_CHANGED: <GitBranch size={14} aria-hidden />,
  BUILD_TASK_COMPLETED: <CheckCircle2 size={14} aria-hidden />,
  FILE_REGISTERED: <FilePlus2 size={14} aria-hidden />,
  BUILD_COMPLETED: <CheckCircle2 size={14} aria-hidden />,
  BUILD_FAILED: <XCircle size={14} aria-hidden />,
};

const CATEGORY_STYLE: Record<string, { bg: string; fg: string }> = {
  document: { bg: "var(--well-blue)", fg: "var(--text-primary)" },
  analysis: { bg: "var(--well-amber)", fg: "var(--text-primary)" },
  build: { bg: "var(--well-green)", fg: "var(--text-primary)" },
  collab: { bg: "var(--well-purple)", fg: "var(--text-primary)" },
};

/** Collapse repeated events of the same type that occurred close together
 * (e.g. 8 FILE_REGISTERED rows during a single phase) into one chip with
 * a count suffix so the strip stays scannable. */
function collapse(events: ActivityLogEntry[]): ActivityLogEntry[] {
  const COLLAPSIBLE = new Set([
    "FILE_REGISTERED",
    "BUILD_PHASE_CHANGED",
    "BUILD_TASK_COMPLETED",
    "ANALYSIS_REFINED",
    "AMBIGUITY_RESOLVED",
    "CONTRADICTION_ACCEPTED",
    "EDGE_CASE_ACCEPTED",
    "SECTION_EDITED",
    "SECTION_ADDED",
    "VERSION_ADDED",
    "COMMENT_ADDED",
  ]);
  const out: ActivityLogEntry[] = [];
  for (const evt of events) {
    const last = out[out.length - 1];
    if (last && last.event_type === evt.event_type && COLLAPSIBLE.has(evt.event_type)) {
      // Merge — bump a count counter on the latest entry.
      const merged: ActivityLogEntry = {
        ...last,
        // We append (xN) to the label.
        // Track raw count via a transient field on payload.
        payload: {
          ...(last.payload || {}),
          _count: ((last.payload as Record<string, unknown>)?._count as number || 1) + 1,
        },
      };
      out[out.length - 1] = merged;
    } else {
      out.push({ ...evt, payload: { ...(evt.payload || {}), _count: 1 } });
    }
  }
  return out;
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

interface Props {
  fsId: string;
  /** Optional title; default is "Lifecycle". */
  title?: string;
}

export function DocumentLifecycle({ fsId, title = "Lifecycle" }: Props) {
  const [events, setEvents] = useState<ActivityLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await getActivityLog({
          fsId,
          limit: 200,
          offset: 0,
          includePayload: true,
        });
        if (cancelled) return;
        const list = res.data?.events ?? [];
        // API returns newest-first; we want chronological for the strip.
        list.sort((a, b) => {
          const ta = a.created_at ? Date.parse(a.created_at) : 0;
          const tb = b.created_at ? Date.parse(b.created_at) : 0;
          return ta - tb;
        });
        setEvents(list);
      } catch (e) {
        if (!cancelled) setError((e as Error).message || "Failed to load lifecycle");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fsId]);

  if (error) {
    return (
      <div
        data-testid="lifecycle-error"
        style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}
      >
        Lifecycle unavailable
      </div>
    );
  }
  if (!events) {
    return (
      <div
        data-testid="lifecycle-loading"
        style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}
      >
        Loading activity…
      </div>
    );
  }
  if (events.length === 0) {
    return (
      <div
        data-testid="lifecycle-empty"
        style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}
      >
        No activity yet for this document.
      </div>
    );
  }

  const chips = collapse(events);

  return (
    <section
      aria-label={title}
      data-testid="document-lifecycle"
      style={{ marginTop: "1rem" }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          marginBottom: "0.5rem",
          fontSize: "0.75rem",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          color: "var(--text-muted)",
          fontWeight: 600,
        }}
      >
        <Activity size={14} aria-hidden />
        {title}
        <span style={{ color: "var(--text-muted)", fontWeight: 400, textTransform: "none" }}>
          ({events.length} {events.length === 1 ? "event" : "events"})
        </span>
      </header>
      <ol
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          gap: "0.5rem",
          overflowX: "auto",
          paddingBottom: "0.25rem",
        }}
      >
        {chips.map((evt, idx) => {
          const style = CATEGORY_STYLE[evt.category || "document"] || CATEGORY_STYLE.document;
          const count = (evt.payload?._count as number) || 1;
          const labelSuffix = count > 1 ? ` (×${count})` : "";
          const tooltipParts = [
            evt.event_label,
            evt.detail || undefined,
            evt.created_at ? formatTime(evt.created_at) : undefined,
            count > 1 ? `${count} occurrences` : undefined,
          ].filter(Boolean);
          return (
            <li
              key={`${evt.event_type}-${evt.created_at}-${idx}`}
              data-testid="lifecycle-chip"
              data-event-type={evt.event_type}
              title={tooltipParts.join(" · ")}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                padding: "0.35rem 0.6rem",
                borderRadius: "999px",
                background: style.bg,
                color: style.fg,
                fontSize: "0.78rem",
                whiteSpace: "nowrap",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <span aria-hidden style={{ display: "inline-flex" }}>
                {ICON_BY_TYPE[evt.event_type] || <Activity size={14} aria-hidden />}
              </span>
              <span style={{ fontWeight: 600 }}>
                {evt.event_label}
                {labelSuffix}
              </span>
              {evt.detail ? (
                <span style={{ color: "var(--text-secondary)" }}>· {evt.detail}</span>
              ) : null}
              <span style={{ color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
                · {formatTime(evt.created_at)}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export default DocumentLifecycle;
