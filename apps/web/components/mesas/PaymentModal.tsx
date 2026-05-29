"use client";

import { useEffect, useState } from "react";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { MesaModal } from "./MesaModal";
import { MesaBtn as Btn } from "./MesaBtn";
import { OrderLine, PaymentRow } from "./types";
import { fmt, PAY_METHODS, buildCheckoutSplit } from "./helpers";

/**
 * Detalle de cada producto sin stock que el backend devuelve cuando el
 * checkout falla con 409. Antes el frontend mostraba un genérico ("No hay
 * stock suficiente") y Mario tenía que ir a buscar en el inventario cuál
 * producto faltaba. Ahora replicamos lo que hace Fudo: lista exacta como
 * "FANTA 350cc: 0 disponible / 2 requerido".
 */
export interface StockShortage {
  product_id: number;
  name: string;
  available: string;
  required: string;
  unit: string;
}

interface PaymentModalProps {
  total: number;
  tableName: string;
  onConfirm: (
    payments: PaymentRow[],
    tip: number,
    mode: "all" | "partial",
    lineIds: number[],
    saleType?: string,
    /** Propinas explícitas (Fudo-style split). Cada fila {método, monto}
        viaja como SaleTip. Reemplaza el antiguo `tipMethod` único. */
    tipsArr?: { method: string; amount: number }[],
    /** Cobro parcial intra-line: {line_id: qty_a_cobrar}. Si la qty es
        menor a line.qty, deja remanente en la mesa. Mario 25/05/26. */
    lineQtys?: Record<number, number>,
  ) => void;
  onClose: () => void;
  loading: boolean;
  unpaidLines: OrderLine[];
  canConsumoInterno?: boolean;
  error?: string;
  shortages?: StockShortage[];
}

