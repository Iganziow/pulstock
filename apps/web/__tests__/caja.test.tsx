import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// caja does NOT use useGlobalStyles

const { default: CajaPage } = await import(
  "@/app/(dashboard)/dashboard/caja/page"
);

function setupMocks(hasSession = false) {
  mockFetch.mockImplementation(async (url: string) => {
    if (url.includes("/caja/registers/")) {
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => [{ id: 1, name: "Caja 1", is_active: true }] };
    }
    if (url.includes("/caja/sessions/current/")) {
      if (hasSession) {
        return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ id: 1, register: 1, opened_at: "2026-04-04T08:00:00Z", opening_amount: "50000", status: "open" }) };
      }
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => null };
    }
    if (url.includes("/caja/sessions/")) {
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ count: 0, results: [] }) };
    }
    return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }), json: async () => ({}) };
  });
}

beforeEach(() => {
  mockFetch.mockReset();
  localStorage.clear();
  localStorage.setItem("access", "fake-token");
  setupMocks();
});

describe("CajaPage", () => {
  it("renders page heading", async () => {
    render(<CajaPage />);
    await waitFor(() => {
      expect(screen.getByText("Caja")).toBeInTheDocument();
    });
  });

  it("shows register name", async () => {
    render(<CajaPage />);
    await waitFor(() => {
      expect(screen.getByText("Caja 1")).toBeInTheDocument();
    });
  });

  it("shows loading spinner initially", async () => {
    mockFetch.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<CajaPage />);
    await waitFor(() => {
      expect(container.querySelector("svg")).toBeInTheDocument();
    });
  });

  it("shows open session form when no active session", async () => {
    render(<CajaPage />);
    await waitFor(() => {
      expect(screen.getByText("Abrir nuevo arqueo")).toBeInTheDocument();
    });
  });
});
