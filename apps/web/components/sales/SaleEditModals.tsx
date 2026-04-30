"use client";

/**
 * Modales para editar una venta cerrada (manager/owner).
 * - EditPaymentsModal: cambiar método y monto de pagos.
 * - EditTipModal: cambiar propina.
 *
 * NO incluye edición de cantidad/líneas: corregir cantidades requiere
 * anular la venta y crear una nueva (anti-fraude — Daniel 29/04/26).
 *
 * Diseño Fudo-like: cada acción es un modal independiente. La propina
 * y el dinero del local se tratan separados (Sale.tip no entra en
 * Sale.total ni en gross_profit).
 */

import { useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";

type Method = "cash" | "card" | "debit" | "transfer";
type Payment = { method: Method; amount: string };

const METHOD_LABELS: Record<Method, string> = {
  cash: "Efectivo",
  debit: "Tarj. Débito",
  card: "Tarj. Crédito",
  transfer: "Transferencia",
};

const inputStyle: React.CSSProperties = {
  padding: "8px 10px",
  border: `1px solid ${C.border}`,
  borderRadius: 6,
  fontSize: 13,
  fontFamily: "inherit",
  background: C.surface,
  color: C.text,
  width: "100%",
};

/** Formatea CLP entero con separador de miles. 4000 → "4.000". */
function fmtCLPInt(n: number | string): string {
  const v = typeof n === "string" ? Number(n) : n;
  if (!Number.isFinite(v)) return "0";
  return Math.round(v).toLocaleString("es-CL");
}

/** Limpia el valor para que sea solo dígitos enteros (CLP no tiene decimales). */
function cleanIntMoney(raw: string): string {
  return raw.replace(/[^\d]/g, "");
}

/** Limpia para qty decimal: dígitos + UN solo separador (punto o coma → punto). */
function cleanQty(raw: string): string {
  // Permitir dígitos, punto, coma. Reemplazar coma por punto, dejar 1 solo punto.
  let s = raw.replace(/[^\d.,]/g, "").replace(/,/g, ".");
  const firstDot = s.indexOf(".");
  if (firstDot >= 0) {
    s = s.slice(0, firstDot + 1) + s.slice(firstDot + 1).replace(/\./g, "");
  }
  return s;
}

/** Quita ceros decimales innecesarios de una qty para mostrar.
 * "1.000" → "1", "1.500" → "1.5", "0.150" → "0.15" */
function trimQtyZeros(raw: string): string {
  if (!raw) return "";
  const n = Number(raw);
  if (!Number.isFinite(n)) return raw;
  // Si es entero, mostrar sin decimales.
  if (Number.isInteger(n)) return String(n);
  // Si tiene decimales, eliminar trailing zeros.
  return String(parseFloat(n.toFixed(6))); // máx 6 decimales para no perder precisión
}

function ModalShell({
  open, title, onClose, children, busy,
}: {
  open: boolean; title: string; onClose: () => void;
  children: React.ReactNode; busy?: boolean;
}) {
  if (!open) return null;
  return (
    <div
      onClick={() => !busy && onClose()}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000, padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: C.surface, borderRadius: C.rMd, width: 480, maxWidth: "100%",
          boxShadow: C.shLg, overflow: "hidden",
        }}
      >
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${C.border}` }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>{title}</div>
        </div>
        <div style={{ padding: "16px 20px" }}>{children}</div>
      </div>
    </div>
  );
}

function ErrorBanner({ msg }: { msg: string | null }) {
  if (!msg) return null;
  return (
    <div style={{
      padding: "8px 12px", background: C.redBg, border: `1px solid ${C.redBd}`,
      borderRadius: 6, color: C.red, fontSize: 12, marginBottom: 12,
    }}>{msg}</div>
  );
}


// ─── EditPaymentsModal ───────────────────────────────────────────────────


export function EditPaymentsModal({
  open, saleId, currentPayments, total, tip, onClose, onSaved,
}: {
  open: boolean; saleId: number; currentPayments: Payment[];
  total: number; tip: number;
  onClose: () => void; onSaved: () => void;
}) {
  // Inicializar amounts como string entero (sin decimales). 4000.00 → "4000"
  const [rows, setRows] = useState<Payment[]>(
    currentPayments.length > 0
      ? currentPayments.map(p => ({ method: p.method, amount: String(Math.round(Number(p.amount) || 0)) }))
      : [{ method: "cash", amount: "" }]
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Regla: subtotal de la venta SIEMPRE debe estar cubierto por los pagos.
  // La propina es libre (puede sumarse aparte sin afectar este cuadre).
  const total_paid = rows.reduce((s, r) => s + Number(r.amount || 0), 0);
  const required = total;
  const diff = total_paid - required;

  function updateRow(i: number, patch: Partial<Payment>) {
    setRows(rs => rs.map((r, idx) => idx === i ? { ...r, ...patch } : r));
  }
  function addRow() {
    setRows(rs => [...rs, { method: "cash", amount: "0" }]);
  }
  function removeRow(i: number) {
    setRows(rs => rs.length > 1 ? rs.filter((_, idx) => idx !== i) : rs);
  }

  async function save() {
    setBusy(true); setErr(null);
    try {
      const body = {
        payments: rows.map(r => ({
          method: r.method,
          amount: String(Number(r.amount || 0)),
        })),
      };
      await apiFetch(`/sales/sales/${saleId}/payments/`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      onSaved();
      onClose();
    } catch (e: any) {
      setErr(e instanceof ApiError ? e.message : (e?.message ?? "Error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ModalShell open={open} title="Editar método de pago" onClose={onClose} busy={busy}>
      <ErrorBanner msg={err} />
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
        {rows.map((r, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 36px", gap: 8 }}>
            <select
              value={r.method}
              onChange={e => updateRow(i, { method: e.target.value as Method })}
              style={inputStyle}
              disabled={busy}
            >
              {(Object.keys(METHOD_LABELS) as Method[]).map(m => (
                <option key={m} value={m}>{METHOD_LABELS[m]}</option>
              ))}
            </select>
            {/* Input con formato CLP: muestra "4.000", guarda "4000". */}
            <div style={{ position: "relative" }}>
              <span style={{
                position: "absolute", left: 10, top: "50%",
                transform: "translateY(-50%)",
                fontSize: 13, color: C.mute, pointerEvents: "none",
              }}>$</span>
              <input
                type="text"
                inputMode="numeric"
                value={r.amount === "" ? "" : fmtCLPInt(r.amount)}
                onChange={e => updateRow(i, { amount: cleanIntMoney(e.target.value) })}
                style={{ ...inputStyle, paddingLeft: 22, fontVariantNumeric: "tabular-nums" }}
                disabled={busy}
                placeholder="0"
              />
            </div>
            <button
              onClick={() => removeRow(i)}
              disabled={busy || rows.length === 1}
              style={{
                background: C.redBg, color: C.red, border: `1px solid ${C.redBd}`,
                borderRadius: 6, cursor: rows.length === 1 ? "not-allowed" : "pointer",
                fontSize: 16, opacity: rows.length === 1 ? 0.5 : 1,
              }}
              title="Eliminar pago"
            >×</button>
          </div>
        ))}
        <button
          onClick={addRow}
          disabled={busy}
          style={{
            padding: "6px 12px", border: `1px dashed ${C.border}`, borderRadius: 6,
            background: "transparent", color: C.mid, fontSize: 12, cursor: "pointer",
          }}
        >
          + Agregar pago (split)
        </button>
      </div>

      <div style={{
        padding: "10px 12px", background: C.bg, borderRadius: 6,
        fontSize: 12, color: C.mute, marginBottom: 14,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>Subtotal de la venta:</span>
          <span style={{ fontWeight: 700, color: C.text }}>${total.toLocaleString("es-CL")}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
          <span>Suma de pagos:</span>
          <span style={{ color: diff < 0 ? C.red : C.green, fontWeight: 700 }}>
            ${total_paid.toLocaleString("es-CL")}
          </span>
        </div>
        {diff < 0 && (
          <div style={{ color: C.red, fontSize: 11, marginTop: 4 }}>
            Faltan ${Math.abs(diff).toLocaleString("es-CL")} para cubrir el subtotal.
          </div>
        )}
        {tip > 0 && (
          <div style={{ fontSize: 10, color: C.mute, marginTop: 6, lineHeight: 1.4, fontStyle: "italic" }}>
            La propina (${tip.toLocaleString("es-CL")}) se trata aparte. No afecta esta validación.
          </div>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button onClick={onClose} disabled={busy} style={{
          padding: "8px 16px", border: `1px solid ${C.border}`, borderRadius: 6,
          background: C.surface, color: C.mid, cursor: "pointer",
        }}>Cancelar</button>
        <button onClick={save} disabled={busy || diff < 0} style={{
          padding: "8px 16px", border: "none", borderRadius: 6,
          background: C.accent, color: "#fff", cursor: busy || diff < 0 ? "not-allowed" : "pointer",
          opacity: busy || diff < 0 ? 0.5 : 1, fontWeight: 600,
        }}>{busy ? "Guardando..." : "Guardar"}</button>
      </div>
    </ModalShell>
  );
}


// ─── EditTipModal (split, Fudo-style) ────────────────────────────────────


type Tip = { method: Method; amount: string };

export function EditTipModal({
  open, saleId, currentTips, total, totalPaid, onClose, onSaved,
}: {
  open: boolean; saleId: number;
  /** Lista de propinas actuales. Si vacía, se inicializa con 1 fila cash. */
  currentTips: Tip[];
  total: number; totalPaid: number;
  onClose: () => void; onSaved: () => void;
}) {
  // Inicializar amounts como string entero (sin decimales).
  const [rows, setRows] = useState<Tip[]>(
    currentTips.length > 0
      ? currentTips.map(t => ({ method: t.method, amount: String(Math.round(Number(t.amount) || 0)) }))
      : [{ method: "cash", amount: "" }]
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function updateRow(i: number, patch: Partial<Tip>) {
    setRows(rs => rs.map((r, idx) => idx === i ? { ...r, ...patch } : r));
  }
  function addRow() {
    setRows(rs => [...rs, { method: "cash", amount: "0" }]);
  }
  function removeRow(i: number) {
    setRows(rs => rs.length > 1 ? rs.filter((_, idx) => idx !== i) : rs);
  }

  // Total de propinas (puede ser 0 → eliminar todas).
  const tipTotal = rows.reduce((s, r) => s + Number(r.amount || 0), 0);

  async function save() {
    setBusy(true); setErr(null);
    try {
      // Solo enviamos filas con monto > 0. El backend acepta lista vacía
      // como "eliminar todas las propinas" (Sale.tip queda en 0).
      const tips = rows
        .filter(r => Number(r.amount || 0) > 0)
        .map(r => ({ method: r.method, amount: String(Number(r.amount || 0)) }));
      await apiFetch(`/sales/sales/${saleId}/tip/`, {
        method: "PATCH",
        body: JSON.stringify({ tips }),
      });
      onSaved();
      onClose();
    } catch (e: any) {
      setErr(e instanceof ApiError ? e.message : (e?.message ?? "Error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ModalShell open={open} title="Editar propina" onClose={onClose} busy={busy}>
      <ErrorBanner msg={err} />
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
        {rows.map((r, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 36px", gap: 8 }}>
            <select
              value={r.method}
              onChange={e => updateRow(i, { method: e.target.value as Method })}
              style={inputStyle}
              disabled={busy}
            >
              {(Object.keys(METHOD_LABELS) as Method[]).map(m => (
                <option key={m} value={m}>{METHOD_LABELS[m]}</option>
              ))}
            </select>
            <div style={{ position: "relative" }}>
              <span style={{
                position: "absolute", left: 10, top: "50%",
                transform: "translateY(-50%)",
                fontSize: 13, color: C.mute, pointerEvents: "none",
              }}>$</span>
              <input
                type="text"
                inputMode="numeric"
                value={r.amount === "" ? "" : fmtCLPInt(r.amount)}
                onChange={e => updateRow(i, { amount: cleanIntMoney(e.target.value) })}
                style={{ ...inputStyle, paddingLeft: 22, fontVariantNumeric: "tabular-nums" }}
                disabled={busy}
                placeholder="0"
              />
            </div>
            <button
              onClick={() => removeRow(i)}
              disabled={busy || rows.length === 1}
              style={{
                background: C.redBg, color: C.red, border: `1px solid ${C.redBd}`,
                borderRadius: 6, cursor: rows.length === 1 ? "not-allowed" : "pointer",
                fontSize: 16, opacity: rows.length === 1 ? 0.5 : 1,
              }}
              title="Eliminar propina"
            >×</button>
          </div>
        ))}
        <button
          onClick={addRow}
          disabled={busy}
          style={{
            padding: "6px 12px", border: `1px dashed ${C.border}`, borderRadius: 6,
            background: "transparent", color: C.mid, fontSize: 12, cursor: "pointer",
          }}
        >
          + Agregar propina (split por método)
        </button>
      </div>

      <div style={{
        padding: "10px 12px", background: C.bg, borderRadius: 6,
        fontSize: 12, color: C.mute, marginBottom: 14, lineHeight: 1.5,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>Total propina:</span>
          <span style={{ fontWeight: 700, color: C.text }}>${tipTotal.toLocaleString("es-CL")}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
          <span>Subtotal de la venta:</span>
          <span style={{ color: C.text }}>${total.toLocaleString("es-CL")}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>Pagos registrados:</span>
          <span style={{ color: C.text }}>${totalPaid.toLocaleString("es-CL")}</span>
        </div>
        <div style={{ fontSize: 11, color: C.mute, marginTop: 6, fontStyle: "italic" }}>
          La propina es del equipo y se trata aparte del ingreso del local.
          Podés dividirla en varios métodos (ej. cliente paga débito y deja
          $300 cash + $200 transferencia).
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button onClick={onClose} disabled={busy} style={{
          padding: "8px 16px", border: `1px solid ${C.border}`, borderRadius: 6,
          background: C.surface, color: C.mid, cursor: "pointer",
        }}>Cancelar</button>
        <button onClick={save} disabled={busy} style={{
          padding: "8px 16px", border: "none", borderRadius: 6,
          background: C.accent, color: "#fff",
          cursor: busy ? "not-allowed" : "pointer",
          opacity: busy ? 0.5 : 1, fontWeight: 600,
        }}>{busy ? "Guardando..." : "Guardar"}</button>
      </div>
    </ModalShell>
  );
}
