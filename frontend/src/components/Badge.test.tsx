import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Badge, { StatusBadge } from "./Badge";

describe("Badge", () => {
  it("renders children and applies the default neutral variant class", () => {
    render(<Badge>Hello</Badge>);
    const el = screen.getByText("Hello");
    expect(el).toBeInTheDocument();
    expect(el.className).toMatch(/badge-neutral/);
  });

  it("applies the variant class when provided", () => {
    render(<Badge variant="success">Ok</Badge>);
    expect(screen.getByText("Ok").className).toMatch(/badge-success/);
  });

  it("adds the dot class when dot is true", () => {
    render(<Badge dot>D</Badge>);
    expect(screen.getByText("D").className).toMatch(/badge-dot/);
  });
});

describe("StatusBadge", () => {
  it("renders arbitrary status strings", () => {
    render(<StatusBadge status="UPLOADED" />);
    expect(screen.getByText(/uploaded/i)).toBeInTheDocument();
  });
});
