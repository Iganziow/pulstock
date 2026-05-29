/** Format CLP number (no symbol, dot-separated thousands). */
export function fmt(v: string | number) {
  const n = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(n) ? Math.round(n).toLocaleString("es-CL") : "0";
}

/** Format an ISO timestamp to HH:MM (es-CL locale). */
export function fmtTime(iso: string) {
  return new Date(iso).toLocaleString("es-CL", { hour: "2-digit", minute: "2-digit" });
}

/** Relative time label from ISO timestamp (e.g. "5m", "1h 20m"). */
export function timeAgo(iso: string) {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (diff < 1) return "ahora";
  if (diff < 60) return `${diff}m`;
  const h = Math.floor(diff / 60);
  return `${h}h${diff % 60 > 0 ? ` ${diff % 60}m` : ""}`;
}

/** CSS injected once into the document head for mesa-card hover animations. */
export const PAGE_CSS = `
@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
@keyframes fadeIn{from{opacity:0;transform:scale(0.97)}to{opacity:1;transform:scale(1)}}
* { box-sizing: border-box; }
.mesa-card{transition:all 0.13s ease;cursor:pointer;}
.mesa-card:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,0,0,0.1);}
.summary-row{transition:background 0.12s ease;cursor:pointer;}
.summary-row:hover{background:#F4F4F5 !important;}
`;

export const PAY_METHODS = [
  { value: "cash", label: "Efectivo" },
  { value: "debit", label: "Débito" },
  { value: "card", label: "Crédito" },
  { value: "transfer", label: "Transferencia" },
] as const;

// ─── Separación propina ↔ pago (Fudo-style, backend Fase A) ─────────────
//
// El modal de cobro trabaja con PAGO = total (subtotal + propina), igual
// que Fudo. Para el backend hay que separar:
//   - SaleTip (propina) → por método, explícito.
//   - SalePayment (cuenta) → bruto del PAGO menos la propina de ESE método,
//     clampeado al subtotal (el vuelto NO entra a la caja).
//
// Esta función es PURA y testeable (ver __tests__/mesas-checkout.test.ts).
// Extraída del onClick del PaymentModal para poder auditarla con todos los
// casos borde: 1 método, split de pago, propina split, propina en método
// distinto al pago, vuelto, etc.

export interface AmountRow {
  method: string;
  amount: string | number;
}

export interface CheckoutSplit {
  /** Pagos de la CUENTA por método (sum == subtotal, sin propina, sin vuelto). */
  payments: { method: string; amount: string }[];
  /** Propinas explícitas por método (SaleTip). */
  tips: { method: string; amount: number }[];
  /** Suma de propinas (= Sale.tip denormalizado). */
  tipTotal: number;
}

/**
 * Separa las filas de PAGO (bruto = subtotal + propina) y de PROPINA en el
 * payload que espera el backend: payments (solo cuenta) + tips (propina).
 *
 * @param paymentRows  Filas de la sección PAGO (montos brutos, incluyen propina).
 * @param tipRows      Filas de la sección PROPINA (método + monto).
 * @param lineSubtotal Subtotal de la cuenta (lo que DEBE cubrir el pago).
 */
export function buildCheckoutSplit(
  paymentRows: AmountRow[],
  tipRows: AmountRow[],
  lineSubtotal: number,
): CheckoutSplit {
  // 1. Propina por método
  const tipsClean = tipRows
    .map(r => ({ method: r.method, amount: Math.round(Number(r.amount) || 0) }))
    .filter(r => r.amount > 0);
  const tipTotal = tipsClean.reduce((s, r) => s + r.amount, 0);
  const tipByMethod: Record<string, number> = {};
  for (const r of tipsClean) tipByMethod[r.method] = (tipByMethod[r.method] || 0) + r.amount;

  // 2. Pago de la cuenta = bruto − propina por método
  const grossByMethod: Record<string, number> = {};
  for (const r of paymentRows) {
    const amt = Number(r.amount) || 0;
    if (amt > 0) grossByMethod[r.method] = (grossByMethod[r.method] || 0) + amt;
  }
  let salePays = Object.entries(grossByMethod)
    .map(([method, gross]) => ({ method, amount: gross - (tipByMethod[method] || 0) }))
    .filter(p => p.amount > 0);

  // 3. Clamp al subtotal (vuelto solo en UI, no entra a SalePayment)
  if (salePays.length > 0 && lineSubtotal > 0) {
    let running = 0;
    salePays = salePays
      .map((p, i) => {
        if (i < salePays.length - 1) { running += p.amount; return p; }
        return { ...p, amount: Math.max(0, lineSubtotal - running) };
      })
      .filter(p => p.amount > 0);
  }

  // Fallback defensivo: si la resta dejó el pago en 0 (ej. propina en un
  // método sin pago), mandar 1 pago por el subtotal en el método del
  // primer PAGO para no enviar payments vacíos.
  if (salePays.length === 0 && lineSubtotal > 0) {
    salePays = [{ method: paymentRows[0]?.method || "cash", amount: lineSubtotal }];
  }

  return {
    payments: salePays.map(p => ({ method: p.method, amount: String(p.amount) })),
    tips: tipsClean,
    tipTotal,
  };
}
