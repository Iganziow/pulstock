import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

let mockPathname = "/dashboard/catalog";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => mockPathname,
  useSearchParams: () => new URLSearchParams(),
}));

const { default: CatalogPage } = await import(
  "@/app/(dashboard)/dashboard/catalog/page"
);

function mockApiResponses() {
  mockFetch.mockImplementation(async (url: string) => {
    if (url.includes("/catalog/products/")) {
      return {
        ok: true, status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          count: 2,
          results: [
            { id: 1, name: "Arroz Grado 1", sku: "ARR-001", price: "1500", is_active: true, category: { id: 1, name: "Granos", is_active: true }, barcodes: [{ id: 1, code: "7802810050232" }], unit: "KG" },
            { id: 2, name: "Aceite Vegetal", sku: "ACE-002", price: "2800", is_active: true, category: { id: 2, name: "Aceites", is_active: true }, barcodes: [], unit: "LT" },
          ],
        }),
      };
    }
    if (url.includes("/catalog/categories/")) {
      return {
        ok: true, status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ([
          { id: 1, name: "Granos", code: "GRN", is_active: true, children_count: 0 },
          { id: 2, name: "Aceites", code: "ACE", is_active: true, children_count: 0 },
        ]),
      };
    }
    if (url.includes("/catalog/units/")) {
      return {
        ok: true, status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ results: [{ id: 1, code: "UN", name: "Unidad" }] }),
      };
    }
    // Default
    return {
      ok: true, status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({}),
    };
  });
}

beforeEach(() => {
  mockFetch.mockReset();
  localStorage.clear();
  localStorage.setItem("access", "fake-token");
  mockApiResponses();
});

describe("CatalogPage", () => {
  it("renders the page title", async () => {
    render(<CatalogPage />);
    await waitFor(() => {
      expect(screen.getByText("Catálogo")).toBeInTheDocument();
    });
  });

  it("renders product list after loading", async () => {
    render(<CatalogPage />);
    await waitFor(() => {
      expect(screen.getByText("Arroz Grado 1")).toBeInTheDocument();
      expect(screen.getByText("Aceite Vegetal")).toBeInTheDocument();
    });
  });

  it("shows total count in stat card", async () => {
    render(<CatalogPage />);
    await waitFor(() => {
      // Multiple "2" elements exist (stat cards); just check at least one
      const els = screen.getAllByText("2");
      expect(els.length).toBeGreaterThan(0);
    });
  });

  it("renders search input", async () => {
    render(<CatalogPage />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/arroz.*7802810050232/i)).toBeInTheDocument();
    });
  });

  it("renders Asignar Barcodes button", async () => {
    render(<CatalogPage />);
    await waitFor(() => {
      expect(screen.getByText("Asignar Barcodes")).toBeInTheDocument();
    });
  });

  it("renders + Producto button", async () => {
    render(<CatalogPage />);
    await waitFor(() => {
      expect(screen.getByText("+ Producto")).toBeInTheDocument();
    });
  });

  it("shows barcode in product row", async () => {
    render(<CatalogPage />);
    await waitFor(() => {
      expect(screen.getByText("7802810050232")).toBeInTheDocument();
    });
  });
});
