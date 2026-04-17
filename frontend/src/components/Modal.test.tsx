import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Modal from "./Modal";

describe("Modal", () => {
  it("does not render when closed", () => {
    render(
      <Modal open={false} onClose={() => {}} title="X">
        <p>hidden</p>
      </Modal>
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders with title and dialog role when open", () => {
    render(
      <Modal open onClose={() => {}} title="Settings">
        <button>OK</button>
      </Modal>
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("calls onClose on Escape", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="X">
        <button>OK</button>
      </Modal>
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("auto-focuses the first focusable element when opened", async () => {
    render(
      <Modal open onClose={() => {}} title="X">
        <button data-testid="first">first</button>
        <button data-testid="second">second</button>
      </Modal>
    );
    const first = await screen.findByTestId("first");
    // Focus happens inside a layout-effect; assert it on the next tick.
    await new Promise((r) => setTimeout(r, 0));
    expect(document.activeElement).toBe(first);
  });

  it("restores focus to the previously focused element on close", async () => {
    const trigger = document.createElement("button");
    trigger.textContent = "opener";
    document.body.appendChild(trigger);
    trigger.focus();

    const { rerender } = render(
      <Modal open onClose={() => {}} title="X">
        <button>inside</button>
      </Modal>
    );
    await new Promise((r) => setTimeout(r, 0));

    rerender(
      <Modal open={false} onClose={() => {}} title="X">
        <button>inside</button>
      </Modal>
    );
    await new Promise((r) => setTimeout(r, 0));

    expect(document.activeElement).toBe(trigger);
    document.body.removeChild(trigger);
  });

  it("traps focus — Tab on the last element returns to the first", async () => {
    render(
      <Modal open onClose={() => {}} title="X">
        <button data-testid="first">first</button>
        <button data-testid="second">second</button>
      </Modal>
    );
    const second = await screen.findByTestId("second");
    second.focus();
    fireEvent.keyDown(window, { key: "Tab" });
    const first = screen.getByTestId("first");
    expect(document.activeElement).toBe(first);
  });

  it("traps focus — Shift+Tab on the first element wraps to the last", async () => {
    render(
      <Modal open onClose={() => {}} title="X">
        <button data-testid="first">first</button>
        <button data-testid="second">second</button>
      </Modal>
    );
    const first = await screen.findByTestId("first");
    first.focus();
    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
    const second = screen.getByTestId("second");
    expect(document.activeElement).toBe(second);
  });
});
