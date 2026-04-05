import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);
vi.mock("@/lib/useGlobalStyles", () => ({ useGlobalStyles: () => {} }));

const { default: SalesPage } = await import(
  "@/app/(dashboard)/dashboard/sales/page"
);

function setupMocks() {
  mockFetch.mockImplementation(async (url: string) => {
    if (url.includes("/core/warehouses/")) {
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => [{ id: 1, name: "Bodega Principal", is_active: true }] };
    }
    if (url.includes("/sales/sales/")) {
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          count: 2,
          results: [
            { id: 1, sale_number: 1001, status: "COMPLETED", subtotal: "15000.000", total_paid: "15000", created_at: "2026-04-04T10:00:00Z", warehouse_name: "Bodega Principal", lines_count: 3, sale_type: "venta", payments: [] },
            { id: 2, sale_number: 1002, status: "VOID", subtotal: "8000.000", total_paid: "8000", created_at: "2026-04-04T11:00:00Z", warehouse_name: "Bodega Principal", lines_count: 1, sale_type: "venta", payments: [] },
          ],
        }) };
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

describe("SalesPage", () => {
  it("renders page heading", async () => {
    render(<SalesPage />);
    await waitFor(() => {
      expect(screen.getByText("Ventas")).toBeInTheDocument();
    });
  });

  it("shows sales after loading", async () => {
    render(<SalesPage />);
    await waitFor(() => {
      expect(screen.getByText(/#1001/)).toBeInTheDocument();
    });
  });

  it("displays VOID status badge", async () => {
    render(<SalesPage />);
    await waitFor(() => {
      const badges = screen.getAllByText(/anulada/i);
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  it("renders search input", async () => {
    render(<SalesPage />);
    await waitFor(() => {
      const input = screen.getByPlaceholderText(/buscar|nº venta|cliente/i);
      expect(input).toBeInTheDocument();
    });
  });

  it("shows loading spinner initially", async () => {
    mockFetch.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<SalesPage />);
    await waitFor(() => {
      expect(container.querySelector("svg")).toBeInTheDocument();
    });
  });

  it("shows total count", async () => {
    render(<SalesPage />);
    await waitFor(() => {
      expect(screen.getByText("2")).toBeInTheDocument();
    });
  });
});
