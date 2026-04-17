"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { getActivityLog, getMCPSessions, getMCPSessionEvents, getMCPSession, listProviders, type ProviderInfo } from "@/lib/api";
import type { MCPSession, MCPSessionEvent, ActivityLogEntry } from "@/lib/api";
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
  Activity,
  Zap,
  Clock,
  Radio,
  ChevronDown,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Terminal,
  FileText,
  Search,
  Upload,
  BarChart3,
  Edit3,
  PlusCircle,
  XCircle,
  Cpu,
  Hammer,
  Monitor,
} from "lucide-react";
import Link from "next/link";

type MainTab = "activity" | "sessions" | "tools";

function formatTime(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatDuration(ms: number | null): string {
  if (ms == null || ms < 0) return "—";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m < 60) return `${m}m ${r}s`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h}h ${rm}m`;
}

function isSessionActive(s: MCPSession): boolean {
  return s.status === "RUNNING";
}

function truncateId(id: string, keep = 10): string {
  if (id.length <= keep) return id;
  return `${id.slice(0, keep)}…`;
}

function activityBorderColor(eventType: string): string {
  const t = eventType.toUpperCase();
  if (
    t.includes("REJECT") ||
    t.includes("FAIL") ||
    t.includes("ERROR") ||
    t === "ANALYSIS_CANCELLED"
  ) {
    return "var(--error)";
  }
  if (t === "ANALYZED" || t === "APPROVED") return "var(--success)";
  if (t === "UPLOADED" || t === "PARSED") return "var(--accent-primary)";
  if (t === "SECTION_EDITED" || t === "SECTION_ADDED") return "var(--warning)";
  return "var(--accent-primary)";
}

function ActivityTypeIcon({ eventType }: { eventType: string }) {
  const t = eventType.toUpperCase();
  if (t === "UPLOADED") return <Upload size={18} aria-hidden />;
  if (t === "PARSED") return <FileText size={18} aria-hidden />;
  if (t === "ANALYZED") return <BarChart3 size={18} aria-hidden />;
  if (t === "SECTION_EDITED") return <Edit3 size={18} aria-hidden />;
  if (t === "SECTION_ADDED") return <PlusCircle size={18} aria-hidden />;
  if (t === "ANALYSIS_CANCELLED") return <XCircle size={18} aria-hidden />;
  if (t === "APPROVED") return <CheckCircle2 size={18} aria-hidden />;
  return <Activity size={18} aria-hidden />;
}

function humanizeEventType(eventType: string): string {
  return eventType.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function eventDotClass(e: MCPSessionEvent): string {
  const blob = `${e.event_type} ${e.status} ${e.message || ""}`.toLowerCase();
  if (blob.includes("fail") || blob.includes("error")) return "timeline-dot error";
  if (blob.includes("pass") || blob.includes("ok") || blob.includes("success"))
    return "timeline-dot success";
  return "timeline-dot active";
}

function EventTypeIcon({ e }: { e: MCPSessionEvent }) {
  const blob = `${e.event_type} ${e.status} ${e.message || ""}`.toLowerCase();
  if (blob.includes("fail") || blob.includes("error"))
    return <AlertTriangle size={14} aria-hidden />;
  if (blob.includes("pass") || blob.includes("ok") || blob.includes("success"))
    return <CheckCircle2 size={14} aria-hidden />;
  return <Terminal size={14} aria-hidden />;
}

function mcpEventTitle(e: MCPSessionEvent): string {
  const msg = e.message?.trim();
  if (msg) return msg;
  return humanizeEventType(e.event_type);
}

function mcpEventSubtitle(e: MCPSessionEvent): string {
  const bits: string[] = [formatTime(e.created_at)];
  bits.push(`Phase ${e.phase}`);
  if (e.status && e.status.toUpperCase() !== "OK") bits.push(e.status);
  return bits.join(" · ");
}

export default function MonitoringPage() {
  const [mainTab, setMainTab] = useState<MainTab>("activity");

  const [activityEvents, setActivityEvents] = useState<ActivityLogEntry[]>([]);
  const [activityTotal, setActivityTotal] = useState(0);
  const [activityLoading, setActivityLoading] = useState(true);
  const [activityRefreshing, setActivityRefreshing] = useState(false);
  const [activityError, setActivityError] = useState<string | null>(null);
  const [docSearch, setDocSearch] = useState("");
  const [eventTypeFilter, setEventTypeFilter] = useState("");
  const [knownEventTypes, setKnownEventTypes] = useState<string[]>([]);

  const [sessions, setSessions] = useState<MCPSession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<MCPSession | null>(null);
  const [events, setEvents] = useState<MCPSessionEvent[]>([]);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [listRefreshing, setListRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [eventCounts, setEventCounts] = useState<Record<string, number>>({});
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [toolProviders, setToolProviders] = useState<ProviderInfo[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);

  const selectedIdRef = useRef<string | null>(null);
  useEffect(() => {
    selectedIdRef.current = selectedSessionId;
  }, [selectedSessionId]);

  const timelineEndRef = useRef<HTMLDivElement>(null);

  const fetchActivity = useCallback(
    async (opts?: { manual?: boolean }) => {
      if (opts?.manual) setActivityRefreshing(true);
      else setActivityLoading(true);
      try {
        const trimmedSearch = docSearch.trim();
        const res = await getActivityLog(
          50,
          0,
          eventTypeFilter || undefined,
          trimmedSearch || undefined,
        );
        const rows = res.data?.events ?? [];
        setActivityEvents(rows);
        setActivityTotal(res.data?.total ?? rows.length);
        if (!eventTypeFilter && !trimmedSearch) {
          const types = Array.from(
            new Set(rows.map((r) => r.event_type).filter(Boolean))
          ).sort() as string[];
          setKnownEventTypes(types);
        }
        setActivityError(null);
      } catch (e) {
        setActivityError(e instanceof Error ? e.message : "Failed to load activity");
      } finally {
        setActivityLoading(false);
        if (opts?.manual) setActivityRefreshing(false);
      }
    },
    [eventTypeFilter, docSearch]
  );

  useEffect(() => {
    const handle = setTimeout(() => void fetchActivity(), docSearch ? 250 : 0);
    return () => clearTimeout(handle);
  }, [fetchActivity, docSearch]);

  const fetchSessions = useCallback(async (opts?: { isManual?: boolean }) => {
    if (opts?.isManual) setListRefreshing(true);
    try {
      const res = await getMCPSessions(100);
      const rows = res.data?.sessions || [];
      setSessions(rows);
      if (!selectedIdRef.current && rows.length > 0) {
        setSelectedSessionId(rows[0].id);
      }
      setSessionsError(null);
    } catch (e) {
      setSessionsError(e instanceof Error ? e.message : "Failed to load sessions");
    } finally {
      setSessionsLoading(false);
      if (opts?.isManual) setListRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (mainTab !== "sessions") return;
    setSessionsLoading(true);
    void fetchSessions();
  }, [mainTab, fetchSessions]);

  useEffect(() => {
    if (mainTab !== "sessions" || !autoRefresh) return;
    const timer = setInterval(() => void fetchSessions(), 5000);
    return () => clearInterval(timer);
  }, [mainTab, autoRefresh, fetchSessions]);

  useEffect(() => {
    if (mainTab !== "sessions" || !selectedSessionId) return;
    const sid = selectedSessionId;
    let cancelled = false;
    async function loadDetails() {
      setEventsLoading(true);
      try {
        const [sessionRes, eventRes] = await Promise.all([
          getMCPSession(sid),
          getMCPSessionEvents(sid, 300),
        ]);
        if (cancelled) return;
        setSelectedSession(sessionRes.data || null);
        const evs = eventRes.data?.events || [];
        setEvents(evs);
        setEventCounts((prev) => ({ ...prev, [sid]: evs.length }));
        setSessionsError(null);
      } catch (e) {
        if (cancelled) return;
        setSessionsError(
          e instanceof Error ? e.message : "Failed to load session details"
        );
      } finally {
        if (!cancelled) setEventsLoading(false);
      }
    }
    void loadDetails();
    if (!autoRefresh) {
      return () => {
        cancelled = true;
      };
    }
    const timer = setInterval(loadDetails, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [mainTab, selectedSessionId, autoRefresh]);

  const fetchToolProviders = useCallback(async () => {
    setToolsLoading(true);
    try {
      const res = await listProviders();
      setToolProviders(res.data ?? []);
    } catch { /* ignore */ } finally {
      setToolsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (mainTab === "tools") {
      void fetchToolProviders();
    }
  }, [mainTab, fetchToolProviders]);

  const sortedActivity = useMemo(() => {
    const rows = [...activityEvents];
    rows.sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
      return tb - ta;
    });
    return rows;
  }, [activityEvents]);

  const documentsActiveCount = useMemo(() => {
    const ids = new Set<string>();
    for (const e of activityEvents) {
      if (e.fs_id) ids.add(e.fs_id);
    }
    return ids.size;
  }, [activityEvents]);

  const latestActivityTime = useMemo(() => {
    let best: string | null = null;
    let bestT = 0;
    for (const e of activityEvents) {
      if (!e.created_at) continue;
      const t = new Date(e.created_at).getTime();
      if (t > bestT) {
        bestT = t;
        best = e.created_at;
      }
    }
    return best;
  }, [activityEvents]);

  const sortedEvents = useMemo(() => {
    return [...events].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );
  }, [events]);

  const activeCount = useMemo(
    () => sessions.filter((s) => isSessionActive(s)).length,
    [sessions]
  );

  const latestSessionDuration = useMemo(() => {
    const s = sessions[0];
    if (!s) return null;
    const start = new Date(s.started_at).getTime();
    const end = s.ended_at ? new Date(s.ended_at).getTime() : Date.now();
    return end - start;
  }, [sessions]);

  useEffect(() => {
    if (sortedEvents.length === 0) return;
    timelineEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [sortedEvents, mainTab]);

  const handleSessionsManualRefresh = () => {
    void fetchSessions({ isManual: true });
    if (!selectedSessionId) return;
    const sid = selectedSessionId;
    void (async () => {
      setEventsLoading(true);
      try {
        const [sessionRes, eventRes] = await Promise.all([
          getMCPSession(sid),
          getMCPSessionEvents(sid, 300),
        ]);
        setSelectedSession(sessionRes.data || null);
        const evs = eventRes.data?.events || [];
        setEvents(evs);
        setEventCounts((prev) => ({ ...prev, [sid]: evs.length }));
        setSessionsError(null);
      } catch (e) {
        setSessionsError(
          e instanceof Error ? e.message : "Failed to load session details"
        );
      } finally {
        setEventsLoading(false);
      }
    })();
  };

  const combinedError = activityError || sessionsError;

  return (
    <>
      <PageShell
        title="Monitoring"
        subtitle="See recent document activity and live MCP build sessions"
        actions={
          <>
            {mainTab === "sessions" && (
              <button
                type="button"
                className={`tab ${autoRefresh ? "active" : ""}`}
                onClick={() => setAutoRefresh((v) => !v)}
                title={autoRefresh ? "Auto-refresh on" : "Auto-refresh off"}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
              >
                <Radio size={14} aria-hidden />
                Auto-refresh
              </button>
            )}
            {mainTab === "activity" && (
              <button
                type="button"
                className="tab"
                onClick={() => void fetchActivity({ manual: true })}
                disabled={activityRefreshing || activityLoading}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
              >
                <RefreshCw
                  size={14}
                  aria-hidden
                  style={{
                    animation: activityRefreshing ? "spin 0.8s linear infinite" : undefined,
                  }}
                />
                Refresh
              </button>
            )}
            {mainTab === "sessions" && (
              <button
                type="button"
                className="tab"
                onClick={handleSessionsManualRefresh}
                disabled={listRefreshing || sessionsLoading}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
              >
                <RefreshCw
                  size={14}
                  aria-hidden
                  style={{
                    animation: listRefreshing ? "spin 0.8s linear infinite" : undefined,
                  }}
                />
                Refresh
              </button>
            )}
          </>
        }
      >
        {combinedError && (
          <FadeIn>
            <div
              className="card"
              style={{
                borderLeft: "3px solid var(--error)",
                marginBottom: "1rem",
                padding: "0.75rem 1rem",
              }}
            >
              {combinedError}
            </div>
          </FadeIn>
        )}

        <div style={{ marginBottom: "1.25rem" }}>
          <Tabs
            items={[
              { key: "activity", label: "Activity Log" },
              { key: "sessions", label: "Build Sessions" },
              { key: "tools", label: "Tool Execution" },
            ]}
            active={mainTab}
            onChange={(k) => setMainTab(k as MainTab)}
          />
        </div>

        <AnimatePresence mode="wait">
          {mainTab === "activity" && (
            <motion.div
              key="activity"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              <div className="kpi-row" style={{ marginBottom: "1.25rem" }}>
                <KpiCard
                  label="Total events"
                  value={activityTotal}
                  icon={<Activity size={20} />}
                  iconBg="var(--accent-primary)"
                  delay={0}
                />
                <KpiCard
                  label="Documents active"
                  value={documentsActiveCount}
                  icon={<FileText size={20} />}
                  iconBg="var(--well-green)"
                  delay={0.05}
                />
                <KpiCard
                  label="Latest event"
                  valueText={formatTime(latestActivityTime)}
                  icon={<Clock size={20} />}
                  iconBg="var(--warning)"
                  delay={0.1}
                />
              </div>

              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "0.75rem",
                  marginBottom: "1rem",
                  alignItems: "flex-end",
                }}
              >
                <div style={{ flex: "1 1 220px", minWidth: 200 }}>
                  <label className="form-label" htmlFor="activity-doc-search">
                    Filter by document
                  </label>
                  <div style={{ position: "relative" }}>
                    <Search
                      size={16}
                      style={{
                        position: "absolute",
                        left: 12,
                        top: "50%",
                        transform: "translateY(-50%)",
                        color: "var(--text-muted)",
                      }}
                      aria-hidden
                    />
                    <input
                      id="activity-doc-search"
                      type="search"
                      className="form-input"
                      placeholder="Search document name…"
                      value={docSearch}
                      onChange={(ev) => setDocSearch(ev.target.value)}
                      style={{ paddingLeft: "2.25rem", width: "100%" }}
                    />
                  </div>
                </div>
                <div style={{ flex: "0 1 200px" }}>
                  <label className="form-label" htmlFor="activity-event-type">
                    Event type
                  </label>
                  <select
                    id="activity-event-type"
                    className="form-select"
                    value={eventTypeFilter}
                    onChange={(ev) => setEventTypeFilter(ev.target.value)}
                    style={{ width: "100%" }}
                  >
                    <option value="">All types</option>
                    {knownEventTypes.map((t) => (
                      <option key={t} value={t}>
                        {humanizeEventType(t)}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {activityLoading ? (
                <div className="card" style={{ padding: "2.5rem", textAlign: "center" }}>
                  <div className="spinner" style={{ margin: "0 auto 0.75rem" }} aria-hidden />
                  <p className="page-subtitle" style={{ margin: 0 }}>
                    Loading activity…
                  </p>
                </div>
              ) : sortedActivity.length === 0 ? (
                <EmptyState
                  icon={<Activity size={40} strokeWidth={1.25} />}
                  title="No activity yet"
                  description="Upload or analyze a document to see events here."
                />
              ) : (
                <StaggerList
                  style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}
                >
                  {sortedActivity.map((e) => {
                    const border = activityBorderColor(e.event_type);
                    const docHref = `/documents/${e.fs_id}`;
                    return (
                      <StaggerItem key={e.id ?? `${e.fs_id}-${e.created_at}-${e.event_type}`}>
                        <motion.div
                          className="card card-flat"
                          initial={{ opacity: 0, x: -6 }}
                          animate={{ opacity: 1, x: 0 }}
                          style={{
                            padding: "0.85rem 1rem",
                            borderLeft: `4px solid ${border}`,
                            display: "grid",
                            gridTemplateColumns: "auto 1fr",
                            gap: "0.65rem 0.85rem",
                            alignItems: "start",
                          }}
                        >
                          <div
                            style={{
                              color: "var(--text-secondary)",
                              marginTop: 2,
                              display: "flex",
                              alignItems: "center",
                            }}
                          >
                            <ActivityTypeIcon eventType={e.event_type} />
                          </div>
                          <div style={{ minWidth: 0 }}>
                            <div
                              style={{
                                display: "flex",
                                flexWrap: "wrap",
                                alignItems: "baseline",
                                justifyContent: "space-between",
                                gap: "0.35rem 0.75rem",
                              }}
                            >
                              <span style={{ fontWeight: 600, fontSize: "0.9375rem" }}>
                                {e.event_label || humanizeEventType(e.event_type)}
                              </span>
                              <span className="timeline-time" style={{ marginTop: 0 }}>
                                {formatTime(e.created_at)}
                              </span>
                            </div>
                            <div style={{ marginTop: "0.35rem" }}>
                              <Link
                                href={docHref}
                                className="timeline-desc"
                                style={{
                                  fontWeight: 500,
                                  color: "var(--accent-primary)",
                                  textDecoration: "none",
                                }}
                              >
                                {e.document_name || "Untitled document"}
                              </Link>
                            </div>
                            {e.detail ? (
                              <p
                                className="timeline-desc"
                                style={{ margin: "0.4rem 0 0", lineHeight: 1.5 }}
                              >
                                {e.detail}
                              </p>
                            ) : null}
                          </div>
                        </motion.div>
                      </StaggerItem>
                    );
                  })}
                </StaggerList>
              )}
            </motion.div>
          )}

          {mainTab === "sessions" && (
            <motion.div
              key="sessions"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              <div className="kpi-row" style={{ marginBottom: "1.25rem" }}>
                <KpiCard
                  label="Active sessions"
                  value={activeCount}
                  icon={<Zap size={20} />}
                  iconBg="var(--well-green)"
                  delay={0}
                />
                <KpiCard
                  label="Events (selected)"
                  valueText={selectedSessionId ? String(events.length) : "—"}
                  icon={<Activity size={20} />}
                  iconBg="var(--accent-primary)"
                  delay={0.05}
                />
                <KpiCard
                  label="Latest session duration"
                  valueText={formatDuration(latestSessionDuration)}
                  icon={<Clock size={20} />}
                  iconBg="var(--warning)"
                  delay={0.1}
                />
              </div>

              {sessionsLoading && sessions.length === 0 ? (
                <div className="card" style={{ padding: "2.5rem", textAlign: "center" }}>
                  <div className="spinner" style={{ margin: "0 auto 0.75rem" }} aria-hidden />
                  <p className="page-subtitle" style={{ margin: 0 }}>
                    Loading sessions…
                  </p>
                </div>
              ) : sessions.length === 0 ? (
                <EmptyState
                  icon={<Terminal size={40} strokeWidth={1.25} />}
                  title="No MCP sessions yet"
                  description="When a build session starts, it will appear here with a live event timeline."
                />
              ) : (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "minmax(280px, 320px) 1fr",
                    gap: "1rem",
                    alignItems: "stretch",
                  }}
                >
                  <div className="card" style={{ padding: "1rem", minHeight: 420 }}>
                    <h3 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>Sessions</h3>
                    <StaggerList
                      style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}
                    >
                      {sessions.map((s) => {
                        const active = isSessionActive(s);
                        const selected = selectedSessionId === s.id;
                        const count =
                          eventCounts[s.id] !== undefined
                            ? eventCounts[s.id]
                            : selected
                              ? events.length
                              : undefined;
                        return (
                          <StaggerItem key={s.id}>
                            <button
                              type="button"
                              onClick={() => setSelectedSessionId(s.id)}
                              className="card"
                              style={{
                                width: "100%",
                                textAlign: "left",
                                padding: "0.75rem",
                                cursor: "pointer",
                                border: selected
                                  ? "1px solid var(--accent-primary)"
                                  : "1px solid var(--border-subtle)",
                                background: selected
                                  ? "var(--bg-tertiary)"
                                  : "var(--bg-card)",
                                borderRadius: "var(--radius-lg)",
                                color: "inherit",
                                display: "grid",
                                gap: "0.35rem",
                              }}
                            >
                              <div
                                style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
                              >
                                <span
                                  title={active ? "Active" : "Inactive"}
                                  aria-hidden
                                  style={{
                                    width: 8,
                                    height: 8,
                                    borderRadius: "50%",
                                    flexShrink: 0,
                                    background: active ? "var(--success)" : "var(--text-muted)",
                                    opacity: active ? 1 : 0.45,
                                    animation: active
                                      ? "pulse 2s ease-in-out infinite"
                                      : undefined,
                                  }}
                                />
                                <span
                                  style={{
                                    fontFamily: "var(--font-mono, ui-monospace, monospace)",
                                    fontSize: "0.8125rem",
                                    fontWeight: 600,
                                  }}
                                >
                                  {truncateId(s.id)}
                                </span>
                                {count !== undefined && (
                                  <Badge variant="neutral" style={{ marginLeft: "auto" }}>
                                    {count} events
                                  </Badge>
                                )}
                              </div>
                              <div className="timeline-time" style={{ marginTop: 0 }}>
                                Started {formatTime(s.started_at)}
                              </div>
                              <div
                                style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}
                              >
                                {s.target_stack || "Unknown stack"} · {s.status} · phase{" "}
                                {s.phase}/{s.total_phases || "?"}
                              </div>
                            </button>
                          </StaggerItem>
                        );
                      })}
                    </StaggerList>
                  </div>

                  <div
                    className="card"
                    style={{
                      padding: "1rem",
                      minHeight: 420,
                      display: "flex",
                      flexDirection: "column",
                    }}
                  >
                    <AnimatePresence mode="wait">
                      {!selectedSessionId ? (
                        <motion.div
                          key="empty"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          style={{
                            flex: 1,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                          }}
                        >
                          <EmptyState
                            icon={<Radio size={36} strokeWidth={1.25} />}
                            title="Select a session"
                            description="Choose a session on the left to view its event timeline."
                          />
                        </motion.div>
                      ) : (
                        <motion.div
                          key={selectedSessionId}
                          initial={{ opacity: 0, y: 6 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -6 }}
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            flex: 1,
                            minHeight: 0,
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              alignItems: "flex-start",
                              justifyContent: "space-between",
                              gap: "0.75rem",
                              marginBottom: "0.75rem",
                              flexWrap: "wrap",
                            }}
                          >
                            <div>
                              <h3 style={{ margin: 0, fontSize: "1rem" }}>Event timeline</h3>
                              <p
                                className="page-subtitle"
                                style={{ margin: "0.25rem 0 0", fontSize: "0.8125rem" }}
                              >
                                Session{" "}
                                <span
                                  style={{
                                    fontFamily: "var(--font-mono, ui-monospace, monospace)",
                                  }}
                                >
                                  {truncateId(selectedSessionId, 14)}
                                </span>
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={() => setDetailsOpen((o) => !o)}
                              className="tab"
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.35rem",
                              }}
                              aria-expanded={detailsOpen}
                            >
                              Session details
                              <ChevronDown
                                size={14}
                                aria-hidden
                                style={{
                                  transform: detailsOpen ? "rotate(180deg)" : undefined,
                                  transition: "transform 0.2s ease",
                                }}
                              />
                            </button>
                          </div>

                          <AnimatePresence>
                            {detailsOpen && selectedSession && (
                              <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: "auto", opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                style={{ overflow: "hidden", marginBottom: "0.75rem" }}
                              >
                                <div className="info-grid" style={{ marginBottom: 0 }}>
                                  <div className="info-item">
                                    <div className="info-label">Status</div>
                                    <div className="info-value">{selectedSession.status}</div>
                                  </div>
                                  <div className="info-item">
                                    <div className="info-label">Phase</div>
                                    <div className="info-value">
                                      {selectedSession.phase}/
                                      {selectedSession.total_phases || "?"}
                                    </div>
                                  </div>
                                  <div className="info-item">
                                    <div className="info-label">Stack</div>
                                    <div className="info-value">
                                      {selectedSession.target_stack || "—"}
                                    </div>
                                  </div>
                                  <div className="info-item">
                                    <div className="info-label">Current step</div>
                                    <div className="info-value">
                                      {selectedSession.current_step || "—"}
                                    </div>
                                  </div>
                                  <div className="info-item">
                                    <div className="info-label">Started</div>
                                    <div className="info-value">
                                      {formatTime(selectedSession.started_at)}
                                    </div>
                                  </div>
                                  <div className="info-item">
                                    <div className="info-label">Ended</div>
                                    <div className="info-value">
                                      {formatTime(selectedSession.ended_at)}
                                    </div>
                                  </div>
                                </div>
                              </motion.div>
                            )}
                          </AnimatePresence>

                          <div
                            style={{
                              flex: 1,
                              minHeight: 280,
                              maxHeight: 520,
                              overflowY: "auto",
                              position: "relative",
                            }}
                          >
                            {eventsLoading && sortedEvents.length === 0 ? (
                              <div style={{ padding: "2rem", textAlign: "center" }}>
                                <div
                                  className="spinner"
                                  style={{ margin: "0 auto 0.5rem" }}
                                  aria-hidden
                                />
                                <span className="page-subtitle">Loading events…</span>
                              </div>
                            ) : sortedEvents.length === 0 ? (
                              <div style={{ padding: "1.5rem", textAlign: "center" }}>
                                <Terminal size={32} style={{ color: "var(--text-muted)", marginBottom: "0.75rem" }} aria-hidden />
                                <p className="page-subtitle" style={{ margin: "0 0 0.35rem", fontWeight: 600 }}>
                                  No events recorded
                                </p>
                                <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", margin: 0, maxWidth: "24rem", marginLeft: "auto", marginRight: "auto" }}>
                                  This session has no logged events. Events are recorded when a build runs through the MCP server. Manual or external builds do not generate event logs here.
                                </p>
                              </div>
                            ) : (
                              <div className="timeline">
                                {sortedEvents.map((ev) => (
                                  <div key={ev.id} className="timeline-item">
                                    <div className={eventDotClass(ev)} aria-hidden />
                                    <div className="timeline-content">
                                      <div
                                        className="timeline-title"
                                        style={{
                                          display: "flex",
                                          alignItems: "center",
                                          gap: "0.35rem",
                                          flexWrap: "wrap",
                                        }}
                                      >
                                        <EventTypeIcon e={ev} />
                                        <span>{mcpEventTitle(ev)}</span>
                                        <Badge variant="neutral">{ev.status}</Badge>
                                      </div>
                                      <div className="timeline-time">{mcpEventSubtitle(ev)}</div>
                                      <div className="timeline-desc" style={{ marginTop: "0.25rem" }}>
                                        <span style={{ color: "var(--text-muted)" }}>
                                          {humanizeEventType(ev.event_type)}
                                        </span>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                                <div ref={timelineEndRef} />
                              </div>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              )}
            </motion.div>
          )}
          {mainTab === "tools" && (
            <motion.div
              key="tools"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              <div className="kpi-row" style={{ marginBottom: "1.25rem" }}>
                <KpiCard
                  label="Total Providers"
                  value={toolProviders.length}
                  icon={<Cpu size={20} />}
                  iconBg="var(--well-blue)"
                  delay={0}
                />
                <KpiCard
                  label="Healthy"
                  value={toolProviders.filter((p) => p.healthy === true).length}
                  icon={<CheckCircle2 size={20} />}
                  iconBg="var(--well-green)"
                  delay={0.05}
                />
                <KpiCard
                  label="Capabilities"
                  value={Array.from(new Set(toolProviders.flatMap((p) => p.capabilities))).length}
                  icon={<Hammer size={20} />}
                  iconBg="var(--well-amber)"
                  delay={0.1}
                />
              </div>

              {toolsLoading && toolProviders.length === 0 ? (
                <div className="card" style={{ padding: "2.5rem", textAlign: "center" }}>
                  <div className="spinner" style={{ margin: "0 auto 0.75rem" }} aria-hidden />
                  <p className="page-subtitle" style={{ margin: 0 }}>Loading providers…</p>
                </div>
              ) : toolProviders.length === 0 ? (
                <EmptyState
                  icon={<Cpu size={40} strokeWidth={1.25} />}
                  title="No providers configured"
                  description="Configure tool providers in Settings to see execution activity here."
                />
              ) : (
                <StaggerList style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {toolProviders.map((p) => {
                    const capIcons: Record<string, typeof Cpu> = {
                      llm: Cpu,
                      build: Hammer,
                      frontend: Monitor,
                      fullstack: Zap,
                    };

                    return (
                      <StaggerItem key={p.name}>
                        <div
                          className="card card-flat"
                          style={{
                            padding: "1rem 1.25rem",
                            borderLeft: `4px solid ${p.healthy === true ? "var(--success)" : p.healthy === false ? "var(--error)" : "var(--border-strong)"}`,
                            display: "flex",
                            alignItems: "center",
                            gap: "1rem",
                          }}
                        >
                          <div style={{
                            width: 40, height: 40, borderRadius: "0.625rem",
                            background: p.healthy === true ? "var(--well-green)" : "var(--well-gray)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            flexShrink: 0,
                          }}>
                            {p.healthy === true ? (
                              <CheckCircle2 size={20} style={{ color: "var(--success)" }} />
                            ) : p.healthy === false ? (
                              <XCircle size={20} style={{ color: "var(--error)" }} />
                            ) : (
                              <AlertTriangle size={20} style={{ color: "var(--text-muted)" }} />
                            )}
                          </div>

                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontWeight: 600, fontSize: "0.9375rem" }}>{p.display_name}</div>
                            <div style={{ fontSize: "0.8rem", color: "var(--text-tertiary)", marginTop: "0.25rem" }}>
                              {p.healthy === true ? "Connected & healthy" : p.healthy === false ? "Not available" : "Status unknown"}
                            </div>
                          </div>

                          <div style={{ display: "flex", gap: "0.375rem", flexShrink: 0 }}>
                            {p.capabilities.map((cap) => {
                              const CapIcon = capIcons[cap] || Activity;
                              return (
                                <span
                                  key={cap}
                                  title={cap}
                                  style={{
                                    display: "inline-flex", alignItems: "center", gap: "0.25rem",
                                    padding: "0.2rem 0.5rem", borderRadius: "0.25rem",
                                    background: "var(--well-blue)", fontSize: "0.7rem",
                                    fontWeight: 500, color: "var(--text-secondary)",
                                    textTransform: "uppercase",
                                  }}
                                >
                                  <CapIcon size={10} />
                                  {cap}
                                </span>
                              );
                            })}
                          </div>
                        </div>
                      </StaggerItem>
                    );
                  })}
                </StaggerList>
              )}

              <div className="card" style={{ padding: "1.25rem", marginTop: "1rem" }}>
                <h3 style={{ margin: "0 0 0.75rem", fontSize: "1rem", fontWeight: 600 }}>
                  Execution Cost Comparison
                </h3>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div style={{
                    padding: "1rem", borderRadius: "0.75rem",
                    background: "var(--well-peach)", textAlign: "center",
                  }}>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>Direct API</div>
                    <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>Pay-per-token</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "0.25rem" }}>Usage-based pricing</div>
                  </div>
                  <div style={{
                    padding: "1rem", borderRadius: "0.75rem",
                    background: "var(--well-green)", textAlign: "center",
                  }}>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>Subscription Tools</div>
                    <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--success)" }}>Included</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "0.25rem" }}>Cursor / Claude Code</div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </PageShell>
    </>
  );
}
