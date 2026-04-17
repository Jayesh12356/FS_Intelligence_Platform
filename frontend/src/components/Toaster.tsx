"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, AlertTriangle, Info, XCircle, X } from "lucide-react";

export type ToastKind = "success" | "error" | "info" | "warning";

export interface Toast {
  id: string;
  kind: ToastKind;
  title: string;
  description?: string;
  duration?: number;
}

interface ToastContextValue {
  toast: (t: Omit<Toast, "id">) => string;
  success: (title: string, description?: string) => string;
  error: (title: string, description?: string) => string;
  info: (title: string, description?: string) => string;
  warning: (title: string, description?: string) => string;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setItems((list) => list.filter((t) => t.id !== id));
    const handle = timers.current.get(id);
    if (handle) {
      clearTimeout(handle);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (t: Omit<Toast, "id">) => {
      const id = Math.random().toString(36).slice(2);
      const toast: Toast = { duration: 4500, ...t, id };
      setItems((list) => [...list, toast].slice(-5));
      if (toast.duration && toast.duration > 0) {
        const handle = setTimeout(() => dismiss(id), toast.duration);
        timers.current.set(id, handle);
      }
      return id;
    },
    [dismiss]
  );

  useEffect(() => {
    const storedTimers = timers.current;
    return () => {
      storedTimers.forEach((h) => clearTimeout(h));
      storedTimers.clear();
    };
  }, []);

  const api = useMemo<ToastContextValue>(
    () => ({
      toast: push,
      success: (title, description) => push({ kind: "success", title, description }),
      error: (title, description) => push({ kind: "error", title, description, duration: 7000 }),
      info: (title, description) => push({ kind: "info", title, description }),
      warning: (title, description) => push({ kind: "warning", title, description }),
      dismiss,
    }),
    [push, dismiss]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        role="region"
        aria-label="Notifications"
        style={{
          position: "fixed",
          top: "1rem",
          right: "1rem",
          zIndex: 9999,
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
          maxWidth: "min(420px, calc(100vw - 2rem))",
          pointerEvents: "none",
        }}
      >
        <AnimatePresence>
          {items.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: -10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 16 }}
              transition={{ duration: 0.18 }}
              role="status"
              style={{
                pointerEvents: "auto",
                display: "flex",
                alignItems: "flex-start",
                gap: "0.75rem",
                padding: "0.75rem 0.875rem",
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderLeft: `3px solid ${kindColor(t.kind)}`,
                borderRadius: "0.5rem",
                boxShadow: "var(--shadow-lg)",
                fontSize: "0.875rem",
                color: "var(--text-primary)",
              }}
            >
              <span style={{ color: kindColor(t.kind), marginTop: 2, flexShrink: 0 }}>
                {iconFor(t.kind)}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{t.title}</div>
                {t.description && (
                  <div style={{ color: "var(--text-secondary)", marginTop: 2, wordBreak: "break-word" }}>
                    {t.description}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss"
                style={{
                  background: "transparent",
                  border: 0,
                  color: "var(--text-tertiary, var(--text-secondary))",
                  cursor: "pointer",
                  padding: 2,
                  display: "flex",
                }}
              >
                <X size={14} />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

function kindColor(k: ToastKind): string {
  switch (k) {
    case "success":
      return "var(--success, #16a34a)";
    case "error":
      return "var(--error, #dc2626)";
    case "warning":
      return "var(--warning, #d97706)";
    default:
      return "var(--accent, #2563eb)";
  }
}

function iconFor(k: ToastKind) {
  const size = 16;
  switch (k) {
    case "success":
      return <CheckCircle2 size={size} />;
    case "error":
      return <XCircle size={size} />;
    case "warning":
      return <AlertTriangle size={size} />;
    default:
      return <Info size={size} />;
  }
}
