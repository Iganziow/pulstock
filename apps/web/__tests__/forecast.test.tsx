import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// forecast page does NOT use useGlobalStyles

const { default: ForecastPage } = await import(
  "@/app/(dashboard)/dashboard/forecast/page"
);

function setupMocks() {
  mockFetch.mockImplementation(async (url: string) => {
    if (url.includes("/forecast/dashboard/")) {
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ kpis: { imminent_3d: 1, at_risk_7d: 3, pending_suggestions: 2, products_with_forecast: 45, value_at_risk: 150000 } }) };
    }
    if (url.includes("/forecast/products/")) {
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          count: 1,
          results: [
            { product_id: 1, product_name: "Arroz Grado 1", sku: "ARR-001", algorithm: "adaptive_ma", confidence_label: "high", confidence_label_display: "Alta", days_to_stockout: 5, avg_daily: "8.500", current_stock: "42.000", category_name: "Granos" },
          ],
        }) };
    }
    if (url.includes("/catalog/categories/")) {
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
        json: async () => [] };
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

describe("ForecastPage", () => {
  it("renders page heading", async () => {
    render(<ForecastPage />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    });
  });

  it("shows product name after loading", async () => {
    render(<ForecastPage />);
    await waitFor(() => {
      expect(screen.getByText("Arroz Grado 1")).toBeInTheDocument();
    });
  });

  it("shows loading skeleton initially", async () => {
    mockFetch.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<ForecastPage />);
    await waitFor(() => {
      expect(container.querySelectorAll("div[style*='shimmer']").length).toBeGreaterThan(0);
    });
  });

  it("displays KPI section with urgent count", async () => {
    render(<ForecastPage />);
    await waitFor(() => {
      // imminent_3d=1 triggers the alert banner
      expect(screen.getByText(/se va a agotar/i)).toBeInTheDocument();
    });
  });

  it("shows SKU in product list", async () => {
    render(<ForecastPage />);
    await waitFor(() => {
      expect(screen.getByText("ARR-001")).toBeInTheDocument();
    });
  });
});
