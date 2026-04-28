/**
 * Receipt content builders — generates ESC/POS bytes or HTML for
 * pre-cuentas and boletas/receipts.
 */

import { EscPos, COLS_58MM, COLS_80MM } from "./escpos";

// ── Types ────────────────────────────────────────────────────────────────────

export interface ReceiptLine {
  name: string;
  qty: number | string;
  unitPrice?: number | string;
  total: number | string;
}

export interface PreCuentaData {
  tableName: string;
  lines: ReceiptLine[];
  subtotal: number;
  date: Date;
  attendedBy?: string;
  tenant?: { name?: string; rut?: string; address?: string; receipt_header?: string };
}

export interface ComandaData {
  /** Mesa o referencia (ej. "Mesa 5", "Para llevar #12"). */
  reference: string;
  /** Estación destino — solo se imprime en el header, ej. "Cocina", "Bar". */
  stationName?: string;
  /** Líneas que van a esta estación. */
  lines: ReceiptLine[];
  /** Mesero/cajero que envió la comanda. */
  attendedBy?: string;
  /** Notas globales (ej. "Mesa con prisa"). */
  note?: string;
  date: Date;
}

export interface PaymentInfo {
  method: string;
  amount: number | string;
}

export interface ReceiptData {
  saleNumber: number | string;
  date: string; // ISO
  lines: ReceiptLine[];
  subtotal: number;
  tip?: number;
  total: number;
  payments?: PaymentInfo[];
  tenant?: {
    name?: string;
    rut?: string;
    address?: string;
    receipt_header?: string;
    receipt_footer?: string;
  };
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtCLP(n: number | string): string {
  const num = typeof n === "string" ? parseFloat(n) : n;
  if (!Number.isFinite(num)) return "$0";
  return "$" + Math.round(num).toLocaleString("es-CL");
}

function fmtDate(d: Date | string): string {
  const date = typeof d === "string" ? new Date(d) : d;
  return date.toLocaleString("es-CL", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function colsFor(paperWidth: 58 | 80): number {
  return paperWidth === 58 ? COLS_58MM : COLS_80MM;
}

const PAYMENT_LABELS: Record<string, string> = {
  cash: "Efectivo",
  card: "Tarjeta",
  transfer: "Transferencia",
};

// ── ESC/POS Builders ─────────────────────────────────────────────────────────

/**
 * Comanda (kitchen ticket) — ticket que va a cocina/bar/despacho.
 * NO incluye precios ni totales (al cocinero no le importa) — sólo lo que
 * tiene que preparar y para qué mesa.
 */
export function buildComanda(data: ComandaData, paperWidth: 58 | 80 = 80): Uint8Array {
  const cols = colsFor(paperWidth);
  const p = new EscPos().init();

  p.align("center").bold(true).fontSize(2, 2);
  p.text(data.stationName ? data.stationName.toUpperCase() : "COMANDA").nl();
  p.fontSize(1, 1).bold(false);
  p.doubleSeparator(cols);

  p.align("left");
  p.bold(true).fontSize(1, 2).text(data.reference).nl().fontSize(1, 1).bold(false);
  p.textLine("Hora:", fmtDate(data.date), cols);
  if (data.attendedBy) p.textLine("Atendido por:", data.attendedBy, cols);
  if (data.note) {
    p.separator("-", cols);
    p.bold(true).text("NOTA: ").bold(false).text(data.note).nl();
  }
  p.separator("-", cols);

  for (const l of data.lines) {
    const qty = typeof l.qty === "string" ? parseFloat(l.qty) : l.qty;
    const qtyStr = Number.isInteger(qty) ? String(qty) : qty.toFixed(1);
    p.bold(true).fontSize(1, 2);
    p.text(`${qtyStr}x ${l.name}`).nl();
    p.fontSize(1, 1).bold(false);
  }

  p.separator("-", cols);
  p.feed(2);
  p.cut();
  return p.build();
}

/** HTML fallback para la comanda (cuando se imprime via window.print). */
export function buildComandaHTML(data: ComandaData): string {
  const lines = data.lines.map(l => {
    const qty = typeof l.qty === "string" ? parseFloat(l.qty) : l.qty;
    const qtyStr = Number.isInteger(qty) ? String(qty) : qty.toFixed(1);
    return `<div class="row" style="padding:6px 0;font-size:18px;font-weight:700"><span>${qtyStr}x ${esc(l.name)}</span></div>`;
  }).join("");
  return `
    <div class="title" style="font-size:24px;font-weight:900">${esc((data.stationName || "COMANDA").toUpperCase())}</div>
    <div class="sep-double"></div>
    <div style="font-size:18px;font-weight:800;margin-bottom:4px">${esc(data.reference)}</div>
    <div class="row info"><span>Hora:</span><span>${fmtDate(data.date)}</span></div>
    ${data.attendedBy ? `<div class="row info"><span>Atendido por:</span><span>${esc(data.attendedBy)}</span></div>` : ""}
    ${data.note ? `<div class="sep"></div><div style="font-weight:700">NOTA: ${esc(data.note)}</div>` : ""}
    <div class="sep"></div>
    ${lines}
    <div class="sep"></div>
  `;
}

export function buildPreCuenta(data: PreCuentaData, paperWidth: 58 | 80 = 80): Uint8Array {
  const cols = colsFor(paperWidth);
  const p = new EscPos().init();

  p.align("center").bold(true).fontSize(2, 2);
  p.text("PRE-CUENTA").nl();
  p.fontSize(1, 1).bold(false).align("left");
  p.doubleSeparator(cols);

  p.textLine("Mesa:", data.tableName, cols);
  p.textLine("Fecha:", fmtDate(data.date), cols);
  if (data.attendedBy) p.textLine("Atendido por:", data.attendedBy, cols);
  p.separator("-", cols);

  // Header
  if (cols >= 48) {
    p.bold(true).textLine("Cant  Producto", "Total", cols).bold(false);
  } else {
    p.bold(true).textLine("Cant Producto", "Total", cols).bold(false);
  }
  p.separator("-", cols);

  // Lines
  for (const l of data.lines) {
    const qty = typeof l.qty === "string" ? parseFloat(l.qty) : l.qty;
    const qtyStr = Number.isInteger(qty) ? String(qty) : qty.toFixed(1);
    const name = l.name.length > (cols - 16) ? l.name.slice(0, cols - 16) : l.name;
    const left = `${qtyStr.padStart(3)}  ${name}`;
    p.textLine(left, fmtCLP(l.total), cols);
  }

  p.separator("-", cols);
  // Subtotal SIN propina (ganancia del local, va a la caja)
  p.textLine("SUBTOTAL", fmtCLP(data.subtotal), cols);

  // Propina sugerida 10% + total con propina. La propina es del equipo
  // (mesero/cajero), no del local — la idea es que el cliente decida
  // si la deja o no, y le entreguen el total con o sin propina.
  const tipSuggested = Math.round(data.subtotal * 0.10);
  const totalWithTip = data.subtotal + tipSuggested;
  if (tipSuggested > 0) {
    p.textLine("Propina (10%)", fmtCLP(tipSuggested), cols);
    p.separator("-", cols);
    p.bold(true).textLine("TOTAL CON PROPINA", fmtCLP(totalWithTip), cols).bold(false);
  } else {
    p.bold(true).textLine("TOTAL", fmtCLP(data.subtotal), cols).bold(false);
  }
  p.doubleSeparator(cols);

  p.feed(1);
  p.align("center");
  if (tipSuggested > 0) {
    p.text("La propina es opcional").nl();
    p.text("y va para el equipo").nl();
    p.feed(1);
  }
  p.text("** ESTE NO ES UN").nl();
  p.text("DOCUMENTO FISCAL **").nl();
  p.feed(3);
  p.cut();

  return p.build();
}

export function buildReceipt(data: ReceiptData, paperWidth: 58 | 80 = 80): Uint8Array {
  const cols = colsFor(paperWidth);
  const p = new EscPos().init();

  // Tenant header
  if (data.tenant) {
    p.align("center").bold(true).fontSize(2, 1);
    if (data.tenant.name) p.text(data.tenant.name).nl();
    p.fontSize(1, 1).bold(false);
    if (data.tenant.receipt_header) p.text(data.tenant.receipt_header).nl();
    if (data.tenant.rut) p.text(`RUT: ${data.tenant.rut}`).nl();
    if (data.tenant.address) p.text(data.tenant.address).nl();
    p.align("left");
  }

  p.doubleSeparator(cols);
  p.align("center").bold(true).fontSize(1, 2);
  p.text(`BOLETA #${data.saleNumber}`).nl();
  p.fontSize(1, 1).bold(false);
  p.text(fmtDate(data.date)).nl();
  p.align("left");
  p.separator("-", cols);

  // Header
  if (cols >= 48) {
    p.bold(true).textLine("Cant  Producto", "Total", cols).bold(false);
  } else {
    p.bold(true).textLine("Cant Producto", "Total", cols).bold(false);
  }
  p.separator("-", cols);

  // Lines
  for (const l of data.lines) {
    const qty = typeof l.qty === "string" ? parseFloat(l.qty) : l.qty;
    const qtyStr = Number.isInteger(qty) ? String(qty) : qty.toFixed(1);
    const name = l.name.length > (cols - 16) ? l.name.slice(0, cols - 16) : l.name;
    const left = `${qtyStr.padStart(3)}  ${name}`;
    p.textLine(left, fmtCLP(l.total), cols);
  }

  p.separator("-", cols);

  // Totals — patrón Fudo/Wabi: subtotal (valor de la cuenta del local,
  // ya con descuentos si los hay) y propina por separado. TOTAL = lo
  // que el cliente paga = data.total + data.tip.
  //
  // Antes el TOTAL impreso era solo data.total (sin propina), entonces
  // si el cliente dejó propina, la boleta mostraba un total menor al
  // que realmente pagó. Mario lo reportó: "en las boletas todavía no
  // puedo ver las propinas en las mesas que dejaron".
  const tipAmt = data.tip && data.tip > 0 ? data.tip : 0;
  const totalToPay = (data.total || 0) + tipAmt;
  p.textLine("SUBTOTAL", fmtCLP(data.total), cols);
  if (tipAmt > 0) {
    p.textLine("PROPINA", fmtCLP(tipAmt), cols);
  }
  p.bold(true).fontSize(1, 2);
  p.textLine("TOTAL", fmtCLP(totalToPay), cols);
  p.fontSize(1, 1).bold(false);
  p.separator("-", cols);

  // Payments
  if (data.payments && data.payments.length > 0) {
    for (const pm of data.payments) {
      const label = PAYMENT_LABELS[pm.method] || pm.method;
      p.textLine(`Pago: ${label}`, fmtCLP(pm.amount), cols);
    }
    p.separator("-", cols);
  }

  // Footer
  p.feed(1);
  p.align("center");
  if (data.tenant?.receipt_footer) {
    p.text(data.tenant.receipt_footer).nl();
  } else {
    p.text("Gracias por su compra").nl();
  }
  p.feed(3);
  p.cut();

  return p.build();
}

// ── HTML Builders (fallback for window.print) ────────────────────────────────

export function buildPreCuentaHTML(data: PreCuentaData): string {
  const neto = Math.round(data.subtotal / 1.19);
  const iva = data.subtotal - neto;

  const lines = data.lines.map(l => {
    const qty = typeof l.qty === "string" ? parseFloat(l.qty) : l.qty;
    const qtyStr = Number.isInteger(qty) ? String(qty) : qty.toFixed(1);
    const totalNum = typeof l.total === "string" ? parseFloat(l.total) : l.total;
    const unitPrice = qty > 0 ? Math.round(totalNum / qty) : 0;
    return `
      <div class="row" style="padding:3px 0">
        <span class="item-name" style="flex:1">${esc(l.name)}</span>
        <span class="price">${fmtCLP(l.total)}</span>
      </div>
      <div class="row info" style="padding:0 0 4px;color:#888;font-size:11px">
        <span>${qtyStr} × ${fmtCLP(unitPrice)}</span>
      </div>`;
  }).join("");

  const totalItems = data.lines.reduce((s, l) => {
    const qty = typeof l.qty === "string" ? parseFloat(l.qty) : l.qty;
    return s + qty;
  }, 0);

  return `
    ${data.tenant?.name ? `<div class="title" style="font-size:18px;margin-bottom:2px">${esc(data.tenant.name)}</div>` : ""}
    ${data.tenant?.receipt_header ? `<div class="center info">${esc(data.tenant.receipt_header)}</div>` : ""}
    ${data.tenant?.rut ? `<div class="center info" style="font-size:11px">RUT: ${esc(data.tenant.rut)}</div>` : ""}
    ${data.tenant?.address ? `<div class="center info" style="font-size:11px">${esc(data.tenant.address)}</div>` : ""}
    <div class="sep-double" style="margin-top:8px"></div>
    <div class="title">PRE-CUENTA</div>
    <div class="sep-double"></div>
    <div class="row info"><span>Mesa:</span><span>${esc(data.tableName)}</span></div>
    <div class="row info"><span>Fecha:</span><span>${fmtDate(data.date)}</span></div>
    ${data.attendedBy ? `<div class="row info"><span>Atendido por:</span><span>${esc(data.attendedBy)}</span></div>` : ""}
    <div class="row info"><span>Items:</span><span>${data.lines.length} producto(s), ${totalItems} unid.</span></div>
    <div class="sep"></div>
    ${lines}
    <div class="sep"></div>
    <div class="row info"><span>Neto</span><span>${fmtCLP(neto)}</span></div>
    <div class="row info"><span>IVA (19%)</span><span>${fmtCLP(iva)}</span></div>
    <div class="row"><span>SUBTOTAL</span><span class="price">${fmtCLP(data.subtotal)}</span></div>
    ${(() => {
      const tip = Math.round(data.subtotal * 0.10);
      if (tip <= 0) return `<div class="row total-row"><span>TOTAL</span><span class="price">${fmtCLP(data.subtotal)}</span></div>`;
      return `
    <div class="row" style="color:#666"><span>Propina (10%)</span><span>${fmtCLP(tip)}</span></div>
    <div class="sep"></div>
    <div class="row total-row"><span>TOTAL CON PROPINA</span><span class="price">${fmtCLP(data.subtotal + tip)}</span></div>
    <div class="center info" style="margin-top:6px;font-size:11px;color:#888">La propina es opcional y va para el equipo</div>`;
    })()}
    <div class="sep-double"></div>
    <div class="disclaimer">** ESTE NO ES UN DOCUMENTO FISCAL **</div>
  `;
}

export function buildReceiptHTML(data: ReceiptData): string {
  const lines = data.lines.map(l => {
    const qty = typeof l.qty === "string" ? parseFloat(l.qty) : l.qty;
    const qtyStr = Number.isInteger(qty) ? String(qty) : qty.toFixed(1);
    return `<div class="row"><span class="item-name">${qtyStr}x ${esc(l.name)}</span><span class="price">${fmtCLP(l.total)}</span></div>`;
  }).join("");

  const payments = (data.payments || []).map(pm => {
    const label = PAYMENT_LABELS[pm.method] || pm.method;
    return `<div class="row info"><span>Pago: ${label}</span><span class="price">${fmtCLP(pm.amount)}</span></div>`;
  }).join("");

  return `
    ${data.tenant?.name ? `<div class="title">${esc(data.tenant.name)}</div>` : ""}
    ${data.tenant?.receipt_header ? `<div class="center info">${esc(data.tenant.receipt_header)}</div>` : ""}
    ${data.tenant?.rut ? `<div class="center info">RUT: ${esc(data.tenant.rut)}</div>` : ""}
    ${data.tenant?.address ? `<div class="center info">${esc(data.tenant.address)}</div>` : ""}
    <div class="sep-double"></div>
    <div class="title">BOLETA #${data.saleNumber}</div>
    <div class="center info">${fmtDate(data.date)}</div>
    <div class="sep"></div>
    ${lines}
    <div class="sep"></div>
    <div class="row"><span>SUBTOTAL</span><span class="price">${fmtCLP(data.total)}</span></div>
    ${data.tip && data.tip > 0 ? `<div class="row" style="color:#d97706"><span>PROPINA</span><span class="price">${fmtCLP(data.tip)}</span></div>` : ""}
    <div class="row total-row"><span>TOTAL</span><span class="price">${fmtCLP((data.total || 0) + (data.tip || 0))}</span></div>
    <div class="sep"></div>
    ${payments}
    ${payments ? '<div class="sep"></div>' : ""}
    <div class="footer">${esc(data.tenant?.receipt_footer || "Gracias por su compra")}</div>
  `;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
