"use client";

import { type ReactNode } from "react";
import { motion } from "framer-motion";
import AnimatedNumber from "./AnimatedNumber";

interface KpiCardProps {
  label: string;
  /** Shown when `valueText` is not set */
  value?: number;
  /** When set, replaces the animated numeric value (e.g. file size, status labels) */
  valueText?: string;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  trend?: { value: string; direction: "up" | "down" | "neutral" };
  icon: ReactNode;
  iconBg?: string;
  delay?: number;
}

export default function KpiCard({
  label,
  value = 0,
  valueText,
  prefix = "",
  suffix = "",
  decimals = 0,
  trend,
  icon,
  iconBg = "var(--well-green)",
  delay = 0,
}: KpiCardProps) {
  return (
    <motion.div
      className="kpi-card"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: [0.4, 0, 0.2, 1] }}
    >
      <div className="kpi-content">
        <span className="kpi-label">{label}</span>
        {valueText != null ? (
          <span className="kpi-value">{valueText}</span>
        ) : (
        <AnimatedNumber
          className="kpi-value"
          value={value}
          prefix={prefix}
          suffix={suffix}
          decimals={decimals}
        />
        )}
        {trend && (
          <span className={`kpi-trend ${trend.direction}`}>
            {trend.direction === "up" ? "↑" : trend.direction === "down" ? "↓" : "—"}{" "}
            {trend.value}
          </span>
        )}
      </div>
      <div className="kpi-icon" style={{ background: iconBg }}>
        {icon}
      </div>
    </motion.div>
  );
}
