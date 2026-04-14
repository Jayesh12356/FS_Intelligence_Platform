"use client";

import type { CSSProperties } from "react";

type BadgeVariant = "success" | "warning" | "error" | "info" | "neutral" | "accent";

const variantClass: Record<BadgeVariant, string> = {
  success: "badge-success",
  warning: "badge-warning",
  error: "badge-error",
  info: "badge-info",
  neutral: "badge-neutral",
  accent: "badge-accent",
};

interface BadgeProps {
  variant?: BadgeVariant;
  dot?: boolean;
  children: React.ReactNode;
  className?: string;
  style?: CSSProperties;
  id?: string;
}

export default function Badge({
  variant = "neutral",
  dot = false,
  children,
  className = "",
  style,
  id,
}: BadgeProps) {
  return (
    <span
      id={id}
      className={`badge ${variantClass[variant]} ${dot ? "badge-dot" : ""} ${className}`.trim()}
      style={style}
    >
      {children}
    </span>
  );
}

const statusVariant: Record<string, BadgeVariant> = {
  UPLOADED: "info",
  PARSING: "warning",
  PARSED: "success",
  ANALYZING: "warning",
  COMPLETE: "success",
  ERROR: "error",
  FAILED: "error",
  PENDING: "neutral",
  IN_PROGRESS: "accent",
  RUNNING: "accent",
};

export function StatusBadge({ status }: { status: string }) {
  const v = statusVariant[status.toUpperCase()] ?? "neutral";
  return (
    <Badge variant={v} dot>
      {status}
    </Badge>
  );
}
