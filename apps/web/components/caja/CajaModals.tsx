"use client";

import React, { useEffect, useState } from "react";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { Btn, fmt, type LiveSummary } from "./CajaShared";
import { apiFetch } from "@/lib/api";

// ─── Add Movement Modal ─────────────────────────────────────────────────────
interface AddMovementModalProps {
  // Daniel 01/05/26 — el botón "+ Movimiento" ahora SIEMPRE visible (estilo
  // Fudo). Si no hay caja abierta, el modal muestra mensaje claro en vez
  // del formulario (no puede crear movs sin sesión activa).
  hasOpenSession?: boolean;
  moveType: "IN" | "OUT"; setMoveType: (v: "IN" | "OUT") => void;
  moveAmt: string; setMoveAmt: (v: string) => void;
  moveDesc: string; setMoveDesc: (v: string) => void;
  // Daniel 01/05/26 - categoría opcional para clasificar movimientos.
  moveCategory?: string;
  setMoveCategory?: (v: string) => void;
  busy: boolean;
  onClose: () => void;
  onSubmit: () => void;
}

type CategoryOption = { code: string; label: string };

export function AddMovementModal({
  hasOpenSession = true,
  moveType, setMoveType, moveAmt, setMoveAmt, moveDesc, setMoveDesc,
  moveCategory = "", setMoveCategory,
  busy, onClose, onSubmit,
}: AddMovementModalProps) {
  // Cargar categorías del backend (1 sola vez, independiente del tipo)
  const [allCats, setAllCats] = useState<{ income: CategoryOption[]; expense: CategoryOption[] }>({ income: [], expense: [] });

  useEffect(() => {
    let alive = true;
    apiFetch("/caja/movements/categories/")
      .then((d: any) => { if (alive) setAllCats(d || { income: [], expense: [] }); })
      .catch(() => { /* silent: feature degrada a sin dropdown */ });
    return () => { alive = false; };
  }, []);

  // Mostrar solo categorías relevantes según moveType
  const cats = moveType === "IN" ? allCats.income : allCats.expense;

  // Si el usuario cambia tipo IN→OUT y la categoría no aplica, limpiarla
  useEffect(() => {
    if (!setMoveCategory || !moveCategory) return;
    const validCodes = new Set(cats.map(c => c.code));
    if (!validCodes.has(moveCategory)) setMoveCategory("");
  }, [moveType, cats]); // eslint-disable-line react-hooks/exhaustive-deps

  // Si no hay caja abierta, mostrar mensaje en vez del formulario.
  if (!hasOpenSession) {
    return (
      <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
        <div style={{ background: C.surface, borderRadius: 14, padding: 28, width: "100%", maxWidth: 420, boxShadow: "0 20px 52px rgba(0,0,0,0.18)", textAlign: "center" }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>🔒</div>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.text, marginBottom: 8 }}>
            No hay caja abierta
          </div>
          <div style={{ fontSize: 13, color: C.mute, lineHeight: 1.5, marginBottom: 22 }}>
            Para registrar un ingreso o egreso necesitás abrir un arqueo primero.
            Los movimientos quedan asociados a la sesión activa.
          </div>
          <Btn variant="primary" onClick={onClose}>
            Entendido
          </Btn>
        </div>
      </div>
    );
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ background: C.surface, borderRadius: 14, padding: 28, width: "100%", maxWidth: 420, boxShadow: "0 20px 52px rgba(0,0,0,0.18)", maxHeight: "calc(100vh - 32px)", overflowY: "auto" }}>
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
          {/* Categoría — solo si hay opciones cargadas y el callback se proveyó */}
          {setMoveCategory && cats.length > 0 && (
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>
                Categoría <span style={{ fontWeight: 400, color: C.mute }}>(opcional)</span>
              </div>
              <select
                value={moveCategory}
                onChange={e => setMoveCategory(e.target.value)}
                disabled={busy}
                style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box", background: C.surface, color: C.text, cursor: "pointer" }}
              >
                <option value="">Sin categoría</option>
                {cats.map(c => (
                  <option key={c.code} value={c.code}>{c.label}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Monto</div>
            <input value={moveAmt} onChange={e => setMoveAmt(e.target.value)} placeholder="$0" inputMode="decimal"
              style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Descripción</div>
            <input value={moveDesc} onChange={e => setMoveDesc(e.target.value)} placeholder="Ej: Compra de gas, Retiro para banco..."
              style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
          </div>
          {/* Aviso fat-finger Daniel 01/05/26: monto > $50k pide doble check */}
          {Number(moveAmt) > 50000 && (
            <div style={{
              padding: "8px 12px", background: C.amberBg, border: `1px solid ${C.amberBd}`,
              borderRadius: 6, fontSize: 12, color: C.amber, lineHeight: 1.4,
            }}>
              ⚠️ Monto alto: <b>${Math.round(Number(moveAmt)).toLocaleString("es-CL")}</b>.
              Verificá que esté correcto y que sea {moveType === "IN" ? "INGRESO" : "EGRESO"}.
            </div>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 20, justifyContent: "flex-end" }}>
          <Btn variant="ghost" onClick={onClose} disabled={busy}>Cancelar</Btn>
          <Btn
            variant="primary"
            onClick={() => {
              if (Number(moveAmt) > 50000) {
                const ok = window.confirm(
                  `Vas a registrar un ${moveType === "IN" ? "INGRESO" : "EGRESO"} de $${Math.round(Number(moveAmt)).toLocaleString("es-CL")}.\n\n¿Confirmás?`
                );
                if (!ok) return;
              }
              onSubmit();
            }}
            disabled={busy || !moveAmt || !moveDesc}
          >
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
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ background: C.surface, borderRadius: 14, padding: 28, width: "100%", maxWidth: 440, boxShadow: "0 20px 52px rgba(0,0,0,0.18)", maxHeight: "calc(100vh - 32px)", overflowY: "auto" }}>
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
