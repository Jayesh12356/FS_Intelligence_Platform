import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CategoryChip } from "./CategoryChip";

describe("CategoryChip", () => {
  it("falls back to the 'document' bucket when category is missing", () => {
    render(<CategoryChip />);
    const el = screen.getByTestId("category-chip");
    expect(el.getAttribute("data-category")).toBe("document");
    expect(el.textContent).toBe("Document");
  });

  it.each([
    ["analysis", "Analysis"],
    ["build", "Build"],
    ["collab", "Collab"],
    ["document", "Document"],
  ])("renders the %s bucket as %s", (category, label) => {
    render(<CategoryChip category={category} />);
    const el = screen.getByTestId("category-chip");
    expect(el.getAttribute("data-category")).toBe(category);
    expect(el.textContent).toBe(label);
  });

  it("treats unknown categories as document so the UI never breaks", () => {
    render(<CategoryChip category="totally-bogus" />);
    const el = screen.getByTestId("category-chip");
    expect(el.textContent).toBe("Document");
  });
});
