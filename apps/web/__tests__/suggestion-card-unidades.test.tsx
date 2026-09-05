/**
 * SuggestionCard — la cantidad en la unidad del producto.
 *
 * El 04/09/26 la tarjeta decía "453 u." para Chocolate Premium: eran gramos.
 * También redondeaba cualquier número con punto del texto del backend, así
 * que "1.234 unidades" (punto de miles) se convertía en "1 unidades".
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn(), apiUpload: vi.fn() }));

const { SuggestionCard } = await import("@/components/forecast/SuggestionCard");

function sugerencia() {
  return {
    id: 178, warehouse_id: 1, supplier_name: "", status: "PENDING", priority: "CRITICAL",
    total_estimated: "85700", generated_at: "2026-09-04T04:30:00Z", approved_at: null,
    purchase_id: null, lines_count: 2,
    lines: [
      {
        product_id: 1, product_name: "Chocolate Premium", unit: "GR",
        current_stock: "560", avg_daily_demand: "43", days_to_stockout: 8,
        suggested_qty: "453", estimated_cost: "22650",
        reasoning: "Te quedan 560 g y vendes cerca de 43 g al día.",
      },
      {
        product_id: 2, product_name: "Vasos", unit: "UN",
        current_stock: "0", avg_daily_demand: "40", days_to_stockout: 0,
        suggested_qty: "1234", estimated_cost: "12340",
        reasoning: "Con 1.234 unidades te alcanza para unas 4 semanas.",
      },
    ],
  };
}

describe("SuggestionCard habla en la unidad del producto", () => {
  it("gramos se muestran como gramos, no como 'u.'", () => {
    render(<SuggestionCard s={sugerencia()} expanded mob={false} acting={null} onToggle={() => {}} onConfirmAction={() => {}} />);
    expect(screen.getByText(/¿Por qué pedir 453 g\?/)).toBeTruthy();
    expect(screen.getAllByText(/560 g/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/453 u\./)).toBeNull();
  });

  it("los miles del texto del backend no se redondean a 1", () => {
    render(<SuggestionCard s={sugerencia()} expanded mob={false} acting={null} onToggle={() => {}} onConfirmAction={() => {}} />);
    expect(screen.getByText(/1\.234 unidades te alcanza/)).toBeTruthy();
    expect(screen.queryByText(/Con 1 unidades/)).toBeNull();
  });

  it("no suma unidades de productos distintos en la cabecera", () => {
    render(<SuggestionCard s={sugerencia()} expanded={false} mob={false} acting={null} onToggle={() => {}} onConfirmAction={() => {}} />);
    expect(screen.queryByText(/^Unidades$/)).toBeNull();
    expect(screen.getByText(/Productos/)).toBeTruthy();
  });
});
