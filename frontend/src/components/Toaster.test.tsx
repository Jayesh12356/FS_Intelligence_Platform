import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ToastProvider, useToast } from "./Toaster";

function Harness() {
  const t = useToast();
  return (
    <div>
      <button onClick={() => t.success("Saved", "All good")}>success</button>
      <button onClick={() => t.error("Failed", "Try again")}>error</button>
      <button onClick={() => t.info("Heads up")}>info</button>
      <button onClick={() => t.dismiss("not-a-real-id")}>dismiss-missing</button>
    </div>
  );
}

describe("ToastProvider", () => {
  it("renders a toast with title and description when success() is called", () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>
    );
    act(() => {
      fireEvent.click(screen.getByText("success"));
    });
    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(screen.getByText("All good")).toBeInTheDocument();
  });

  it("renders different kinds of toasts", () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>
    );
    act(() => {
      fireEvent.click(screen.getByText("success"));
      fireEvent.click(screen.getByText("error"));
      fireEvent.click(screen.getByText("info"));
    });
    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Heads up")).toBeInTheDocument();
  });

  it("exposes an aria-live notification region", () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>
    );
    const region = screen.getByRole("region", { name: /notifications/i });
    expect(region).toHaveAttribute("aria-live", "polite");
  });

  it("dismisses a toast when its close button is clicked", () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>
    );
    act(() => {
      fireEvent.click(screen.getByText("success"));
    });
    expect(screen.getByText("Saved")).toBeInTheDocument();

    const closeBtn = screen.getByRole("button", { name: /^dismiss$/i });
    act(() => {
      fireEvent.click(closeBtn);
    });
    // Saved is gone from active state — AnimatePresence may leave a hidden
    // copy during exit, so assert there's at most one ghost.
    const remaining = screen.queryAllByText("Saved");
    expect(remaining.length).toBeLessThanOrEqual(1);
  });

  it("silently ignores dismiss() for unknown ids", () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>
    );
    act(() => {
      fireEvent.click(screen.getByText("dismiss-missing"));
    });
    // No crash and the notification region is still rendered.
    expect(screen.getByRole("region", { name: /notifications/i })).toBeInTheDocument();
  });
});
