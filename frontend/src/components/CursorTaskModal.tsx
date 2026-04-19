"use client";

/**
 * CursorTaskModal — Paste-per-action handoff modal for Cursor.
 *
 * When the user triggers Generate FS / Analyze / Reverse FS with
 * `llm_provider == "cursor"`, the backend mints a `CursorTask` and
 * returns a `CursorTaskEnvelope`. This modal:
 *
 *   1. Shows the mega-prompt the user must paste into a NEW Cursor
 *      chat session (with the MCP server connected).
 *   2. Polls `GET /api/cursor-tasks/{task_id}` every 2s.
 *   3. Calls `onDone(resultRef)` when the task reaches status
 *      `done`, or surfaces an error for `failed` / `expired`.
 *
 * The modal is intentionally self-contained: it owns polling, copy
 * buttons, and cancellation. Callers only supply the envelope and a
 * navigation callback.
 *
 * This is the ONLY UI surface used for Cursor handoffs — Create,
 * Document detail (Analyze + Build) and the Reverse FS page all
 * delegate here so the UX is identical across the product.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  Copy,
  ExternalLink,
  Loader2,
  Server,
  XCircle,
} from "lucide-react";

import Modal from "./Modal";
import {
  cancelCursorTask,
  type CursorTaskEnvelope,
  type CursorTaskPoll,
  pollCursorTask,
} from "@/lib/api";

const SUBMIT_TOOL_BY_KIND: Record<CursorTaskEnvelope["kind"], string> = {
  generate_fs: "submit_generate_fs",
  analyze: "submit_analyze",
  reverse_fs: "submit_reverse_fs",
  refine: "submit_refine",
  impact: "submit_impact",
};

export interface CursorTaskModalProps {
  envelope: CursorTaskEnvelope | null;
  onClose: () => void;
  /** Called when the task reaches `done`. `resultRef` is usually the new FSDocument id. */
  onDone?: (resultRef: string | null, poll: CursorTaskPoll) => void;
  /** Override the poll interval (ms). Defaults to 2000. */
  pollIntervalMs?: number;
}

const KIND_COPY: Record<
  CursorTaskEnvelope["kind"],
  { title: string; description: string; cta: string }
> = {
  generate_fs: {
    title: "Generate FS with Cursor",
    description:
      "Paste this prompt into a new Cursor chat (MCP enabled). Cursor will generate the FS and push it back here via the platform's MCP tools — no Direct API tokens are spent.",
    cta: "Paste into Cursor",
  },
  analyze: {
    title: "Analyze with Cursor",
    description:
      "Paste this prompt into a new Cursor chat (MCP enabled). Cursor will run quality + ambiguity + task analysis and submit the results through MCP.",
    cta: "Paste into Cursor",
  },
  reverse_fs: {
    title: "Reverse FS with Cursor",
    description:
      "Paste this prompt into a new Cursor chat (MCP enabled). Cursor will read the code context, draft the reverse-engineered FS, and submit the result through MCP.",
    cta: "Paste into Cursor",
  },
  refine: {
    title: "Refine FS with Cursor",
    description:
      "Paste this prompt into a new Cursor chat (MCP enabled). Cursor will rewrite the FS using the accepted clarifications and submit the refined markdown through MCP.",
    cta: "Paste into Cursor",
  },
  impact: {
    title: "Impact analysis with Cursor",
    description:
      "Paste this prompt into a new Cursor chat (MCP enabled). Cursor will diff the two FS versions, classify task impacts, and submit the results through MCP.",
    cta: "Paste into Cursor",
  },
};

