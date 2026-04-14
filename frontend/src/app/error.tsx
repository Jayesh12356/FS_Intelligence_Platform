"use client";

import { AlertTriangle } from "lucide-react";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon"><AlertTriangle size={40} /></div>
      <h3>Something went wrong</h3>
      <p>{error.message || "An unexpected error occurred."}</p>
      <button className="btn btn-primary" onClick={reset}>Try Again</button>
    </div>
  );
}
