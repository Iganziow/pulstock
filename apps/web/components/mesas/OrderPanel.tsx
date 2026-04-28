"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { useIsMobile } from "@/hooks/useIsMobile";
import { MesaBtn as Btn } from "./MesaBtn";
import { PaymentModal } from "./PaymentModal";
import { AddItemPanel } from "./AddItemPanel";
import { AddItemFullscreen } from "./AddItemFullscreen";
import { Order, OrderLine, PaymentRow } from "./types";
import { fmt, fmtTime, timeAgo } from "./helpers";

interface OrderPanelProps {
  order: Order;
  tableName: string;
  isCounter: boolean;
  onRefresh: () => void;
  onClose: () => void;
  onOrderUpdate: (o: Order) => void;
  canConsumoInterno?: boolean;
}

export function OrderPanel({ order, tableName, isCounter, onRefresh, onClose, onOrderUpdate, canConsumoInterno }: OrderPanelProps) {
  const mob = useIsMobile();
  const [showPayment, setShowPayment] = useState(false);
  // Pantalla full-screen para agregar items en móvil. Reemplaza al
  // AddItemPanel inline (que en mobile competía con el botón "Cobrar"
  // por espacio y dejaba el dropdown de búsqueda tapado). Mario reportó
  // "no aparece nada al buscar" — este modal lo soluciona dándole toda
  // la pantalla al search + lista.
  const [showAddFullscreen, setShowAddFullscreen] = useState(false);
  const [deletingLine, setDeletingLine] = useState<number | null>(null);
  const [confirmDeleteLine, setConfirmDeleteLine] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [payLoading, setPayLoading] = useState(false);
  const [payErr, setPayErr] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  // Lock por botón para evitar doble-click. Mario reportó: si apreta
  // muchas veces el botón de imprimir, salía error (la BT no soporta
  // operaciones concurrentes). Hay un lock global en printer.ts pero
  // queremos también deshabilitar el botón para que el feedback sea
  // visual y el usuario no piense que "no pasa nada".
  const [printing, setPrinting] = useState<null | "comanda" | "precuenta" | "boleta">(null);
  const [cancelling, setCancelling] = useState(false);
  const [cancelErr, setCancelErr] = useState("");

  async function cancelOrder() {
    if (!confirm("¿Cerrar esta mesa sin cobrar?")) return;
    setCancelling(true); setCancelErr("");
    try {
      await apiFetch(`/tables/orders/${order.id}/cancel/`, { method: "POST" });
      onClose();
      onRefresh();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error al cancelar";
      setCancelErr(msg);
    } finally { setCancelling(false); }
  }

  const unpaidLines = order.lines.filter(l => !l.is_paid && !l.is_cancelled);
  const cancelledLines = order.lines.filter(l => l.is_cancelled);
  const paidLines = order.lines.filter(l => l.is_paid);

  const [quickPayLine, setQuickPayLine] = useState<OrderLine | null>(null);

  async function handleSendComanda() {
    // Comanda: ticket sin precios para cocina/bar/despacho. Se splittea
    // automáticamente por estación según el `print_station_id` que viene
    // resuelto en cada línea desde el backend.
    if (!unpaidLines.length) {
      setPayErr("No hay items pendientes para enviar a comanda.");
      return;
    }
    // Guard contra doble-click: si ya hay impresión en curso, ignorar.
    if (printing) return;
    setPrinting("comanda");
    try {
      const { printUniversal, splitLinesByStation } = await import("@/lib/printer");
      const { buildComanda, buildComandaHTML } = await import("@/lib/receipt-builder");
      const { isUserCancellation } = await import("@/lib/errors");

      // Cargar nombres de estaciones para el header del ticket
      let stationsByName: Record<number, string> = {};
      try {
        const sList: any[] = await apiFetch("/printing/stations/");
        for (const s of sList || []) stationsByName[s.id] = s.name;
      } catch { /* ok seguir sin nombres */ }

      const groups = splitLinesByStation(
        unpaidLines.map(l => ({
          id: l.id,
          product_name: l.product_name,
          qty: parseFloat(l.qty),
          line_total: parseFloat(l.line_total),
          print_station_id: (l as any).print_station_id ?? null,
        }))
      );

      const ref = order.customer_name || tableName;
      const errors: string[] = [];
      let printed = 0;

      for (const g of groups) {
        const stationName = g.stationId ? stationsByName[g.stationId] : "";
        const data = {
          reference: ref,
          stationName: stationName || (g.stationId ? `Estación #${g.stationId}` : "Comanda"),
          lines: g.lines.map(l => ({ name: l.product_name, qty: l.qty, total: l.line_total })),
          attendedBy: order.opened_by,
          date: new Date(),
        };
        const r = await printUniversal({
          bytes: buildComanda(data, 80),
          html: buildComandaHTML(data),
          paperWidth: 80,
          source: "comanda",
          stationId: g.stationId,
        });
        if (r.ok) printed += 1;
        else if (!(r as any).cancelled) errors.push(`${data.stationName}: ${r.error || "error"}`);
      }

      if (errors.length > 0 && printed === 0) {
        setPayErr(`No se imprimió ninguna comanda:\n${errors.join("\n")}`);
      } else if (errors.length > 0) {
        setPayErr(`Algunas estaciones fallaron:\n${errors.join("\n")}`);
        setSuccessMsg(`Se imprimieron ${printed} de ${groups.length} comandas`);
        setTimeout(() => setSuccessMsg(""), 5000);
      } else if (printed > 0) {
        setSuccessMsg(
          groups.length === 1
            ? "Comanda enviada"
            : `Comandas enviadas a ${groups.length} estaciones`
        );
        setTimeout(() => setSuccessMsg(""), 4000);
      }
    } catch (e: unknown) {
      const { isUserCancellation } = await import("@/lib/errors");
      if (isUserCancellation(e)) return;
      setPayErr(e instanceof Error ? e.message : "Error al enviar comanda");
    } finally {
      setPrinting(null);
    }
  }

  async function handlePrintPreCuenta() {
    if (!unpaidLines.length) {
      setPayErr("No hay items pendientes para imprimir en la pre-cuenta.");
      return;
    }
    if (printing) return;  // anti doble-click
    setPrinting("precuenta");
    try {
      const { getDefaultPrinter, printUniversal } = await import("@/lib/printer");
      const { buildPreCuenta, buildPreCuentaHTML } = await import("@/lib/receipt-builder");
      const tenantData = await apiFetch("/core/settings/").catch(() => null);
      const data = {
        tableName: order.customer_name || tableName,
        lines: unpaidLines.map(l => ({ name: l.product_name, qty: parseFloat(l.qty), total: parseFloat(l.line_total) })),
        subtotal: parseFloat(order.subtotal_unpaid || "0"),
        date: new Date(),
        attendedBy: order.opened_by,
        tenant: tenantData ? { name: tenantData.name, rut: tenantData.rut, address: tenantData.address, receipt_header: tenantData.receipt_header } : undefined,
      };
      const local = getDefaultPrinter();
      const paperWidth: 58 | 80 = (local?.paperWidth as 58 | 80) || 80;
      const r = await printUniversal({
        bytes: buildPreCuenta(data, paperWidth),
        html: buildPreCuentaHTML(data),
        paperWidth,
        source: "precuenta",
      });
      if (!r.ok) {
        // Si el user canceló el picker (BT/USB), no mostrar banner rojo —
        // fue su decisión, puede reintentar apretando el botón de nuevo.
        if ((r as any).cancelled) return;
        setPayErr(r.error || "No se pudo imprimir la pre-cuenta");
      }
    } catch (e: unknown) {
      // Misma lógica para excepciones no atrapadas dentro de printUniversal.
      const { isUserCancellation } = await import("@/lib/errors");
      if (isUserCancellation(e)) return;
      const msg = e instanceof Error ? e.message : "Error al imprimir pre-cuenta";
      setPayErr(msg);
    } finally {
      setPrinting(null);
    }
  }

  async function deleteLine(lineId: number) {
    if (!cancelReason.trim()) { setPayErr("Debes ingresar un motivo"); return; }
    setDeletingLine(lineId);
    try {
      const data = await apiFetch(`/tables/orders/${order.id}/lines/${lineId}/`, {
        method: "DELETE",
        body: JSON.stringify({ reason: cancelReason.trim() }),
      });
      onOrderUpdate(data);
      setConfirmDeleteLine(null);
      setCancelReason("");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error al eliminar item";
      setPayErr(msg);
    } finally { setDeletingLine(null); }
  }

  const [lastSaleId, setLastSaleId] = useState<number | null>(null);

  async function handleCheckout(payments: PaymentRow[], tip: number, mode: "all" | "partial", lineIds: number[], saleType?: string) {
    setPayLoading(true); setPayErr("");
    try {
      const payArr = payments.map(r => ({ method: r.method, amount: Number(r.amount) }));
      const res = await apiFetch(`/tables/orders/${order.id}/checkout/`, {
        method: "POST",
        body: JSON.stringify({
          mode, line_ids: mode === "partial" ? lineIds : [],
          payments: payArr, tip: tip > 0 ? tip : undefined,
          sale_type: saleType || "VENTA",
        }),
      });
      setShowPayment(false);
      const saleId = res?.sale_id || res?.id || null;
      setLastSaleId(saleId);
      setSuccessMsg("¡Cobro registrado!");
      setTimeout(() => setSuccessMsg(""), 6000);
      // Auto-print boleta tras el cobro. Modelo Fudo: SIEMPRE intentamos
      // imprimir (al PC del local), no condicionado a config en este
      // dispositivo. Si no hay agente conectado, mostramos el mensaje del
      // backend pero NO bloqueamos el cobro.
      if (saleId) {
        try {
          await handlePrintReceipt(saleId);
        } catch (e) {
          // eslint-disable-next-line no-console
          console.warn("[auto-print] falló:", e);
        }
      }
      onRefresh();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error al cobrar";
      setPayErr(msg);
    } finally { setPayLoading(false); }
  }

  async function handlePrintReceipt(saleId: number) {
    if (printing) return;  // anti doble-click
    setPrinting("boleta");
    try {
      const { getDefaultPrinter, printUniversal } = await import("@/lib/printer");
      const { buildReceipt, buildReceiptHTML } = await import("@/lib/receipt-builder");
      const [sale, tenant] = await Promise.all([
        apiFetch(`/sales/sales/${saleId}/`),
        apiFetch("/core/settings/").catch(() => null),
      ]);
      const receiptData = {
        saleNumber: sale.sale_number || sale.id,
        date: sale.created_at,
        lines: (sale.lines || []).map((l: Record<string, unknown>) => ({
          name: (l.product as Record<string, unknown>)?.name || "Producto",
          qty: l.qty,
          unitPrice: l.unit_price,
          total: l.line_total,
        })),
        subtotal: parseFloat(sale.subtotal || "0"),
        tip: parseFloat(sale.tip || "0"),
        total: parseFloat(sale.total || "0"),
        payments: (sale.payments || []).map((p: Record<string, unknown>) => ({ method: p.method, amount: p.amount })),
        tenant: tenant ? {
          name: tenant.name, rut: tenant.rut, address: tenant.address,
          receipt_header: tenant.receipt_header, receipt_footer: tenant.receipt_footer,
        } : undefined,
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
        // Cancelación del picker = no es error (mismo trato que pre-cuenta).
        if ((r as any).cancelled) return;
        setPayErr(r.error || "No se pudo imprimir la boleta");
      }
    } catch (e: unknown) {
      const { isUserCancellation } = await import("@/lib/errors");
      if (isUserCancellation(e)) return;
      const msg = e instanceof Error ? e.message : "Error al imprimir boleta";
      setPayErr(msg);
    } finally {
      setPrinting(null);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 8 }}>
        <button type="button" aria-label="Volver" onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 2, display: "flex", borderRadius: 4 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <span style={{ fontSize: 16 }}>{isCounter ? "📦" : "🪑"}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 800, fontSize: 15, color: C.text }}>
            {order.customer_name || tableName}
          </div>
          <div style={{ fontSize: 10, color: C.mute }}>
            {order.customer_name && <>{tableName} &middot; </>}
            {order.opened_by} &middot; {fmtTime(order.opened_at)} &middot; {timeAgo(order.opened_at)}
          </div>
        </div>
        {unpaidLines.length > 0 && (
          <>
            <button type="button" onClick={handleSendComanda}
              disabled={!!printing}
              title={printing ? "Imprimiendo..." : "Enviar comanda a cocina/bar"}
              style={{ background: C.accentBg, border: `1px solid ${C.accentBd}`, borderRadius: 6, cursor: printing ? "wait" : "pointer", padding: "4px 8px", display: "flex", alignItems: "center", gap: 4, color: C.accent, fontSize: 11, fontWeight: 700, opacity: printing ? 0.5 : 1 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M3 12h3l3-9 6 18 3-9h3"/>
              </svg>
              {printing === "comanda" ? "Enviando..." : "Comanda"}
            </button>
            <button type="button" onClick={handlePrintPreCuenta}
              disabled={!!printing}
              title={printing ? "Imprimiendo..." : "Imprimir pre-cuenta"}
              style={{ background: "none", border: `1px solid ${C.border}`, borderRadius: 6, cursor: printing ? "wait" : "pointer", padding: "4px 8px", display: "flex", alignItems: "center", gap: 4, color: C.mid, fontSize: 11, fontWeight: 600, opacity: printing ? 0.5 : 1 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>
              </svg>
              {printing === "precuenta" ? "Imprimiendo..." : "Pre-cuenta"}
            </button>
          </>
        )}
      </div>

      {successMsg && (
        <div style={{ margin: "8px 16px 0", padding: "6px 10px", borderRadius: C.r, background: C.greenBg, border: `1px solid ${C.greenBd}`, color: C.green, fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ flex: 1 }}>{successMsg}</span>
          {lastSaleId && (
            <button type="button" onClick={() => handlePrintReceipt(lastSaleId)}
              disabled={!!printing}
              style={{ background: C.green, color: "#fff", border: "none", borderRadius: 4, padding: "3px 8px", fontSize: 10, fontWeight: 700, cursor: printing ? "wait" : "pointer", display: "flex", alignItems: "center", gap: 4, whiteSpace: "nowrap", opacity: printing ? 0.6 : 1 }}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>
              </svg>
              {printing === "boleta" ? "Imprimiendo..." : "Imprimir"}
            </button>
          )}
        </div>
      )}

      {/* Body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "10px 16px" }}>
        {/* Unpaid lines */}
        {unpaidLines.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
              Pendiente ({unpaidLines.length})
            </div>
            <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden", background: C.surface }}>
              {unpaidLines.map((l, idx) => (
                <div key={l.id} style={{ borderBottom: idx < unpaidLines.length - 1 ? `1px solid ${C.border}` : "none" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 12px" }}>
                    {/* Qty badge */}
                    <div style={{
                      width: 28, height: 28, borderRadius: 8,
                      background: C.accent + "14", border: `1px solid ${C.accentBd}`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 12, fontWeight: 800, color: C.accent, flexShrink: 0,
                    }}>{parseFloat(l.qty) % 1 === 0 ? Math.round(parseFloat(l.qty)) : parseFloat(l.qty)}</div>

                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{l.product_name}</div>
                      {l.note && (
                        <div style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10, color: C.amber, marginTop: 2, padding: "1px 6px", background: C.amberBg, borderRadius: 4, border: `1px solid ${C.amberBd}`, width: "fit-content" }}>
                          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                          {l.note}
                        </div>
                      )}
                      <div style={{ fontSize: 10, color: C.mute, marginTop: 1 }}>${fmt(l.unit_price)} c/u</div>
                    </div>

                    <div style={{ fontWeight: 800, fontSize: 14, color: C.text, whiteSpace: "nowrap", flexShrink: 0 }}>${fmt(l.line_total)}</div>

                    <div style={{ display: "flex", gap: 3, flexShrink: 0 }}>
                      <button type="button" onClick={() => { setPayErr(""); setQuickPayLine(l); }} title="Cobrar item"
                        style={{ width: 34, height: 34, borderRadius: 6, background: C.greenBg, border: `1px solid ${C.greenBd}`, cursor: "pointer", color: C.green, display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                      </button>
                      <button type="button" aria-label="Eliminar" onClick={() => { setConfirmDeleteLine(l.id); setCancelReason(""); setPayErr(""); }} disabled={deletingLine === l.id}
                        style={{ width: 34, height: 34, borderRadius: 6, background: C.redBg, border: `1px solid ${C.redBd}`, cursor: "pointer", color: C.red, display: "flex", alignItems: "center", justifyContent: "center", opacity: deletingLine === l.id ? 0.4 : 1 }}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
                      </button>
                    </div>
                  </div>
                  {confirmDeleteLine === l.id && (
                    <div style={{ padding: "6px 12px 10px", background: C.redBg, display: "flex", flexDirection: "column", gap: 6 }}>
                      <input value={cancelReason} onChange={e => setCancelReason(e.target.value)}
                        placeholder="Motivo de cancelación (obligatorio)" autoFocus
                        style={{ width: "100%", padding: "8px 10px", border: `1.5px solid ${C.redBd}`, borderRadius: 6, fontSize: 12, background: "#fff", outline: "none", fontFamily: "inherit", color: C.text }} />
                      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                        <button type="button" onClick={() => { setConfirmDeleteLine(null); setCancelReason(""); }}
                          style={{ padding: "5px 14px", borderRadius: 6, border: `1px solid ${C.border}`, background: "#fff", cursor: "pointer", fontSize: 11, fontWeight: 600, fontFamily: "inherit", color: C.mid }}>Cancelar</button>
                        <button type="button" onClick={() => deleteLine(l.id)} disabled={deletingLine === l.id || !cancelReason.trim()}
                          style={{ padding: "5px 14px", borderRadius: 6, border: "none", background: C.red, cursor: cancelReason.trim() ? "pointer" : "not-allowed", fontSize: 11, fontWeight: 600, fontFamily: "inherit", color: "#fff", opacity: cancelReason.trim() ? 1 : 0.5 }}>
                          {deletingLine === l.id ? <Spinner size={10} /> : "Eliminar"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
              {/* Total row */}
              <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 12px", background: C.bg, borderTop: `1px solid ${C.border}` }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: C.mid }}>Total</span>
                <span style={{ fontSize: 18, fontWeight: 900, color: C.text }}>${fmt(order.subtotal_unpaid)}</span>
              </div>
            </div>
          </div>
        )}

        {/* Cancelled lines */}
        {cancelledLines.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.red, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
              Cancelado ({cancelledLines.length})
            </div>
            {cancelledLines.map(l => (
              <div key={l.id} style={{ padding: "4px 0" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, opacity: 0.5 }}>
                  <span style={{ flex: 1, fontSize: 11, color: C.red, textDecoration: "line-through" }}>{l.product_name}</span>
                  <span style={{ fontSize: 11, color: C.red, textDecoration: "line-through" }}>${fmt(l.line_total)}</span>
                </div>
                {l.cancel_reason && (
                  <div style={{ fontSize: 10, color: C.red, marginTop: 2, paddingLeft: 2, fontStyle: "italic", opacity: 0.7 }}>
                    Motivo: {l.cancel_reason}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Paid lines */}
        {paidLines.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
              Cobrado ({paidLines.length})
            </div>
            {paidLines.map(l => (
              <div key={l.id} style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 0", opacity: 0.4 }}>
                <span style={{ flex: 1, fontSize: 11, color: C.mid, textDecoration: "line-through" }}>{l.product_name}</span>
                <span style={{ fontSize: 11, color: C.mute, textDecoration: "line-through" }}>${fmt(l.line_total)}</span>
              </div>
            ))}
          </div>
        )}

        {order.lines.length === 0 && (
          <div style={{ textAlign: "center", color: C.mute, fontSize: 13, padding: "24px 0" }}>
            <div style={{ fontSize: 28, marginBottom: 6 }}>🍽️</div>
            Sin items — busca productos abajo.
          </div>
        )}

        {/* Add items — embebido en desktop, botón → modal full-screen en móvil */}
        <div style={{
          marginTop: 12, paddingTop: 12, borderTop: `1px solid ${C.border}`,
        }}>
          {mob ? (
            // Móvil: botón grande que abre el modal full-screen estilo Wabi.
            // El modal le da TODA la pantalla al search + lista de productos
            // sin compartirla con el botón "Cobrar" → resuelve el bug del
            // dropdown tapado.
            <button
              type="button"
              onClick={() => setShowAddFullscreen(true)}
              style={{
                width: "100%", padding: "16px 18px",
                border: `2px dashed ${C.accentBd}`, borderRadius: 12,
                background: C.accentBg, color: C.accent,
                fontSize: 15, fontWeight: 700, cursor: "pointer",
                fontFamily: C.font,
                display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              Adicionar productos
            </button>
          ) : (
            <>
              <div style={{ fontSize: 11, fontWeight: 700, color: C.accent, textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
                Agregar productos
              </div>
              <AddItemPanel orderId={order.id} onAdded={async () => {
                try {
                  const updated = await apiFetch(`/tables/orders/${order.id}/`);
                  onOrderUpdate(updated);
                } catch { /* parent refresh will cover it */ }
                onRefresh();
              }} />
            </>
          )}
        </div>
      </div>

      {/* Footer */}
      {(payErr || cancelErr) && <div style={{ margin: "0 16px 6px", padding: "6px 10px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 11 }}>{payErr || cancelErr}</div>}
      <div style={{ padding: "10px 16px", borderTop: `1px solid ${C.border}`, display: "flex", gap: 8 }}>
        {unpaidLines.length === 0 && (
          <Btn variant="danger" disabled={cancelling} onClick={cancelOrder}>
            {cancelling ? <Spinner size={13} /> : null}
            Cerrar mesa
          </Btn>
        )}
        {unpaidLines.length > 0 && (
          <Btn variant="primary" full size="lg" onClick={() => { setPayErr(""); setShowPayment(true); }}>
            Cobrar ${fmt(order.subtotal_unpaid)}
          </Btn>
        )}
      </div>

      {showPayment && (
        <PaymentModal total={Number(order.subtotal_unpaid)} tableName={order.customer_name || tableName}
          unpaidLines={unpaidLines} onClose={() => setShowPayment(false)}
          loading={payLoading} onConfirm={handleCheckout} canConsumoInterno={canConsumoInterno} error={payErr} />
      )}
      {quickPayLine && (
        <PaymentModal total={Number(quickPayLine.line_total)} tableName={`${quickPayLine.product_name}`}
          unpaidLines={[quickPayLine]} onClose={() => setQuickPayLine(null)}
          loading={payLoading} onConfirm={(payments, tip, _mode, _lineIds) => {
            handleCheckout(payments, tip, "partial", [quickPayLine.id]);
            setQuickPayLine(null);
          }} />
      )}

      {/* Modal full-screen para agregar productos (solo móvil). Le pasamos
          el tableName para mostrarlo en el header del modal y los callbacks
          para refrescar la mesa y cerrarse. */}
      {showAddFullscreen && (
        <AddItemFullscreen
          orderId={order.id}
          tableName={order.customer_name || tableName}
          onAdded={async () => {
            try {
              const updated = await apiFetch(`/tables/orders/${order.id}/`);
              onOrderUpdate(updated);
            } catch { /* parent refresh will cover it */ }
            onRefresh();
          }}
          onClose={() => setShowAddFullscreen(false)}
        />
      )}
    </div>
  );
}
