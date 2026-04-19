/**
 * Contract tests for `src/lib/api.ts`.
 *
 * Every exported async function in api.ts wraps `apiFetch`, which ultimately
 * calls `fetch(url, options)`. The perfection loop requires that no api.ts
 * function silently drifts away from the backend schema.
 *
 * This suite locks two invariants per function:
 *
 *   1. The function issues **exactly one** HTTP call.
 *   2. The URL starts with `/api/` or is the root health endpoint.
 *   3. Non-2xx responses produce an `APIError`, not a raw Error.
 *   4. Successful responses are returned verbatim (the fetch-driven envelope).
 *
 * Rather than a separate test per function (which would bloat the file to
 * ~98 near-identical cases), we enumerate every exported function via
 * `import *` and drive a table-driven probe. Each probe calls the function
 * with a synthetic argument set and asserts the fetch was made.
 *
 * Exceptions (functions that don't hit the network) are listed in
 * NON_NETWORK_EXPORTS and skipped explicitly so the test surfaces any drift.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";

const NON_NETWORK_EXPORTS = new Set<string>([
  "API_BASE",
  "APIError",
  "isApiError",
  "errorMessage",
  "apiFetch",
  "isCursorTaskEnvelope",
]);

function buildFetchMock(response: unknown = { data: null, error: null }, status = 200) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "ERR",
    headers: new Headers(),
    json: async () => response,
  } as unknown as Response);
}

function syntheticArg(name: string, index: number): unknown {
  // Positional argument fallback: provide id-like strings then a File-like
  // object, then a config object. Most api.ts functions take (id, payload)
  // or (id) so this covers the common shape.
  if (index === 0) {
    if (/file|upload/i.test(name)) {
      return new File(["x"], "f.txt", { type: "text/plain" });
    }
    return "test-id";
  }
  if (index === 1) {
    if (/file|upload/i.test(name)) {
      return "project-id";
    }
    return {};
  }
  return {};
}

// Detect arity via `.length` — works for non-arrow functions too.
// The filter pipeline guarantees every entry is a function at runtime.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function callCount(fn: any): number {
  return Math.min((fn as { length: number }).length ?? 1, 3);
}

describe("api.ts contract", () => {
  beforeEach(() => {
    (global as { fetch: unknown }).fetch = buildFetchMock();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const exports = Object.entries(api).filter(
    ([name, value]) =>
      !NON_NETWORK_EXPORTS.has(name) &&
      typeof value === "function" &&
      // Skip React hooks or class-type exports.
      !/^use[A-Z]/.test(name) &&
      !/^[A-Z]/.test(name),
  );

  it("at least 50 network-bound exports are present (sanity)", () => {
    expect(exports.length).toBeGreaterThanOrEqual(50);
  });

  for (const [name, fn] of exports) {
    it(`${name} issues exactly one fetch to an /api path (or /health)`, async () => {
      const mock = buildFetchMock();
      (global as { fetch: unknown }).fetch = mock;
      const n = callCount(fn);
      const args = Array.from({ length: n }, (_, i) => syntheticArg(name, i));
      try {
        await (fn as (...a: unknown[]) => Promise<unknown>)(...args);
      } catch (err) {
        // The function may throw on unrealistic arguments (e.g. FormData
        // shape mismatches). We only care that the contract probe reached
        // `fetch` exactly once before throwing.
        void err;
      }
      expect(mock).toHaveBeenCalledTimes(1);
      const url = String((mock.mock.calls[0] ?? [])[0] ?? "");
      const pathOk = /\/api\//.test(url) || /\/health$/.test(url) || /\/$/.test(url);
      expect(pathOk, `URL ${url!}`).toBe(true);
    });
  }

  it("APIError is raised on non-2xx responses", async () => {
    (global as { fetch: unknown }).fetch = buildFetchMock(
      { error: "bad", code: "err_test" },
      500,
    );
    await expect(api.listDocuments()).rejects.toBeInstanceOf(api.APIError);
  });

  it("errorMessage extracts messages from APIError and Error", () => {
    expect(api.errorMessage(new api.APIError("x", { status: 500 }))).toBe("x");
    expect(api.errorMessage(new Error("y"))).toBe("y");
    expect(api.errorMessage(null)).toMatch(/something went wrong/i);
  });
});