export default function CursorTaskModal({
  envelope,
  onClose,
  onDone,
  pollIntervalMs = 2000,
}: CursorTaskModalProps) {
  const [poll, setPoll] = useState<CursorTaskPoll | null>(null);
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const [copiedMcp, setCopiedMcp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  const open = envelope !== null;

  const status = poll?.status ?? envelope?.status ?? "pending";
  const kindCopy = envelope ? KIND_COPY[envelope.kind] : null;
  const submitTool = envelope
    ? SUBMIT_TOOL_BY_KIND[envelope.kind] ?? "submit_*"
    : "submit_*";
  const promptText = envelope?.prompt ?? "";
  const mcpSnippet = envelope?.mcp_snippet ?? "";

  const copyToClipboard = useCallback(async (text: string): Promise<boolean> => {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return false;
    }
  }, []);

  const handleCopyPrompt = useCallback(async () => {
    if (!envelope) return;
    if (await copyToClipboard(promptText)) {
      setCopiedPrompt(true);
      setTimeout(() => setCopiedPrompt(false), 2200);
    }
  }, [envelope, promptText, copyToClipboard]);

  const handleCopyMcp = useCallback(async () => {
    if (!envelope) return;
    if (await copyToClipboard(mcpSnippet)) {
      setCopiedMcp(true);
      setTimeout(() => setCopiedMcp(false), 2200);
    }
  }, [envelope, mcpSnippet, copyToClipboard]);

  const handleCancel = useCallback(async () => {
    if (!envelope) {
      onClose();
      return;
    }
    try {
      await cancelCursorTask(envelope.task_id);
    } catch {
      /* ignore cancel errors; we close anyway */
    }
    onClose();
  }, [envelope, onClose]);

  useEffect(() => {
    if (!envelope) return;
    let alive = true;
    const controller = new AbortController();

    const tick = async () => {
      try {
        const res = await pollCursorTask(envelope.task_id, {
          signal: controller.signal,
        });
        if (!alive) return;
        const next = res.data ?? null;
        setPoll(next);
        if (!next) return;
        if (next.status === "done") {
          onDoneRef.current?.(next.result_ref, next);
        } else if (next.status === "failed" || next.status === "expired") {
          setError(next.error ?? `Task ${next.status}.`);
        }
      } catch (err) {
        if (!alive) return;
        if ((err as { name?: string }).name === "AbortError") return;
        // Keep polling — transient network errors should not close the modal.
      }
    };

    void tick();
    const id = window.setInterval(tick, pollIntervalMs);
    return () => {
      alive = false;
      controller.abort();
      window.clearInterval(id);
    };
  }, [envelope, pollIntervalMs]);

  useEffect(() => {
    if (!open) {
      setPoll(null);
      setCopiedPrompt(false);
      setCopiedMcp(false);
      setError(null);
    }
  }, [open]);

  const finalStatus =
    status === "done" || status === "failed" || status === "expired";

  return (
    <Modal
      open={open}
      onClose={finalStatus ? onClose : handleCancel}
      title={kindCopy?.title ?? "Cursor task"}
      maxWidth={720}
      footer={
        <>
          {!finalStatus && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleCancel}
            >
              Cancel task
            </button>
          )}
          <button type="button" className="btn btn-primary" onClick={onClose}>
            {finalStatus ? "Close" : "Keep working"}
          </button>
        </>
      }
    >
      {envelope && kindCopy && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <p style={{ margin: 0, color: "var(--text-secondary)", lineHeight: 1.5 }}>
            {kindCopy.description}
          </p>

          <StatusBanner status={status} error={error} />

          <McpSetupSection
            snippet={mcpSnippet}
            submitTool={submitTool}
            copied={copiedMcp}
            onCopy={handleCopyMcp}
          />

          <PromptSection
            prompt={promptText}
            copied={copiedPrompt}
            onCopy={handleCopyPrompt}
          />

          <McpTroubleshootingNote submitTool={submitTool} onCopyMcp={handleCopyMcp} />

          <StepsChecklist taskId={envelope.task_id} submitTool={submitTool} />
        </div>
      )}
    </Modal>
  );
}

