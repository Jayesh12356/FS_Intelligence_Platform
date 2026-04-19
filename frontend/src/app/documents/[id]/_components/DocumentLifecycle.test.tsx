import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DocumentLifecycle } from "./DocumentLifecycle";

vi.mock("@/lib/api", () => ({
  getActivityLog: vi.fn(),
}));

import { getActivityLog } from "@/lib/api";

const FS_ID = "11111111-2222-3333-4444-555555555555";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DocumentLifecycle", () => {
  it("renders nothing visible until events arrive (loading state)", () => {
    (getActivityLog as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise(() => {})
    );
    render(<DocumentLifecycle fsId={FS_ID} />);
    expect(screen.getByTestId("lifecycle-loading")).toBeInTheDocument();
  });

  it("shows an empty state when no events exist for the document", async () => {
    (getActivityLog as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { events: [], total: 0 },
    });
    render(<DocumentLifecycle fsId={FS_ID} />);
    await waitFor(() =>
      expect(screen.getByTestId("lifecycle-empty")).toBeInTheDocument()
    );
  });

  it("renders chips chronologically and collapses repeats", async () => {
    (getActivityLog as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        events: [
          {
            id: "1",
            fs_id: FS_ID,
            document_name: "doc",
            event_type: "FILE_REGISTERED",
            event_label: "File registered",
            detail: "src/a.py",
            category: "build",
            payload: { file_path: "src/a.py" },
            user_id: "agent",
            created_at: "2026-04-18T10:00:00Z",
          },
          {
            id: "2",
            fs_id: FS_ID,
            document_name: "doc",
            event_type: "FILE_REGISTERED",
            event_label: "File registered",
            detail: "src/b.py",
            category: "build",
            payload: { file_path: "src/b.py" },
            user_id: "agent",
            created_at: "2026-04-18T10:01:00Z",
          },
          {
            id: "3",
            fs_id: FS_ID,
            document_name: "doc",
            event_type: "BUILD_COMPLETED",
            event_label: "Build completed",
            detail: "2/2 tasks · 12s",
            category: "build",
            payload: { completed_tasks: 2 },
            user_id: "agent",
            created_at: "2026-04-18T10:02:00Z",
          },
        ],
        total: 3,
      },
    });

    render(<DocumentLifecycle fsId={FS_ID} />);

    const chips = await screen.findAllByTestId("lifecycle-chip");
    // FILE_REGISTERED collapses to one chip with ×2; BUILD_COMPLETED stays.
    expect(chips).toHaveLength(2);
    expect(chips[0].getAttribute("data-event-type")).toBe("FILE_REGISTERED");
    expect(chips[0].textContent).toContain("×2");
    expect(chips[1].getAttribute("data-event-type")).toBe("BUILD_COMPLETED");
  });

  it("requests activity log filtered by fsId with payload included", async () => {
    (getActivityLog as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { events: [], total: 0 },
    });
    render(<DocumentLifecycle fsId={FS_ID} />);
    await waitFor(() => expect(getActivityLog).toHaveBeenCalled());
    const args = (getActivityLog as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(args).toMatchObject({
      fsId: FS_ID,
      includePayload: true,
    });
  });
});
