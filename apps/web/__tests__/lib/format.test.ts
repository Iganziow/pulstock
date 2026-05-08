/**
 * Tests de extractErr — la función que convierte errores de API en
 * mensajes humanos para mostrar al usuario.
 *
 * Bug detectado el 08/05/26: la versión vieja hacía JSON.stringify(e.data)
 * y al usuario le aparecía algo como
 *   {"detail":"Algunos productos no existen o no están activos."}
 * en pantalla. Ahora extraemos el mensaje real.
 */
import { describe, it, expect } from "vitest";
import { extractErr, formatCLP } from "@/lib/format";

describe("extractErr — DRF error shapes", () => {
  it("string directo se devuelve tal cual", () => {
    expect(extractErr({ data: "Plain message" }, "fb")).toBe("Plain message");
  });

  it("{detail: 'X'} → 'X' (caso más común DRF)", () => {
    expect(
      extractErr({ data: { detail: "Algunos productos no existen o no están activos." } }, "fb"),
    ).toBe("Algunos productos no existen o no están activos.");
  });

  it("{detail: ['X', 'Y']} → 'X; Y'", () => {
    expect(
      extractErr({ data: { detail: ["Falta nombre", "Falta fecha"] } }, "fb"),
    ).toBe("Falta nombre; Falta fecha");
  });

  it("{non_field_errors: ['X']} → 'X' (sin nombre de campo)", () => {
    expect(
      extractErr({ data: { non_field_errors: ["Las fechas no son válidas"] } }, "fb"),
    ).toBe("Las fechas no son válidas");
  });

  it("{field: ['X']} → 'field: X' (con nombre de campo)", () => {
    expect(
      extractErr({ data: { discount_value: ["Debe ser mayor a 0"] } }, "fb"),
    ).toBe("discount_value: Debe ser mayor a 0");
  });

  it("múltiples campos se unen con ';'", () => {
    expect(
      extractErr(
        { data: { name: ["Es obligatorio"], end_date: ["Anterior a inicio"] } },
        "fb",
      ),
    ).toMatch(/name: Es obligatorio.*end_date: Anterior a inicio/);
  });

  it("array directo de strings → 'X; Y'", () => {
    expect(extractErr({ data: ["Err1", "Err2"] }, "fb")).toBe("Err1; Err2");
  });

  it("objeto anidado: {field: {nested: ['X']}}", () => {
    expect(
      extractErr({ data: { product: { name: ["Demasiado largo"] } } }, "fb"),
    ).toBe("product: name: Demasiado largo");
  });

  it("fallback cuando no hay data ni message", () => {
    expect(extractErr({}, "Mi fallback")).toBe("Mi fallback");
  });

  it("usa e.message si no hay e.data", () => {
    expect(extractErr({ message: "Network error" }, "fb")).toBe("Network error");
  });

  it("data null/undefined → fallback", () => {
    expect(extractErr({ data: null }, "fb")).toBe("fb");
    expect(extractErr({ data: undefined }, "fb")).toBe("fb");
  });

  it("REGRESION: NO devuelve JSON.stringify del payload", () => {
    const result = extractErr(
      { data: { detail: "Algunos productos no existen o no están activos." } },
      "fb",
    );
    // Antes: '{"detail":"..."}'  Ahora: 'Algunos productos...'
    expect(result).not.toContain('"detail"');
    expect(result).not.toContain("{");
    expect(result).not.toContain("}");
  });
});

describe("formatCLP", () => {
  it("formatea numero como CLP con punto separador", () => {
    expect(formatCLP(1500)).toBe("1.500");
    expect(formatCLP(1500000)).toBe("1.500.000");
  });

  it("acepta string", () => {
    expect(formatCLP("3000")).toBe("3.000");
  });

  it("NaN devuelve el valor original como string", () => {
    expect(formatCLP("abc")).toBe("abc");
  });
});
