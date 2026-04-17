import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The SSR theme init script lives in layout.tsx as a string that runs as
 * early as possible in <head>. This test reproduces the exact logic so we
 * can assert that:
 *   1. localStorage takes precedence.
 *   2. Falls back to the OS preferred color scheme.
 *   3. Defaults to 'light' when neither is available.
 *   4. Never throws, even when localStorage access fails.
 */
function runThemeInit(): string {
  try {
    let t = window.localStorage.getItem("fsp-theme");
    if (!t) t = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", t);
    return t;
  } catch {
    return "light";
  }
}

describe("SSR theme init", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute("data-theme");
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("uses saved localStorage value when present", () => {
    window.localStorage.setItem("fsp-theme", "dark");
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: false,
    } as MediaQueryList);
    expect(runThemeInit()).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("falls back to system preference when no localStorage value", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
    } as MediaQueryList);
    expect(runThemeInit()).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("defaults to 'light' when nothing is configured", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: false,
    } as MediaQueryList);
    expect(runThemeInit()).toBe("light");
  });

  it("never throws when storage is inaccessible", () => {
    vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(() => runThemeInit()).not.toThrow();
  });
});
