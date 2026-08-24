/**
 * El umbral de "stock bajo" en pantalla.
 *
 * Estaba fijo en 5 unidades para todo el catálogo. Para la leche —que se
 * consume por litros al día— 5 no es "bajo", es un quiebre en curso; para un
 * syrup que sale una vez por semana, 5 son casi dos meses de stock y la franja
 * ámbar aparece sin motivo.
 *
 * Es el mismo defecto que se arregló en el correo de alertas, pero acá se ve
 * en pantalla, que es donde Mario lo mira todos los días.
 */
import { describe, it, expect } from "vitest";
import { bajoMinimo, minimoEfectivo, type StockRow } from "@/components/inventory/StockShared";

function fila(extra: Partial<StockRow> = {}): StockRow {
  return {
    product_id: 1, sku: "X", name: "Producto", category: null, barcode: null,
    on_hand: "10", ...extra,
  };
}

describe("cuál mínimo manda", () => {
  it("el que definió el dueño le gana al calculado", () => {
    // Sabe algo que el historial no dice: viene un evento, cambió el proveedor.
    const r = fila({ min_stock: "20", min_stock_auto: "3" });
    expect(minimoEfectivo(r)).toBe(20);
  });

  it("sin mínimo manual usa el calculado", () => {
    expect(minimoEfectivo(fila({ min_stock: "0", min_stock_auto: "3.5" }))).toBe(3.5);
  });

  it("sin ninguno de los dos devuelve null, no cero", () => {
    // Cero se leería como "el mínimo es cero"; null dice "no hay", que es
    // distinto y es la verdad.
    expect(minimoEfectivo(fila())).toBeNull();
    expect(minimoEfectivo(fila({ min_stock_auto: null }))).toBeNull();
  });
});

describe("cuándo se marca stock bajo", () => {
  it("no marca a un producto de alta rotación que está sobre su mínimo", () => {
    // Leche: 4 unidades con el umbral viejo era "bajo"; su mínimo real es 3.
    expect(bajoMinimo(fila({ on_hand: "4", min_stock_auto: "3" }))).toBe(false);
  });

  it("marca a un producto de baja rotación que el umbral plano ignoraba", () => {
    // Syrup: 4 unidades pasaba el filtro de ≤5 por poco y no se avisaba,
    // aunque su mínimo real es 8.
    expect(bajoMinimo(fila({ on_hand: "6", min_stock_auto: "8" }))).toBe(true);
  });

  it("sin mínimo se cae al umbral plano en vez de dejar de marcar", () => {
    // Un producto nuevo todavía no tiene mínimo calculado. Peor que marcar de
    // más es quedarse mudo.
    expect(bajoMinimo(fila({ on_hand: "3" }))).toBe(true);
    expect(bajoMinimo(fila({ on_hand: "50" }))).toBe(false);
  });

  it("un producto en cero no es 'bajo': es 'sin stock'", () => {
    // Son dos estados distintos y la fila los pinta distinto (rojo vs ámbar).
    expect(bajoMinimo(fila({ on_hand: "0", min_stock_auto: "3" }))).toBe(false);
  });

  it("justo en el mínimo ya cuenta como bajo", () => {
    expect(bajoMinimo(fila({ on_hand: "3", min_stock_auto: "3" }))).toBe(true);
  });
});
