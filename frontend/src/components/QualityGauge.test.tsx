import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import QualityGauge from "./QualityGauge";

describe("QualityGauge", () => {
  it("renders the rounded score and /100 suffix", () => {
    render(<QualityGauge score={87.4} />);
    expect(screen.getByText("87")).toBeInTheDocument();
    expect(screen.getByText(/\/ 100/)).toBeInTheDocument();
  });

  it("renders a custom label", () => {
    render(<QualityGauge score={50} label="Health" />);
    expect(screen.getByText("Health")).toBeInTheDocument();
  });
});
