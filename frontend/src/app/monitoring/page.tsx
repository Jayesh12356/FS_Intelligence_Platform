"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getMcpSession,
  listMcpSessionEvents,
  listMcpSessions,
  MCPSession,
  MCPSessionEvent,
} from "@/lib/api";

function formatTime(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

export default function MonitoringPage() {
  const [sessions, setSessions] = useState<MCPSession[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<MCPSession | null>(null);
  const [events, setEvents] = useState<MCPSessionEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function loadSessions() {
      try {
        const res = await listMcpSessions(100);
        if (!mounted) return;
        const rows = res.data?.sessions || [];
        setSessions(rows);
        if (!selectedId && rows.length > 0) {
          setSelectedId(rows[0].id);
        }
      } catch (e) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : "Failed to load sessions");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadSessions();
    const timer = setInterval(loadSessions, 5000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    const sid = selectedId;
    let cancelled = false;
    async function loadDetails() {
      try {
        const [sessionRes, eventRes] = await Promise.all([
          getMcpSession(sid),
          listMcpSessionEvents(sid, 300),
        ]);
        if (cancelled) return;
        setSelected(sessionRes.data || null);
        setEvents(eventRes.data?.events || []);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load session details");
      }
    }
    loadDetails();
    const timer = setInterval(loadDetails, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [selectedId]);

  const fsChecks = useMemo(() => {
    return events.filter((e) =>
      e.event_type.includes("check") || e.event_type.includes("manifest")
    );
  }, [events]);

  return (
    <section>
      <h1 style={{ marginBottom: "0.5rem" }}>Live MCP Monitoring</h1>
      <p style={{ color: "var(--text-muted)", marginBottom: "1rem" }}>
        Observe active MCP sessions, current phase, compliance checks, and errors in near real time.
      </p>
      {error && (
        <div className="card" style={{ borderLeft: "3px solid #ef4444", marginBottom: "1rem" }}>
          {error}
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: "1rem" }}>
        <div className="card">
          <h3>Sessions</h3>
          {loading && <p>Loading...</p>}
          {!loading && sessions.length === 0 && <p>No MCP sessions yet.</p>}
          <div style={{ display: "grid", gap: "0.5rem" }}>
            {sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => setSelectedId(s.id)}
                style={{
                  textAlign: "left",
                  border: selectedId === s.id ? "1px solid var(--color-primary)" : "1px solid var(--border-color)",
                  background: "transparent",
                  borderRadius: "8px",
                  padding: "0.6rem",
                  cursor: "pointer",
                  color: "inherit",
                }}
              >
                <div style={{ fontWeight: 600 }}>{s.target_stack || "Unknown stack"}</div>
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{s.status} - phase {s.phase}/{s.total_phases || "?"}</div>
              </button>
            ))}
          </div>
        </div>
        <div className="card">
          <h3>Session Details</h3>
          {!selected && <p>Select a session.</p>}
          {selected && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(120px,1fr))", gap: "0.75rem", marginBottom: "1rem" }}>
                <div><strong>Status</strong><div>{selected.status}</div></div>
                <div><strong>Phase</strong><div>{selected.phase}/{selected.total_phases || "?"}</div></div>
                <div><strong>Started</strong><div>{formatTime(selected.started_at)}</div></div>
                <div><strong>Ended</strong><div>{formatTime(selected.ended_at)}</div></div>
              </div>
              <h4>FS Compliance / Guardrail Events</h4>
              <div style={{ maxHeight: 160, overflow: "auto", marginBottom: "1rem" }}>
                {fsChecks.length === 0 && <p style={{ color: "var(--text-muted)" }}>No compliance events yet.</p>}
                {fsChecks.map((e) => (
                  <div key={e.id} style={{ fontSize: "0.85rem", marginBottom: "0.4rem" }}>
                    [{e.status}] {e.message}
                  </div>
                ))}
              </div>
              <h4>Timeline</h4>
              <div style={{ maxHeight: 360, overflow: "auto" }}>
                {events.map((e) => (
                  <div key={e.id} style={{ borderBottom: "1px solid var(--border-color)", padding: "0.45rem 0" }}>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                      {formatTime(e.created_at)} - phase {e.phase} - {e.event_type}
                    </div>
                    <div style={{ fontSize: "0.9rem" }}>{e.message || "(no message)"}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

