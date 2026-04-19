import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AnimatedNumber from "./AnimatedNumber";

describe("AnimatedNumber", () => {
  it("renders a span containing the prefix and suffix", () => {
    render(<AnimatedNumber value={10} prefix="$" suffix=" tasks" />);
    const span = screen.getByText(/\$0 tasks/);
    expect(span.tagName).toBe("SPAN");
  });

  it("applies className when provided", () => {
    render(<AnimatedNumber value={5} className="kpi-value" />);
    expect(screen.getByText("0").className).toMatch(/kpi-value/);
  });
});
