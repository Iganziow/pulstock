"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";

// ─── Types ────────────────────────────────────────────────────────────────────

type Product  = { id: number; name: string; sku?: string | null };
type Payment  = { method: string; amount: string };
type SaleLine = { id: number; product: Product; qty: string; unit_price: string; line_total: string };
type Tenant   = { name?: string; rut?: string; address?: string; receipt_header?: string; receipt_footer?: string; receipt_show_rut?: boolean };
type Sale     = {
  id: number; sale_number?: number | null; created_at: string; warehouse_id: number;
  subtotal: string; total: string; tip?: string | null;
  status: "COMPLETED" | "VOID" | string;
  lines: SaleLine[];
  payments?: Payment[];
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toNumber(v: string | number) { const n = typeof v === "string" ? Number(v) : v; return Number.isFinite(n) ? n : 0; }
function fmt(v: number) { return "$" + Math.round(v).toLocaleString("es-CL"); }
function fmtDt(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-CL", { day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit" });
}

const MONO = "'Courier New','Lucida Console',monospace";
const PM_LABELS: Record<string, string> = { cash: "Efectivo", card: "Tarjeta", transfer: "Transferencia" };

// ─── Separator components ────────────────────────────────────────────────────

function Dash() {
  return <div style={{ borderTop: "1px dashed #bbb", margin: "6px 0" }} />;
}
function DoubleLine() {
  return <div style={{ borderTop: "2px solid #333", margin: "6px 0" }} />;
}
function Row({ left, right, bold, big, color }: { left: string; right: string; bold?: boolean; big?: boolean; color?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "1px 0" }}>
      <span style={{ fontWeight: bold ? 900 : 400, fontSize: big ? 16 : 12, color: color || "#000" }}>{left}</span>
      <span style={{ fontWeight: bold ? 900 : 400, fontSize: big ? 16 : 12, color: color || "#000", fontVariantNumeric: "tabular-nums", textAlign: "right" }}>{right}</span>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

const PAGE_CSS = `
@media print {
  .no-print{display:none!important}
  body{background:white!important;padding:0!important;margin:0!important}
  @page{margin:0;size:80mm auto}
  .receipt-outer{padding:0!important;background:white!important;min-height:auto!important}
  .receipt-card{box-shadow:none!important;border:none!important;border-radius:0!important;max-width:100%!important;width:72mm!important;margin:0!important}
}
`;

