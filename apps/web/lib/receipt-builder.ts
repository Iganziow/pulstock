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
  p.bold(true).textLine("SUBTOTAL", fmtCLP(data.subtotal), cols).bold(false);
  p.doubleSeparator(cols);

  p.feed(1);
  p.align("center");
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

  // Totals
  p.textLine("SUBTOTAL", fmtCLP(data.subtotal), cols);
  if (data.tip && data.tip > 0) {
    p.textLine("PROPINA", fmtCLP(data.tip), cols);
  }
  p.bold(true).fontSize(1, 2);
  p.textLine("TOTAL", fmtCLP(data.total), cols);
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
    <div class="row total-row"><span>TOTAL</span><span class="price">${fmtCLP(data.subtotal)}</span></div>
    <div class="sep-double"></div>
    <div class="disclaimer">** ESTE NO ES UN DOCUMENTO FISCAL **</div>
    <div class="center info" style="margin-top:8px;font-size:11px;color:#888">Propina sugerida (10%): ${fmtCLP(Math.round(data.subtotal * 0.10))}</div>
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
    <div class="row"><span>SUBTOTAL</span><span class="price">${fmtCLP(data.subtotal)}</span></div>
    ${data.tip && data.tip > 0 ? `<div class="row"><span>PROPINA</span><span class="price">${fmtCLP(data.tip)}</span></div>` : ""}
    <div class="row total-row"><span>TOTAL</span><span class="price">${fmtCLP(data.total)}</span></div>
    <div class="sep"></div>
    ${payments}
    ${payments ? '<div class="sep"></div>' : ""}
    <div class="footer">${esc(data.tenant?.receipt_footer || "Gracias por su compra")}</div>
  `;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
