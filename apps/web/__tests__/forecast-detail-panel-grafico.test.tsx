/**
 * ForecastDetailPanel — el gráfico dice lo esencial y en la unidad correcta.
 *
 * Rediseño del 05/09/26. El gráfico anterior dibujaba cinco líneas, una
 * banda y tres marcadores con etiquetas de 9px, y el stock era una línea
 * roja punteada cruzando las de venta con un badge "SE ACABA" encima. Ahora:
 * resumen por semana en palabras, ventas + predicción + banda + "Hoy", y una
 * barra de stock con la fecha en que se acaba.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn(), apiUpload: vi.fn() }));

const { ForecastDetailPanel } = await import("@/components/forecast/ForecastDetailPanel");

function iso(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function detalle() {
  return {
    product: { id: 5, name: "Chocolate Premium", sku: "CHOC", category: "Insumos", unit_code: "GR", unit_family: "mass" },
    stock: { on_hand: "560", avg_cost: "50" },
    model: { algorithm: "theta", metrics: {}, data_points: 30, params: {} },
    suggestion: null,
    history: Array.from({ length: 14 }, (_, i) => ({ date: iso(i - 14), qty_sold: "40", revenue: "2000" })),
    forecast: Array.from({ length: 14 }, (_, i) => ({
      date: iso(i + 1), qty_predicted: "45", lower_bound: "30", upper_bound: "60", days_to_stockout: 12,
    })),
  };
}

describe("ForecastDetailPanel, gráfico rediseñado", () => {
  it("resume la semana en palabras y en la unidad del producto", () => {
    render(<ForecastDetailPanel detail={detalle()} loading={false} mob={false} />);
    expect(screen.getByText(/Últimos 7 días/)).toBeTruthy();
    expect(screen.getByText("280 g")).toBeTruthy();          // 7 × 40
    expect(screen.getByText(/Próximos 7 días/)).toBeTruthy();
    expect(screen.getByText("315 g")).toBeTruthy();          // 7 × 45
    expect(screen.getByText("+13%")).toBeTruthy();           // (315-280)/280
  });

  it("el stock es una barra con la fecha en que se acaba, no una línea sobre el gráfico", () => {
    render(<ForecastDetailPanel detail={detalle()} loading={false} mob={false} />);
    expect(screen.getByText(/Alcanza hasta el .* \(12 días\)/)).toBeTruthy();
    expect(screen.queryByText("SE ACABA")).toBeNull();
    expect(screen.queryByText("REPONER PRONTO")).toBeNull();
    expect(screen.queryByText("Stock disponible")).toBeNull();
  });

  it("sin etiquetas Pasado/Futuro, sin pico, sin emojis", () => {
    const { container } = render(<ForecastDetailPanel detail={detalle()} loading={false} mob={false} />);
    expect(screen.queryByText("Pasado")).toBeNull();
    expect(screen.queryByText("Futuro")).toBeNull();
    expect(container.textContent).not.toMatch(/★|📈|⏰|👁|⏳/);
    expect(screen.getByText("Cuánto vendes y cuánto vas a vender")).toBeTruthy();
  });

  it("sin stock y sin quiebre calculado no dibuja la barra", () => {
    const d = detalle();
    d.stock = { on_hand: "0", avg_cost: "0" };
    d.forecast = d.forecast.map(f => ({ ...f, days_to_stockout: null }));
    render(<ForecastDetailPanel detail={d} loading={false} mob={false} />);
    expect(screen.queryByText(/Alcanza hasta el/)).toBeNull();
  });
});
