"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AnalysisPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/documents");
  }, [router]);

  return (
    <div className="page-loading">
      <div className="spinner" />
      Redirecting to documents\u2026
    </div>
  );
}
