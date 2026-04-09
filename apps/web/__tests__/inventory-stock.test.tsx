import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/dashboard/inventory/stock",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/useGlobalStyles", () => ({
  useGlobalStyles: () => {},
}));

const { default: StockPage } = await import(
  "@/app/(dashboard)/dashboard/inventory/stock/page"
);

const ME_RESPONSE = {
  id: 1,
  email: "t@t.cl",
  active_store_id: 1,
  tenant_id: 1,
  default_warehouse_id: 1,
};

const WAREHOUSES_RESPONSE = [
  { id: 1, name: "Bodega Principal", is_active: true, warehouse_type: "warehouse" },
];

const STOCK_RESPONSE = {
  count: 2,
  results: [
    {
      id: 1,
      product_id: 1,
      name: "Arroz",
      sku: "ARR-001",
      category: "Granos",
      barcode: null,
      on_hand: "50.000",
      avg_cost: "800.000",
      stock_value: "40000.000",
    },
    {
      id: 2,
      product_id: 2,
      name: "Aceite",
      sku: "ACE-002",
      category: "Aceites",
      barcode: null,
      on_hand: "0.000",
      avg_cost: "1500.000",
      stock_value: "0.000",
    },
  ],
};

function mockApiResponses() {
  mockFetch.mockImplementation(async (url: string) => {
    if (url.includes("/core/me/")) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ME_RESPONSE,
      };
    }
    if (url.includes("/core/warehouses/")) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => WAREHOUSES_RESPONSE,
      };
    }
    if (url.includes("/inventory/stock/")) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => STOCK_RESPONSE,
      };
    }
    return {
      ok: true,
      status: 200,
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

describe("StockPage", () => {
  it("renders stock page heading", async () => {
    render(<StockPage />);
    await waitFor(() => {
      expect(screen.getByText("Stock actual")).toBeInTheDocument();
    });
  });

  it("shows warehouse name badge", async () => {
    render(<StockPage />);
    await waitFor(() => {
      expect(screen.getByText("Bodega Principal")).toBeInTheDocument();
    });
  });

  it("displays product names after loading", async () => {
    render(<StockPage />);
    await waitFor(() => {
      expect(screen.getByText("Arroz")).toBeInTheDocument();
      expect(screen.getByText("Aceite")).toBeInTheDocument();
    });
  });

  it("shows product SKU codes", async () => {
    render(<StockPage />);
    await waitFor(() => {
      expect(screen.getByText("ARR-001")).toBeInTheDocument();
      expect(screen.getByText("ACE-002")).toBeInTheDocument();
    });
  });

  it("shows zero stock indicator for out-of-stock items", async () => {
    render(<StockPage />);
    await waitFor(() => {
      expect(screen.getByText("Sin stock")).toBeInTheDocument();
    });
  });

  it("renders search input", async () => {
    render(<StockPage />);
    await waitFor(() => {
      expect(
        screen.getByPlaceholderText(/buscar por nombre o sku/i)
      ).toBeInTheDocument();
    });
  });

  it("shows loading skeleton initially", () => {
    const { container } = render(<StockPage />);
    const skeletons = container.querySelectorAll("div[style*='shimmer']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders stat cards with metrics", async () => {
    render(<StockPage />);
    await waitFor(() => {
      expect(screen.getByText("Productos")).toBeInTheDocument();
      expect(screen.getByText("Sin stock")).toBeInTheDocument();
      expect(screen.getByText("Stock bajo")).toBeInTheDocument();
    });
  });

  it("renders action buttons for each product row", async () => {
    render(<StockPage />);
    await waitFor(() => {
      const recButtons = screen.getAllByText("Recibir");
      expect(recButtons.length).toBeGreaterThanOrEqual(2);
      const issButtons = screen.getAllByText("Egresar");
      expect(issButtons.length).toBeGreaterThanOrEqual(2);
    });
  });
});
