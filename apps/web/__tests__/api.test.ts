import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const {
  apiFetch, getAccessToken, setTokens, clearTokens,
  decodeTokenPayload, ApiError, isSuperAdmin, setSuperAdmin,
} = await import("@/lib/api");

beforeEach(() => {
  mockFetch.mockReset();
  localStorage.clear();
});

describe("Token helpers", () => {
  it("getAccessToken returns null when no token", () => {
    expect(getAccessToken()).toBeNull();
  });

  it("setTokens stores access in localStorage", () => {
    setTokens("my-token");
    expect(localStorage.getItem("access")).toBe("my-token");
  });

  it("clearTokens removes all auth keys", () => {
    localStorage.setItem("access", "tok");
    localStorage.setItem("is_superuser", "true");
    clearTokens();
    expect(localStorage.getItem("access")).toBeNull();
    expect(localStorage.getItem("is_superuser")).toBeNull();
  });

  it("decodeTokenPayload decodes a valid JWT payload", () => {
    const payload = { user_id: 1, email: "test@test.cl" };
    const b64 = btoa(JSON.stringify(payload));
    const token = `header.${b64}.signature`;
    expect(decodeTokenPayload(token)).toEqual(payload);
  });

  it("decodeTokenPayload returns null for invalid token", () => {
    expect(decodeTokenPayload("not-a-jwt")).toBeNull();
    expect(decodeTokenPayload(null)).toBeNull();
  });

  it("isSuperAdmin returns false by default", () => {
    expect(isSuperAdmin()).toBe(false);
  });

  it("setSuperAdmin toggles the flag", () => {
    setSuperAdmin(true);
    expect(isSuperAdmin()).toBe(true);
    setSuperAdmin(false);
    expect(isSuperAdmin()).toBe(false);
  });
});

describe("apiFetch", () => {
  it("makes GET request with Authorization header", async () => {
    localStorage.setItem("access", "test-token");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ data: "ok" }),
    });

    const result = await apiFetch("/core/me/");
    expect(result).toEqual({ data: "ok" });
    expect(mockFetch).toHaveBeenCalledOnce();

    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toContain("/core/me/");
    expect(opts.headers.Authorization).toBe("Bearer test-token");
  });

  it("throws ApiError on 400 response", async () => {
    localStorage.setItem("access", "test-token");
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Bad request" }),
    });

    let caught: any;
    try {
      await apiFetch("/bad/");
    } catch (e: any) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught.status).toBe(400);
  });

  it("attempts token refresh on 401", async () => {
    localStorage.setItem("access", "expired-token");

    // First call: 401
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Token expired" }),
    });

    // Refresh call: success
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ access: "new-token" }),
    });

    // Retry call: success
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ data: "refreshed" }),
    });

    const result = await apiFetch("/protected/");
    expect(result).toEqual({ data: "refreshed" });
    // Should have made 3 calls: original, refresh, retry
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it("sends POST body as JSON", async () => {
    localStorage.setItem("access", "test-token");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ id: 1 }),
    });

    await apiFetch("/products/", {
      method: "POST",
      body: JSON.stringify({ name: "Test" }),
      headers: { "Content-Type": "application/json" },
    });

    const [, opts] = mockFetch.mock.calls[0];
    expect(opts.method).toBe("POST");
  });
});