export default function ReceiptPage() {
  useGlobalStyles(PAGE_CSS);
  const params = useParams<{ id: string }>();
  const saleId = Number(params?.id);

  const [sale, setSale] = useState<Sale | null>(null);
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [err, setErr]   = useState<string | null>(null);
  const [hasThermal, setHasThermal] = useState(false);

  useEffect(() => {
    if (!saleId) { setErr("ID inválido."); return; }
    (async () => {
      try {
        const [data, t] = await Promise.all([
          apiFetch(`/sales/sales/${saleId}/`) as Promise<Sale>,
          apiFetch("/core/settings/").catch(() => null),
        ]);
        setSale(data); setTenant(t); setErr(null);
      } catch (e: any) {
        const msg = e?.message ?? "";
        const friendly = msg.includes("matches the given query") ? "No se encontró la venta solicitada." : (msg || "No se pudo cargar el recibo.");
        setErr(friendly);
      }
    })();
  }, [saleId]);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("pulstock_printers");
      if (saved && JSON.parse(saved).length > 0) setHasThermal(true);
    } catch {}
  }, []);

  const total = useMemo(() => toNumber(sale?.total ?? 0), [sale?.total]);
  const subtotal = useMemo(() => toNumber(sale?.subtotal ?? 0), [sale?.subtotal]);
  const tip = useMemo(() => toNumber(sale?.tip ?? 0), [sale?.tip]);
  const isVoid = sale?.status === "VOID";

  async function handleThermalPrint() {
    if (!sale) return;
    try {
      const { getDefaultPrinter, printBytes, printHTML } = await import("@/lib/printer");
      const { buildReceipt, buildReceiptHTML } = await import("@/lib/receipt-builder");
      const printer = getDefaultPrinter();
      const receiptData = {
        saleNumber: sale.sale_number ?? sale.id,
        date: sale.created_at,
        lines: (sale.lines || []).map(l => ({
          name: l.product?.name || "Producto", qty: l.qty, unitPrice: l.unit_price, total: l.line_total,
        })),
        subtotal, tip, total,
        payments: (sale.payments || []).map((p: any) => ({ method: p.method, amount: p.amount })),
        tenant: tenant ? { name: tenant.name, rut: tenant.rut, address: tenant.address, receipt_header: tenant.receipt_header, receipt_footer: tenant.receipt_footer } : undefined,
      };
      if (printer && printer.type === "system") {
        const { printSystemReceipt } = await import("@/lib/printer");
        printSystemReceipt(buildReceiptHTML(receiptData), printer);
      } else if (printer) {
        await printBytes(buildReceipt(receiptData, printer.paperWidth || 80), printer);
      } else {
        printHTML(buildReceiptHTML(receiptData));
      }
    } catch (e: any) { alert(e?.message || "Error al imprimir"); }
  }

  function handleBrowserPrint() { window.print(); }

  // ── Loading / Error ────────────────────────────────────────────────────────

  if (err || !sale) {
    return (
      <div style={{ fontFamily: MONO, color: "#333", background: "#f5f5f5", minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <div style={{ textAlign: "center", padding: 32 }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>{err ? "⚠️" : "⏳"}</div>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>{err ? "Error al cargar el recibo" : "Cargando recibo…"}</div>
          {err && <div style={{ fontSize: 12, color: "#999", marginBottom: 16 }}>{err}</div>}
          <Link href="/dashboard/pos" style={{ fontSize: 12, fontWeight: 600, color: C.accent, textDecoration: "none" }}>
            ← Volver al POS
          </Link>
        </div>
      </div>
    );
  }

  // ── Receipt (POS ticket style) ─────────────────────────────────────────────

  return (
    <div className="receipt-outer" style={{ fontFamily: MONO, color: "#000", background: "#e8e8e8", minHeight: "100vh", padding: "24px 16px" }}>

      {/* Top nav — hidden on print */}
      <div className="no-print" style={{ maxWidth: 360, margin: "0 auto 16px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <Link href="/dashboard/pos" style={{
          display: "inline-flex", alignItems: "center", gap: 5,
          fontSize: 11, fontWeight: 600, color: "#666", textDecoration: "none",
          padding: "6px 10px", border: "1px solid #ccc", borderRadius: 6, background: "#fff",
        }}>
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
          Volver
        </Link>
        <div style={{ display: "flex", gap: 5 }}>
          {hasThermal && (
            <button type="button" onClick={handleThermalPrint} style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              fontSize: 11, fontWeight: 700, color: C.accent, padding: "6px 10px",
              border: `1.5px solid ${C.accent}`, borderRadius: 6, background: "#fff", cursor: "pointer", fontFamily: "inherit",
            }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>
              </svg>
              Térmica
            </button>
          )}
          <button type="button" onClick={handleBrowserPrint} style={{
            display: "inline-flex", alignItems: "center", gap: 5,
            fontSize: 11, fontWeight: 700, color: "#fff", padding: "6px 12px",
            border: "none", borderRadius: 6, background: C.accent, cursor: "pointer", fontFamily: "inherit",
          }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>
            </svg>
            Imprimir
          </button>
        </div>
      </div>

      {/* Receipt ticket */}
      <div className="receipt-card" style={{
        maxWidth: 320, margin: "0 auto", background: "#fff",
        borderRadius: 4, boxShadow: "0 2px 16px rgba(0,0,0,.12)",
        padding: "16px 14px", fontSize: 12, lineHeight: 1.5,
      }}>

        {/* VOID banner */}
        {isVoid && (
          <div style={{ textAlign: "center", background: "#fee", border: "1px solid #fcc", borderRadius: 3, padding: "4px 8px", marginBottom: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 900, color: "#c00", letterSpacing: "0.1em" }}>*** ANULADA ***</span>
          </div>
        )}

        {/* Tenant header */}
        {tenant?.name && (
          <div style={{ textAlign: "center", marginBottom: 2 }}>
            <div style={{ fontSize: 16, fontWeight: 900, letterSpacing: "0.02em" }}>{tenant.name}</div>
          </div>
        )}
        {tenant?.receipt_header && <div style={{ textAlign: "center", fontSize: 10, color: "#555" }}>{tenant.receipt_header}</div>}
        {tenant?.rut && <div style={{ textAlign: "center", fontSize: 10, color: "#555" }}>RUT: {tenant.rut}</div>}
        {tenant?.address && <div style={{ textAlign: "center", fontSize: 10, color: "#555" }}>{tenant.address}</div>}

        <DoubleLine />

        {/* Sale number + date */}
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 18, fontWeight: 900, letterSpacing: "0.02em" }}>BOLETA #{sale.sale_number ?? sale.id}</div>
          <div style={{ fontSize: 10, color: "#555", marginTop: 2 }}>{fmtDt(sale.created_at)}</div>
        </div>

        <Dash />

        {/* Line items */}
        {sale.lines?.map((l) => {
          const qty = toNumber(l.qty);
          const qtyStr = Number.isInteger(qty) ? String(qty) : qty.toFixed(1);
          return (
            <div key={l.id} style={{ marginBottom: 4 }}>
              <div style={{ fontWeight: 700, fontSize: 12, wordBreak: "break-word" }}>{l.product?.name ?? "Producto"}</div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#444" }}>
                <span>{qtyStr} x {fmt(toNumber(l.unit_price))}</span>
                <span style={{ fontWeight: 700, color: "#000", fontVariantNumeric: "tabular-nums" }}>{fmt(toNumber(l.line_total))}</span>
              </div>
            </div>
          );
        })}

        <Dash />

        {/* Totals */}
        <Row left="Subtotal" right={fmt(subtotal)} />
        {tip > 0 && <Row left="Propina" right={fmt(tip)} />}
        <DoubleLine />
        <Row left="TOTAL" right={fmt(total)} bold big />
        <DoubleLine />

        {/* Payments */}
        {sale.payments && sale.payments.length > 0 && (
          <>
            {sale.payments.map((p, i) => (
              <Row key={i} left={`Pago: ${PM_LABELS[p.method] || p.method}`} right={fmt(toNumber(p.amount))} />
            ))}
            <Dash />
          </>
        )}

        {/* Footer */}
        <div style={{ textAlign: "center", marginTop: 4 }}>
          <div style={{ fontSize: 11, color: "#555" }}>{tenant?.receipt_footer || "Gracias por su compra"}</div>
          <div style={{ fontSize: 9, color: "#999", marginTop: 4 }}>
            Venta #{sale.sale_number ?? sale.id} · {fmtDt(sale.created_at)}
          </div>
        </div>
      </div>
    </div>
  );
}
