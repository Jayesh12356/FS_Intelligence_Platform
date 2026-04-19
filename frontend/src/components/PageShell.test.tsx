import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PageShell from "./PageShell";

describe("PageShell", () => {
  it("renders the title and subtitle", () => {
    render(
      <PageShell title="My Page" subtitle="a subtitle">
        <div>body</div>
      </PageShell>,
    );
    expect(screen.getByRole("heading", { name: /my page/i })).toBeInTheDocument();
    expect(screen.getByText("a subtitle")).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
  });

  it("renders a back link when backHref is provided", () => {
    render(
      <PageShell title="X" backHref="/" backLabel="Go home">
        <div />
      </PageShell>,
    );
    expect(screen.getByRole("link", { name: /go home/i })).toHaveAttribute("href", "/");
  });

  it("renders actions and badges", () => {
    render(
      <PageShell
        title="X"
        actions={<button>act</button>}
        badge={<span>beta</span>}
      >
        <div />
      </PageShell>,
    );
    expect(screen.getByRole("button", { name: /act/i })).toBeInTheDocument();
    expect(screen.getByText("beta")).toBeInTheDocument();
  });
});