function StatusBanner({
  status,
  error,
}: {
  status: string;
  error: string | null;
}) {
  if (status === "done") {
    return (
      <Banner tone="success">
        <Check size={16} aria-hidden />
        Cursor submitted the result — we&apos;re taking you there.
      </Banner>
    );
  }
  if (status === "failed" || status === "expired") {
    return (
      <Banner tone="error">
        <XCircle size={16} aria-hidden />
        {error ?? `Task ${status}. Re-run from the previous page to try again.`}
      </Banner>
    );
  }
  if (status === "claimed") {
    return (
      <Banner tone="info">
        <Loader2 size={16} aria-hidden className="spin" />
        Cursor is working on this task. This dialog will update automatically.
      </Banner>
    );
  }
  return (
    <Banner tone="info">
      <Loader2 size={16} aria-hidden className="spin" />
      Waiting for Cursor to claim the task. Paste the prompt below into a new
      Cursor chat window.
    </Banner>
  );
}

function Banner({
  tone,
  children,
}: {
  tone: "info" | "success" | "error";
  children: React.ReactNode;
}) {
  const palette = {
    info: {
      bg: "var(--bg-accent-subtle, #eef2ff)",
      fg: "var(--text-accent, #4338ca)",
      border: "var(--border-accent, #c7d2fe)",
    },
    success: {
      bg: "var(--bg-success-subtle, #ecfdf5)",
      fg: "var(--text-success, #047857)",
      border: "var(--border-success, #a7f3d0)",
    },
    error: {
      bg: "var(--bg-danger-subtle, #fef2f2)",
      fg: "var(--text-danger, #b91c1c)",
      border: "var(--border-danger, #fecaca)",
    },
  }[tone];

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.5rem",
        padding: "0.65rem 0.9rem",
        borderRadius: "var(--radius-md)",
        background: palette.bg,
        color: palette.fg,
        border: `1px solid ${palette.border}`,
        fontSize: "0.875rem",
        lineHeight: 1.4,
      }}
    >
      {children}
    </div>
  );
}

function SectionHeader({
  title,
  copied,
  onCopy,
  copyLabel = "Copy",
  copyTestId,
  icon,
}: {
  title: string;
  copied: boolean;
  onCopy: () => void;
  copyLabel?: string;
  copyTestId?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: "0.5rem",
        gap: "0.75rem",
      }}
    >
      <h3
        style={{
          margin: 0,
          display: "inline-flex",
          alignItems: "center",
          gap: "0.4rem",
          fontSize: "0.8125rem",
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          color: "var(--text-secondary)",
        }}
      >
        {icon}
        {title}
      </h3>
      <button
        type="button"
        onClick={onCopy}
        className="btn btn-secondary btn-sm"
        data-testid={copyTestId}
        style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
        {copied ? "Copied" : copyLabel}
      </button>
    </div>
  );
}

function CodeBlock({
  children,
  testId,
  maxHeight = "18rem",
}: {
  children: React.ReactNode;
  testId?: string;
  maxHeight?: string;
}) {
  return (
    <pre
      data-testid={testId}
      style={{
        margin: 0,
        padding: "0.9rem 1rem",
        borderRadius: "var(--radius-md)",
        background: "var(--bg-subtle)",
        border: "1px solid var(--border-subtle)",
        fontSize: "0.78rem",
        lineHeight: 1.55,
        maxHeight,
        overflow: "auto",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        fontFamily:
          "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace",
      }}
    >
      {children}
    </pre>
  );
}

function McpSetupSection({
  snippet,
  submitTool,
  copied,
  onCopy,
}: {
  snippet: string;
  submitTool: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <section data-testid="mcp-setup-section">
      <SectionHeader
        title="1. Connect the FS Intelligence Platform MCP server"
        copied={copied}
        onCopy={onCopy}
        copyLabel="Copy MCP config"
        copyTestId="copy-mcp-snippet"
        icon={<Server size={14} aria-hidden />}
      />
      <ol
        style={{
          margin: "0 0 0.65rem 0",
          paddingLeft: "1.1rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.3rem",
          color: "var(--text-secondary)",
          fontSize: "0.85rem",
          lineHeight: 1.55,
        }}
      >
        <li>
          Open Cursor with the <strong>FS Intelligence Platform repo</strong> as
          the workspace root (the folder that contains{" "}
          <code style={{ fontFamily: "inherit" }}>mcp-server/server.py</code>).
        </li>
        <li>
          Save the snippet below as{" "}
          <code style={{ fontFamily: "inherit" }}>.cursor/mcp.json</code> at
          that workspace root (merge into the existing file if present).
        </li>
        <li>
          <strong>Fully restart Cursor</strong> (Quit, then reopen) and confirm{" "}
          <code style={{ fontFamily: "inherit" }}>fs-intelligence-platform</code>{" "}
          shows green in the MCP panel — and that{" "}
          <code style={{ fontFamily: "inherit" }}>{submitTool}</code> is listed.
        </li>
      </ol>
      <CodeBlock testId="mcp-snippet-block" maxHeight="12rem">
        {snippet}
      </CodeBlock>
    </section>
  );
}

