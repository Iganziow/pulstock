/**
 * El peso chileno no tiene centavos.
 *
 * `formatCLP` no pasaba opciones a `toLocaleString`, que usa 3 decimales por
 * defecto. El dashboard mostraba el stock valorizado como "$5.096.714,232".
 *
 * El error sobrevivió tanto porque en es-CL el punto separa miles y la coma
 * separa decimales —al revés del inglés— así que "5.096.714,232" se parece
 * bastante a algo correcto. Hay que mirarlo dos veces para ver que dice
 * "cinco millones con 232 milésimas".
 */
import { describe, it, expect } from "vitest";
import { formatCLP } from "@/lib/format";

describe("formatCLP", () => {
  it("no muestra decimales", () => {
    // El caso real del dashboard: ,232 se descarta.
    expect(formatCLP("5096714.232")).toBe("5.096.714");
    // Y de la mitad para arriba redondea al peso siguiente.
    expect(formatCLP(1500.6)).toBe("1.501");
  });

  it("separa los miles con punto, como se escribe en Chile", () => {
    expect(formatCLP(1500)).toBe("1.500");
    expect(formatCLP(84110)).toBe("84.110");
  });

  it("funciona con montos chicos y con cero", () => {
    expect(formatCLP(0)).toBe("0");
    expect(formatCLP(640)).toBe("640");
  });

  it("acepta el string que llega del backend", () => {
    // Los DecimalField de Django serializan como "1500.000".
    expect(formatCLP("1500.000")).toBe("1.500");
  });

  it("no rompe con basura", () => {
    expect(formatCLP("no es un numero")).toBe("no es un numero");
  });
});
