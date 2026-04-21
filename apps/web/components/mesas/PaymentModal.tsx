"use client";

import { useState } from "react";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { MesaModal } from "./MesaModal";
import { MesaBtn as Btn } from "./MesaBtn";
import { OrderLine, PaymentRow } from "./types";
import { fmt, PAY_METHODS } from "./helpers";

interface PaymentModalProps {
  total: number;
  tableName: string;
  onConfirm: (payments: PaymentRow[], tip: number, mode: "all" | "partial", lineIds: number[], saleType?: string) => void;
  onClose: () => void;
  loading: boolean;
  unpaidLines: OrderLine[];
  canConsumoInterno?: boolean;
  error?: string;
}

export function PaymentModal({
  total, tableName, onConfirm, onClose, loading, unpaidLines, canConsumoInterno, error,
}: PaymentModalProps) {
  const [rows, setRows] = useState<PaymentRow[]>([{ method: "cash", amount: "" }]);
  const [tipStr, setTipStr] = useState("");
  const [splitN, setSplitN] = useState("");
  const [checkoutMode, setCheckoutMode] = useState<"all" | "partial">("all");
  const [selLines, setSelLines] = useState<Set<number>>(new Set(unpaidLines.map(l => l.id)));
  const [isConsumoInterno, setIsConsumoInterno] = useState(false);

  const toggleLine = (id: number) => {
    setSelLines(prev => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });
  };

  const lineSubtotal = checkoutMode === "partial"
    ? unpaidLines.filter(l => selLines.has(l.id)).reduce((s, l) => s + Number(l.line_total), 0)
    : total;
  const tip = Math.max(0, Number(tipStr) || 0);
  const grandTotal = lineSubtotal + tip;
  const totalPaid = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  const change = Math.max(0, totalPaid - grandTotal);
  const pending = Math.max(0, grandTotal - totalPaid);
  const splitPer = splitN && Number(splitN) > 0 ? Math.round(grandTotal / Number(splitN)) : null;

  function addRow() {
    const used = new Set(rows.map(r => r.method));
    const next = PAY_METHODS.find(m => !used.has(m.value))?.value || "cash";
    setRows(prev => [...prev, { method: next, amount: "" }]);
  }
  function removeRow(i: number) { setRows(prev => prev.filter((_, j) => j !== i)); }
  function updateRow(i: number, field: keyof PaymentRow, val: string) {
    if (field === "amount" && val !== "" && Number(val) < 0) return;
    setRows(prev => prev.map((r, j) => j === i ? { ...r, [field]: val } : r));
  }
  function quickFill(i: number) {
    const rest = rows.reduce((s, r, j) => j !== i ? s + (Number(r.amount) || 0) : s, 0);
    const val = Math.max(0, Math.round(grandTotal - rest));
    if (val > 0) updateRow(i, "amount", String(val));
  }

  return (
    <MesaModal title={`Cobrar — ${tableName}`} onClose={onClose} width={480}>
      {/* Mode selector */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {(["all", "partial"] as const).map(m => (
          <button type="button" key={m} onClick={() => setCheckoutMode(m)} style={{
            flex: 1, padding: "8px", borderRadius: C.r, fontSize: 12, fontWeight: 600,
            border: `2px solid ${checkoutMode === m ? C.accent : C.border}`,
            background: checkoutMode === m ? C.accentBg : C.surface,
            color: checkoutMode === m ? C.accent : C.mid,
            cursor: "pointer", fontFamily: "inherit",
          }}>
            {m === "all" ? "Cobrar todo" : "Por items"}
          </button>
        ))}
      </div>

      {/* Partial: line selector */}
      {checkoutMode === "partial" && (
        <div style={{ marginBottom: 14, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", maxHeight: 180, overflowY: "auto" }}>
          {unpaidLines.map(l => (
            <label key={l.id} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "8px 10px",
              borderBottom: `1px solid ${C.border}`, cursor: "pointer",
              background: selLines.has(l.id) ? C.accentBg : C.surface,
            }}>
              <input type="checkbox" checked={selLines.has(l.id)} onChange={() => toggleLine(l.id)}
                style={{ accentColor: C.accent, width: 20, height: 20, flexShrink: 0 }} />
              <span style={{ flex: 1, fontSize: 12, fontWeight: 600, color: C.text }}>{l.product_name}</span>
              <span style={{ fontWeight: 700, fontSize: 12, color: C.text }}>${fmt(l.line_total)}</span>
            </label>
          ))}
        </div>
      )}

      {/* Items list -- always visible in "all" mode */}
      {checkoutMode === "all" && unpaidLines.length > 0 && (
        <div style={{
          marginBottom: 14, border: `1px solid ${isConsumoInterno ? "#F59E0B" : C.border}`,
          borderRadius: C.r, overflow: "hidden", maxHeight: 200, overflowY: "auto",
          background: isConsumoInterno ? "#FFFBEB" : C.surface,
        }}>
          <div style={{
            padding: "6px 10px", borderBottom: `1px solid ${isConsumoInterno ? "#F59E0B" : C.border}`,
            fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em",
            background: isConsumoInterno ? "#FEF3C7" : C.bg,
            color: isConsumoInterno ? "#92400E" : C.mute,
          }}>
            {isConsumoInterno ? "Items a registrar como consumo" : `${unpaidLines.length} producto(s)`}
          </div>
          {unpaidLines.map(l => (
            <div key={l.id} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "7px 10px",
              borderBottom: `1px solid ${C.border}`,
            }}>
              <span style={{ flex: 1, fontSize: 12, fontWeight: 600, color: C.text }}>{l.product_name}</span>
              <span style={{ fontSize: 11, color: C.mid }}>{l.qty} x ${fmt(l.unit_price)}</span>
              <span style={{ fontWeight: 700, fontSize: 12, color: isConsumoInterno ? "#92400E" : C.text }}>${fmt(l.line_total)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Consumo interno toggle */}
      {canConsumoInterno && (
        <label style={{
          display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
          borderRadius: C.r, border: `1px solid ${isConsumoInterno ? "#F59E0B" : C.border}`,
          background: isConsumoInterno ? "#FFFBEB" : "transparent",
          cursor: "pointer", marginBottom: 12,
        }}>
          <input type="checkbox" checked={isConsumoInterno}
            onChange={e => setIsConsumoInterno(e.target.checked)}
            style={{ accentColor: "#D97706", width: 15, height: 15, flexShrink: 0 }} />
          <span style={{ fontSize: 13, fontWeight: 600, color: isConsumoInterno ? "#D97706" : C.mid }}>
            Consumo interno (sin cobro)
          </span>
        </label>
      )}

      {/* Payment rows */}
      {!isConsumoInterno && <div style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.05em" }}>Forma de pago</span>
          {rows.length < PAY_METHODS.length && (
            <button type="button" onClick={addRow} style={{
              display: "flex", alignItems: "center", gap: 4, padding: "3px 10px", borderRadius: C.r,
              border: `1px dashed ${C.borderMd}`, background: "transparent", cursor: "pointer",
              fontSize: 11, fontWeight: 600, color: C.accent, fontFamily: "inherit",
            }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              Agregar
            </button>
          )}
        </div>
        {rows.map((row, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 6, marginBottom: 6,
            padding: "5px 8px", borderRadius: C.r,
            background: Number(row.amount) > 0 ? C.accentBg : "transparent",
            border: `1px solid ${Number(row.amount) > 0 ? C.accentBd : "transparent"}`,
          }}>
            <select value={row.method} onChange={e => updateRow(i, "method", e.target.value)}
              style={{
                padding: "6px 8px", border: `1px solid ${C.border}`, borderRadius: C.r,
                fontSize: 12, fontWeight: 600, fontFamily: "inherit", outline: "none",
                background: C.surface, color: C.text, cursor: "pointer", minWidth: 110,
              }}>
              {PAY_METHODS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <input type="number" min="0" value={row.amount}
              onChange={e => updateRow(i, "amount", e.target.value)}
              placeholder="$0" style={{
                flex: 1, padding: "6px 10px",
                border: `1px solid ${Number(row.amount) > 0 ? C.accentBd : C.border}`,
                borderRadius: C.r, fontSize: 13, fontFamily: "inherit", outline: "none",
              }} />
            <button type="button" aria-label="Completar" onClick={() => quickFill(i)} title="Completar"
              style={{ width: 28, height: 28, borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: C.accent, fontWeight: 700, fontSize: 13, fontFamily: "inherit", flexShrink: 0 }}>
              →
            </button>
            {rows.length > 1 && (
              <button type="button" aria-label="Eliminar" onClick={() => removeRow(i)} style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 2, display: "flex", flexShrink: 0 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            )}
          </div>
        ))}
      </div>}

      {/* Tip */}
      {!isConsumoInterno && (
      <div style={{ marginBottom: 14, padding: "10px 12px", borderRadius: C.r, border: `1px solid ${C.amberBd}`, background: C.amberBg }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: C.amber }}>Propina (opcional)</span>
        </div>
        <input type="number" min="0" value={tipStr} onChange={e => setTipStr(e.target.value)}
          placeholder="$0" style={{ width: "100%", padding: "6px 10px", border: `1px solid ${C.amberBd}`, borderRadius: C.r, fontSize: 13, fontFamily: "inherit", outline: "none", background: "#fff" }} />
      </div>
      )}

      {/* Summary */}
      <div style={{ background: C.bg, borderRadius: C.r, padding: "12px 14px", marginBottom: 14, border: `1px solid ${C.border}` }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.mid, marginBottom: 3 }}>
          <span>Subtotal</span><span>${fmt(lineSubtotal)}</span>
        </div>
        {tip > 0 && (
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.amber, marginBottom: 3 }}>
            <span>Propina</span><span>+${fmt(tip)}</span>
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 15, fontWeight: 800, color: C.text, borderTop: `1px solid ${C.border}`, paddingTop: 6, marginTop: 3 }}>
          <span>Total a cobrar</span><span>${fmt(grandTotal)}</span>
        </div>
        {!isConsumoInterno && totalPaid > 0 && (
          <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.mid, marginBottom: 2 }}>
              <span>Pagado</span><span>${fmt(totalPaid)}</span>
            </div>
            {change > 0 && <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 700, color: C.green }}><span>Vuelto</span><span>${fmt(change)}</span></div>}
            {pending > 0 && <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 700, color: C.red }}><span>Falta</span><span>${fmt(pending)}</span></div>}
            {pending === 0 && change === 0 && <div style={{ fontSize: 13, fontWeight: 700, color: C.green, textAlign: "center" }}>Pagado exacto</div>}
          </div>
        )}
      </div>

      {/* Split */}
      {!isConsumoInterno && (
      <div style={{ marginBottom: 14, display: "flex", gap: 8, alignItems: "center" }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: C.mid }}>Dividir en:</span>
        <input type="number" min="1" value={splitN} onChange={e => setSplitN(e.target.value)}
          placeholder="N" style={{ width: 50, padding: "5px 8px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 13, fontFamily: "inherit", outline: "none" }} />
        <span style={{ fontSize: 11, color: C.mute }}>pers.</span>
        {splitPer != null && <span style={{ fontSize: 13, fontWeight: 700, color: C.accent, marginLeft: "auto" }}>${fmt(splitPer)} c/u</span>}
      </div>
      )}

      {/* Error from checkout attempt */}
      {error && (
        <div style={{
          padding: "10px 14px", marginBottom: 10, borderRadius: C.r,
          background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red,
          fontSize: 12, fontWeight: 600,
        }}>
          {error.includes("Insufficient stock") || error.includes("stock")
            ? "No hay stock suficiente para completar esta venta. Verifica el inventario."
            : error}
        </div>
      )}

      <div style={{ display: "flex", gap: 8 }}>
        <Btn variant="secondary" onClick={onClose}>Cancelar</Btn>
        <Btn variant={isConsumoInterno ? "danger" : "primary"} full size="lg"
          disabled={loading || grandTotal === 0 || (checkoutMode === "partial" && selLines.size === 0) || (!isConsumoInterno && totalPaid < grandTotal)}
          onClick={() => onConfirm(
            isConsumoInterno ? [] : rows.filter(r => Number(r.amount) > 0),
            isConsumoInterno ? 0 : tip,
            checkoutMode, [...selLines],
            isConsumoInterno ? "CONSUMO_INTERNO" : "VENTA",
          )}>
          {loading ? <Spinner size={14} /> : null}
          {loading ? "Procesando…" : isConsumoInterno ? "Registrar consumo" : `Cobrar $${fmt(grandTotal)}`}
        </Btn>
      </div>
    </MesaModal>
  );
}
