import { afterEach, describe, expect, it, vi } from "vitest";
import { APIError, apiFetch, errorMessage, isApiError } from "./api";

const origFetch = global.fetch;

afterEach(() => {
  global.fetch = origFetch;
  vi.restoreAllMocks();
});

function mockResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

describe("apiFetch", () => {
  it("parses a successful response", async () => {
    const payload = { data: { hello: "world" }, error: null, meta: null };
    global.fetch = vi.fn().mockResolvedValue(mockResponse(200, payload));
    const out = await apiFetch<{ hello: string }>("/ok");
    expect(out.data).toEqual({ hello: "world" });
  });

  it("throws APIError with code + request_id on structured 4xx", async () => {
    const body = { error: "Something broke", code: "bad_thing", request_id: "rid-123" };
    global.fetch = vi.fn().mockResolvedValue(
      mockResponse(400, body, { "X-Request-ID": "rid-123" })
    );
    await expect(apiFetch("/bad")).rejects.toMatchObject({
      status: 400,
      code: "bad_thing",
      requestId: "rid-123",
      message: "Something broke",
    });
  });

  it("flattens FastAPI pydantic validation errors into a readable message", async () => {
    const body = {
      detail: [
        { msg: "field required", loc: ["body", "name"] },
        { msg: "string too short", loc: ["body", "bio"] },
      ],
    };
    global.fetch = vi.fn().mockResolvedValue(mockResponse(422, body));
    await expect(apiFetch("/form")).rejects.toMatchObject({
      status: 422,
      message: "field required; string too short",
    });
  });

  it("uses status text when body is empty", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 500, statusText: "Server Error" }));
    await expect(apiFetch("/crash")).rejects.toMatchObject({
      status: 500,
      message: expect.stringMatching(/500/),
    });
  });

  it("raises AbortError verbatim when request is cancelled", async () => {
    const abortErr = Object.assign(new Error("aborted"), { name: "AbortError" });
    global.fetch = vi.fn().mockRejectedValue(abortErr);
    await expect(apiFetch("/slow")).rejects.toBe(abortErr);
  });

  it("wraps network errors into APIError with code=network_error", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(apiFetch("/off")).rejects.toMatchObject({
      status: 0,
      code: "network_error",
    });
  });
});

describe("APIError helpers", () => {
  it("isApiError discriminates properly", () => {
    const err = new APIError("nope", { status: 404 });
    expect(isApiError(err)).toBe(true);
    expect(isApiError(new Error("plain"))).toBe(false);
    expect(isApiError(null)).toBe(false);
  });

  it("errorMessage reads APIError.message, Error.message, or fallback", () => {
    expect(errorMessage(new APIError("boom", { status: 500 }))).toBe("boom");
    expect(errorMessage(new Error("bang"))).toBe("bang");
    expect(errorMessage(null, "fallback msg")).toBe("fallback msg");
  });
});
