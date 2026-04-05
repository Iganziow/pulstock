"use client";

import React from "react";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { Btn, fmt, type LiveSummary } from "./CajaShared";

// ─── Add Movement Modal ─────────────────────────────────────────────────────
interface AddMovementModalProps {
  moveType: "IN" | "OUT"; setMoveType: (v: "IN" | "OUT") => void;
  moveAmt: string; setMoveAmt: (v: string) => void;
  moveDesc: string; setMoveDesc: (v: string) => void;
  busy: boolean;
  onClose: () => void;
  onSubmit: () => void;
}

export function AddMovementModal({ moveType, setMoveType, moveAmt, setMoveAmt, moveDesc, setMoveDesc, busy, onClose, onSubmit }: AddMovementModalProps) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: C.surface, borderRadius: 14, padding: 28, width: 400, boxShadow: "0 20px 52px rgba(0,0,0,0.18)" }}>
        <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 16 }}>Agregar movimiento</div>
        <div style={{ display: "grid", gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Tipo</div>
            <div style={{ display: "flex", gap: 8 }}>
              {(["IN", "OUT"] as const).map(t => (
                <button type="button" key={t} onClick={() => setMoveType(t)} style={{
                  flex: 1, padding: "8px 0", borderRadius: C.r, fontSize: 13, fontWeight: 600, cursor: "pointer",
                  background: moveType === t ? (t === "IN" ? C.greenBg : C.redBg) : C.bg,
                  border: `1px solid ${moveType === t ? (t === "IN" ? C.greenBd : C.redBd) : C.border}`,
                  color: moveType === t ? (t === "IN" ? C.green : C.red) : C.mid,
                }}>
                  {t === "IN" ? "↑ Ingreso" : "↓ Egreso"}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Monto</div>
            <input value={moveAmt} onChange={e => setMoveAmt(e.target.value)} placeholder="$0" inputMode="decimal"
              style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Descripcion</div>
            <input value={moveDesc} onChange={e => setMoveDesc(e.target.value)} placeholder="Ej: Compra de gas, Retiro para banco..."
              style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 20, justifyContent: "flex-end" }}>
          <Btn variant="ghost" onClick={onClose} disabled={busy}>Cancelar</Btn>
          <Btn variant="primary" onClick={onSubmit} disabled={busy || !moveAmt || !moveDesc}>
            {busy ? <Spinner size={14} /> : "Agregar"}
          </Btn>
        </div>
      </div>
    </div>
  );
}

// ─── Close Session Modal ─────────────────────────────────────────────────────
interface CloseSessionModalProps {
  live: LiveSummary;
  countedCash: string; setCountedCash: (v: string) => void;
  closeNote: string; setCloseNote: (v: string) => void;
  busy: boolean;
  onClose: () => void;
  onSubmit: () => void;
}

export function CloseSessionModal({ live, countedCash, setCountedCash, closeNote, setCloseNote, busy, onClose, onSubmit }: CloseSessionModalProps) {
  const difference = countedCash !== "" ? Number(countedCash) - Number(live.expected_cash) : null;

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: C.surface, borderRadius: 14, padding: 28, width: 440, boxShadow: "0 20px 52px rgba(0,0,0,0.18)" }}>
        <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 6 }}>Cerrar arqueo</div>
        <div style={{ fontSize: 13, color: C.mute, marginBottom: 18 }}>Cuenta el efectivo en caja e ingresa el monto real.</div>
        <div style={{ display: "grid", gap: 12 }}>
          <div style={{ padding: "12px 16px", background: C.bg, borderRadius: C.r, display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontSize: 13, color: C.mid }}>Efectivo esperado</span>
            <span style={{ fontSize: 16, fontWeight: 800, color: C.text }}>${fmt(live.expected_cash)}</span>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Efectivo contado en caja</div>
            <input value={countedCash} onChange={e => setCountedCash(e.target.value)} placeholder="$0" inputMode="decimal" autoFocus
              style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
          </div>
          {countedCash !== "" && (
            <div style={{ padding: "10px 14px", borderRadius: C.r, background: difference !== null && difference >= 0 ? C.greenBg : C.redBg, border: `1px solid ${difference !== null && difference >= 0 ? C.greenBd : C.redBd}` }}>
              <div style={{ fontSize: 12, color: C.mid }}>Diferencia</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: difference !== null && difference >= 0 ? C.green : C.red, fontVariantNumeric: "tabular-nums" }}>
                {difference !== null && difference >= 0 ? "+" : ""}${fmt(difference ?? 0)}
              </div>
              {difference !== null && difference < 0 && <div style={{ fontSize: 11, color: C.red, marginTop: 2 }}>Hay un faltante de ${fmt(Math.abs(difference))}</div>}
              {difference !== null && difference > 0 && <div style={{ fontSize: 11, color: C.green, marginTop: 2 }}>Hay un sobrante de ${fmt(difference)}</div>}
            </div>
          )}
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Nota (opcional)</div>
            <input value={closeNote} onChange={e => setCloseNote(e.target.value)} placeholder="Ej: Todo en orden"
              style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 20, justifyContent: "flex-end" }}>
          <Btn variant="ghost" onClick={onClose} disabled={busy}>Cancelar</Btn>
          <Btn variant="danger" onClick={onSubmit} disabled={busy || countedCash === ""}>
            {busy ? <Spinner size={14} /> : "Confirmar cierre"}
          </Btn>
        </div>
      </div>
    </div>
  );
}
