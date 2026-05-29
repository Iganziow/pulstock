import { describe, it, expect } from "vitest";
import { buildCheckoutSplit } from "@/components/mesas/helpers";

/**
 * Auditoría de la separación propina↔pago del modal de cobro de mesas
 * (Mario 28/05/26). El modal trabaja con PAGO = total (subtotal + propina);
 * buildCheckoutSplit() separa eso en payments (solo cuenta) + tips (propina)
 * para el backend Fase A.
 *
 * INVARIANTE CRÍTICO (no se puede romper, es dinero real):
 *   sum(payments) === subtotal exacto   (la cuenta queda cubierta, sin vuelto)
 *   sum(tips)     === propina total      (la propina se guarda completa)
 *   Cada propina queda en SU método (para cuadrar caja por método).
 */

// Helper: suma de payments del resultado
const sumPays = (s: ReturnType<typeof buildCheckoutSplit>) =>
  s.payments.reduce((a, p) => a + Number(p.amount), 0);
const sumTips = (s: ReturnType<typeof buildCheckoutSplit>) =>
  s.tips.reduce((a, t) => a + t.amount, 0);

describe("buildCheckoutSplit — caso 1: un solo método", () => {
  it("CON propina (café típico): cuenta 13980 + propina 1398 efectivo", () => {
    // El modal autoSync pone PAGO = grandTotal = 15378 en 1 fila efectivo.
    const s = buildCheckoutSplit(
      [{ method: "cash", amount: 15378 }],
      [{ method: "cash", amount: 1398 }],
      13980,
    );
    expect(s.payments).toEqual([{ method: "cash", amount: "13980" }]);
    expect(s.tips).toEqual([{ method: "cash", amount: 1398 }]);
    expect(sumPays(s)).toBe(13980); // cuenta exacta
    expect(s.tipTotal).toBe(1398);
  });

  it("SIN propina: cuenta 13980, pago 13980 efectivo", () => {
    const s = buildCheckoutSplit(
      [{ method: "cash", amount: 13980 }],
      [],
      13980,
    );
    expect(s.payments).toEqual([{ method: "cash", amount: "13980" }]);
    expect(s.tips).toEqual([]);
    expect(s.tipTotal).toBe(0);
  });
});

describe("buildCheckoutSplit — caso 2: propina en método DISTINTO al pago", () => {
  it("cuenta 5000 efectivo + propina 500 débito (autoSync pone 5500 cash)", () => {
    // El cliente paga la cuenta en efectivo y deja propina en débito.
    // El modal con autoSync pone PAGO = 5500 efectivo (no sabe que la
    // propina es débito). La separación clampea el pago al subtotal.
    const s = buildCheckoutSplit(
      [{ method: "cash", amount: 5500 }],
      [{ method: "debit", amount: 500 }],
      5000,
    );
    // El pago efectivo se clampea a la cuenta (5000); la propina débito
    // va aparte. Total recibido: 5000 cash + 500 debit = 5500.
    expect(s.payments).toEqual([{ method: "cash", amount: "5000" }]);
    expect(s.tips).toEqual([{ method: "debit", amount: 500 }]);
    expect(sumPays(s)).toBe(5000);
    expect(sumTips(s)).toBe(500);
  });

  it("cuenta 5000 débito + propina 500 efectivo (cajero ajustó las filas)", () => {
    // Cajero pone PAGO: débito 5000 (cuenta) + efectivo 500 (lo que el
    // cliente entregó cash como propina) — o autoSync 1 fila. Probamos el
    // caso donde el cajero refleja ambos métodos en PAGO.
    const s = buildCheckoutSplit(
      [{ method: "debit", amount: 5000 }, { method: "cash", amount: 500 }],
      [{ method: "cash", amount: 500 }],
      5000,
    );
    // débito 5000 (sin propina débito) + efectivo 500-500=0 (se filtra).
    // Clamp: queda débito 5000.
    expect(sumPays(s)).toBe(5000);
    expect(s.payments).toEqual([{ method: "debit", amount: "5000" }]);
    expect(s.tips).toEqual([{ method: "cash", amount: 500 }]);
  });
});

describe("buildCheckoutSplit — caso 3: split de pago (varios métodos)", () => {
  it("SIN propina: cuenta 10000 = 5000 efectivo + 5000 débito", () => {
    const s = buildCheckoutSplit(
      [{ method: "cash", amount: 5000 }, { method: "debit", amount: 5000 }],
      [],
      10000,
    );
    expect(sumPays(s)).toBe(10000);
    expect(s.payments).toEqual([
      { method: "cash", amount: "5000" },
      { method: "debit", amount: "5000" },
    ]);
    expect(s.tips).toEqual([]);
  });

  it("CON propina: cuenta 10000 (cajero infla cash con propina 1000)", () => {
    // Split + propina: el cajero pone cash 6000 (5000 cuenta + 1000 propina)
    // + débito 5000. PROPINA: cash 1000.
    const s = buildCheckoutSplit(
      [{ method: "cash", amount: 6000 }, { method: "debit", amount: 5000 }],
      [{ method: "cash", amount: 1000 }],
      10000,
    );
    expect(sumPays(s)).toBe(10000); // cuenta exacta
    expect(s.payments).toEqual([
      { method: "cash", amount: "5000" }, // 6000 − 1000 propina
      { method: "debit", amount: "5000" },
    ]);
    expect(s.tips).toEqual([{ method: "cash", amount: 1000 }]);
    expect(s.tipTotal).toBe(1000);
  });
});

