import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PageSkeleton, {
  CardListSkeleton,
  KpiRowSkeleton,
  SkeletonCard,
  SkeletonText,
} from "./LoadingSkeleton";

describe("LoadingSkeleton primitives", () => {
  it("SkeletonText renders a single skeleton element", () => {
    const { container } = render(<SkeletonText />);
    expect(container.querySelectorAll(".skeleton").length).toBe(1);
  });

  it("SkeletonCard applies the provided height", () => {
    const { container } = render(<SkeletonCard height={72} />);
    const el = container.querySelector(".skeleton-card") as HTMLElement | null;
    expect(el).toBeTruthy();
    expect(el!.style.height).toBe("72px");
  });

  it("KpiRowSkeleton renders N kpi cards", () => {
    const { container } = render(<KpiRowSkeleton count={3} />);
    expect(container.querySelectorAll(".kpi-card").length).toBe(3);
  });

  it("CardListSkeleton renders N cards", () => {
    const { container } = render(<CardListSkeleton count={4} />);
    expect(container.querySelectorAll(".skeleton-card").length).toBe(4);
  });

  it("PageSkeleton renders the combined page shell", () => {
    const { container } = render(<PageSkeleton />);
    expect(container.querySelectorAll(".kpi-card").length).toBeGreaterThanOrEqual(1);
  });
});