function PromptSection({
  prompt,
  copied,
  onCopy,
}: {
  prompt: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <section data-testid="prompt-section">
      <SectionHeader
        title="2. Paste this prompt into a new Cursor chat"
        copied={copied}
        onCopy={onCopy}
        copyLabel="Copy prompt"
        copyTestId="copy-prompt"
      />
      <CodeBlock testId="prompt-block">{prompt}</CodeBlock>
    </section>
  );
}

function McpTroubleshootingNote({
  submitTool,
  onCopyMcp,
}: {
  submitTool: string;
  onCopyMcp: () => void;
}) {
  return (
    <div
      data-testid="mcp-troubleshoot"
      role="note"
      style={{
        display: "flex",
        gap: "0.55rem",
        padding: "0.65rem 0.85rem",
        borderRadius: "var(--radius-md)",
        background: "var(--bg-warning-subtle, #fffbeb)",
        color: "var(--text-warning, #92400e)",
        border: "1px solid var(--border-warning, #fde68a)",
        fontSize: "0.825rem",
        lineHeight: 1.5,
      }}
    >
      <AlertTriangle size={16} aria-hidden style={{ marginTop: 2, flexShrink: 0 }} />
      <div>
        If Cursor reports{" "}
        <em>“no MCP server is registered for fs-intelligence-platform”</em> or{" "}
        <em>“MCP tool {submitTool} is not available”</em>, the snippet above
        wasn’t loaded. {" "}
        <button
          type="button"
          onClick={onCopyMcp}
          className="link-button"
          style={{
            background: "transparent",
            border: 0,
            padding: 0,
            color: "inherit",
            textDecoration: "underline",
            cursor: "pointer",
            font: "inherit",
          }}
        >
          Copy the MCP config again
        </button>
        , merge it into{" "}
        <code style={{ fontFamily: "inherit" }}>.cursor/mcp.json</code>, fully
        restart Cursor, and try once more. <strong>Do not</strong> let the
        agent fall back to writing the result to a JSON file at the workspace
        root — the platform never reads it.
      </div>
    </div>
  );
}

function StepsChecklist({
  taskId,
  submitTool,
}: {
  taskId: string;
  submitTool: string;
}) {
  return (
    <section>
      <h3
        style={{
          margin: 0,
          marginBottom: "0.5rem",
          fontSize: "0.8125rem",
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          color: "var(--text-secondary)",
        }}
      >
        What happens next
      </h3>
      <ol
        style={{
          margin: 0,
          paddingLeft: "1.1rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.3rem",
          color: "var(--text-secondary)",
          fontSize: "0.875rem",
          lineHeight: 1.5,
        }}
      >
        <li>Paste the prompt above into the new Cursor chat and press Enter.</li>
        <li>
          Cursor will call <code style={{ fontFamily: "inherit" }}>claim_cursor_task</code>{" "}
          for task <code style={{ fontFamily: "inherit" }}>{taskId.slice(0, 8)}…</code>{" "}
          and finish by calling{" "}
          <code style={{ fontFamily: "inherit" }}>{submitTool}</code> via MCP.
        </li>
        <li>
          This dialog will update automatically — no need to refresh. <ExternalLink size={12} aria-hidden />
        </li>
      </ol>
    </section>
  );
}
