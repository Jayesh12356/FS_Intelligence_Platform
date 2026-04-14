"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";

interface QualityGaugeProps {
  score: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
}

function scoreColor(score: number): string {
  if (score >= 90) return "var(--success)";
  if (score >= 70) return "var(--accent-primary)";
  if (score >= 50) return "var(--warning)";
  return "var(--error)";
}

export default function QualityGauge({
  score,
  size = 160,
  strokeWidth = 12,
  label = "Quality",
}: QualityGaugeProps) {
  const ref = useRef<SVGSVGElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-20px" });
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const color = scoreColor(score);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      <svg ref={ref} width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--bg-tertiary)"
          strokeWidth={strokeWidth}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={isInView ? { strokeDashoffset: circumference * (1 - score / 100) } : {}}
          transition={{ duration: 1, ease: [0.4, 0, 0.2, 1], delay: 0.15 }}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x={size / 2}
          y={size / 2 - 6}
          textAnchor="middle"
          dominantBaseline="central"
          fill="var(--text-primary)"
          fontSize={size * 0.2}
          fontWeight={700}
          fontFamily="var(--font-sans)"
        >
          {Math.round(score)}
        </text>
        <text
          x={size / 2}
          y={size / 2 + size * 0.12}
          textAnchor="middle"
          dominantBaseline="central"
          fill="var(--text-muted)"
          fontSize={size * 0.085}
          fontWeight={500}
          fontFamily="var(--font-sans)"
        >
          / 100
        </text>
      </svg>
      <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-secondary)" }}>
        {label}
      </span>
    </div>
  );
}
