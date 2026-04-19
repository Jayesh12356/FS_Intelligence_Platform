"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Sparkles,
  Loader2,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  Lightbulb,
  MessageSquare,
  FileText,
  ChevronDown,
  ChevronUp,
  Cpu,
  Terminal,
  Monitor,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { CursorTaskModal, PageShell, Tabs } from "@/components/index";
import {
  generateFSFromIdea,
  guidedIdeaStep,
  isCursorTaskEnvelope,
  type CursorTaskEnvelope,
  type GuidedQuestion,
} from "@/lib/api";
import { useToolConfig } from "@/lib/toolConfig";

const INDUSTRIES = [
  "FinTech", "HealthTech", "EdTech", "E-Commerce", "SaaS", "Social Media",
  "IoT", "Enterprise", "Gaming", "AI / ML", "Other",
];

const COMPLEXITIES = [
  { value: "simple", label: "Simple", desc: "MVP / Single feature" },
  { value: "moderate", label: "Moderate", desc: "Multi-feature product" },
  { value: "enterprise", label: "Enterprise", desc: "Full-scale platform" },
];

export default function CreatePage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState(0);
  const [showGuide, setShowGuide] = useState(false);

  return (
    <PageShell
      title="Create from Idea"
      subtitle="Describe your product idea and generate a professional Functional Specification"
      backHref="/"
      backLabel="Home"
      maxWidth="56rem"
    >
      <WorkflowGuide open={showGuide} onToggle={() => setShowGuide(!showGuide)} />

      <Tabs
        items={[
          { key: "quick", label: "Quick Create" },
          { key: "guided", label: "Guided Create" },
        ]}
        active={activeTab === 0 ? "quick" : "guided"}
        onChange={(k) => setActiveTab(k === "quick" ? 0 : 1)}
      />

      <div style={{ marginTop: "1.5rem" }}>
        <AnimatePresence mode="wait">
          {activeTab === 0 ? (
            <motion.div
              key="quick"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              <QuickCreate router={router} />
            </motion.div>
          ) : (
            <motion.div
              key="guided"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              <GuidedCreate router={router} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </PageShell>
  );
}

function QuickCreate({ router }: { router: ReturnType<typeof useRouter> }) {
  const [idea, setIdea] = useState("");
  const [industry, setIndustry] = useState("");
  const [complexity, setComplexity] = useState("moderate");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [cursorTask, setCursorTask] = useState<CursorTaskEnvelope | null>(null);
  useToolConfig();

  const handleGenerate = useCallback(async () => {
    if (idea.trim().length < 10) {
      setError("Please describe your idea in at least 10 characters.");
      return;
    }
    setError("");

    setLoading(true);
    try {
      const res = await generateFSFromIdea(
        idea.trim(),
        industry || undefined,
        complexity || undefined,
      );
      const data = res.data;
      if (isCursorTaskEnvelope(data)) {
        setCursorTask(data);
      } else if (data && "document_id" in data && data.document_id) {
        router.push(`/documents/${data.document_id}`);
      } else {
        setError(res.error || "Generation failed. Please try again.");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Generation failed.");
    } finally {
      setLoading(false);
    }
  }, [idea, industry, complexity, router]);

  return (
    <div className="card" style={{ padding: "2rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.5rem" }}>
        <div style={{
          width: 40, height: 40, borderRadius: "0.75rem",
          background: "var(--well-blue)", display: "flex",
          alignItems: "center", justifyContent: "center",
        }}>
          <Lightbulb size={20} style={{ color: "var(--accent-primary)" }} />
        </div>
        <div>
          <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 600 }}>Describe Your Product</h3>
          <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-tertiary)" }}>
            A sentence or paragraph about what you want to build
          </p>
        </div>
      </div>

      <textarea
        value={idea}
        onChange={(e) => setIdea(e.target.value)}
        placeholder="e.g., A real-time collaborative project management tool with Gantt charts, resource allocation, and AI-powered task estimation for enterprise teams..."
        style={{
          width: "100%", minHeight: 140, padding: "1rem",
          borderRadius: "0.75rem", border: "1px solid var(--border-subtle)",
          background: "var(--bg-main)", color: "var(--text-primary)",
          fontSize: "0.95rem", fontFamily: "inherit", resize: "vertical",
          lineHeight: 1.6,
        }}
        disabled={loading}
      />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginTop: "1.25rem" }}>
        <div>
          <label htmlFor="quick-industry" style={{ display: "block", fontSize: "0.85rem", fontWeight: 500, marginBottom: "0.5rem", color: "var(--text-secondary)" }}>
            Industry (optional)
          </label>
          <select
            id="quick-industry"
            aria-label="Industry"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            disabled={loading}
            style={{
              width: "100%", padding: "0.6rem 0.75rem", borderRadius: "0.5rem",
              border: "1px solid var(--border-subtle)", background: "var(--bg-main)",
              color: "var(--text-primary)", fontSize: "0.9rem",
            }}
          >
            <option value="">Select industry…</option>
            {INDUSTRIES.map((ind) => (
              <option key={ind} value={ind}>{ind}</option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="quick-complexity" style={{ display: "block", fontSize: "0.85rem", fontWeight: 500, marginBottom: "0.5rem", color: "var(--text-secondary)" }}>
            Complexity
          </label>
          <select
            id="quick-complexity"
            aria-label="Complexity"
            value={complexity}
            onChange={(e) => setComplexity(e.target.value)}
            disabled={loading}
            style={{
              width: "100%", padding: "0.6rem 0.75rem", borderRadius: "0.5rem",
              border: "1px solid var(--border-subtle)", background: "var(--bg-main)",
              color: "var(--text-primary)", fontSize: "0.9rem",
            }}
          >
            {COMPLEXITIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label} — {c.desc}</option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div style={{
          marginTop: "1rem", padding: "0.75rem 1rem", borderRadius: "0.5rem",
          background: "var(--error-bg)", color: "var(--error)",
          fontSize: "0.85rem",
        }}>
          {error}
        </div>
      )}

      <button
        className="btn btn-primary"
        onClick={handleGenerate}
        disabled={loading || idea.trim().length < 10}
        style={{ marginTop: "1.5rem", width: "100%", justifyContent: "center", gap: "0.5rem" }}
      >
        {loading ? (
          <>
            <Loader2 size={18} className="spin" />
            Generating FS Document…
          </>
        ) : (
          <>
            <Sparkles size={18} />
            Generate Functional Specification
          </>
        )}
      </button>

      <CursorTaskModal
        envelope={cursorTask}
        onClose={() => setCursorTask(null)}
        onDone={(resultRef) => {
          setCursorTask(null);
          if (resultRef) router.push(`/documents/${resultRef}`);
        }}
      />
    </div>
  );
}

