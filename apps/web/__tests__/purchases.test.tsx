import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);
vi.mock("@/lib/useGlobalStyles", () => ({ useGlobalStyles: () => {} }));

const { default: PurchasesPage } = await import(
  "@/app/(dashboard)/dashboard/purchases/page"
);

function setupMocks() {
  mockFetch.mockImplementation(async (url: string) => {
    if (url.includes("/core/warehouses/")) {
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => [{ id: 1, name: "Bodega Principal", is_active: true }] };
    }
    if (url.includes("/purchases/")) {
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          count: 1,
          results: [
            { id: 1, invoice_number: "FC-001", supplier_name: "Proveedor SA", status: "POSTED", total: "50000.000", created_at: "2026-04-04T10:00:00Z", warehouse_name: "Bodega Principal", lines_count: 5 },
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

describe("PurchasesPage", () => {
  it("renders page heading", async () => {
    render(<PurchasesPage />);
    await waitFor(() => {
      expect(screen.getByText("Compras")).toBeInTheDocument();
    });
  });

  it("shows purchase list after loading", async () => {
    render(<PurchasesPage />);
    await waitFor(() => {
      expect(screen.getByText("FC-001")).toBeInTheDocument();
    });
  });

  it("shows supplier name", async () => {
    render(<PurchasesPage />);
    await waitFor(() => {
      expect(screen.getByText("Proveedor SA")).toBeInTheDocument();
    });
  });

  it("shows loading spinner initially", async () => {
    mockFetch.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<PurchasesPage />);
    await waitFor(() => {
      expect(container.querySelector("svg")).toBeInTheDocument();
    });
  });

  it("renders new purchase button", async () => {
    render(<PurchasesPage />);
    await waitFor(() => {
      expect(screen.getByText(/nueva compra/i)).toBeInTheDocument();
    });
  });
});
