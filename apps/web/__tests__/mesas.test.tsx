import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

let mockPathname = "/dashboard/mesas";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => mockPathname,
  useSearchParams: () => new URLSearchParams(),
}));

const { default: MesasPage } = await import(
  "@/app/(dashboard)/dashboard/mesas/page"
);

const ME_RESPONSE = { id: 1, email: "t@t.cl", role: "owner", active_store_id: 1 };

const TABLES_RESPONSE = [
  { id: 1, name: "Mesa 1", capacity: 4, status: "FREE", zone: "salon", is_active: true, is_counter: false, active_order: null, position_x: 20, position_y: 30, shape: "square", width: 8, height: 8, rotation: 0 },
  { id: 2, name: "Mesa 2", capacity: 2, status: "OPEN", zone: "salon", is_active: true, is_counter: false, active_order: { id: 10, opened_at: "2026-04-03T10:00:00Z", items_count: 2, subtotal: "5000", customer_name: "" }, position_x: 50, position_y: 30, shape: "round", width: 8, height: 8, rotation: 0 },
];

function setupMocks(tables = TABLES_RESPONSE) {
  mockFetch.mockImplementation(async (url: string) => {
    let json: unknown = [];
    if (url.includes("/core/me/")) json = ME_RESPONSE;
    else if (url.match(/\/tables\/tables\/\d+\/order\//)) json = { id: 10, lines: [], subtotal: "5000", opened_at: "2026-04-03T10:00:00Z", payments: [] };
    else if (url.includes("/tables/tables/")) json = tables;
    return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }), json: async () => json };
  });
}

beforeEach(() => {
  mockFetch.mockReset();
  localStorage.clear();
  localStorage.setItem("access", "fake-token");
  setupMocks();
});

describe("MesasPage", () => {
  it("renders the page heading", async () => {
    render(<MesasPage />);
    await waitFor(() => {
      expect(screen.getByText("Mesas")).toBeInTheDocument();
    });
  });

  it("shows occupied and free counts", async () => {
    render(<MesasPage />);
    await waitFor(() => {
      expect(screen.getByText(/ocupada/i)).toBeInTheDocument();
      expect(screen.getByText(/libre/i)).toBeInTheDocument();
    });
  });

  it("renders loading spinner initially", async () => {
    mockFetch.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<MesasPage />);
    await waitFor(() => {
      expect(container.querySelector("svg")).toBeInTheDocument();
    });
  });

  it("shows empty state when no tables", async () => {
    setupMocks([]);
    render(<MesasPage />);
    await waitFor(() => {
      expect(screen.getByText("Sin mesas configuradas")).toBeInTheDocument();
    });
  });

  it("shows Config button", async () => {
    render(<MesasPage />);
    await waitFor(() => {
      expect(screen.getByText("Config")).toBeInTheDocument();
    });
  });

  it("renders table names after loading", async () => {
    render(<MesasPage />);
    await waitFor(() => {
      expect(screen.getByText("Mesa 1")).toBeInTheDocument();
    });
  });
});
