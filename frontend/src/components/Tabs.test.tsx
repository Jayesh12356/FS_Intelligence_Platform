import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Tabs from "./Tabs";

const ITEMS = [
  { key: "a", label: "Alpha" },
  { key: "b", label: "Beta", count: 2 },
  { key: "c", label: "Gamma" },
];

describe("Tabs keyboard navigation", () => {
  it("uses roving tabindex so only the active tab is focusable", () => {
    render(<Tabs items={ITEMS} active="a" onChange={() => {}} aria-label="demo" />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveAttribute("tabIndex", "0");
    expect(tabs[1]).toHaveAttribute("tabIndex", "-1");
    expect(tabs[2]).toHaveAttribute("tabIndex", "-1");
  });

  it("advances to the next tab with ArrowRight", () => {
    const onChange = vi.fn();
    render(<Tabs items={ITEMS} active="a" onChange={onChange} aria-label="demo" />);
    const tabs = screen.getAllByRole("tab");
    tabs[0].focus();
    fireEvent.keyDown(tabs[0], { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("wraps to the first tab with ArrowRight on the last tab", () => {
    const onChange = vi.fn();
    render(<Tabs items={ITEMS} active="c" onChange={onChange} aria-label="demo" />);
    const tabs = screen.getAllByRole("tab");
    tabs[2].focus();
    fireEvent.keyDown(tabs[2], { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("a");
  });

  it("moves to the previous tab with ArrowLeft (wrapping)", () => {
    const onChange = vi.fn();
    render(<Tabs items={ITEMS} active="a" onChange={onChange} aria-label="demo" />);
    const tabs = screen.getAllByRole("tab");
    tabs[0].focus();
    fireEvent.keyDown(tabs[0], { key: "ArrowLeft" });
    expect(onChange).toHaveBeenCalledWith("c");
  });

  it("jumps to first/last tab with Home / End", () => {
    const onChange = vi.fn();
    render(<Tabs items={ITEMS} active="b" onChange={onChange} aria-label="demo" />);
    const tabs = screen.getAllByRole("tab");
    tabs[1].focus();
    fireEvent.keyDown(tabs[1], { key: "End" });
    expect(onChange).toHaveBeenLastCalledWith("c");
    fireEvent.keyDown(tabs[1], { key: "Home" });
    expect(onChange).toHaveBeenLastCalledWith("a");
  });

  it("ignores unrelated keys", () => {
    const onChange = vi.fn();
    render(<Tabs items={ITEMS} active="a" onChange={onChange} aria-label="demo" />);
    const tabs = screen.getAllByRole("tab");
    fireEvent.keyDown(tabs[0], { key: "a" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("fires onChange when clicked", () => {
    const onChange = vi.fn();
    render(<Tabs items={ITEMS} active="a" onChange={onChange} aria-label="demo" />);
    fireEvent.click(screen.getByText("Beta"));
    expect(onChange).toHaveBeenCalledWith("b");
  });
});
