"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Settings,
  CheckCircle2,
  XCircle,
  Loader2,
  RefreshCw,
  Cpu,
  Hammer,
  Monitor,
  ChevronDown,
  ChevronUp,
  Zap,
  AlertCircle,
  Terminal,
  Info,
} from "lucide-react";
import { PageShell } from "@/components/index";
import {
  listProviders,
  getToolConfig,
  updateToolConfig,
  testProvider,
  type ProviderInfo,
  type ToolConfig,
} from "@/lib/api";
import { notifyToolConfigUpdated } from "@/lib/toolConfig";

const CAPABILITY_LABELS: Record<
  string,
  { label: string; icon: typeof Cpu; caption: string }
> = {
  llm: {
    label: "Document LLM",
    icon: Cpu,
    caption:
      "Powers Generate FS, Analyze, and Reverse FS. Direct API and Claude Code run synchronously on the backend; Cursor opens a one-click paste dialog for each action so the IDE does the work — zero Direct API tokens are spent on the Cursor path.",
  },
  build: {
    label: "Build Agent",
    icon: Hammer,
    caption:
      "Powers the Build step. Runs autonomously inside Cursor (via MCP) or headless Claude Code, writing files into your output folder.",
  },
  fullstack: { label: "Full-Stack Provider", icon: Zap, caption: "" },
};

function parseJsonObject(text: string): Record<string, unknown> | Error {
  try {
    const trimmed = (text || "").trim();
    if (!trimmed) return {};
    const parsed = JSON.parse(trimmed);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return new Error("Must be a JSON object (e.g. {\"key\": \"value\"}).");
    }
    return parsed as Record<string, unknown>;
  } catch (err) {
    return err instanceof Error ? err : new Error("Invalid JSON");
  }
}

