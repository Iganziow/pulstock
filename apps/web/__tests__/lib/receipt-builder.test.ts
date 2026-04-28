/**
 * Tests para los builders de tickets:
 *   - buildComanda / buildComandaHTML  (NUEVO — kitchen ticket por estación)
 *   - buildPreCuenta / buildPreCuentaHTML (con propina sugerida 10%)
 *
 * Como ESC/POS son bytes binarios, validamos que:
 *   - el output sea un Uint8Array no vacío
 *   - contenga (decoded como string) las palabras esperadas
 *   - HTML contenga los strings esperados sin XSS
 */
import { describe, it, expect } from "vitest";
import {
  buildComanda,
  buildComandaHTML,
  buildPreCuenta,
  buildPreCuentaHTML,
  type ComandaData,
  type PreCuentaData,
} from "@/lib/receipt-builder";

function decode(bytes: Uint8Array): string {
  // Decodificamos como ASCII — los printables se ven, los control bytes
  // (ESC/POS commands) se vuelven caracteres no imprimibles que igual no
  // afectan los includes() de palabras conocidas.
  return Array.from(bytes).map(b => b >= 32 && b < 127 ? String.fromCharCode(b) : "").join("");
}

describe("buildComanda (ESC/POS)", () => {
  const baseData: ComandaData = {
    reference: "Mesa 5",
    stationName: "Cocina",
    lines: [
      { name: "Hamburguesa", qty: 2, total: 12000 },
      { name: "Papas fritas", qty: 1, total: 3000 },
    ],
    attendedBy: "Juan",
    date: new Date("2025-01-01T14:30:00"),
  };

  it("returns non-empty Uint8Array", () => {
    const result = buildComanda(baseData);
    expect(result).toBeInstanceOf(Uint8Array);
    expect(result.length).toBeGreaterThan(0);
  });

  it("includes station name as header", () => {
    const result = buildComanda(baseData);
    expect(decode(result)).toContain("COCINA"); // uppercase
  });

  it("includes table reference", () => {
    const result = buildComanda(baseData);
    expect(decode(result)).toContain("Mesa 5");
  });

  it("includes all line product names with quantity", () => {
    const result = buildComanda(baseData);
    const text = decode(result);
    expect(text).toContain("2x Hamburguesa");
    expect(text).toContain("1x Papas fritas");
  });

  it("does NOT include prices (kitchen ticket should be price-free)", () => {
    const result = buildComanda(baseData);
    const text = decode(result);
    expect(text).not.toContain("12000");
    expect(text).not.toContain("3000");
  });

  it("includes attended-by", () => {
    const result = buildComanda(baseData);
    expect(decode(result)).toContain("Juan");
  });

  it("includes note when provided", () => {
    const data = { ...baseData, note: "Sin cebolla" };
    const result = buildComanda(data);
    const text = decode(result);
    expect(text).toContain("NOTA");
    expect(text).toContain("Sin cebolla");
  });

  it("uses 'COMANDA' as fallback when stationName is missing", () => {
    const data = { ...baseData, stationName: undefined };
    const result = buildComanda(data);
    expect(decode(result)).toContain("COMANDA");
  });

  it("works for 58mm paper width", () => {
    const result = buildComanda(baseData, 58);
    expect(result).toBeInstanceOf(Uint8Array);
    expect(result.length).toBeGreaterThan(0);
  });
});

