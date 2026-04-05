import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/dashboard/pos",
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

const { default: PosPage } = await import(
  "@/app/(dashboard)/dashboard/pos/page"
);

const ME_DATA = {
  id: 1,
  email: "test@test.cl",
  active_store_id: 1,
  tenant_id: 1,
  role: "owner",
  default_warehouse_id: 1,
};

const WAREHOUSES_DATA = [
  { id: 1, name: "Bodega Principal", is_active: true, warehouse_type: "warehouse" },
];

function mockApiResponses() {
  mockFetch.mockImplementation(async (url: string) => {
    if (url.includes("/core/me/")) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ME_DATA,
      };
    }
    if (url.includes("/core/warehouses/")) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => WAREHOUSES_DATA,
      };
    }
    if (url.includes("/catalog/products/")) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ count: 0, results: [] }),
      };
    }
    if (url.includes("/promotions/")) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ count: 0, results: [] }),
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

describe("PosPage", () => {
  it("renders the POS page heading", async () => {
    render(<PosPage />);
    await waitFor(() => {
      expect(screen.getByText("Punto de Venta")).toBeInTheDocument();
    });
  });

  it("shows warehouse selector", async () => {
    render(<PosPage />);
    await waitFor(() => {
      expect(screen.getByText("Bodega Principal")).toBeInTheDocument();
    });
  });

  it("renders the Bodega Principal option in select", async () => {
    render(<PosPage />);
    await waitFor(() => {
      expect(screen.getByText("Bodega Principal (Bodega)")).toBeInTheDocument();
    });
  });

  it("renders the subtitle text", async () => {
    render(<PosPage />);
    await waitFor(() => {
      expect(screen.getByText(/Escanea, escribe SKU o busca por nombre/)).toBeInTheDocument();
    });
  });

  it("shows Vaciar button", async () => {
    render(<PosPage />);
    await waitFor(() => {
      expect(screen.getByText("Vaciar")).toBeInTheDocument();
    });
  });

  it("handles API error for /core/me/", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.includes("/core/me/")) {
        return {
          ok: false,
          status: 500,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Server error" }),
        };
      }
      if (url.includes("/core/warehouses/")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => WAREHOUSES_DATA,
        };
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({}),
      };
    });

    render(<PosPage />);
    await waitFor(() => {
      // When /core/me/ fails, a config error banner appears
      expect(screen.getByText(/Config:/)).toBeInTheDocument();
    });
  });

  it("renders the page with the heading level 1", async () => {
    render(<PosPage />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    });
  });

  it("shows keyboard shortcut hints on desktop", async () => {
    render(<PosPage />);
    await waitFor(() => {
      expect(screen.getByText("Enter")).toBeInTheDocument();
    });
  });
});
