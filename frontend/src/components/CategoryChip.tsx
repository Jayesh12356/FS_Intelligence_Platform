/**
 * CategoryChip — small pill that visualises which lifecycle bucket an
 * audit event belongs to (document / analysis / build / collab). Used
 * by both the global Monitoring activity feed and the per-document
 * Lifecycle strip so the colour coding stays consistent.
 *
 * Keep this component dependency-free so vitest can test it in
 * isolation without importing the monitoring page graph.
 */

const CATEGORY_STYLE: Record<string, { bg: string; fg: string; label: string }> = {
  document: { bg: "var(--well-blue)", fg: "var(--text-primary)", label: "Document" },
  analysis: { bg: "var(--well-amber)", fg: "var(--text-primary)", label: "Analysis" },
  build: { bg: "var(--well-green)", fg: "var(--text-primary)", label: "Build" },
  collab: { bg: "var(--well-purple)", fg: "var(--text-primary)", label: "Collab" },
};

export interface CategoryChipProps {
  category?: string | null;
}

export function CategoryChip({ category }: CategoryChipProps) {
  const key = (category || "document") as keyof typeof CATEGORY_STYLE;
  const style = CATEGORY_STYLE[key] || CATEGORY_STYLE.document;
  return (
    <span
      data-testid="category-chip"
      data-category={key}
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "0.1rem 0.5rem",
        borderRadius: "999px",
        background: style.bg,
        color: style.fg,
        fontSize: "0.7rem",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.04em",
        border: "1px solid var(--border-subtle)",
      }}
    >
      {style.label}
    </span>
  );
}

export default CategoryChip;