describe("buildComandaHTML", () => {
  const baseData: ComandaData = {
    reference: "Mesa 7",
    stationName: "Bar",
    lines: [{ name: "Cerveza", qty: 3, total: 9000 }],
    date: new Date(),
  };

  it("returns HTML string with station name uppercased", () => {
    const html = buildComandaHTML(baseData);
    expect(typeof html).toBe("string");
    expect(html).toContain("BAR");
  });

  it("includes line items with quantity prefix", () => {
    const html = buildComandaHTML(baseData);
    expect(html).toContain("3x Cerveza");
  });

  it("does NOT include prices", () => {
    const html = buildComandaHTML(baseData);
    expect(html).not.toContain("9000");
  });

  it("escapes HTML special chars in product names", () => {
    const data = {
      ...baseData,
      lines: [{ name: "<script>alert('xss')</script>", qty: 1, total: 100 }],
    };
    const html = buildComandaHTML(data);
    // El nombre escapado no debe contener <script> raw
    expect(html).not.toContain("<script>alert");
    expect(html).toContain("&lt;script&gt;");
  });

  it("escapes HTML in reference", () => {
    const data = { ...baseData, reference: "Mesa <evil>" };
    const html = buildComandaHTML(data);
    expect(html).not.toContain("<evil>");
    expect(html).toContain("&lt;evil&gt;");
  });

  it("escapes HTML in note", () => {
    const data = { ...baseData, note: "<b>warning</b>" };
    const html = buildComandaHTML(data);
    expect(html).not.toContain("<b>warning</b>");
    expect(html).toContain("&lt;b&gt;warning&lt;/b&gt;");
  });

  it("uses 'COMANDA' fallback for missing stationName", () => {
    const data = { ...baseData, stationName: undefined };
    const html = buildComandaHTML(data);
    expect(html).toContain("COMANDA");
  });

  it("includes attended-by when provided", () => {
    const data = { ...baseData, attendedBy: "Pedro" };
    const html = buildComandaHTML(data);
    expect(html).toContain("Pedro");
  });
});

describe("buildPreCuenta — propina 10%", () => {
  const data: PreCuentaData = {
    tableName: "Mesa 3",
    lines: [{ name: "Café", qty: 2, total: 4000 }],
    subtotal: 10000,
    date: new Date(),
  };

  it("includes SUBTOTAL line", () => {
    const result = buildPreCuenta(data);
    expect(decode(result)).toContain("SUBTOTAL");
  });

  it("includes 10% tip suggestion", () => {
    const result = buildPreCuenta(data);
    const text = decode(result);
    expect(text).toContain("Propina");
    expect(text).toContain("10%");
    // 10% de 10000 = 1000 → debería aparecer
    expect(text).toContain("1.000");
  });

  it("includes suggested total with tip when tip > 0", () => {
    const result = buildPreCuenta(data);
    const text = decode(result);
    // Wording cambiado de "TOTAL CON PROPINA" a "SUGERIDO C/PROPINA"
    // para que el cliente entienda que es sugerencia, no factura final.
    expect(text).toContain("SUGERIDO C/PROPINA");
    // 10000 + 1000 tip = 11000
    expect(text).toContain("11.000");
  });

  it("uses TOTAL (without tip) when subtotal is 0", () => {
    const noTipData = { ...data, subtotal: 0 };
    const result = buildPreCuenta(noTipData);
    const text = decode(result);
    expect(text).toContain("TOTAL");
    expect(text).not.toContain("SUGERIDO");
  });

  it("includes 'opcional' wording for tip", () => {
    const result = buildPreCuenta(data);
    const text = decode(result);
    expect(text.toLowerCase()).toContain("opcional");
  });
});

describe("buildPreCuentaHTML — propina 10%", () => {
  const data: PreCuentaData = {
    tableName: "Mesa 3",
    lines: [{ name: "Café", qty: 2, total: 4000 }],
    subtotal: 10000,
    date: new Date(),
  };

  it("includes propina suggestion in HTML", () => {
    const html = buildPreCuentaHTML(data);
    expect(html).toContain("Propina");
    expect(html).toContain("SUGERIDO C/PROPINA");
  });

  it("shows correct tip amount (10% of subtotal)", () => {
    const html = buildPreCuentaHTML(data);
    expect(html).toContain("$1.000");  // tip
    expect(html).toContain("$11.000"); // total con propina
  });

  it("falls back to 'TOTAL' when subtotal is 0", () => {
    const html = buildPreCuentaHTML({ ...data, subtotal: 0 });
    expect(html).not.toContain("CON PROPINA");
  });

  it("escapes XSS in tableName", () => {
    const html = buildPreCuentaHTML({ ...data, tableName: "<img src=x>" });
    expect(html).not.toContain("<img src=x>");
    expect(html).toContain("&lt;img src=x&gt;");
  });
});
