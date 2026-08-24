/**
 * El margen no puede inventarse cuando falta el costo.
 *
 * La Lista de Precios mostraba "100,0%" en verde para todo producto con costo
 * $0. En Marbrava son **141 de 242 productos activos**: más de la mitad del
 * catálogo aparecía con el margen perfecto.
 *
 * Un costo en cero casi nunca significa "me sale gratis" — significa que nadie
 * lo cargó. Y el resultado era que el dato menos confiable se mostraba de la
 * forma más tranquilizadora posible, justo en la pantalla donde se deciden los
 * precios.
 *
 * Un guion es información. "100%" es una mentira que se ve bien.
 */
import { describe, it, expect } from "vitest";
import { calcMargin, sinCosto } from "@/components/prices/helpers";

describe("cuándo hay margen que mostrar", () => {
  it("lo calcula bien cuando hay costo y precio", () => {
    // Americano: costo $400, precio $2.800 → 85,7%
    expect(calcMargin("400", "2800")).toBeCloseTo(85.71, 1);
  });

  it("NO inventa 100% cuando falta el costo", () => {
    // EL BUG. Agua Puyehue mostraba 100,0% en verde con costo sin cargar.
    expect(calcMargin("0", "1500")).toBeNull();
  });

  it("tampoco con precio en cero", () => {
    expect(calcMargin("500", "0")).toBeNull();
  });

  it("muestra el margen negativo, que es el que más importa ver", () => {
    // Vender bajo el costo tiene que saltar a la vista, no esconderse.
    expect(calcMargin("1615", "1500")).toBeLessThan(0);
  });

  it("no se rompe con datos basura", () => {
    expect(calcMargin("abc", "1500")).toBeNull();
    expect(calcMargin("", "")).toBeNull();
  });
});

describe("detectar el costo faltante", () => {
  it("reconoce el cero y el vacío", () => {
    expect(sinCosto("0")).toBe(true);
    expect(sinCosto("")).toBe(true);
    expect(sinCosto("abc")).toBe(true);
  });

  it("un costo real no cuenta como faltante", () => {
    expect(sinCosto("400")).toBe(false);
    expect(sinCosto("0.5")).toBe(false);
  });
});
