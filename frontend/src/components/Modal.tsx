"use client";

import { type ReactNode, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  footer?: ReactNode;
}

export default function Modal({ open, onClose, title, children, footer }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          onClick={onClose}
          style={{
            position: "fixed", inset: 0, zIndex: 1000,
            background: "rgba(0,0,0,0.4)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: "1rem",
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.2 }}
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "var(--bg-card)", borderRadius: "var(--radius-xl)",
              width: "100%", maxWidth: 480, maxHeight: "85vh",
              overflow: "auto", boxShadow: "var(--shadow-xl)",
            }}
          >
            {title && (
              <div style={{
                padding: "1.25rem 1.5rem", borderBottom: "1px solid var(--border-subtle)",
                fontWeight: 600, fontSize: "1.0625rem",
              }}>
                {title}
              </div>
            )}
            <div style={{ padding: "1.5rem" }}>{children}</div>
            {footer && (
              <div style={{
                padding: "1rem 1.5rem", borderTop: "1px solid var(--border-subtle)",
                display: "flex", justifyContent: "flex-end", gap: "0.5rem",
              }}>
                {footer}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
