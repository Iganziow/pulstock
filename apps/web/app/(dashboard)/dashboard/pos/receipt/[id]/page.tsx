"use client";

import { useEffect, useMemo, useState, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { useIsMobile } from "@/hooks/useIsMobile";
import { humanizeError } from "@/lib/errors";

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
@keyframes spin { to { transform: rotate(360deg); } }
`;

export default function ReceiptPage() {
  useGlobalStyles(PAGE_CSS);
  const mob = useIsMobile();
  const params = useParams<{ id: string }>();
  const saleId = Number(params?.id);

  const [sale, setSale] = useState<Sale | null>(null);
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [err, setErr]   = useState<string | null>(null);
  const [hasThermal, setHasThermal] = useState(false);
  // Estado del auto-print: idle (no se intentó), printing, done, error.
  // Mostramos un mensaje arriba del recibo para que el usuario sepa qué pasó.
  const [printStatus, setPrintStatus] = useState<"idle" | "printing" | "done" | "error">("idle");
  const [printErr, setPrintErr] = useState<string>("");
  // Evitar disparar el auto-print más de una vez si re-renderiza.
  const autoPrintTriedRef = useRef(false);

  useEffect(() => {
    if (!saleId) { setErr("ID inválido."); return; }
    // Cleanup flag — antes había un bug donde el user volvía atrás antes de
    // que terminara el fetch y el setState corría sobre componente desmontado,
    // tirando warning "can't perform setState on unmounted component" + a
    // veces error visible al usuario.
    let mounted = true;
    (async () => {
      try {
        const [data, t] = await Promise.all([
          apiFetch(`/sales/sales/${saleId}/`) as Promise<Sale>,
          apiFetch("/core/settings/").catch(() => null),
        ]);
        if (!mounted) return;
        setSale(data); setTenant(t); setErr(null);
      } catch (e: any) {
        if (!mounted) return;
        const msg = e?.message ?? "";
        const friendly = msg.includes("matches the given query") ? "No se encontró la venta solicitada." : (msg || "No se pudo cargar el recibo.");
        setErr(friendly);
      }
    })();
    return () => { mounted = false; };
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
    setPrintStatus("printing");
    setPrintErr("");
    try {
      const { getDefaultPrinter, printUniversal } = await import("@/lib/printer");
      const { buildReceipt, buildReceiptHTML } = await import("@/lib/receipt-builder");
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
      const local = getDefaultPrinter();
      const paperWidth: 58 | 80 = (local?.paperWidth as 58 | 80) || 80;
      const r = await printUniversal({
        bytes: buildReceipt(receiptData, paperWidth),
        html: buildReceiptHTML(receiptData),
        paperWidth,
        source: "pos",
      });
      if (!r.ok) {
        setPrintStatus("error");
        setPrintErr(r.error || "No se pudo imprimir");
      } else {
        setPrintStatus("done");
      }
    } catch (e: any) {
      setPrintStatus("error");
      setPrintErr(humanizeError(e, "Error al imprimir"));
    }
  }

  // Auto-print al cargar el recibo. La estrategia depende del tipo de
  // impresora configurada como default:
  //
  //  - USB / red / system (vía agente PC): siempre auto-print. No
  //    requiere user gesture porque la impresión la hace un proceso
  //    server-side / nativo, no el browser.
  //
  //  - Bluetooth: intentamos reconectar al device autorizado vía
  //    `navigator.bluetooth.getDevices()` (Chrome ≥85). Si funciona,
  //    auto-print sin pedir picker. Si el browser no soporta o el
  //    device no está autorizado, el user verá el botón "Térmica" y
  //    podrá disparar manualmente (lo que abre el picker para parear
  //    por primera vez).
  //
  // En todos los casos, solo se intenta una vez por carga (autoPrintTriedRef).
  useEffect(() => {
    if (!sale || !hasThermal || autoPrintTriedRef.current) return;
    autoPrintTriedRef.current = true;

    (async () => {
      try {
        const { getDefaultPrinter, tryReconnectBluetooth } = await import("@/lib/printer");
        const def = getDefaultPrinter();
        if (!def) return;

        if (def.type === "bluetooth") {
          // Intentar retomar device BT autorizado previamente (sin picker).
          const reconnected = await tryReconnectBluetooth();
          if (!reconnected) {
            // No hay device autorizado en este browser → el user tiene
            // que apretar "Térmica" para abrir el picker la primera vez.
            // No marcamos error — solo dejamos el botón visible.
            return;
          }
        }
        await handleThermalPrint();
      } catch { /* falla silenciosa — el user puede apretar el botón */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sale, hasThermal]);

  // Botón secundario "Imprimir en este dispositivo" — abre el diálogo nativo
  // del navegador. En mobile lo ocultamos cuando hay térmica configurada
  // (el dueño confunde el botón "Imprimir" pensando que es la térmica).
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

      {/* Top nav — hidden on print.
          Reorganizado: cuando hay térmica configurada, "Térmica" es el
          botón primario (color lleno) y "Imprimir" se oculta en mobile
          para evitar confusión (el dueño apretaba "Imprimir" pensando
          que era la térmica y le abría el dialog Android nativo). */}
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
            <button
              type="button"
              onClick={handleThermalPrint}
              disabled={printStatus === "printing"}
              style={{
                display: "inline-flex", alignItems: "center", gap: 5,
                fontSize: 11, fontWeight: 700,
                color: "#fff", padding: "6px 12px",
                border: "none", borderRadius: 6,
                background: printStatus === "printing" ? "#999" : C.accent,
                cursor: printStatus === "printing" ? "default" : "pointer",
                fontFamily: "inherit",
                opacity: printStatus === "printing" ? 0.7 : 1,
              }}
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>
              </svg>
              {printStatus === "printing" ? "Imprimiendo…" : printStatus === "done" ? "Reimprimir" : "Térmica"}
            </button>
          )}
          {/* Imprimir nativo (PDF/A4) — oculto en mobile cuando hay térmica
              porque el dueño apretaba este pensando que era la térmica.
              En desktop lo dejamos visible (sirve para guardar PDF). */}
          {(!hasThermal || !mob) && (
            <button type="button" onClick={handleBrowserPrint} style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              fontSize: 11, fontWeight: 700,
              color: hasThermal ? "#666" : "#fff",
              padding: "6px 12px",
              border: hasThermal ? "1px solid #ccc" : "none",
              borderRadius: 6,
              background: hasThermal ? "#fff" : C.accent,
              cursor: "pointer", fontFamily: "inherit",
            }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>
              </svg>
              {hasThermal ? "PDF" : "Imprimir"}
            </button>
          )}
        </div>
      </div>

      {/* Banner de estado del print — solo se muestra si hubo intento. */}
      {hasThermal && printStatus !== "idle" && (
        <div className="no-print" style={{ maxWidth: 360, margin: "0 auto 12px" }}>
          {printStatus === "printing" && (
            <div style={{
              padding: "8px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600,
              background: C.accentBg, color: C.accent, border: `1px solid ${C.accentBd}`,
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <span style={{ display: "inline-block", width: 12, height: 12, borderRadius: "50%", border: `2px solid ${C.accent}`, borderTopColor: "transparent", animation: "spin 0.8s linear infinite" }} />
              Imprimiendo el ticket…
            </div>
          )}
          {printStatus === "done" && (
            <div style={{
              padding: "8px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600,
              background: C.greenBg, color: C.green, border: `1px solid ${C.greenBd}`,
            }}>
              ✓ Ticket impreso
            </div>
          )}
          {printStatus === "error" && (
            <div style={{
              padding: "8px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600,
              background: C.redBg, color: C.red, border: `1px solid ${C.redBd}`,
            }}>
              ⚠ {printErr || "No se pudo imprimir"}. Probá apretar el botón otra vez.
            </div>
          )}
        </div>
      )}

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
