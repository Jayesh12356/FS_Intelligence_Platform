import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  cancelCursorTask: vi.fn().mockResolvedValue({ data: null, error: null }),
  pollCursorTask: vi.fn().mockResolvedValue({
    data: { status: "pending", result_ref: null, error: null, updated_at: null },
    error: null,
  }),
}));

import CursorTaskModal from "./CursorTaskModal";

const MCP_SNIPPET = JSON.stringify(
  {
    mcpServers: {
      "fs-intelligence-platform": {
        command: "python",
        args: ["mcp-server/server.py"],
        env: { BACKEND_URL: "http://localhost:8000" },
      },
    },
  },
  null,
  2,
);

const baseEnvelope = {
  mode: "cursor_task" as const,
  task_id: "abcdef0123456789",
  kind: "reverse_fs" as const,
  prompt: "Paste me into Cursor for reverse FS work.",
  mcp_snippet: MCP_SNIPPET,
  status: "pending" as const,
};

describe("CursorTaskModal", () => {
  it("renders nothing when no envelope is provided", () => {
    const { container } = render(
      <CursorTaskModal envelope={null} onClose={() => {}} />,
    );
    expect(container.textContent ?? "").not.toContain("Cursor");
  });

  it("renders the MCP setup section ABOVE the prompt", () => {
    render(<CursorTaskModal envelope={baseEnvelope} onClose={() => {}} />);

    const mcp = screen.getByTestId("mcp-setup-section");
    const prompt = screen.getByTestId("prompt-section");
    // Document order: MCP setup must precede prompt so users configure
    // MCP before pasting (the bug fix).
    expect(
      mcp.compareDocumentPosition(prompt) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("shows the MCP snippet verbatim and the prompt verbatim, NOT combined", () => {
    render(<CursorTaskModal envelope={baseEnvelope} onClose={() => {}} />);

    expect(screen.getByTestId("mcp-snippet-block").textContent).toContain(
      "fs-intelligence-platform",
    );
    expect(screen.getByTestId("mcp-snippet-block").textContent).toContain(
      "BACKEND_URL",
    );

    const promptBlock = screen.getByTestId("prompt-block").textContent ?? "";
    expect(promptBlock).toContain("Paste me into Cursor for reverse FS work.");
    // The old combined-paste behaviour is gone — prompt block must NOT
    // contain the MCP JSON.
    expect(promptBlock).not.toContain("fs-intelligence-platform");
  });

  it("offers a dedicated copy button for the MCP config", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<CursorTaskModal envelope={baseEnvelope} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId("copy-mcp-snippet"));

    expect(writeText).toHaveBeenCalledWith(MCP_SNIPPET);
  });

  it("offers a separate copy button that copies ONLY the prompt", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<CursorTaskModal envelope={baseEnvelope} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId("copy-prompt"));

    expect(writeText).toHaveBeenCalledWith(baseEnvelope.prompt);
    expect(writeText).not.toHaveBeenCalledWith(
      expect.stringContaining("fs-intelligence-platform"),
    );
  });

  it("renders a permanent troubleshooting note that names the exact Cursor error", () => {
    render(<CursorTaskModal envelope={baseEnvelope} onClose={() => {}} />);

    const note = screen.getByTestId("mcp-troubleshoot");
    const text = note.textContent ?? "";
    expect(text).toContain("no MCP server is registered for fs-intelligence-platform");
    // For each kind the note must reference the matching submit tool.
    expect(text).toContain("submit_reverse_fs");
    // And it must explicitly forbid the JSON-on-disk fallback.
    expect(text).toMatch(/Do not.*JSON file.*workspace root/i);
  });

  it("references the correct submit tool per kind", () => {
    const { rerender } = render(
      <CursorTaskModal
        envelope={{ ...baseEnvelope, kind: "analyze" }}
        onClose={() => {}}
      />,
    );
    expect(
      screen.getByTestId("mcp-troubleshoot").textContent ?? "",
    ).toContain("submit_analyze");

    rerender(
      <CursorTaskModal
        envelope={{ ...baseEnvelope, kind: "generate_fs" }}
        onClose={() => {}}
      />,
    );
    expect(
      screen.getByTestId("mcp-troubleshoot").textContent ?? "",
    ).toContain("submit_generate_fs");
  });
});
