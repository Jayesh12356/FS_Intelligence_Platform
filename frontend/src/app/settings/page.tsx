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

const CAPABILITY_LABELS: Record<string, { label: string; icon: typeof Cpu }> = {
  llm: { label: "LLM Provider", icon: Cpu },
  build: { label: "Build Provider", icon: Hammer },
  frontend: { label: "Frontend Provider", icon: Monitor },
  fullstack: { label: "Full-Stack Provider", icon: Zap },
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
        frontend_provider: config.frontend_provider,
        fallback_chain: config.fallback_chain,
        cursor_config: cursorParsed,
        claude_code_config: claudeParsed,
      });
      if (res.data) {
        setConfig(res.data);
        setCursorConfigText(JSON.stringify(res.data.cursor_config ?? {}, null, 2));
        setClaudeConfigText(JSON.stringify(res.data.claude_code_config ?? {}, null, 2));
        setSaveMsg("Configuration saved successfully");
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
      return base.filter((p) => p.llm_selectable !== false);
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
          color: saveMsg.includes("success") ? "var(--success)" : "var(--error)",
          fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.5rem",
        }}>
          {saveMsg.includes("success") ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          {saveMsg}
        </div>
      )}

      {/* Provider Selection Cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        {(["llm", "build", "frontend"] as const).map((cap) => {
          const capInfo = CAPABILITY_LABELS[cap];
          const Icon = capInfo?.icon ?? Cpu;
          const available = providersForCap(cap);
          const currentValue = config
            ? cap === "llm" ? config.llm_provider
              : cap === "build" ? config.build_provider
              : config.frontend_provider
            : "";

          return (
            <div key={cap} className="card" style={{ padding: "1.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
                <div style={{
                  width: 36, height: 36, borderRadius: "0.625rem",
                  background: cap === "llm" ? "var(--well-blue)" : cap === "build" ? "var(--well-amber)" : "var(--well-purple)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <Icon size={18} style={{ color: "var(--accent-primary)" }} />
                </div>
                <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>
                  {capInfo?.label ?? cap}
                </h3>
              </div>
              {cap === "llm" && (
                <p style={{
                  margin: "0 0 1rem",
                  fontSize: "0.8rem",
                  lineHeight: 1.45,
                  color: "var(--text-tertiary)",
                }}>
                  All three providers can run complete analysis. Direct API uses your configured keys. Claude Code tries the CLI first, falling back to Direct API if needed. Cursor drives workflows via MCP tools in the IDE.
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
                        else if (cap === "build") updated.build_provider = p.name;
                        else updated.frontend_provider = p.name;
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
                        {health === true && <CheckCircle2 size={12} style={{ color: "var(--success)" }} />}
                        {health === false && <XCircle size={12} style={{ color: "var(--error)" }} />}
                        {health == null && <span style={{ color: "var(--text-tertiary)" }}>Not tested</span>}
                        {health === true && <span style={{ color: "var(--success)" }}>Healthy</span>}
                        {health === false && <span style={{ color: "var(--error)" }}>Unavailable</span>}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* Provider Workflow Guide */}
        <ProviderWorkflowGuide />

        {/* Fallback Chain */}
        <div className="card" style={{ padding: "1.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
            <div style={{
              width: 36, height: 36, borderRadius: "0.625rem",
              background: "var(--well-peach)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <RefreshCw size={18} style={{ color: "var(--accent-primary)" }} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>Fallback Chain</h3>
              <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-tertiary)" }}>
                If the primary provider fails, the system tries providers in this order
              </p>
            </div>
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {(config?.fallback_chain ?? ["api"]).map((name, i) => (
              <div key={`${name}-${i}`} style={{
                display: "flex", alignItems: "center", gap: "0.5rem",
                padding: "0.5rem 0.75rem", borderRadius: "0.5rem",
                background: "var(--bg-main)", border: "1px solid var(--border-subtle)",
                fontSize: "0.85rem",
              }}>
                <span style={{ fontWeight: 600, color: "var(--accent-primary)", fontSize: "0.75rem" }}>{i + 1}</span>
                <span>{providers.find((p) => p.name === name)?.display_name ?? name}</span>
              </div>
            ))}
          </div>
        </div>

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
            description="Forwarded to the Claude Code provider (e.g. { 'cli_binary': 'claude', 'fallback_to_api': true })."
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
                        <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--success)" }}>
                          Provider is connected and healthy.
                        </div>
                      )}
                      {health === false && (
                        <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--error)" }}>
                          Provider is not available. Check configuration and API keys.
                        </div>
                      )}
                      {testErrors[p.name] && (
                        <div
                          style={{
                            marginTop: "0.5rem",
                            padding: "0.5rem 0.6rem",
                            fontSize: "0.75rem",
                            color: "var(--error)",
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
      />
      {error && (
        <p style={{ margin: "0.35rem 0 0", fontSize: "0.75rem", color: "var(--error)" }}>
          {error}
        </p>
      )}
    </div>
  );
}

const PROVIDER_DESCRIPTIONS = [
  {
    icon: Cpu,
    name: "Direct API",
    color: "var(--well-blue)",
    what: "Server-side LLM via Anthropic, OpenAI, Groq, or OpenRouter API keys.",
    when: "Web UI analysis, refinement, and FS generation. The engine behind all providers.",
    limits: "No autonomous builds. Use Claude Code or Cursor for code generation.",
  },
  {
    icon: Terminal,
    name: "Claude Code",
    color: "var(--well-purple)",
    what: "Tries Claude CLI first for text generation; falls back to Direct API if CLI returns insufficient content. Full builds via CLI agent with MCP tools.",
    when: "Fully autonomous headless workflows. Ideal when you have a Claude subscription (any model via CLI). Falls back seamlessly.",
    limits: "Requires Claude CLI installed and authenticated (claude login).",
  },
  {
    icon: Monitor,
    name: "Cursor",
    color: "var(--well-amber, rgba(245,158,11,0.1))",
    what: "Full analysis + builds via 88 MCP tools inside the Cursor IDE.",
    when: "Interactive workflows with IDE visibility. Complete idea-to-production with agent mode.",
    limits: "Cursor IDE must be running with MCP server connected.",
  },
];

function ProviderWorkflowGuide() {
  return (
    <div className="card" style={{ padding: "1.5rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
        <div style={{
          width: 36, height: 36, borderRadius: "0.625rem",
          background: "var(--well-blue)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <Info size={18} style={{ color: "var(--accent-primary)" }} />
        </div>
        <div>
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>Which Provider Should I Use?</h3>
          <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-tertiary)" }}>
            Three providers, three workflows -- pick the one that fits your process
          </p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "1rem" }}>
        {PROVIDER_DESCRIPTIONS.map((p) => {
          const Icon = p.icon;
          return (
            <div key={p.name} style={{
              padding: "1rem",
              borderRadius: "0.75rem",
              background: "var(--bg-main)",
              border: "1px solid var(--border-subtle)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <div style={{
                  width: 28, height: 28, borderRadius: "0.375rem",
                  background: p.color, display: "flex",
                  alignItems: "center", justifyContent: "center",
                }}>
                  <Icon size={14} style={{ color: "var(--accent-primary)" }} />
                </div>
                <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  {p.name}
                </span>
              </div>
              <div style={{ fontSize: "0.8rem", lineHeight: 1.55, color: "var(--text-secondary)" }}>
                <p style={{ margin: "0 0 0.35rem" }}><strong>What:</strong> {p.what}</p>
                <p style={{ margin: "0 0 0.35rem" }}><strong>Best for:</strong> {p.when}</p>
                <p style={{ margin: 0, color: "var(--text-tertiary)", fontStyle: "italic" }}>{p.limits}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
