"use client";

import React, { useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { fmt, fmtDate, FlowRow, type Session } from "./CajaShared";

interface CajaHistoryProps {
  history: Session[];
  histLoad: boolean;
  histPage: number;
  histTotal: number;
  onPageChange: (page: number) => void;
}

export function CajaHistory({ history, histLoad, histPage, histTotal, onPageChange }: CajaHistoryProps) {
  // Mario lo pidió en el historial: "no me deja ver detalles, cuanto es
  // de debito efectivo credito etc". Cada arqueo cerrado ahora se puede
  // clickear para abrir un modal con el desglose completo (estilo Fudo:
  // ventas por método, propinas, movimientos, expected vs contado).
  const [selectedId, setSelectedId] = useState<number | null>(null);

  if (histLoad) return <div style={{ textAlign: "center", padding: 48 }}><Spinner /></div>;
  if (history.length === 0) return <div style={{ padding: 32, textAlign: "center", color: C.mute, fontSize: 14 }}>Sin arqueos cerrados.</div>;

  const totalPages = Math.ceil(histTotal / 20);

  return (
    <>
      <div style={{ display: "grid", gap: 10 }}>
        {history.map(s => {
          const diff = Number(s.difference ?? 0);
          return (
            <button
              type="button"
              key={s.id}
              onClick={() => setSelectedId(s.id)}
              className="ib"
              style={{
                background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd,
                padding: "14px 18px", textAlign: "left", cursor: "pointer", fontFamily: "inherit",
                width: "100%",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: C.text }}>{s.register_name}</div>
                  <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>
                    {fmtDate(s.opened_at)} → {s.closed_at ? fmtDate(s.closed_at) : "—"}
                  </div>
                  <div style={{ fontSize: 12, color: C.mute }}>Cajero: {s.opened_by}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 11, color: C.mute }}>Diferencia</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: diff >= 0 ? C.green : C.red, fontVariantNumeric: "tabular-nums" }}>
                    {diff >= 0 ? "+" : ""}${fmt(Math.abs(diff))}
                  </div>
                </div>
              </div>
              <div style={{ marginTop: 10, display: "flex", gap: 24, fontSize: 12, color: C.mid, alignItems: "center" }}>
                <span>Esperado: <b style={{ color: C.text }}>${fmt(s.expected_cash ?? 0)}</b></span>
                <span>Contado: <b style={{ color: C.text }}>${fmt(s.counted_cash ?? 0)}</b></span>
                <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 600, color: C.accent }}>Ver detalle →</span>
              </div>
            </button>
          );
        })}
      </div>

      {histTotal > 20 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 12 }}>
          <button
            type="button"
            disabled={histPage <= 1}
            onClick={() => onPageChange(histPage - 1)}
            style={{ padding: "6px 14px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: histPage <= 1 ? "default" : "pointer", opacity: histPage <= 1 ? 0.4 : 1, fontSize: 13 }}
          >← Anterior</button>
          <span style={{ fontSize: 13, color: C.mid, alignSelf: "center" }}>
            Pagina {histPage} de {totalPages}
          </span>
          <button
            type="button"
            disabled={histPage >= totalPages}
            onClick={() => onPageChange(histPage + 1)}
            style={{ padding: "6px 14px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: histPage >= totalPages ? "default" : "pointer", opacity: histPage >= totalPages ? 0.4 : 1, fontSize: 13 }}
          >Siguiente →</button>
        </div>
      )}

      {selectedId !== null && (
        <SessionDetailModal sessionId={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// SessionDetailModal — desglose completo de un arqueo cerrado.
//
// Lo que muestra (estilo Fudo):
//   - Header: caja + fechas + cajero + diferencia
//   - Ventas por método (efectivo / débito / crédito / transferencia)
//   - Propinas por método (si las hubo)
//   - Flujo de caja: fondo, ventas en efectivo, propinas en efectivo,
//     movimientos manuales, esperado, contado, diferencia.
//   - Movimientos no-venta (si los hubo)
// ─────────────────────────────────────────────────────────────────────────
function SessionDetailModal({ sessionId, onClose }: { sessionId: number; onClose: () => void }) {
  const [session, setSession] = React.useState<Session | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr]         = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true); setErr(null);
    apiFetch(`/caja/sessions/${sessionId}/`)
      .then((data: any) => { if (!cancelled) setSession(data as Session); })
      .catch(e => { if (!cancelled) setErr(e?.message || "Error cargando arqueo"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId]);

  // Cierra con ESC / back-button
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(0,0,0,0.5)",
        display: "flex", alignItems: "flex-start", justifyContent: "center",
        overflowY: "auto", padding: "30px 12px",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: "100%", maxWidth: 560,
          background: C.surface, borderRadius: 12,
          boxShadow: "0 16px 56px rgba(0,0,0,0.25)",
          overflow: "hidden",
          animation: "mIn 0.22s cubic-bezier(0.34,1.38,0.64,1) both",
        }}
      >
        {/* Header */}
        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 800, color: C.text }}>Detalle de arqueo</div>
            {session && <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{session.register_name} · Cajero: {session.opened_by}</div>}
          </div>
          <button type="button" onClick={onClose} aria-label="Cerrar"
            style={{ width: 32, height: 32, borderRadius: 8, border: `1px solid ${C.border}`, background: C.bg, color: C.mid, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>
            ✕
          </button>
        </div>

        <div style={{ padding: "16px 18px" }}>
          {loading && <div style={{ display: "flex", justifyContent: "center", padding: 30 }}><Spinner /></div>}
          {err && (
            <div style={{ padding: "10px 12px", borderRadius: C.r, border: `1px solid ${C.redBd}`, background: C.redBg, color: C.red, fontSize: 13 }}>
              {err}
            </div>
          )}
          {session && !loading && <SessionDetailBody session={session} />}
        </div>
      </div>
    </div>
  );
}

function SessionDetailBody({ session }: { session: Session }) {
  const live = session.live;
  const diff = Number(session.difference ?? 0);

  return (
    <div style={{ display: "grid", gap: 14 }}>
      {/* Periodo */}
      <div style={{ background: C.bg, borderRadius: C.r, padding: "10px 14px", fontSize: 12, color: C.mid }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>Apertura</span><b style={{ color: C.text }}>{fmtDate(session.opened_at)}</b>
        </div>
        {session.closed_at && (
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
            <span>Cierre</span><b style={{ color: C.text }}>{fmtDate(session.closed_at)}</b>
          </div>
        )}
      </div>

      {/* Ventas por método */}
      {live && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontWeight: 700, fontSize: 12, color: C.mid, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Ventas del turno
          </div>
          <div style={{ padding: "6px 14px" }}>
            {[
              { label: "Efectivo",       amount: live.cash_sales,     icon: "💵" },
              { label: "Tarj. Débito",   amount: live.debit_sales,    icon: "💳" },
              { label: "Tarj. Crédito",  amount: live.card_sales,     icon: "💳" },
              { label: "Transferencia",  amount: live.transfer_sales, icon: "🏦" },
            ].map(r => {
              const n = Number(r.amount);
              return (
                <div key={r.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: `1px solid ${C.border}` }}>
                  <span style={{ fontSize: 13, color: C.mid, display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 16 }}>{r.icon}</span>{r.label}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: n > 0 ? C.text : C.mute, fontVariantNumeric: "tabular-nums" }}>
                    ${fmt(n)}
                  </span>
                </div>
              );
            })}
            <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 0 4px", borderTop: `2px solid ${C.border}`, marginTop: 4 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Total ventas</span>
              <span style={{ fontSize: 16, fontWeight: 900, color: C.text, fontVariantNumeric: "tabular-nums" }}>${fmt(live.total_sales)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Propinas (si las hubo) */}
      {live && Number(live.total_tips ?? 0) > 0 && (
        <div style={{ background: C.amberBg, border: `1px solid ${C.amberBd}`, borderRadius: C.rMd, overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", background: C.amber, color: "#fff", display: "flex", justifyContent: "space-between", fontWeight: 700, fontSize: 12 }}>
            <span>💵 Propinas del turno</span>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>${fmt(live.total_tips ?? 0)}</span>
          </div>
          <div style={{ padding: "6px 14px", background: C.surface }}>
            {(() => {
              const tbm = live.tips_by_method;
              if (!tbm) return null;
              const rows = [
                { method: "cash",     label: "Efectivo",       amount: tbm.cash     || "0", icon: "💵" },
                { method: "debit",    label: "Débito",         amount: tbm.debit    || "0", icon: "💳" },
                { method: "card",     label: "Crédito",        amount: tbm.card     || "0", icon: "💳" },
                { method: "transfer", label: "Transferencia",  amount: tbm.transfer || "0", icon: "🏦" },
              ].filter(r => Number(r.amount) > 0);
              return rows.map(r => (
                <div key={r.method} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: `1px solid ${C.border}` }}>
                  <span style={{ fontSize: 12, color: C.mid, display: "flex", gap: 6, alignItems: "center" }}>
                    <span style={{ fontSize: 14 }}>{r.icon}</span>{r.label}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: C.amber, fontVariantNumeric: "tabular-nums" }}>${fmt(r.amount)}</span>
                </div>
              ));
            })()}
            <div style={{ paddingTop: 6, fontSize: 10, color: C.mute, fontStyle: "italic" }}>
              Las propinas son del equipo — no se mezclan con ventas del local.
            </div>
          </div>
        </div>
      )}

      {/* Flujo de caja físico */}
      {live && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontWeight: 700, fontSize: 12, color: C.mid, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Flujo de caja (efectivo físico)
          </div>
          <div style={{ padding: "4px 14px" }}>
            <FlowRow label="Fondo inicial" amount={live.initial_amount} color={C.green} />
            <div style={{ borderTop: `1px solid ${C.border}` }} />
            <FlowRow label="Ventas en efectivo" amount={live.cash_sales} color={C.green} />
            <FlowRow label="Propinas en efectivo" amount={live.cash_tips} color={C.green} />
            <FlowRow label="Ingresos manuales" amount={live.movements_in} color={C.green} />
            <FlowRow label="Egresos / Retiros" amount={`-${live.movements_out}`} color={Number(live.movements_out) > 0 ? C.red : C.mid} />
            <div style={{ borderTop: `2px solid ${C.border}`, paddingTop: 10, paddingBottom: 6, display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Esperado en caja</span>
              <span style={{ fontSize: 16, fontWeight: 900, color: C.accent, fontVariantNumeric: "tabular-nums" }}>${fmt(live.expected_cash)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Reconciliación cierre */}
      <div style={{ background: diff === 0 ? C.greenBg : (diff > 0 ? "#FEF3C7" : C.redBg), border: `1px solid ${diff === 0 ? C.greenBd : (diff > 0 ? "#F59E0B" : C.redBd)}`, borderRadius: C.rMd, padding: "12px 14px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
          Cierre del arqueo
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
          <span style={{ color: C.mid }}>Esperado</span>
          <span style={{ fontWeight: 700, color: C.text, fontVariantNumeric: "tabular-nums" }}>${fmt(session.expected_cash ?? 0)}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
          <span style={{ color: C.mid }}>Contado por cajero</span>
          <span style={{ fontWeight: 700, color: C.text, fontVariantNumeric: "tabular-nums" }}>${fmt(session.counted_cash ?? 0)}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, paddingTop: 8, marginTop: 4, borderTop: `1px dashed ${C.border}` }}>
          <span style={{ fontWeight: 700, color: C.text }}>Diferencia</span>
          <span style={{ fontWeight: 900, color: diff === 0 ? C.green : (diff > 0 ? "#D97706" : C.red), fontVariantNumeric: "tabular-nums", fontSize: 16 }}>
            {diff >= 0 ? "+" : ""}${fmt(Math.abs(diff))}
          </span>
        </div>
        {diff !== 0 && (
          <div style={{ fontSize: 11, color: C.mute, marginTop: 6, fontStyle: "italic" }}>
            {diff > 0 ? "Sobró efectivo en caja respecto a lo esperado." : "Faltó efectivo respecto a lo esperado."}
          </div>
        )}
        {session.note && (
          <div style={{ marginTop: 10, padding: "8px 10px", background: C.surface, borderRadius: 6, fontSize: 12, color: C.mid }}>
            <b style={{ color: C.text }}>Nota:</b> {session.note}
          </div>
        )}
      </div>

      {/* Movimientos no-venta */}
      {session.movements && session.movements.length > 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontWeight: 700, fontSize: 12, color: C.mid, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Movimientos no-venta ({session.movements.length})
          </div>
          {session.movements.map(m => (
            <div key={m.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", borderBottom: `1px solid ${C.border}` }}>
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
    </div>
  );
}