function GuidedCreate({ router }: { router: ReturnType<typeof useRouter> }) {
  const [idea, setIdea] = useState("");
  const [industry, setIndustry] = useState("");
  const [complexity, setComplexity] = useState("moderate");
  const [step, setStep] = useState(-1);
  const [sessionId, setSessionId] = useState("");
  const [questions, setQuestions] = useState<GuidedQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [cursorTask, setCursorTask] = useState<CursorTaskEnvelope | null>(null);
  useToolConfig();

  const handleStartGuided = useCallback(async () => {
    if (idea.trim().length < 10) {
      setError("Please describe your idea in at least 10 characters.");
      return;
    }
    setError("");

    setLoading(true);
    try {
      const res = await guidedIdeaStep({
        idea: idea.trim(),
        step: 0,
        industry: industry || undefined,
        complexity: complexity || undefined,
      });
      const data = res.data;
      if (isCursorTaskEnvelope(data)) {
        setCursorTask(data);
      } else {
        const payload = data as {
          session_id?: string;
          questions?: GuidedQuestion[];
        } | undefined;
        if (payload?.session_id && payload?.questions) {
          setSessionId(payload.session_id);
          setQuestions(payload.questions);
          setStep(0);
        } else {
          setError(res.error || "Failed to start guided flow.");
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start.");
    } finally {
      setLoading(false);
    }
  }, [idea, industry, complexity]);

  const handleSubmitAnswers = useCallback(async () => {
    setError("");

    setLoading(true);
    try {
      const res = await guidedIdeaStep({
        session_id: sessionId,
        idea: idea.trim(),
        step: 1,
        answers,
        industry: industry || undefined,
        complexity: complexity || undefined,
      });
      const data = res.data;
      if (isCursorTaskEnvelope(data)) {
        setCursorTask(data);
      } else {
        const payload = data as { document_id?: string } | undefined;
        if (payload?.document_id) {
          router.push(`/documents/${payload.document_id}`);
        } else {
          setError(res.error || "FS generation failed.");
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Generation failed.");
    } finally {
      setLoading(false);
    }
  }, [sessionId, answers, idea, industry, complexity, router]);

  if (step === -1) {
    return (
      <div className="card" style={{ padding: "2rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.5rem" }}>
          <div style={{
            width: 40, height: 40, borderRadius: "0.75rem",
            background: "var(--well-purple)", display: "flex",
            alignItems: "center", justifyContent: "center",
          }}>
            <MessageSquare size={20} style={{ color: "var(--accent-primary)" }} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 600 }}>Guided Discovery</h3>
            <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-tertiary)" }}>
              We&apos;ll ask a few questions to build the perfect spec for your idea
            </p>
          </div>
        </div>

        <textarea
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="Describe your product idea in a few sentences…"
          style={{
            width: "100%", minHeight: 120, padding: "1rem",
            borderRadius: "0.75rem", border: "1px solid var(--border-subtle)",
            background: "var(--bg-main)", color: "var(--text-primary)",
            fontSize: "0.95rem", fontFamily: "inherit", resize: "vertical",
            lineHeight: 1.6,
          }}
          disabled={loading}
        />

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginTop: "1.25rem" }}>
          <div>
            <label htmlFor="guided-industry" style={{ display: "block", fontSize: "0.85rem", fontWeight: 500, marginBottom: "0.5rem", color: "var(--text-secondary)" }}>
              Industry (optional)
            </label>
            <select
              id="guided-industry"
              aria-label="Industry"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              disabled={loading}
              style={{
                width: "100%", padding: "0.6rem 0.75rem", borderRadius: "0.5rem",
                border: "1px solid var(--border-subtle)", background: "var(--bg-main)",
                color: "var(--text-primary)", fontSize: "0.9rem",
              }}
            >
              <option value="">Select industry…</option>
              {INDUSTRIES.map((ind) => (
                <option key={ind} value={ind}>{ind}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="guided-complexity" style={{ display: "block", fontSize: "0.85rem", fontWeight: 500, marginBottom: "0.5rem", color: "var(--text-secondary)" }}>
              Complexity
            </label>
            <select
              id="guided-complexity"
              aria-label="Complexity"
              value={complexity}
              onChange={(e) => setComplexity(e.target.value)}
              disabled={loading}
              style={{
                width: "100%", padding: "0.6rem 0.75rem", borderRadius: "0.5rem",
                border: "1px solid var(--border-subtle)", background: "var(--bg-main)",
                color: "var(--text-primary)", fontSize: "0.9rem",
              }}
            >
              {COMPLEXITIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label} — {c.desc}</option>
              ))}
            </select>
          </div>
        </div>

        {error && (
          <div style={{
            marginTop: "1rem", padding: "0.75rem 1rem", borderRadius: "0.5rem",
            background: "var(--error-bg)", color: "var(--error)",
            fontSize: "0.85rem",
          }}>
            {error}
          </div>
        )}

        <button
          className="btn btn-primary"
          onClick={handleStartGuided}
          disabled={loading || idea.trim().length < 10}
          style={{ marginTop: "1.5rem", width: "100%", justifyContent: "center", gap: "0.5rem" }}
        >
          {loading ? (
            <>
              <Loader2 size={18} className="spin" />
              Generating questions…
            </>
          ) : (
            <>
              <ArrowRight size={18} />
              Start Guided Discovery
            </>
          )}
        </button>

        <CursorTaskModal
          envelope={cursorTask}
          onClose={() => setCursorTask(null)}
          onDone={(resultRef) => {
            setCursorTask(null);
            if (resultRef) router.push(`/documents/${resultRef}`);
          }}
        />
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: "2rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.5rem" }}>
        <div style={{
          width: 40, height: 40, borderRadius: "0.75rem",
          background: "var(--well-purple)", display: "flex",
          alignItems: "center", justifyContent: "center",
        }}>
          <FileText size={20} style={{ color: "var(--accent-primary)" }} />
        </div>
        <div>
          <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 600 }}>Answer Discovery Questions</h3>
          <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-tertiary)" }}>
            Your answers will tailor the FS document to your exact needs
          </p>
        </div>
      </div>

      <div style={{ background: "var(--bg-main)", borderRadius: "0.75rem", padding: "1rem", marginBottom: "1rem", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
        <strong>Your idea:</strong> {idea}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        {questions.map((q, i) => (
          <div key={q.id} style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <label style={{ fontSize: "0.9rem", fontWeight: 500, color: "var(--text-primary)" }}>
              <span style={{ color: "var(--accent-primary)", marginRight: "0.5rem" }}>{i + 1}.</span>
              {q.question}
            </label>
            {q.dimension && (
              <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                {q.dimension}
              </span>
            )}
            {q.options && q.options.length > 0 ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                {q.options.map((opt) => (
                  <button
                    key={opt}
                    className={`btn btn-sm ${answers[q.id] === opt ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: opt }))}
                    disabled={loading}
                    style={{ fontSize: "0.8rem" }}
                  >
                    {opt}
                  </button>
                ))}
                <input
                  type="text"
                  placeholder="Or type your own…"
                  value={answers[q.id]?.startsWith("__custom:") ? answers[q.id].slice(9) : ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setAnswers((prev) => ({ ...prev, [q.id]: v ? `__custom:${v}` : "" }));
                  }}
                  disabled={loading}
                  style={{
                    flex: 1, minWidth: 180, padding: "0.4rem 0.6rem",
                    borderRadius: "0.5rem", border: "1px solid var(--border-subtle)",
                    background: "var(--bg-main)", color: "var(--text-primary)",
                    fontSize: "0.8rem",
                  }}
                />
              </div>
            ) : (
              <textarea
                value={answers[q.id] || ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                placeholder="Type your answer…"
                disabled={loading}
                style={{
                  width: "100%", minHeight: 60, padding: "0.6rem 0.75rem",
                  borderRadius: "0.5rem", border: "1px solid var(--border-subtle)",
                  background: "var(--bg-main)", color: "var(--text-primary)",
                  fontSize: "0.85rem", fontFamily: "inherit", resize: "vertical",
                }}
              />
            )}
          </div>
        ))}
      </div>

      {error && (
        <div style={{
          marginTop: "1rem", padding: "0.75rem 1rem", borderRadius: "0.5rem",
          background: "var(--error-bg)", color: "var(--error)",
          fontSize: "0.85rem",
        }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: "1rem", marginTop: "1.5rem" }}>
        <button
          className="btn btn-secondary"
          onClick={() => { setStep(-1); setQuestions([]); setAnswers({}); }}
          disabled={loading}
          style={{ gap: "0.5rem" }}
        >
          <ArrowLeft size={16} /> Back
        </button>
        <button
          className="btn btn-primary"
          onClick={handleSubmitAnswers}
          disabled={loading || Object.keys(answers).length === 0}
          style={{ flex: 1, justifyContent: "center", gap: "0.5rem" }}
        >
          {loading ? (
            <>
              <Loader2 size={18} className="spin" />
              Generating FS Document…
            </>
          ) : (
            <>
              <CheckCircle2 size={18} />
              Generate Functional Specification
            </>
          )}
        </button>
      </div>

      <CursorTaskModal
        envelope={cursorTask}
        onClose={() => setCursorTask(null)}
        onDone={(resultRef) => {
          setCursorTask(null);
          if (resultRef) router.push(`/documents/${resultRef}`);
        }}
      />
    </div>
  );
}

const WORKFLOW_MODES = [
  {
    icon: Monitor,
    title: "Web UI (Direct API)",
    color: "var(--well-blue)",
    steps: [
      "Enter your idea above (Quick or Guided)",
      "Review generated FS and run Analysis",
      "Refine until quality score >= 90",
      "Export to JIRA, PDF, or Confluence",
    ],
    note: "Best for analysis and refinement. Build requires Cursor or Claude Code.",
  },
  {
    icon: Terminal,
    title: "Claude Code (Headless)",
    color: "var(--well-purple)",
    steps: [
      "Set Document LLM to Claude Code in Settings",
      "Or use CLI: claude --mcp-config mcp-config.json",
      "Run start_full_autonomous_loop prompt with your idea",
      "Claude handles FS generation, analysis, build, and export",
    ],
    note: "Fully autonomous -- zero manual steps from idea to production.",
  },
  {
    icon: Cpu,
    title: "Cursor (paste per action)",
    color: "var(--well-amber, rgba(245,158,11,0.1))",
    steps: [
      "Set Document LLM to Cursor in Settings",
      "Click Generate / Analyze / Reverse FS — a paste dialog opens",
      "Paste the prompt into a new Cursor chat (MCP enabled)",
      "Cursor submits the result via MCP — we pay zero Direct API tokens",
    ],
    note: "One paste per action. No background workers, no leaks — the UI updates as soon as Cursor submits.",
  },
];

function WorkflowGuide({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <div className="card" style={{ marginBottom: "1.5rem", overflow: "hidden" }}>
      <button
        onClick={onToggle}
        aria-expanded={open}
        style={{
          display: "flex", alignItems: "center", width: "100%",
          padding: "1rem 1.25rem", background: "transparent",
          border: "none", cursor: "pointer", gap: "0.75rem",
        }}
      >
        <Sparkles size={18} style={{ color: "var(--accent-primary)" }} />
        <span style={{ flex: 1, textAlign: "left", fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
          How it works -- Three ways to create
        </span>
        {open
          ? <ChevronUp size={16} style={{ color: "var(--text-tertiary)" }} />
          : <ChevronDown size={16} style={{ color: "var(--text-tertiary)" }} />
        }
      </button>
      {open && (
        <div style={{
          padding: "0 1.25rem 1.25rem",
          borderTop: "1px solid var(--border-subtle)",
          paddingTop: "1rem",
        }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "1rem" }}>
            {WORKFLOW_MODES.map((mode) => {
              const Icon = mode.icon;
              return (
                <div key={mode.title} style={{
                  padding: "1rem",
                  borderRadius: "0.75rem",
                  background: "var(--bg-main)",
                  border: "1px solid var(--border-subtle)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: "0.5rem",
                      background: mode.color, display: "flex",
                      alignItems: "center", justifyContent: "center",
                    }}>
                      <Icon size={16} style={{ color: "var(--accent-primary)" }} />
                    </div>
                    <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
                      {mode.title}
                    </span>
                  </div>
                  <ol style={{
                    margin: 0, paddingLeft: "1.25rem",
                    fontSize: "0.8rem", lineHeight: 1.6,
                    color: "var(--text-secondary)",
                  }}>
                    {mode.steps.map((s, i) => <li key={i}>{s}</li>)}
                  </ol>
                  <p style={{
                    margin: "0.5rem 0 0", fontSize: "0.75rem",
                    color: "var(--text-tertiary)", fontStyle: "italic",
                  }}>
                    {mode.note}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
