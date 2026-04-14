"use client";

import { useState, useCallback, useRef } from "react";
import { searchLibrary, type LibraryItem } from "@/lib/api";
import { PageShell, FadeIn, StaggerList, StaggerItem, EmptyState, SearchInput } from "@/components/index";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, Search, FileText, ChevronDown } from "lucide-react";

const DEBOUNCE_MS = 400;

export default function LibraryPage() {
  const searchSeq = useRef(0);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | number | null>(null);

  const runSearch = useCallback(async (trimmed: string) => {
    const seq = ++searchSeq.current;
    setLoading(true);
    setError(null);
    setSearched(true);
    setExpandedKey(null);
    try {
      const res = await searchLibrary(trimmed);
      if (seq !== searchSeq.current) return;
      setResults(res.data?.results || []);
    } catch (err: unknown) {
      if (seq !== searchSeq.current) return;
      setError(err instanceof Error ? err.message : "Search failed");
      setResults([]);
    } finally {
      if (seq === searchSeq.current) {
        setLoading(false);
      }
    }
  }, []);

  const handleQueryChange = useCallback(
    (v: string) => {
      setQuery(v);
      const t = v.trim();
      if (t.length < 3) {
        searchSeq.current += 1;
        setLoading(false);
        setError(null);
        setResults([]);
        setSearched(false);
        setExpandedKey(null);
        return;
      }
      void runSearch(t);
    },
    [runSearch]
  );

  const toggleExpand = (key: string | number) => {
    setExpandedKey((k) => (k === key ? null : key));
  };

  return (
    <PageShell
      title="FS Library"
      subtitle="Search and explore functional specification patterns"
      maxWidth={900}
    >
      <FadeIn>
        <div style={{ marginBottom: "1.25rem" }} id="library-search-region">
          <SearchInput
            value={query}
            onChange={handleQueryChange}
            placeholder="Search requirements... (e.g. user authentication, payment flow)"
            debounceMs={DEBOUNCE_MS}
          />
        </div>
      </FadeIn>

      {error && (
        <div className="alert alert-error" id="library-error" style={{ marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      {loading && (
        <FadeIn>
          <div
            className="page-loading"
            style={{ padding: "1.25rem 0" }}
            aria-busy="true"
            aria-live="polite"
            id="library-loading"
          >
            <div className="spinner" />
            <span>Searching…</span>
          </div>
        </FadeIn>
      )}

      {!loading && !searched && (
        <div id="library-welcome">
          <EmptyState
            icon={<BookOpen size={40} strokeWidth={1.25} aria-hidden />}
            title="Search for patterns to get started"
            description="Enter at least three characters to find reusable requirements from previously approved FS documents."
          />
        </div>
      )}

      {!loading && searched && results.length === 0 && !error && (
        <div id="library-no-results">
          <EmptyState
            icon={<Search size={40} strokeWidth={1.25} aria-hidden />}
            title="No results found"
            description="Try a broader search term, or ensure documents have been approved to populate the library."
          />
        </div>
      )}

      {results.length > 0 && (
        <FadeIn>
          <h3
            style={{
              marginBottom: "1rem",
              fontSize: "1rem",
              fontWeight: 600,
              color: "var(--text-secondary)",
            }}
            id="library-results"
          >
            {results.length} result{results.length !== 1 ? "s" : ""} found
          </h3>
          <StaggerList style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {results.map((item, i) => {
              const key = item.id ?? i;
              const isOpen = expandedKey === key;
              return (
                <StaggerItem key={key}>
                  <div className="card" id={`library-item-${i}`}>
                    <button
                      type="button"
                      onClick={() => toggleExpand(key)}
                      style={{
                        display: "flex",
                        width: "100%",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: "0.75rem",
                        background: "none",
                        border: "none",
                        padding: 0,
                        cursor: "pointer",
                        textAlign: "left",
                      }}
                      aria-expanded={isOpen}
                    >
                      <h4 style={{ margin: 0, flex: 1, color: "var(--text-primary)" }}>
                        {item.section_heading || `Section ${item.section_index}`}
                      </h4>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexShrink: 0 }}>
                        {item.score ? (
                          <span className="badge badge-info">{(item.score * 100).toFixed(0)}% match</span>
                        ) : null}
                        <motion.span
                          animate={{ rotate: isOpen ? 180 : 0 }}
                          transition={{ duration: 0.2 }}
                          style={{ display: "flex" }}
                        >
                          <ChevronDown size={20} aria-hidden style={{ color: "var(--text-muted)" }} />
                        </motion.span>
                      </div>
                    </button>

                    {!isOpen && (
                      <p
                        style={{
                          fontSize: "0.85rem",
                          color: "var(--text-secondary)",
                          lineHeight: 1.5,
                          whiteSpace: "pre-wrap",
                          marginTop: "0.75rem",
                          marginBottom: 0,
                        }}
                      >
                        {item.text.substring(0, 400)}
                        {item.text.length > 400 ? "…" : ""}
                      </p>
                    )}

                    <AnimatePresence initial={false}>
                      {isOpen && (
                        <motion.div
                          key="expanded"
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
                          style={{ overflow: "hidden" }}
                        >
                          <p
                            style={{
                              fontSize: "0.85rem",
                              color: "var(--text-secondary)",
                              lineHeight: 1.5,
                              whiteSpace: "pre-wrap",
                              marginTop: "0.75rem",
                              marginBottom: "0.5rem",
                            }}
                          >
                            {item.text}
                          </p>
                          <div
                            style={{
                              fontSize: "0.75rem",
                              color: "var(--text-muted)",
                              display: "flex",
                              alignItems: "center",
                              gap: "0.35rem",
                            }}
                          >
                            <FileText size={12} aria-hidden />
                            Source document: {item.fs_id.substring(0, 8)}…
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    {!isOpen && (
                      <div
                        style={{
                          marginTop: "0.5rem",
                          fontSize: "0.75rem",
                          color: "var(--text-muted)",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.35rem",
                        }}
                      >
                        <FileText size={12} aria-hidden />
                        Source document: {item.fs_id.substring(0, 8)}…
                      </div>
                    )}
                  </div>
                </StaggerItem>
              );
            })}
          </StaggerList>
        </FadeIn>
      )}
    </PageShell>
  );
}
