"use client";

import { useState } from "react";
import {
  searchLibrary,
  LibraryItem,
} from "@/lib/api";

export default function LibraryPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || query.trim().length < 3) return;

    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const res = await searchLibrary(query.trim());
      setResults(res.data?.results || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Search failed");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <div className="page-header">
        <h1 className="page-title">📚 Requirement Library</h1>
        <p className="page-subtitle">
          Search the reusable requirement library — approved requirements from
          all FS documents are indexed here for cross-project reference.
        </p>
      </div>

      <form
        onSubmit={handleSearch}
        style={{
          display: "flex",
          gap: "0.75rem",
          marginBottom: "2rem",
        }}
      >
        <input
          type="text"
          id="library-search-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search requirements... (e.g. user authentication, payment flow)"
          className="form-input"
          style={{ flex: 1 }}
          minLength={3}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={loading || query.trim().length < 3}
          id="library-search-btn"
        >
          {loading ? "Searching…" : "🔍 Search"}
        </button>
      </form>

      {error && (
        <div className="alert alert-error" id="library-error">
          {error}
        </div>
      )}

      {searched && !loading && results.length === 0 && !error && (
        <div className="empty-state" id="library-no-results">
          <div className="empty-state-icon">🔎</div>
          <h3>No results found</h3>
          <p>
            Try a broader search term, or ensure documents have been approved to
            populate the library.
          </p>
        </div>
      )}

      {results.length > 0 && (
        <div id="library-results">
          <h3 style={{ marginBottom: "1rem" }}>
            {results.length} result{results.length !== 1 ? "s" : ""} found
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {results.map((item, i) => (
              <div key={item.id || i} className="card" id={`library-item-${i}`}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "0.5rem",
                  }}
                >
                  <h4 style={{ margin: 0 }}>
                    {item.section_heading || `Section ${item.section_index}`}
                  </h4>
                  {item.score && (
                    <span className="badge badge-info">
                      {(item.score * 100).toFixed(0)}% match
                    </span>
                  )}
                </div>
                <p
                  style={{
                    fontSize: "0.85rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.5,
                    whiteSpace: "pre-wrap",
                    maxHeight: 120,
                    overflow: "hidden",
                  }}
                >
                  {item.text.substring(0, 400)}
                  {item.text.length > 400 ? "…" : ""}
                </p>
                <div
                  style={{
                    marginTop: "0.5rem",
                    fontSize: "0.75rem",
                    color: "var(--text-muted)",
                  }}
                >
                  Source Document: {item.fs_id.substring(0, 8)}…
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!searched && (
        <div className="empty-state" id="library-welcome">
          <div className="empty-state-icon">📚</div>
          <h3>Requirement Library</h3>
          <p>
            Enter a search query above to find reusable requirements from
            previously approved FS documents.
          </p>
        </div>
      )}
    </div>
  );
}
