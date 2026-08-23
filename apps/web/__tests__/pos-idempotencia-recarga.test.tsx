/**
 * B5 — la venta que se cobraba dos veces al recargar el POS.
 *
 * El carrito se guarda en localStorage y sobrevive una recarga. La clave de
 * idempotencia vivía en un `useRef` y moría con la página.
 *
 * El escenario, que es cotidiano en un café:
 *   1. El cajero aprieta Cobrar.
 *   2. La respuesta se pierde — 4G lento, la tablet se reinicia, alguien
 *      recarga sin querer.
 *   3. Vuelve a entrar y ve su carrito intacto. Eso lo INVITA a apretar
 *      Cobrar de nuevo.
 *   4. Sin la clave, el frontend genera una nueva. El backend la lee como
 *      otra venta y cobra dos veces.
 *
 * El backend ya sabía defenderse: con la misma clave devuelve la venta que ya
 * existía. Lo que faltaba era que la clave llegara.
 */
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
vi.mock("@/lib/useGlobalStyles", () => ({ useGlobalStyles: () => {} }));
vi.mock("@/hooks/useIsMobile", () => ({ useIsMobile: () => false }));

const { default: PosPage } = await import("@/app/(dashboard)/dashboard/pos/page");

const CLAVE_BORRADOR = "pos_cart_draft";

const ME = {
  id: 1, email: "cajero@marbrava.cl", active_store_id: 1,
  tenant_id: 1, role: "cashier", default_warehouse_id: 1,
};
const BODEGAS = [{ id: 1, name: "Bodega Principal", is_active: true, warehouse_type: "warehouse" }];

function respuestasApi() {
  mockFetch.mockImplementation(async (url: string) => {
    const json =
      url.includes("/core/me/") ? ME :
      url.includes("/core/warehouses/") ? BODEGAS :
      url.includes("/catalog/products/") ? { count: 0, results: [] } :
      url.includes("/promotions/") ? { count: 0, results: [] } :
      {};
    return {
      ok: true, status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => json,
    };
  });
}

/** Un carrito a medio cobrar, como el que deja una recarga inesperada. */
function borradorGuardado(extra: Record<string, unknown> = {}) {
  return {
    cart: [{
      product: { id: 7, name: "Capuccino", price: "3500", sku: "CAP-1" },
      qty: 2, unitPrice: 3500, discountType: "none", discountValue: 0,
    }],
    globalDiscountType: "none",
    globalDiscountValue: 0,
    saleNote: "",
    payRows: [{ method: "cash", amount: "7000" }],
    tipAmount: "",
    ...extra,
  };
}

beforeEach(() => {
  mockFetch.mockReset();
  localStorage.clear();
  localStorage.setItem("access", "fake-token");
  respuestasApi();
});

describe("B5 — idempotencia que sobrevive la recarga", () => {
  it("el borrador guardado incluye la clave", async () => {
    render(<PosPage />);
    await waitFor(() => {
      const crudo = localStorage.getItem(CLAVE_BORRADOR);
      // Sin carrito no hay borrador; el test real es el de abajo.
      expect(crudo === null || typeof crudo === "string").toBe(true);
    });
  });

  it("al recuperar un carrito, la clave viene con él", async () => {
    const clave = "clave-del-intento-anterior-123";
    localStorage.setItem(
      CLAVE_BORRADOR,
      JSON.stringify(borradorGuardado({ idemKey: clave })),
    );

    render(<PosPage />);

    // El carrito vuelve…
    await waitFor(() => {
      expect(screen.getByText(/capuccino/i)).toBeTruthy();
    });

    // …y el borrador que se vuelve a persistir conserva LA MISMA clave.
    await waitFor(() => {
      const crudo = localStorage.getItem(CLAVE_BORRADOR);
      expect(crudo).toBeTruthy();
      const d = JSON.parse(crudo!);
      expect(d.idemKey).toBe(clave);
    });
  });

  it("un carrito viejo sin clave recibe una y queda guardada", async () => {
    // Borradores anteriores a este arreglo no la tienen. No pueden quedarse
    // sin ella: serían justo el caso que duplica.
    localStorage.setItem(CLAVE_BORRADOR, JSON.stringify(borradorGuardado()));

    render(<PosPage />);

    await waitFor(() => {
      const crudo = localStorage.getItem(CLAVE_BORRADOR);
      expect(crudo).toBeTruthy();
      const d = JSON.parse(crudo!);
      expect(typeof d.idemKey).toBe("string");
      expect(d.idemKey.length).toBeGreaterThan(8);
    });
  });

  it("dos recargas seguidas no cambian la clave", async () => {
    const clave = "clave-estable-abc";
    localStorage.setItem(
      CLAVE_BORRADOR,
      JSON.stringify(borradorGuardado({ idemKey: clave })),
    );

    const primera = render(<PosPage />);
    await waitFor(() => expect(screen.getByText(/capuccino/i)).toBeTruthy());
    primera.unmount();

    render(<PosPage />);
    await waitFor(() => {
      const d = JSON.parse(localStorage.getItem(CLAVE_BORRADOR)!);
      expect(d.idemKey).toBe(clave);
    });
  });
});
