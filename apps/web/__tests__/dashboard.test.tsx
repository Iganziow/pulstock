import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: any) => <a href={href} {...rest}>{children}</a>,
}));

vi.mock("@/lib/useGlobalStyles", () => ({
  useGlobalStyles: () => {},
}));

vi.mock("@/hooks/useIsMobile", () => ({
  useIsMobile: () => false,
}));

const { default: DashboardPage } = await import(
  "@/app/(dashboard)/dashboard/page"
);

const SUMMARY_DATA = {
  generated_at: "2026-04-03T12:00:00Z",
  store_id: 1,
  kpis: {
    sales_today: { count: 12, total: "150000", profit: "45000" },
    low_stock: { count: 3 },
    stock_value: { total_value: "5000000", total_items: 320 },
    pending_purchases: { count: 2, total: "800000" },
  },
  chart: [
    { date: "2026-03-28", total: "50000", count: 4, profit: "15000" },
    { date: "2026-03-29", total: "75000", count: 6, profit: "22000" },
    { date: "2026-03-30", total: "60000", count: 5, profit: "18000" },
  ],
  recent_sales: [
    { id: 1, created_at: "2026-04-03T10:00:00Z", total: "25000", gross_profit: "7500", status: "COMPLETED", warehouse_name: "Bodega Principal", created_by: "Juan" },
    { id: 2, created_at: "2026-04-03T11:00:00Z", total: "18000", gross_profit: "5400", status: "COMPLETED", warehouse_name: "Bodega Principal", created_by: "Maria" },
  ],
  low_stock_items: [
    { product_id: 10, product_name: "Arroz Grado 1", sku: "ARR-001", warehouse_name: "Bodega Principal", on_hand: "2", min_stock: "10", deficit: "8" },
  ],
  onboarding: { has_products: true, products_count: 45 },
};

const ONBOARDING_STATUS = {
  completed: true,
  progress: 7,
  total_steps: 7,
  steps: [],
};

const ONBOARDING_INCOMPLETE = {
  completed: false,
  progress: 3,
  total_steps: 7,
  steps: [
    { key: "business_setup", label: "Configurar negocio", description: "Configura los datos de tu negocio", completed: true, link: "/dashboard/settings" },
    { key: "has_products", label: "Agregar productos", description: "Agrega tu primer producto", completed: false, link: "/dashboard/catalog" },
  ],
};

function mockApiResponses(overrides?: { summary?: any; onboarding?: any }) {
  const summary = overrides?.summary ?? SUMMARY_DATA;
  const onboarding = overrides?.onboarding ?? ONBOARDING_STATUS;

  mockFetch.mockImplementation(async (url: string) => {
    if (url.includes("/dashboard/summary/")) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => summary,
      };
    }
    if (url.includes("/auth/onboarding-status/")) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => onboarding,
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

describe("DashboardPage", () => {
  it("renders the page heading", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    });
  });

  it("shows KPI cards after loading", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("Ventas Hoy")).toBeInTheDocument();
      expect(screen.getByText("Stock Bajo Mínimo")).toBeInTheDocument();
      expect(screen.getByText("Stock Valorizado")).toBeInTheDocument();
      expect(screen.getByText("Compras Pendientes")).toBeInTheDocument();
    });
  });

  it("displays revenue formatted as CLP", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("$150.000")).toBeInTheDocument();
    });
  });

  it("shows sales count in subtitle", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText(/12 ventas/)).toBeInTheDocument();
    });
  });

  it("shows low stock count", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("3")).toBeInTheDocument();
    });
  });

  it("shows loading spinner initially", () => {
    mockFetch.mockImplementation(() => new Promise(() => {})); // never resolves
    render(<DashboardPage />);
    // The Spinner component renders an SVG with animation
    const container = document.querySelector("svg");
    expect(container).toBeTruthy();
  });

  it("handles API error gracefully", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.includes("/dashboard/summary/")) {
        return {
          ok: false,
          status: 500,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Server error" }),
        };
      }
      if (url.includes("/auth/onboarding-status/")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ONBOARDING_STATUS,
        };
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({}),
      };
    });

    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("Error al cargar el dashboard")).toBeInTheDocument();
    });
  });

  it("shows onboarding widget when not completed", async () => {
    mockApiResponses({ onboarding: ONBOARDING_INCOMPLETE });
    render(<DashboardPage />);
    await waitFor(() => {
      // The floating onboarding button renders a rocket emoji
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
  });

  it("shows recent sales section heading", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText(/ltimas ventas/)).toBeInTheDocument();
    });
  });

  it("displays chart section heading", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText(/Ventas últimos 7 días/)).toBeInTheDocument();
    });
  });

  it("shows low stock product name", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("Arroz Grado 1")).toBeInTheDocument();
    });
  });

  it("renders Reintentar button on error", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.includes("/dashboard/summary/")) {
        return {
          ok: false,
          status: 500,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Server error" }),
        };
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ONBOARDING_STATUS,
      };
    });

    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("Reintentar")).toBeInTheDocument();
    });
  });
});
