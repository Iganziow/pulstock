import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Must import AFTER mocking fetch
const { apiFetch, ApiError } = await import("@/lib/api");

function mockResponse(status: number, body: any, ok?: boolean) {
  const bodyStr = JSON.stringify(body);
  return {
    ok: ok ?? (status >= 200 && status < 300),
    status,
    json: async () => body,
    text: async () => bodyStr,
    headers: new Headers({ "content-type": "application/json" }),
    clone: function () { return this; },
  };
}

beforeEach(() => {
  mockFetch.mockReset();
  localStorage.clear();
});

describe("apiFetch", () => {
  it("makes GET request with correct URL", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse(200, { data: "test" }));

    const result = await apiFetch("/core/health/");
    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/core/health/");
    expect(options.credentials).toBe("include");
  });

  it("includes Authorization header when token exists", async () => {
    localStorage.setItem("access", "test-token-123");
    mockFetch.mockResolvedValueOnce(mockResponse(200, {}));

    await apiFetch("/test/");
    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers["Authorization"]).toBe("Bearer test-token-123");
  });

  it("throws on non-ok response", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse(400, { detail: "Campo requerido" }));
    await expect(apiFetch("/test/")).rejects.toThrow();
  });

  it("throws on network failure", async () => {
    mockFetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(apiFetch("/test/")).rejects.toThrow();
  });

  it("sends POST with correct method", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse(201, { id: 1 }));

    await apiFetch("/products/", {
      method: "POST",
      body: JSON.stringify({ name: "Test" }),
    });

    const [, options] = mockFetch.mock.calls[0];
    expect(options.method).toBe("POST");
    expect(options.headers["Content-Type"]).toBe("application/json");
  });
});
