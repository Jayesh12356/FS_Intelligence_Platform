"use client";

import { type ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { PageMotion } from "./MotionWrap";

interface PageShellProps {
  backHref?: string;
  backLabel?: string;
  title: ReactNode;
  subtitle?: string;
  actions?: ReactNode;
  badge?: ReactNode;
  children: ReactNode;
  maxWidth?: number | string;
}

export default function PageShell({
  backHref,
  backLabel = "Back",
  title,
  subtitle,
  actions,
  badge,
  children,
  maxWidth,
}: PageShellProps) {
  return (
    <PageMotion>
      <div style={{ maxWidth: maxWidth ?? undefined, marginLeft: maxWidth ? "auto" : undefined, marginRight: maxWidth ? "auto" : undefined }}>
        {backHref && (
          <Link href={backHref} className="back-link">
            <ArrowLeft size={16} /> {backLabel}
          </Link>
        )}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.75rem", marginBottom: "1.5rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <h1 className="page-title">{title}</h1>
              {badge}
            </div>
            {subtitle && <p className="page-subtitle">{subtitle}</p>}
          </div>
          {actions && <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>{actions}</div>}
        </div>
        {children}
      </div>
    </PageMotion>
  );
}
