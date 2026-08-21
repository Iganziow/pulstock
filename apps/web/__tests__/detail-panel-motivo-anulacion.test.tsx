/**
 * DetailPanel — el motivo de anulación (B3) en la ficha de la venta.
 *
 * El frontend exigía el motivo desde siempre y el backend lo tiraba: una venta
 * anulada no decía por qué. Ahora se guarda, pero de nada sirve si la ficha no
 * lo muestra — sin este test el único respaldo del arreglo era el typecheck.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn(), apiUpload: vi.fn() }));
vi.mock("@/lib/me", () => ({ fetchMe: vi.fn().mockResolvedValue({ role: "owner" }) }));

const { apiFetch } = await import("@/lib/api");
const { DetailPanel } = await import("@/components/sales/DetailPanel");

function venta(extra: Record<string, unknown> = {}) {
  return {
    id: 300, sale_number: 300, status: "VOID", sale_type: "VENTA",
    created_at: "2026-08-19T14:00:00Z",
    subtotal: "10000", total: "10000", total_cost: "4000", gross_profit: "6000",
    lines: [], payments: [], tips: [],
    warehouse: 1, warehouse_name: "Bodega Principal",
    created_by_name: "Mario", waiter: null, waiter_name: null,
    void_reason: "",
    ...extra,
  };
}

function montar(sale: Record<string, unknown>) {
  (apiFetch as any).mockResolvedValue(sale);
  render(
    <DetailPanel saleId={300} onClose={vi.fn()} onVoided={vi.fn()} warehouses={[]} />,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("DetailPanel — motivo de anulación (B3)", () => {
  it("muestra el motivo cuando la venta fue anulada con uno", async () => {
    montar(venta({ void_reason: "cliente se arrepintio" }));

    expect(await screen.findByText(/venta anulada/i)).toBeTruthy();
    expect(screen.getByText(/cliente se arrepintio/i)).toBeTruthy();
  });

  it("no inventa un motivo vacío si la anulación no lo trae", async () => {
    // Integraciones viejas anulan sin motivo; no debe aparecer "Motivo:" solo.
    montar(venta({ void_reason: "" }));

    expect(await screen.findByText(/venta anulada/i)).toBeTruthy();
    expect(screen.queryByText(/motivo:/i)).toBeNull();
  });

  it("una venta normal no muestra ni el aviso ni el motivo", async () => {
    montar(venta({ status: "COMPLETED", void_reason: "" }));

    expect(await screen.findByText(/total de la venta/i)).toBeTruthy();
    expect(screen.queryByText(/venta anulada/i)).toBeNull();
  });
});
