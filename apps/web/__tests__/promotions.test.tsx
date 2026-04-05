import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// promotions does NOT use useGlobalStyles

const { default: PromotionsPage } = await import(
  "@/app/(dashboard)/dashboard/promotions/page"
);

function setupMocks() {
  mockFetch.mockImplementation(async (url: string) => {
    if (url.includes("/promotions/")) {
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          count: 1,
          results: [
            { id: 1, name: "2x1 en Arroz", discount_type: "percentage", discount_value: "50.00", is_active: true, start_date: "2026-04-01", end_date: "2026-04-30", products: [{ id: 1, product_name: "Arroz" }], days_of_week: [] },
          ],
        }) };
    }
    if (url.includes("/catalog/products/")) {
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ count: 1, results: [{ id: 1, name: "Arroz", sku: "ARR-001", price: "1500" }] }) };
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

describe("PromotionsPage", () => {
  it("renders page heading", async () => {
    render(<PromotionsPage />);
    await waitFor(() => {
      expect(screen.getByText("Ofertas y Promociones")).toBeInTheDocument();
    });
  });

  it("shows promotion name after loading", async () => {
    render(<PromotionsPage />);
    await waitFor(() => {
      expect(screen.getByText("2x1 en Arroz")).toBeInTheDocument();
    });
  });

  it("shows create button", async () => {
    render(<PromotionsPage />);
    await waitFor(() => {
      expect(screen.getByText(/Crear Oferta/i)).toBeInTheDocument();
    });
  });

  it("shows loading spinner initially", async () => {
    mockFetch.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<PromotionsPage />);
    await waitFor(() => {
      expect(container.querySelector("svg")).toBeInTheDocument();
    });
  });

  it("shows active promotion", async () => {
    render(<PromotionsPage />);
    await waitFor(() => {
      const active = screen.getAllByText(/activa/i);
      expect(active.length).toBeGreaterThan(0);
    });
  });
});
