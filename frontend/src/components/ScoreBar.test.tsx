import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ScoreBar from "./ScoreBar";

describe("ScoreBar", () => {
  it("shows the label and formatted value", () => {
    render(<ScoreBar label="Completeness" value={73.4} />);
    expect(screen.getByText("Completeness")).toBeInTheDocument();
    expect(screen.getByText("73.4")).toBeInTheDocument();
  });

  it("accepts a custom color", () => {
    const { container } = render(<ScoreBar label="X" value={50} color="#ff00ff" />);
    const valueSpan = screen.getByText("50.0");
    expect(valueSpan).toHaveStyle({ color: "#ff00ff" });
    expect(container.querySelector(".score-bar-track")).toBeInTheDocument();
  });
});
