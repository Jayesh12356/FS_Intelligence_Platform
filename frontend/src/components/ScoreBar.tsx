"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";

interface ScoreBarProps {
  label: string;
  value: number;
  max?: number;
  color?: string;
}

function defaultColor(v: number): string {
  if (v >= 90) return "var(--success)";
  if (v >= 70) return "var(--accent-primary)";
  if (v >= 50) return "var(--warning)";
  return "var(--error)";
}

export default function ScoreBar({ label, value, max = 100, color }: ScoreBarProps) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-20px" });
  const pct = Math.min(100, (value / max) * 100);
  const fill = color ?? defaultColor(value);

  return (
    <div className="score-bar-wrap" ref={ref}>
      <div className="score-bar-header">
        <span className="score-bar-label">{label}</span>
        <span className="score-bar-value" style={{ color: fill }}>{value.toFixed(1)}</span>
      </div>
      <div className="score-bar-track">
        <motion.div
          className="score-bar-fill"
          style={{ background: fill }}
          initial={{ width: 0 }}
          animate={inView ? { width: `${pct}%` } : { width: 0 }}
          transition={{ duration: 0.8, ease: [0.4, 0, 0.2, 1], delay: 0.1 }}
        />
      </div>
    </div>
  );
}
