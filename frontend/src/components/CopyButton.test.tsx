import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import CopyButton from "./CopyButton";

describe("CopyButton", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it("renders the default label", () => {
    render(<CopyButton text="hi" />);
    expect(screen.getByRole("button", { name: /copy/i })).toBeInTheDocument();
  });

  it("invokes clipboard.writeText with the provided text", () => {
    render(<CopyButton text="payload" />);
    fireEvent.click(screen.getByRole("button"));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("payload");
  });

  it("uses a custom label when provided", () => {
    render(<CopyButton text="x" label="Copy MCP JSON" />);
    expect(screen.getByRole("button", { name: /copy mcp json/i })).toBeInTheDocument();
  });
});