export default function SettingsPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [config, setConfig] = useState<ToolConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, boolean | null>>({});
  const [testErrors, setTestErrors] = useState<Record<string, string | null>>({});
  const [saveMsg, setSaveMsg] = useState("");
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  const [cursorConfigText, setCursorConfigText] = useState("{}");
  const [claudeConfigText, setClaudeConfigText] = useState("{}");
  const [cursorConfigError, setCursorConfigError] = useState<string | null>(null);
  const [claudeConfigError, setClaudeConfigError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const [pRes, cRes] = await Promise.all([listProviders(), getToolConfig()]);
      setProviders(pRes.data ?? []);
      const cfg = cRes.data ?? null;
      setConfig(cfg);
      if (cfg) {
        setCursorConfigText(JSON.stringify(cfg.cursor_config ?? {}, null, 2));
        setClaudeConfigText(JSON.stringify(cfg.claude_code_config ?? {}, null, 2));
        setCursorConfigError(null);
        setClaudeConfigError(null);
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Failed to load settings. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSave = useCallback(async () => {
    if (!config) return;

    const cursorParsed = parseJsonObject(cursorConfigText);
    const claudeParsed = parseJsonObject(claudeConfigText);
    if (cursorParsed instanceof Error) {
      setCursorConfigError(cursorParsed.message);
    } else {
      setCursorConfigError(null);
    }
    if (claudeParsed instanceof Error) {
      setClaudeConfigError(claudeParsed.message);
    } else {
      setClaudeConfigError(null);
    }
    if (cursorParsed instanceof Error || claudeParsed instanceof Error) {
      setSaveMsg("Fix JSON errors before saving");
      setTimeout(() => setSaveMsg(""), 3000);
      return;
    }

    setSaving(true);
    setSaveMsg("");
    try {
      const res = await updateToolConfig({
        llm_provider: config.llm_provider,
        build_provider: config.build_provider,
        cursor_config: cursorParsed,
        claude_code_config: claudeParsed,
      });
      if (res.data) {
        setConfig(res.data);
        setCursorConfigText(JSON.stringify(res.data.cursor_config ?? {}, null, 2));
        setClaudeConfigText(JSON.stringify(res.data.claude_code_config ?? {}, null, 2));
        setSaveMsg("Configuration saved successfully");
        notifyToolConfigUpdated(res.data);
        setTimeout(() => setSaveMsg(""), 3000);
      }
    } catch (err) {
      setSaveMsg(err instanceof Error ? `Failed to save: ${err.message}` : "Failed to save configuration");
    } finally {
      setSaving(false);
    }
  }, [config, cursorConfigText, claudeConfigText]);

  const handleTest = useCallback(async (providerName: string) => {
    setTesting(providerName);
    setTestErrors((prev) => ({ ...prev, [providerName]: null }));
    try {
      const res = await testProvider(providerName);
      const healthy = res.data?.healthy ?? false;
      setTestResults((prev) => ({ ...prev, [providerName]: healthy }));
      setTestErrors((prev) => ({
        ...prev,
        [providerName]: res.data?.error && !healthy ? res.data.error : null,
      }));
    } catch (err) {
      setTestResults((prev) => ({ ...prev, [providerName]: false }));
      setTestErrors((prev) => ({
        ...prev,
        [providerName]:
          err instanceof Error ? err.message : "Connection test failed",
      }));
    } finally {
      setTesting(null);
    }
  }, []);

  const handleTestAll = useCallback(async () => {
    for (const p of providers) {
      await handleTest(p.name);
    }
  }, [providers, handleTest]);

  const providersForCap = (cap: string) => {
    const base = providers.filter((p) => p.capabilities.includes(cap));
    if (cap === "llm") {
      // Honour the provider-side `llm_selectable` flag. Cursor is
      // selectable and runs as paste-per-action: each Generate FS /
      // Analyze / Reverse FS / Refine / Impact click mints its own
      // CursorTask and opens a copy-paste modal. No server-side LLM
      // call is made on the Cursor path.
      return base.filter((p) => p.llm_selectable !== false);
    }
    if (cap === "build") {
      return base.filter((p) => p.name !== "api");
    }
    return base;
  };

  if (loading) {
    return (
      <PageShell title="Settings" subtitle="Configure tool providers and orchestration" backHref="/" backLabel="Home" maxWidth="56rem">
        <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
          <Loader2 size={28} className="spin" style={{ color: "var(--text-tertiary)" }} />
        </div>
      </PageShell>
    );
  }

  if (fetchError) {
    return (
      <PageShell title="Settings" subtitle="Configure tool providers and orchestration" backHref="/" backLabel="Home" maxWidth="56rem">
        <div className="alert alert-error" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <AlertCircle size={18} />
          {fetchError}
        </div>
        <button className="btn btn-primary btn-sm" onClick={fetchData} style={{ marginTop: "0.75rem" }}>
          Retry
        </button>
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Settings"
      subtitle="Configure tool providers and orchestration preferences"
      backHref="/"
      backLabel="Home"
      maxWidth="56rem"
      actions={
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button className="btn btn-secondary btn-sm" onClick={handleTestAll} style={{ gap: "0.4rem" }}>
            <RefreshCw size={14} /> Test All
          </button>
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving} style={{ gap: "0.4rem" }}>
            {saving ? <Loader2 size={14} className="spin" /> : <Settings size={14} />}
            Save Config
          </button>
        </div>
      }
    >
      {saveMsg && (
        <div style={{
          padding: "0.75rem 1rem", borderRadius: "0.5rem", marginBottom: "1rem",
          background: saveMsg.includes("success") ? "var(--success-bg, rgba(34,197,94,0.1))" : "var(--error-bg)",
          color: saveMsg.includes("success") ? "var(--success-text)" : "var(--error-text)",
          fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.5rem",
        }}>
          {saveMsg.includes("success") ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          {saveMsg}
        </div>
      )}

      {/* Provider Selection Cards — two cards, one per role */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        <div
          style={{
            padding: "0.9rem 1rem",
            borderRadius: "0.75rem",
            background: "var(--well-blue)",
            border: "1px solid var(--border-subtle)",
            fontSize: "0.82rem",
            lineHeight: 1.55,
            color: "var(--text-secondary)",
            display: "flex",
            gap: "0.6rem",
            alignItems: "flex-start",
          }}
        >
          <Info size={16} style={{ color: "var(--accent-primary)", flexShrink: 0, marginTop: 2 }} />
          <div>
            <strong style={{ color: "var(--text-primary)" }}>Three-step product, two provider roles.</strong>{" "}
            Pick who writes your Document (Generate FS / Analyze / Reverse FS) and
            who drives the Build (Cursor Agent or headless Claude Code). Direct
            API handles documents fast; Cursor and Claude Code are the only
            providers that can write multi-file code.
          </div>
        </div>

        {(["llm", "build"] as const).map((cap) => {
          const capInfo = CAPABILITY_LABELS[cap];
          const Icon = capInfo?.icon ?? Cpu;
          const available = providersForCap(cap);
          const currentValue = config
            ? cap === "llm"
              ? config.llm_provider
              : config.build_provider
            : "";

          return (
            <div key={cap} className="card" style={{ padding: "1.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.6rem" }}>
                <div style={{
                  width: 36, height: 36, borderRadius: "0.625rem",
                  background: cap === "llm" ? "var(--well-blue)" : "var(--well-amber)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <Icon size={18} style={{ color: "var(--accent-primary)" }} />
                </div>
                <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>
                  {capInfo?.label ?? cap}
                </h3>
              </div>
              {capInfo?.caption && (
                <p style={{
                  margin: "0 0 1rem",
                  fontSize: "0.8rem",
                  lineHeight: 1.5,
                  color: "var(--text-tertiary)",
                }}>
                  {capInfo.caption}
                </p>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "0.75rem" }}>
                {available.map((p) => {
                  const isSelected = p.name === currentValue;
                  const health = p.healthy ?? testResults[p.name];
                  return (
                    <button
                      key={p.name}
                      onClick={() => {
                        if (!config) return;
                        const updated = { ...config };
                        if (cap === "llm") updated.llm_provider = p.name;
                        else updated.build_provider = p.name;
                        setConfig(updated);
                      }}
                      style={{
                        display: "flex", flexDirection: "column", gap: "0.5rem",
                        padding: "1rem", borderRadius: "0.75rem", textAlign: "left",
                        border: isSelected ? "2px solid var(--accent-primary)" : "1px solid var(--border-subtle)",
                        background: isSelected ? "var(--well-blue)" : "var(--bg-main)",
                        cursor: "pointer", transition: "all 0.15s ease",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span style={{ fontSize: "0.9rem", fontWeight: isSelected ? 600 : 500, color: "var(--text-primary)" }}>
                          {p.display_name}
                        </span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.75rem" }}>
                        {health === true && <CheckCircle2 size={12} style={{ color: "var(--success)" }} aria-hidden />}
                        {health === false && <XCircle size={12} style={{ color: "var(--error)" }} aria-hidden />}
                        {health == null && <span style={{ color: "var(--text-tertiary)" }}>Not tested</span>}
                        {health === true && <span style={{ color: "var(--success-text)" }}>Healthy</span>}
                        {health === false && <span style={{ color: "var(--error-text)" }}>Unavailable</span>}
                      </div>
                    </button>
                  );
                })}
                {available.length === 0 && (
                  <div style={{
                    padding: "0.75rem 1rem",
                    fontSize: "0.8rem",
                    color: "var(--text-tertiary)",
                    border: "1px dashed var(--border-subtle)",
                    borderRadius: "0.5rem",
                  }}>
                    No providers registered for this role yet.
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Provider Workflow Guide */}
        <ProviderWorkflowGuide />

        {/* Advanced Provider Config JSON */}
        <div className="card" style={{ padding: "1.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: "0.625rem",
                background: "var(--well-blue)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Settings size={18} style={{ color: "var(--accent-primary)" }} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>
                Advanced provider configuration
              </h3>
              <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-tertiary)" }}>
                JSON blocks passed through to the provider adapters. Invalid JSON
                will prevent saving.
              </p>
            </div>
          </div>

          <JsonConfigEditor
            label="Cursor config"
            description="Forwarded to the Cursor provider (e.g. { 'mcp_session_ttl_s': 3600 })."
            value={cursorConfigText}
            onChange={(next) => {
              setCursorConfigText(next);
              const parsed = parseJsonObject(next);
              setCursorConfigError(parsed instanceof Error ? parsed.message : null);
            }}
            error={cursorConfigError}
          />

          <div style={{ height: "1rem" }} />

          <JsonConfigEditor
            label="Claude Code config"
            description="Forwarded to the Claude Code provider (e.g. { 'cli_binary': 'claude' })."
            value={claudeConfigText}
            onChange={(next) => {
              setClaudeConfigText(next);
              const parsed = parseJsonObject(next);
              setClaudeConfigError(parsed instanceof Error ? parsed.message : null);
            }}
            error={claudeConfigError}
          />
        </div>

        {/* Provider Details */}
        <div className="card" style={{ padding: "1.5rem" }}>
          <h3 style={{ margin: "0 0 1rem", fontSize: "1rem", fontWeight: 600 }}>
            All Providers
          </h3>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {providers.map((p) => {
              const expanded = expandedProvider === p.name;
              const health = p.healthy ?? testResults[p.name];
              return (
                <div key={p.name} style={{
                  borderRadius: "0.75rem", border: "1px solid var(--border-subtle)",
                  overflow: "hidden",
                }}>
                  <button
                    onClick={() => setExpandedProvider(expanded ? null : p.name)}
                    style={{
                      display: "flex", alignItems: "center", width: "100%",
                      padding: "0.75rem 1rem", background: "transparent",
                      border: "none", cursor: "pointer", gap: "0.75rem",
                    }}
                  >
                    <div style={{ flex: 1, textAlign: "left" }}>
                      <span style={{ fontSize: "0.9rem", fontWeight: 500, color: "var(--text-primary)" }}>
                        {p.display_name}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      <div style={{ display: "flex", gap: "0.25rem" }}>
                        {p.capabilities.map((c) => (
                          <span key={c} style={{
                            padding: "0.15rem 0.5rem", borderRadius: "0.25rem",
                            background: "var(--well-blue)", fontSize: "0.7rem",
                            fontWeight: 500, color: "var(--text-secondary)",
                            textTransform: "uppercase",
                          }}>
                            {c}
                          </span>
                        ))}
                      </div>
                      {health === true && <CheckCircle2 size={16} style={{ color: "var(--success)" }} />}
                      {health === false && <XCircle size={16} style={{ color: "var(--error)" }} />}
                      {expanded ? <ChevronUp size={16} style={{ color: "var(--text-tertiary)" }} /> : <ChevronDown size={16} style={{ color: "var(--text-tertiary)" }} />}
                    </div>
                  </button>

                  {expanded && (
                    <div style={{
                      padding: "0 1rem 1rem", borderTop: "1px solid var(--border-subtle)",
                      paddingTop: "0.75rem",
                    }}>
                      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleTest(p.name)}
                          disabled={testing === p.name}
                          style={{ gap: "0.4rem" }}
                        >
                          {testing === p.name ? <Loader2 size={12} className="spin" /> : <RefreshCw size={12} />}
                          Test Connection
                        </button>
                      </div>
                      <div style={{ fontSize: "0.8rem", color: "var(--text-tertiary)" }}>
                        <strong>Capabilities:</strong> {p.capabilities.join(", ")}
                      </div>
                      {p.health_note ? (
                        <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--text-tertiary)" }}>
                          {p.health_note}
                        </div>
                      ) : null}
                      {health === true && (
                        <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--success-text)" }}>
                          Provider is connected and healthy.
                        </div>
                      )}
                      {health === false && (
                        <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--error-text)" }}>
                          Provider is not available. Check configuration and API keys.
                        </div>
                      )}
                      {testErrors[p.name] && (
                        <div
                          style={{
                            marginTop: "0.5rem",
                            padding: "0.5rem 0.6rem",
                            fontSize: "0.75rem",
                            color: "var(--error-text)",
                            background: "var(--bg-error-subtle, rgba(239,68,68,0.08))",
                            border: "1px solid var(--error)",
                            borderRadius: "0.375rem",
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                          }}
                        >
                          <strong>Last error:</strong> {testErrors[p.name]}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </PageShell>
  );
}

interface JsonConfigEditorProps {
  label: string;
  description?: string;
  value: string;
  onChange: (v: string) => void;
  error?: string | null;
}

function JsonConfigEditor({ label, description, value, onChange, error }: JsonConfigEditorProps) {
  const handleFormat = () => {
    const parsed = parseJsonObject(value);
    if (parsed instanceof Error) return;
    onChange(JSON.stringify(parsed, null, 2));
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: "0.5rem", marginBottom: "0.35rem" }}>
        <div>
          <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
            {label}
          </label>
          {description && (
            <p style={{ margin: "0.15rem 0 0", fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
              {description}
            </p>
          )}
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={handleFormat} disabled={!!error}>
          Format
        </button>
      </div>
      <textarea
        spellCheck={false}
        className="form-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={6}
        style={{
          fontFamily: "var(--font-mono, ui-monospace, monospace)",
          fontSize: "0.8125rem",
          width: "100%",
          resize: "vertical",
          borderColor: error ? "var(--error)" : undefined,
        }}
        aria-invalid={!!error}
        aria-label={label}
      />
      {error && (
        <p style={{ margin: "0.35rem 0 0", fontSize: "0.75rem", color: "var(--error-text)" }}>
          {error}
        </p>
      )}
    </div>
  );
}

type Mode = "sync" | "paste" | "cli" | "mcp" | "no";

interface MatrixCell {
  mode: Mode;
  note: string;
}

const MATRIX_COLUMNS: {
  key: "api" | "claude_code" | "cursor";
  label: string;
  icon: typeof Cpu;
  color: string;
}[] = [
  { key: "api", label: "Direct API", icon: Cpu, color: "var(--well-blue)" },
  {
    key: "claude_code",
    label: "Claude Code",
    icon: Terminal,
    color: "var(--well-purple)",
  },
  {
    key: "cursor",
    label: "Cursor",
    icon: Monitor,
    color: "var(--well-amber, rgba(245,158,11,0.1))",
  },
];

const MATRIX_ROWS: {
  key: string;
  label: string;
  cells: Record<"api" | "claude_code" | "cursor", MatrixCell>;
}[] = [
  {
    key: "generate",
    label: "Generate FS",
    cells: {
      api: { mode: "sync", note: "Synchronous call through Direct API." },
      claude_code: {
        mode: "cli",
        note: "Runs via the local claude CLI (no OpenRouter tokens).",
      },
      cursor: {
        mode: "paste",
        note: "Opens a paste dialog; Cursor generates the FS via MCP.",
      },
    },
  },
  {
    key: "analyze",
    label: "Analyze",
    cells: {
      api: { mode: "sync", note: "Synchronous pipeline on Direct API." },
      claude_code: { mode: "cli", note: "Pipeline runs through claude CLI." },
      cursor: {
        mode: "paste",
        note: "Paste dialog; Cursor submits quality + ambiguity results via MCP.",
      },
    },
  },
  {
    key: "reverse",
    label: "Reverse FS",
    cells: {
      api: { mode: "sync", note: "Synchronous reverse pipeline on Direct API." },
      claude_code: { mode: "cli", note: "Reverse pipeline through claude CLI." },
      cursor: {
        mode: "paste",
        note: "Paste dialog; Cursor submits reverse FS + report via MCP.",
      },
    },
  },
  {
    key: "build",
    label: "Build",
    cells: {
      api: { mode: "no", note: "Direct API cannot write multi-file code." },
      claude_code: {
        mode: "mcp",
        note: "Autonomous headless build via claude CLI + MCP.",
      },
      cursor: {
        mode: "mcp",
        note: "Autonomous build inside Cursor via MCP tools.",
      },
    },
  },
];

const MODE_STYLE: Record<
  Mode,
  { label: string; fg: string; bg: string; border: string }
> = {
  sync: {
    label: "Sync call",
    fg: "var(--text-accent, #4338ca)",
    bg: "var(--bg-accent-subtle, #eef2ff)",
    border: "var(--border-accent, #c7d2fe)",
  },
  paste: {
    label: "Paste in Cursor",
    fg: "var(--text-warning, #b45309)",
    bg: "var(--bg-warning-subtle, #fffbeb)",
    border: "var(--border-warning, #fde68a)",
  },
  cli: {
    label: "Claude CLI",
    fg: "var(--text-success, #047857)",
    bg: "var(--bg-success-subtle, #ecfdf5)",
    border: "var(--border-success, #a7f3d0)",
  },
  mcp: {
    label: "MCP autonomous",
    fg: "var(--text-success, #047857)",
    bg: "var(--bg-success-subtle, #ecfdf5)",
    border: "var(--border-success, #a7f3d0)",
  },
  no: {
    label: "Not supported",
    fg: "var(--text-tertiary)",
    bg: "var(--bg-subtle, rgba(0,0,0,0.03))",
    border: "var(--border-subtle)",
  },
};

function ProviderWorkflowGuide() {
  return (
    <div className="card" style={{ padding: "1.5rem" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          marginBottom: "1rem",
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "0.625rem",
            background: "var(--well-blue)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Info size={18} style={{ color: "var(--accent-primary)" }} />
        </div>
        <div>
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>
            Provider matrix
          </h3>
          <p
            style={{
              margin: 0,
              fontSize: "0.8rem",
              color: "var(--text-tertiary)",
            }}
          >
            How each action is served by each provider. Cursor never
            calls the Direct API — it always asks you to paste a prompt.
          </p>
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "separate",
            borderSpacing: 0,
            fontSize: "0.82rem",
            minWidth: 640,
          }}
        >
          <thead>
            <tr>
              <th
                style={{
                  textAlign: "left",
                  padding: "0.6rem 0.75rem",
                  fontSize: "0.72rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  color: "var(--text-tertiary)",
                  borderBottom: "1px solid var(--border-subtle)",
                }}
              >
                Action
              </th>
              {MATRIX_COLUMNS.map((col) => {
                const Icon = col.icon;
                return (
                  <th
                    key={col.key}
                    style={{
                      textAlign: "left",
                      padding: "0.6rem 0.75rem",
                      borderBottom: "1px solid var(--border-subtle)",
                    }}
                  >
                    <div
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.4rem",
                      }}
                    >
                      <div
                        style={{
                          width: 22,
                          height: 22,
                          borderRadius: "0.375rem",
                          background: col.color,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        <Icon size={12} style={{ color: "var(--accent-primary)" }} />
                      </div>
                      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                        {col.label}
                      </span>
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {MATRIX_ROWS.map((row) => (
              <tr key={row.key}>
                <th
                  scope="row"
                  style={{
                    textAlign: "left",
                    padding: "0.75rem",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    borderBottom: "1px solid var(--border-subtle)",
                    verticalAlign: "top",
                  }}
                >
                  {row.label}
                </th>
                {MATRIX_COLUMNS.map((col) => {
                  const cell = row.cells[col.key];
                  const style = MODE_STYLE[cell.mode];
                  return (
                    <td
                      key={col.key}
                      style={{
                        padding: "0.75rem",
                        verticalAlign: "top",
                        borderBottom: "1px solid var(--border-subtle)",
                      }}
                    >
                      <div
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.3rem",
                          padding: "0.15rem 0.45rem",
                          borderRadius: "999px",
                          background: style.bg,
                          border: `1px solid ${style.border}`,
                          color: style.fg,
                          fontSize: "0.72rem",
                          fontWeight: 600,
                          marginBottom: "0.35rem",
                        }}
                      >
                        {style.label}
                      </div>
                      <div
                        style={{
                          color: "var(--text-secondary)",
                          fontSize: "0.78rem",
                          lineHeight: 1.45,
                        }}
                      >
                        {cell.note}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