export function PaymentModal({
  total, tableName, onConfirm, onClose, loading, unpaidLines, canConsumoInterno, error, shortages,
}: PaymentModalProps) {
  const [rows, setRows] = useState<PaymentRow[]>([{ method: "cash", amount: "" }]); // PAGO
  // PROPINA (Fudo-style): filas {metodo, monto}. Vacio = sin propina.
  // Soporta split (varios metodos, ej. $800 efectivo + $600 debito). Los
  // botones rapidos de % setean 1 sola fila. Al enviar, cada fila viaja
  // como SaleTip explicito y se RESTA del pago para obtener la cuenta neta.
  const [tipRows, setTipRows] = useState<PaymentRow[]>([]);
  const [splitN, setSplitN] = useState("");
  const [checkoutMode, setCheckoutMode] = useState<"all" | "partial">("all");
  const [selLines, setSelLines] = useState<Set<number>>(new Set(unpaidLines.map(l => l.id)));
  // Mario reporto (25/05/26): en "Por items", line con qty=2 solo permitia
  // pagar las 2 o ninguna. Ahora cada line tiene un stepper +/- para elegir
  // cuantas unidades cobrar. Por default: line.qty completa (compatibilidad
  // con flujo previo). lineQtys[line.id] = qty a cobrar de esa line.
  const [lineQtys, setLineQtys] = useState<Record<number, number>>(
    () => Object.fromEntries(unpaidLines.map(l => [l.id, Number(l.qty)]))
  );
  const [isConsumoInterno, setIsConsumoInterno] = useState(false);

  // Mario reportó: "tuve que sacar la calculadora para sumar el total con
  // la propina y poder agregarlo en el pago".
  //
  // Caso típico cafetería/restaurante: 1 sola forma de pago (cash o tarjeta).
  // Antes el cajero tenía que escribir el subtotal en el campo "Pagado",
  // luego agregar propina, y MENTALMENTE recalcular el total con propina
  // y reescribirlo. Engorroso y propenso a errores.
  //
  // Solución: autoSync. Cuando hay UNA SOLA fila de pago, el monto se
  // mantiene sincronizado con el grandTotal (subtotal + propina) en todo
  // momento. El cajero ve el campo prellenado con el total a cobrar.
  //
  // Si el cajero edita el monto manualmente a un valor distinto del
  // total (ej: pone $20.000 para vuelto, o un pago parcial), autoSync
  // se desactiva y deja respetar el valor del usuario.
  // Si agrega una segunda fila (split), también se desactiva — split
  // implica que el cajero está manejando los montos a mano.
  const [autoSync, setAutoSync] = useState(true);

  const toggleLine = (id: number) => {
    setSelLines(prev => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });
  };

  // En modo "partial", el subtotal usa lineQtys[id] (cobro parcial intra-line)
  // multiplicado por el unit_price, no el line_total completo. Asi se respeta
  // el caso de pagar 1 de 2 chaparritas (Mario 25/05/26).
  const lineSubtotal = checkoutMode === "partial"
    ? unpaidLines
        .filter(l => selLines.has(l.id))
        .reduce((s, l) => {
          const qty = lineQtys[l.id] ?? Number(l.qty);
          return s + qty * Number(l.unit_price);
        }, 0)
    : total;
  // Propina = suma de las filas PROPINA (split soportado).
  const tip = tipRows.reduce((s, r) => s + Math.max(0, Number(r.amount) || 0), 0);
  const grandTotal = lineSubtotal + tip;
  // PAGO (Fudo-style): cubre el TOTAL (subtotal + propina). `totalPaid` es
  // lo que el cliente entrega en total. Vuelto/falta se calculan contra el
  // grandTotal. Al enviar (ver submit) se separa la propina del pago para
  // que SalePayment = solo la cuenta y SaleTip = propina (Fase A backend).
  const totalPaid = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  const change = Math.max(0, totalPaid - grandTotal);
  const pending = Math.max(0, grandTotal - totalPaid);
  const splitPer = splitN && Number(splitN) > 0 ? Math.round(grandTotal / Number(splitN)) : null;

  // autoSync (Fudo-style): mantener el monto del único pago = grandTotal
  // (subtotal + propina). El cajero ve el PAGO prellenado con el TOTAL a
  // cobrar, igual que Fudo. Cuando cambia la propina, el PAGO se actualiza
  // solo. Al enviar se separa la propina del pago (submit). Si el cajero
  // edita el monto a un valor distinto (vuelto), autoSync se desactiva.
  useEffect(() => {
    if (!autoSync) return;
    if (isConsumoInterno) return;
    if (rows.length !== 1) return;
    const expected = grandTotal > 0 ? String(grandTotal) : "";
    if (rows[0].amount !== expected) {
      setRows([{ method: rows[0].method, amount: expected }]);
    }
  }, [grandTotal, autoSync, rows, isConsumoInterno]);

  // Restaurantes grandes: una mesa de 40 personas puede dividirse en muchos
  // pagos individuales (cada persona paga su parte en el método que quiera —
  // varios en efectivo, otros con tarjeta). Antes el botón Agregar se ocultaba
  // a partir de 4 filas (PAY_METHODS.length), lo que hacía imposible cobrar
  // por separado a una mesa grande. Ahora dejamos hasta 50 filas y permitimos
  // métodos repetidos. El default va al primer método sin usar; si todos
  // están usados, vuelve a "cash" (lo más común).
  const MAX_PAYMENT_ROWS = 50;
  function addRow() {
    if (rows.length >= MAX_PAYMENT_ROWS) return;
    // Split manual: el cajero toma control de los montos.
    setAutoSync(false);
    const used = new Set(rows.map(r => r.method));
    const next = PAY_METHODS.find(m => !used.has(m.value))?.value || "cash";
    setRows(prev => [...prev, { method: next, amount: "" }]);
  }
  function removeRow(i: number) {
    setRows(prev => {
      const next = prev.filter((_, j) => j !== i);
      // Si después de eliminar volvemos a 1 sola fila, re-activar
      // autoSync para retomar el comportamiento "campo = total".
      if (next.length === 1) setAutoSync(true);
      return next;
    });
  }
  function updateRow(i: number, field: keyof PaymentRow, val: string) {
    if (field === "amount" && val !== "" && Number(val) < 0) return;
    if (field === "amount" && rows.length === 1) {
      // Si el cajero edita el monto a un valor distinto del grandTotal
      // (ej: $20.000 cuando el total es $17.787, para tener vuelto),
      // desactivar autoSync y respetar el valor manual.
      // Si el valor coincide con grandTotal (incluyendo cuando borra el
      // campo y grandTotal también pasa a 0), RE-activar autoSync —
      // antes quedaba "trabado" sin forma de recuperarse.
      if (val === String(grandTotal) || (val === "" && grandTotal === 0)) {
        setAutoSync(true);
      } else {
        setAutoSync(false);
      }
    }
    setRows(prev => prev.map((r, j) => j === i ? { ...r, [field]: val } : r));
  }
  function quickFill(i: number) {
    const rest = rows.reduce((s, r, j) => j !== i ? s + (Number(r.amount) || 0) : s, 0);
    const val = Math.max(0, Math.round(grandTotal - rest));
    if (val > 0) updateRow(i, "amount", String(val));
  }

  // ── PROPINA rows (split Fudo-style) ──────────────────────────────────
  function addTipRow() {
    const used = new Set(tipRows.map(r => r.method));
    const next = PAY_METHODS.find(m => !used.has(m.value))?.value || "cash";
    setTipRows(prev => [...prev, { method: next, amount: "" }]);
  }
  function removeTipRow(i: number) {
    setTipRows(prev => prev.filter((_, j) => j !== i));
  }
  function updateTipRow(i: number, field: keyof PaymentRow, val: string) {
    if (field === "amount" && val !== "" && Number(val) < 0) return;
    setTipRows(prev => prev.map((r, j) => j === i ? { ...r, [field]: val } : r));
  }
  // Boton rapido de %: setea UNA sola fila de propina con ese % del
  // subtotal, conservando el metodo de la primera fila (o efectivo).
  function setQuickTip(pct: number) {
    const amount = Math.round(lineSubtotal * pct / 100);
    const method = tipRows[0]?.method || "cash";
    setTipRows(amount > 0 ? [{ method, amount: String(amount) }] : []);
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

      {/* Partial: line selector con stepper +/- (Mario 25/05/26):
          si line.qty > 1, permitir elegir cuantas unidades cobrar
          (ej: 1 de 2 chaparritas). */}
      {checkoutMode === "partial" && (
        <div style={{ marginBottom: 14, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", maxHeight: 220, overflowY: "auto" }}>
          {unpaidLines.map(l => {
            const maxQty = Number(l.qty);
            const currentQty = lineQtys[l.id] ?? maxQty;
            const isSelected = selLines.has(l.id);
            const lineSubtotalRow = currentQty * Number(l.unit_price);
            const canDecrement = isSelected && currentQty > 1;
            const canIncrement = isSelected && currentQty < maxQty;
            return (
              <div key={l.id} style={{
                display: "flex", alignItems: "center", gap: 8, padding: "8px 10px",
                borderBottom: `1px solid ${C.border}`,
                background: isSelected ? C.accentBg : C.surface,
              }}>
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggleLine(l.id)}
                  style={{ accentColor: C.accent, width: 20, height: 20, flexShrink: 0, cursor: "pointer" }}
                />
                <span style={{ flex: 1, fontSize: 12, fontWeight: 600, color: C.text, minWidth: 0 }}>
                  {l.product_name}
                  <span style={{ fontSize: 11, color: C.mute, fontWeight: 500, marginLeft: 6 }}>
                    ${fmt(l.unit_price)} c/u
                  </span>
                </span>
                {/* Stepper qty: solo aparece si line.qty > 1 */}
                {maxQty > 1 && (
                  <div style={{
                    display: "flex", alignItems: "center", gap: 0,
                    border: `1px solid ${isSelected ? C.accentBd : C.border}`,
                    borderRadius: C.r, overflow: "hidden",
                    background: isSelected ? "#fff" : C.bg,
                    opacity: isSelected ? 1 : 0.5,
                  }}>
                    <button
                      type="button"
                      disabled={!canDecrement}
                      onClick={() => {
                        if (!canDecrement) return;
                        setLineQtys(prev => ({ ...prev, [l.id]: currentQty - 1 }));
                      }}
                      style={{
                        width: 26, height: 26, border: "none", background: "transparent",
                        cursor: canDecrement ? "pointer" : "not-allowed",
                        color: canDecrement ? C.accent : C.mute,
                        fontSize: 14, fontWeight: 700, fontFamily: "inherit",
                        display: "flex", alignItems: "center", justifyContent: "center",
                      }}
                    >−</button>
                    <span style={{
                      minWidth: 32, textAlign: "center",
                      fontSize: 12, fontWeight: 700, color: C.text,
                      fontVariantNumeric: "tabular-nums",
                    }}>
                      {currentQty} / {maxQty}
                    </span>
                    <button
                      type="button"
                      disabled={!canIncrement}
                      onClick={() => {
                        if (!canIncrement) return;
                        setLineQtys(prev => ({ ...prev, [l.id]: currentQty + 1 }));
                      }}
                      style={{
                        width: 26, height: 26, border: "none", background: "transparent",
                        cursor: canIncrement ? "pointer" : "not-allowed",
                        color: canIncrement ? C.accent : C.mute,
                        fontSize: 14, fontWeight: 700, fontFamily: "inherit",
                        display: "flex", alignItems: "center", justifyContent: "center",
                      }}
                    >+</button>
                  </div>
                )}
                <span style={{
                  fontWeight: 700, fontSize: 12, color: C.text,
                  minWidth: 70, textAlign: "right",
                  fontVariantNumeric: "tabular-nums",
                }}>
                  ${fmt(lineSubtotalRow)}
                </span>
              </div>
            );
          })}
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
          <span style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Forma de pago {rows.length > 1 && <span style={{ color: C.mid, fontWeight: 600 }}>({rows.length})</span>}
          </span>
          {rows.length < MAX_PAYMENT_ROWS && (
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
        {/* Si hay muchas filas (mesa grande dividida entre varias personas)
            limitamos altura y dejamos scroll vertical para no romper el modal. */}
        <div style={{ maxHeight: rows.length > 6 ? 280 : "none", overflowY: rows.length > 6 ? "auto" : "visible", paddingRight: rows.length > 6 ? 4 : 0 }}>
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
        </div>
        {/* Atajo para mesas grandes: dividir el total entre N personas y
            crear N filas en efectivo prellenadas con la parte proporcional.
            El usuario después puede cambiar método o monto en cada fila. */}
        {rows.length < MAX_PAYMENT_ROWS && grandTotal > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, padding: "6px 8px", borderRadius: C.r, background: C.bg, border: `1px dashed ${C.border}` }}>
            <span style={{ fontSize: 11, color: C.mute, fontWeight: 600 }}>Mesa grande:</span>
            <input
              type="number" min="2" max={MAX_PAYMENT_ROWS}
              value={splitN}
              onChange={e => setSplitN(e.target.value)}
              placeholder="N"
              style={{ width: 56, padding: "5px 8px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 12, fontFamily: "inherit", outline: "none" }}
            />
            <span style={{ fontSize: 11, color: C.mute }}>pers.</span>
            {splitPer != null && Number(splitN) >= 2 && (
              <span style={{ fontSize: 11, fontWeight: 700, color: C.accent }}>≈ ${fmt(splitPer)} c/u</span>
            )}
            <button
              type="button"
              disabled={!splitN || Number(splitN) < 2 || Number(splitN) > MAX_PAYMENT_ROWS}
              onClick={() => {
                const n = Math.min(MAX_PAYMENT_ROWS, Math.max(2, Math.floor(Number(splitN) || 0)));
                if (n < 2) return;
                const per = Math.floor(grandTotal / n);
                const remainder = grandTotal - per * n;
                // 1ª fila absorbe el resto del redondeo así la suma cuadra
                // exactamente con grandTotal (no quedan $1-2 sin pagar).
                const newRows: PaymentRow[] = Array.from({ length: n }, (_, i) => ({
                  method: "cash",
                  amount: String(per + (i === 0 ? remainder : 0)),
                }));
                // Split N personas: cajero maneja los montos a mano de
                // ahí en adelante.
                setAutoSync(false);
                setRows(newRows);
              }}
              style={{
                marginLeft: "auto", padding: "5px 12px", borderRadius: C.r,
                border: `1px solid ${C.accentBd}`, background: C.accentBg, color: C.accent,
                fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
                opacity: !splitN || Number(splitN) < 2 ? 0.5 : 1,
              }}
            >
              Crear {splitN ? `${splitN} ` : ""}filas
            </button>
          </div>
        )}
      </div>}

      {/* PROPINA (Fudo-style): seccion propia con filas {metodo, monto}.
          Soporta split (varios metodos) via "+". Los botones rapidos de %
          setean 1 fila. Vacia = sin propina (estado "Sin propina"). */}
      {!isConsumoInterno && (
      <div style={{ marginBottom: 14, padding: "10px 12px", borderRadius: C.r, border: `1px solid ${C.amberBd}`, background: C.amberBg }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, marginBottom: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: C.amber, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Propina {tipRows.length > 0 ? `· $${fmt(tip)}` : "(opcional)"}
          </span>
          <div style={{ display: "flex", gap: 4 }}>
            {[5, 10, 15].map(pct => {
              const amount = Math.round(lineSubtotal * pct / 100);
              const active = tipRows.length === 1 && tip === amount;
              return (
                <button
                  key={pct}
                  type="button"
                  onClick={() => setQuickTip(pct)}
                  style={{
                    padding: "3px 8px", borderRadius: 99,
                    border: `1px solid ${active ? C.amber : C.amberBd}`,
                    background: active ? C.amber : "#fff",
                    color: active ? "#fff" : C.amber,
                    fontSize: 10, fontWeight: 700, cursor: "pointer",
                    fontFamily: "inherit",
                  }}
                  title={`$${fmt(amount)}`}
                >
                  {pct}%
                </button>
              );
            })}
            {tipRows.length > 0 && (
              <button
                type="button"
                onClick={() => setTipRows([])}
                style={{
                  padding: "3px 8px", borderRadius: 99,
                  border: `1px solid ${C.border}`,
                  background: "transparent", color: C.mute,
                  fontSize: 10, fontWeight: 700, cursor: "pointer",
                  fontFamily: "inherit",
                }}
                title="Sin propina"
              >
                Limpiar
              </button>
            )}
          </div>
        </div>

        {tipRows.length === 0 ? (
          <button
            type="button"
            onClick={addTipRow}
            style={{
              width: "100%", padding: "8px", borderRadius: C.r,
              border: `1px dashed ${C.amberBd}`, background: "#fff",
              color: C.amber, fontSize: 12, fontWeight: 600, cursor: "pointer",
              fontFamily: "inherit", display: "flex", alignItems: "center",
              justifyContent: "center", gap: 6,
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Agregar propina
          </button>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {tipRows.map((row, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <select value={row.method} onChange={e => updateTipRow(i, "method", e.target.value)}
                  style={{
                    padding: "6px 8px", border: `1px solid ${C.amberBd}`, borderRadius: C.r,
                    fontSize: 12, fontWeight: 600, fontFamily: "inherit", outline: "none",
                    background: "#fff", color: C.text, cursor: "pointer", minWidth: 110,
                  }}>
                  {PAY_METHODS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
                <div style={{ position: "relative", flex: 1 }}>
                  <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", fontSize: 12, color: C.amber, pointerEvents: "none" }}>$</span>
                  <input type="number" min="0" value={row.amount}
                    onChange={e => updateTipRow(i, "amount", e.target.value)}
                    placeholder="0" style={{
                      width: "100%", padding: "6px 10px 6px 20px",
                      border: `1px solid ${C.amberBd}`, borderRadius: C.r,
                      fontSize: 13, fontFamily: "inherit", outline: "none", background: "#fff",
                    }} />
                </div>
                <button type="button" aria-label="Eliminar propina" onClick={() => removeTipRow(i)}
                  style={{ background: "none", border: "none", cursor: "pointer", color: C.amber, padding: 2, display: "flex", flexShrink: 0 }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={addTipRow}
              style={{
                alignSelf: "flex-start", padding: "3px 10px", borderRadius: C.r,
                border: `1px dashed ${C.amberBd}`, background: "transparent",
                color: C.amber, fontSize: 11, fontWeight: 600, cursor: "pointer",
                fontFamily: "inherit", display: "flex", alignItems: "center", gap: 4,
              }}
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              Dividir propina
            </button>
          </div>
        )}
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
              {/* PAGO cubre el total (subtotal + propina), igual que Fudo. */}
              <span>Pagado</span><span>${fmt(totalPaid)}</span>
            </div>
            {change > 0 && <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 700, color: C.green }}><span>Vuelto</span><span>${fmt(change)}</span></div>}
            {pending > 0 && <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 700, color: C.red }}><span>Falta</span><span>${fmt(pending)}</span></div>}
            {pending === 0 && change === 0 && <div style={{ fontSize: 13, fontWeight: 700, color: C.green, textAlign: "center" }}>Pagado exacto</div>}
          </div>
        )}
      </div>

      {/* Nota: el control "Dividir en N pers." que estaba acá se reemplazó
          por la sección "Mesa grande" arriba (junto a Forma de pago), que
          además de mostrar lo de cada uno, crea N filas listas para editar. */}

      {/* Error from checkout attempt — si el backend devolvió `shortages`
          (lista detallada de productos sin stock), la mostramos como Fudo.
          Si solo tenemos el string genérico, fallback al mensaje legible. */}
      {(error || (shortages && shortages.length > 0)) && (
        <div style={{
          padding: "10px 14px", marginBottom: 10, borderRadius: C.r,
          background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red,
          fontSize: 12, fontWeight: 600,
        }}>
          {shortages && shortages.length > 0 ? (
            <>
              <div style={{ marginBottom: 6 }}>
                {shortages.length === 1 ? "Producto sin stock:" : `${shortages.length} productos sin stock:`}
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontWeight: 500 }}>
                {shortages.map((s) => (
                  <li key={s.product_id} style={{ marginBottom: 2 }}>
                    <strong>{s.name}</strong>: {s.available} {s.unit} disponible{Number(s.required) > 1 ? `, ${s.required} ${s.unit} requerido` : ""}
                  </li>
                ))}
              </ul>
            </>
          ) : error?.includes("Insufficient stock") || error?.includes("stock") ? (
            "No hay stock suficiente para completar esta venta. Verifica el inventario."
          ) : (
            error
          )}
        </div>
      )}

      <div style={{ display: "flex", gap: 8 }}>
        <Btn variant="secondary" onClick={onClose}>Cancelar</Btn>
        <Btn variant={isConsumoInterno ? "danger" : "primary"} full size="lg"
          disabled={loading || lineSubtotal === 0 || (checkoutMode === "partial" && selLines.size === 0) || (!isConsumoInterno && totalPaid < grandTotal)}
          onClick={() => {
            // Fudo-style: PAGO cubre el TOTAL (subtotal + propina). La
            // separación propina↔cuenta vive en buildCheckoutSplit() (función
            // pura testeada en __tests__/mesas-checkout.test.ts) para poder
            // auditar todos los casos borde sin renderizar el componente.
            const split = buildCheckoutSplit(rows, tipRows, lineSubtotal);

            // En partial mode: mandar lineQtys SOLO para lines seleccionadas
            // donde el qty elegido es < line.qty (cobro parcial real).
            let partialLineQtys: Record<number, number> | undefined;
            if (checkoutMode === "partial" && !isConsumoInterno) {
              partialLineQtys = {};
              for (const lineId of selLines) {
                const line = unpaidLines.find(l => l.id === lineId);
                if (!line) continue;
                const qty = lineQtys[lineId] ?? Number(line.qty);
                if (qty < Number(line.qty)) {
                  partialLineQtys[lineId] = qty;
                }
              }
              if (Object.keys(partialLineQtys).length === 0) {
                partialLineQtys = undefined;
              }
            }
            onConfirm(
              isConsumoInterno ? [] : split.payments.map(p => ({ method: p.method, amount: p.amount })),
              isConsumoInterno ? 0 : split.tipTotal,
              checkoutMode, [...selLines],
              isConsumoInterno ? "CONSUMO_INTERNO" : "VENTA",
              isConsumoInterno ? undefined : split.tips,
              partialLineQtys,
            );
          }}>
          {loading ? <Spinner size={14} /> : null}
          {loading ? "Procesando…" : isConsumoInterno ? "Registrar consumo" : `Cobrar $${fmt(grandTotal)}`}
        </Btn>
      </div>
    </MesaModal>
  );
}
