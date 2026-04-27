"use client";

import React from "react";
import { C } from "@/lib/theme";
import { Btn, FlowRow, fmt, fmtDate, type Session } from "./CajaShared";

interface CajaLiveSessionProps {
  session: Session;
  busy: boolean;
  onShowMove: () => void;
  onShowClose: () => void;
}

export function CajaLiveSession({ session, busy, onShowMove, onShowClose }: CajaLiveSessionProps) {
  const live = session.live;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* Header */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "16px 20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>{session.register_name}</div>
          <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>
            Abierto por <b style={{ color: C.text }}>{session.opened_by}</b> · {fmtDate(session.opened_at)}
          </div>
        </div>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 12px", borderRadius: 99, background: C.greenBg, border: `1px solid ${C.greenBd}`, color: C.green, fontSize: 12, fontWeight: 700 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: C.green }} />
          Sesion abierta
        </div>
      </div>

      {/* Sales breakdown */}
      {live && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden" }}>
          <div style={{ padding: "12px 20px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontWeight: 700, fontSize: 13 }}>Ventas del turno</div>
          <div style={{ padding: "8px 20px" }}>
            {[
              { label: "Efectivo", amount: live.cash_sales },
              { label: "Debito", amount: live.debit_sales },
              { label: "Credito", amount: live.card_sales },
              { label: "Transferencia", amount: live.transfer_sales },
            ].map(r => (
              <FlowRow key={r.label} label={r.label} amount={r.amount} color={Number(r.amount) > 0 ? C.green : C.mid} />
            ))}
            <div style={{ borderTop: `2px solid ${C.border}`, marginTop: 4, paddingTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>Total ventas</span>
              <span style={{ fontSize: 20, fontWeight: 900, color: C.text, fontVariantNumeric: "tabular-nums" }}>${fmt(live.total_sales)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Propinas del turno (por método de pago).
          Mario lo pidió: "los chicos quieren ver durante el turno cuanto
          va de propina por débito/crédito/efectivo". Útil para que el
          equipo sepa en tiempo real lo que llevan acumulado. */}
      {live && Number((live as any).total_tips ?? 0) > 0 && (
        <div style={{ background: C.amberBg, border: `1px solid ${C.amberBd}`, borderRadius: C.rMd, overflow: "hidden" }}>
          <div style={{ padding: "12px 20px", background: C.amber, color: "#fff", fontWeight: 700, fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>💵 Propinas del turno</span>
            <span style={{ fontSize: 16, fontWeight: 900, fontVariantNumeric: "tabular-nums" }}>
              ${fmt((live as any).total_tips ?? 0)}
            </span>
          </div>
          <div style={{ padding: "8px 20px", background: C.surface }}>
            {(() => {
              const tbm = (live as any).tips_by_method as Record<string, string> | undefined;
              const tcbm = (live as any).tip_count_by_method as Record<string, number> | undefined;
              if (!tbm) return null;
              const rows: { method: string; label: string; amount: string; count: number; icon: string }[] = [
                { method: "cash",     label: "Efectivo",      amount: tbm.cash     || "0", count: tcbm?.cash     || 0, icon: "💵" },
                { method: "debit",    label: "Débito",        amount: tbm.debit    || "0", count: tcbm?.debit    || 0, icon: "💳" },
                { method: "card",     label: "Crédito",       amount: tbm.card     || "0", count: tcbm?.card     || 0, icon: "💳" },
                { method: "transfer", label: "Transferencia", amount: tbm.transfer || "0", count: tcbm?.transfer || 0, icon: "🏦" },
              ].filter(r => Number(r.amount) > 0);
              if (rows.length === 0) return <div style={{ padding: "8px 0", fontSize: 12, color: C.mute, fontStyle: "italic" }}>Sin propinas todavía en este turno.</div>;
              return rows.map(r => (
                <div key={r.method} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: `1px solid ${C.border}` }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 18 }}>{r.icon}</span>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{r.label}</div>
                      <div style={{ fontSize: 10, color: C.mute }}>{r.count} {r.count === 1 ? "venta" : "ventas"}</div>
                    </div>
                  </div>
                  <span style={{ fontSize: 14, fontWeight: 700, color: C.amber, fontVariantNumeric: "tabular-nums" }}>${fmt(r.amount)}</span>
                </div>
              ));
            })()}
            <div style={{ paddingTop: 6, fontSize: 10, color: C.mute, fontStyle: "italic" }}>
              Las propinas son del equipo — no se mezclan con ventas del local.
            </div>
          </div>
        </div>
      )}

      {/* Cash flow */}
      {live && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden" }}>
          <div style={{ padding: "12px 20px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontWeight: 700, fontSize: 13 }}>Flujo de caja (efectivo fisico)</div>
          <div style={{ padding: "8px 20px" }}>
            <FlowRow label="Fondo inicial" amount={live.initial_amount} color={C.green} />
            <div style={{ borderTop: `1px solid ${C.border}` }} />
            <FlowRow label="Ventas en efectivo" amount={live.cash_sales} color={C.green} />
            <FlowRow label="Propinas en efectivo" amount={live.cash_tips} color={C.green} />
            <FlowRow label="Ingresos manuales" amount={live.movements_in} color={C.green} />
            <FlowRow label="Egresos / Retiros" amount={`-${live.movements_out}`} color={Number(live.movements_out) > 0 ? C.red : C.mid} />
            <div style={{ borderTop: `2px solid ${C.border}`, marginTop: 4, paddingTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>Efectivo esperado en caja</span>
              <span style={{ fontSize: 22, fontWeight: 900, color: C.accent, fontVariantNumeric: "tabular-nums" }}>${fmt(live.expected_cash)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Movements */}
      {session.movements && session.movements.length > 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden" }}>
          <div style={{ padding: "12px 20px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontWeight: 700, fontSize: 13 }}>Movimientos no-venta</div>
          {session.movements.map(m => (
            <div key={m.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 20px", borderBottom: `1px solid ${C.border}` }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{m.description}</div>
                <div style={{ fontSize: 11, color: C.mute }}>{fmtDate(m.created_at)} · {m.created_by}</div>
              </div>
              <span style={{ fontSize: 14, fontWeight: 700, color: m.type === "IN" ? C.green : C.red, fontVariantNumeric: "tabular-nums" }}>
                {m.type === "IN" ? "+" : "-"}${fmt(m.amount)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: "flex", gap: 10 }}>
        <Btn variant="secondary" onClick={onShowMove} disabled={busy}>+ Agregar movimiento</Btn>
        <Btn variant="danger" onClick={onShowClose} disabled={busy}>Cerrar arqueo</Btn>
      </div>
    </div>
  );
}