describe("buildCheckoutSplit — caso 4: propina split (varios métodos)", () => {
  it("propina 600 efectivo + 400 débito, pago 1 método (autoSync)", () => {
    // cuenta 10000, propina total 1000 dividida. autoSync PAGO = 11000 cash.
    const s = buildCheckoutSplit(
      [{ method: "cash", amount: 11000 }],
      [{ method: "cash", amount: 600 }, { method: "debit", amount: 400 }],
      10000,
    );
    // gross cash 11000 − propina cash 600 = 10400; clamp a 10000.
    expect(sumPays(s)).toBe(10000);
    expect(s.payments).toEqual([{ method: "cash", amount: "10000" }]);
    // Propina split preservada (cada método con su monto, para cuadrar caja)
    expect(s.tips).toEqual([
      { method: "cash", amount: 600 },
      { method: "debit", amount: 400 },
    ]);
    expect(sumTips(s)).toBe(1000);
  });

  it("split de pago + propina split (caso completo restaurante)", () => {
    // cuenta 10000 = cash 5000 + débito 5000. propina 600 cash + 400 débito.
    // Cajero infla: cash 5600 + débito 5400 = 11000.
    const s = buildCheckoutSplit(
      [{ method: "cash", amount: 5600 }, { method: "debit", amount: 5400 }],
      [{ method: "cash", amount: 600 }, { method: "debit", amount: 400 }],
      10000,
    );
    expect(sumPays(s)).toBe(10000);
    expect(s.payments).toEqual([
      { method: "cash", amount: "5000" },  // 5600 − 600
      { method: "debit", amount: "5000" }, // 5400 − 400
    ]);
    expect(s.tips).toEqual([
      { method: "cash", amount: 600 },
      { method: "debit", amount: 400 },
    ]);
  });
});

describe("buildCheckoutSplit — casos borde", () => {
  it("vuelto: cliente paga 20000 por cuenta de 13980 (sin propina)", () => {
    // El vuelto NO debe entrar a SalePayment (la caja no lo espera).
    const s = buildCheckoutSplit(
      [{ method: "cash", amount: 20000 }],
      [],
      13980,
    );
    expect(sumPays(s)).toBe(13980); // clampeado, NO 20000
    expect(s.payments).toEqual([{ method: "cash", amount: "13980" }]);
  });

  it("propina 0 explícita (fila con monto 0 se descarta)", () => {
    const s = buildCheckoutSplit(
      [{ method: "cash", amount: 5000 }],
      [{ method: "cash", amount: 0 }],
      5000,
    );
    expect(s.tips).toEqual([]);
    expect(s.tipTotal).toBe(0);
    expect(sumPays(s)).toBe(5000);
  });

  it("fallback: propina en método sin pago no deja payments vacíos", () => {
    // Edge raro: PAGO solo débito 500, propina débito 500, subtotal 5000.
    // gross debit 500 − tip debit 500 = 0 → se filtra → fallback al subtotal.
    const s = buildCheckoutSplit(
      [{ method: "debit", amount: 500 }],
      [{ method: "debit", amount: 500 }],
      5000,
    );
    // No debe quedar sin pagos: fallback pone el subtotal en el método del pago.
    expect(s.payments.length).toBeGreaterThan(0);
    expect(sumPays(s)).toBe(5000);
  });

  it("redondeo: propina con decimales se redondea a entero (CLP)", () => {
    const s = buildCheckoutSplit(
      [{ method: "cash", amount: 5500 }],
      [{ method: "cash", amount: 499.6 }],
      5000,
    );
    expect(s.tips).toEqual([{ method: "cash", amount: 500 }]); // redondeado
    expect(sumPays(s)).toBe(5000);
  });

  it("montos como string (vienen del input del modal)", () => {
    const s = buildCheckoutSplit(
      [{ method: "cash", amount: "15378" }],
      [{ method: "cash", amount: "1398" }],
      13980,
    );
    expect(s.payments).toEqual([{ method: "cash", amount: "13980" }]);
    expect(s.tips).toEqual([{ method: "cash", amount: 1398 }]);
  });
});

describe("buildCheckoutSplit — INVARIANTE: cuenta siempre cubierta", () => {
  // Propiedad: para cualquier combinación válida donde el bruto cubre el
  // grandTotal, sum(payments) === subtotal y sum(tips) === propina.
  const cases = [
    { pay: [{ method: "cash", amount: 6000 }], tip: [{ method: "cash", amount: 1000 }], sub: 5000 },
    { pay: [{ method: "debit", amount: 11000 }], tip: [{ method: "debit", amount: 1000 }], sub: 10000 },
    { pay: [{ method: "cash", amount: 3300 }], tip: [{ method: "cash", amount: 300 }], sub: 3000 },
    { pay: [{ method: "transfer", amount: 5500 }], tip: [{ method: "transfer", amount: 500 }], sub: 5000 },
  ];
  cases.forEach((c, i) => {
    it(`invariante #${i + 1}: sum(payments)==subtotal && sum(tips)==propina`, () => {
      const s = buildCheckoutSplit(c.pay, c.tip, c.sub);
      expect(sumPays(s)).toBe(c.sub);
      expect(sumTips(s)).toBe(c.tip.reduce((a, t) => a + Number(t.amount), 0));
    });
  });
});
