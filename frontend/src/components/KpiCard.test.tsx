import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import KpiCard from "./KpiCard";

describe("KpiCard", () => {
  it("renders the label", () => {
    render(<KpiCard label="Tasks" value={42} icon={<span>i</span>} />);
    expect(screen.getByText("Tasks")).toBeInTheDocument();
  });

  it("renders valueText when provided (skips animated number)", () => {
    render(<KpiCard label="Status" valueText="Ready" icon={<span>i</span>} />);
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });

  it("renders a trend indicator when provided", () => {
    render(
      <KpiCard
        label="Score"
        value={90}
        icon={<span>i</span>}
        trend={{ value: "+3%", direction: "up" }}
      />,
    );
    expect(screen.getByText(/\+3%/)).toBeInTheDocument();
  });
});
