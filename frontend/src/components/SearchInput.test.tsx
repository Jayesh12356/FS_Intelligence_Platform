import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SearchInput from "./SearchInput";

describe("SearchInput", () => {
  it("calls onChange synchronously when debounceMs is 0", () => {
    const onChange = vi.fn();
    render(<SearchInput value="" onChange={onChange} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "hi" } });
    expect(onChange).toHaveBeenCalledWith("hi");
  });

  it("renders a clear button when text is present", () => {
    const onChange = vi.fn();
    render(<SearchInput value="abc" onChange={onChange} />);
    const clearBtn = screen.getByRole("button", { name: /clear search/i });
    fireEvent.click(clearBtn);
    expect(onChange).toHaveBeenLastCalledWith("");
  });

  it("uses the provided placeholder as aria-label when none given", () => {
    render(<SearchInput value="" onChange={() => {}} placeholder="Find tasks..." />);
    expect(screen.getByRole("searchbox")).toHaveAttribute("aria-label", "Find tasks...");
  });
});
