import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// Mock fetch
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Track pathname for isActive testing
let mockPathname = "/dashboard";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => mockPathname,
  useSearchParams: () => new URLSearchParams(),
}));

const { default: Sidebar } = await import("@/components/Sidebar");

beforeEach(() => {
  mockFetch.mockReset();
  localStorage.clear();
  mockPathname = "/dashboard";

  // Default: handle both /core/me/ and /dashboard/summary/
  mockFetch.mockImplementation(async (url: string) => {
    if (url.includes("/dashboard/summary/")) {
      return {
        ok: true, status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ kpis: { low_stock: { count: 3 } } }),
      };
    }
    return {
      ok: true, status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        permissions: {
          catalog: true, catalog_write: true, pos: true, sales: true,
          caja: true, purchases: true, inventory: true, inventory_write: true,
          forecast: true, reports: true,
        },
        email: "test@test.cl",
        role_label: "Dueño",
      }),
    };
  });
  localStorage.setItem("access", "fake-token");
});

describe("Sidebar", () => {
  it("renders dashboard link", async () => {
    render(<Sidebar />);
    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
  });

  it("renders Catálogo and Recetas items", async () => {
    render(<Sidebar />);
    await waitFor(() => {
      expect(screen.getByText("Catálogo")).toBeInTheDocument();
      expect(screen.getByText("Recetas")).toBeInTheDocument();
    });
  });

  it("renders nav items for all permitted sections", async () => {
    render(<Sidebar />);
    await waitFor(() => {
      // Verify key items from different sections exist
      expect(screen.getByText("Catálogo")).toBeInTheDocument();
      expect(screen.getByText("Punto de Venta")).toBeInTheDocument();
      expect(screen.getByText("Stock")).toBeInTheDocument();
      expect(screen.getByText("Reportes")).toBeInTheDocument();
    });
  });

  it("hides items when permission is false", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.includes("/dashboard/summary/")) {
        return {
          ok: true, status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ kpis: { low_stock: { count: 0 } } }),
        };
      }
      return {
        ok: true, status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          permissions: {
            catalog: false, catalog_write: false, pos: true, sales: true,
            caja: true, purchases: true, inventory: true, inventory_write: true,
            forecast: false, reports: false,
          },
          email: "cashier@test.cl",
          role_label: "Cajero",
        }),
      };
    });

    render(<Sidebar />);
    await waitFor(() => {
      expect(screen.getByText("Punto de Venta")).toBeInTheDocument();
    });
    // Catálogo should be hidden
    expect(screen.queryByText("Catálogo")).not.toBeInTheDocument();
    expect(screen.queryByText("Recetas")).not.toBeInTheDocument();
    expect(screen.queryByText("Predicción")).not.toBeInTheDocument();
  });
});
