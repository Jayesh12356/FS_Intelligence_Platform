import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EmptyState from "./EmptyState";

describe("EmptyState", () => {
  it("renders title and description", () => {
    render(
      <EmptyState
        icon={<span data-testid="icon">icon</span>}
        title="Nothing here"
        description="Try adjusting filters"
      />,
    );
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("Try adjusting filters")).toBeInTheDocument();
    expect(screen.getByTestId("icon")).toBeInTheDocument();
  });

  it("renders an action node when provided", () => {
    render(
      <EmptyState
        icon={<span>i</span>}
        title="Empty"
        action={<button>Retry</button>}
      />,
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
