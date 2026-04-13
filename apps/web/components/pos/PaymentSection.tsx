"use client";

import Link from "next/link";
import { C } from "@/lib/theme";
import { formatCLP } from "@/lib/format";
import { Btn, Spinner } from "@/components/ui";
import type { CartLine, PromoInfo, PosPayRow } from "./types";
import { PAY_METHODS } from "./types";

/* ── Props ─────────────────────────────────────────────────────────────────── */

interface PaymentSectionProps {
  cart: CartLine[];
  mob: boolean;
  busy: boolean;
  meErr: string | null;
  warehouseId: number | null;
  /* Summary data */
  selectedWarehouseName: string;
  itemsCount: number;
  totalLineDiscounts: number;
  globalDiscountAmt: number;
  total: number;
  saleNote: string;
  /* Payment state */
  payRows: PosPayRow[];
  onPayRowsChange: (rows: PosPayRow[]) => void;
  tipAmount: string;
  onTipChange: (v: string) => void;
  tip: number;
  grandTotal: number;
  totalPaid: number;
  pendingAmount: number;
  change: number | null;
  /* Actions */
  onSubmit: () => void;
  /* Last sale */
  lastSaleId: number | null;
  lastSaleNumber: number | null;
}

export function PaymentSection({
  cart, mob, busy, meErr, warehouseId,
  selectedWarehouseName, itemsCount, totalLineDiscounts, globalDiscountAmt,
  total, saleNote,
  payRows, onPayRowsChange, tipAmount, onTipChange,
  tip, grandTotal, totalPaid, pendingAmount, change,
  onSubmit,
  lastSaleId, lastSaleNumber,
}: PaymentSectionProps) {

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:12, position:"sticky", top:mob?undefined:24, bottom:mob?0:undefined, zIndex:mob?30:undefined, ...(mob?{background:C.bg, margin:"0 -12px", padding:"12px 12px 16px", borderTop:`1px solid ${C.border}`, boxShadow:"0 -4px 12px rgba(0,0,0,0.06)"}:{}) }}>

      {/* Summary */}
      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>
        <div style={{ padding:"12px 18px", borderBottom:`1px solid ${C.border}`, background:C.bg }}>
          <div style={{ fontSize:11, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.07em" }}>Resumen</div>
        </div>
        <div style={{ padding:"14px 18px", display:"flex", flexDirection:"column", gap:9 }}>
          <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, color:C.mid }}>
            <span>Productos</span><span style={{ fontWeight:600, color:C.text }}>{cart.length}</span>
          </div>
          <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, color:C.mid }}>
            <span>Unidades</span><span style={{ fontWeight:600, color:C.text }}>{itemsCount}</span>
          </div>
          <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, color:C.mid }}>
            <span>Bodega</span><span style={{ fontWeight:600, color:C.text, fontSize:12 }}>{selectedWarehouseName}</span>
          </div>
          {(totalLineDiscounts + globalDiscountAmt) > 0 && (
            <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, color:C.amber }}>
              <span>Descuentos</span>
              <span style={{ fontWeight:700 }}>-${formatCLP(totalLineDiscounts + globalDiscountAmt)}</span>
            </div>
          )}
          {saleNote && (
            <div style={{
              fontSize:12, color:C.mid, background:C.bg,
              border:`1px solid ${C.border}`, borderRadius:C.r,
              padding:"6px 10px", fontStyle:"italic",
            }}>
              "{saleNote.slice(0,60)}{saleNote.length>60?"...":""}"
            </div>
          )}
          <div style={{ height:1, background:C.border }}/>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline" }}>
            <span style={{ fontSize:13, color:C.mid }}>Total</span>
            <span style={{ fontSize:22, fontWeight:800, color:C.accent, letterSpacing:"-0.03em", fontVariantNumeric:"tabular-nums" }}>
              ${formatCLP(total)}
            </span>
          </div>
        </div>
      </div>

      {/* ═══ PAGO ═══ */}
      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>

        {/* Header */}
        <div style={{ padding:"12px 18px", borderBottom:`1px solid ${C.border}`, background:C.bg, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
          <div style={{ fontSize:11, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.07em" }}>Metodo de pago</div>
          {payRows.length > 1 && pendingAmount > 0 && (
            <div style={{ fontSize:11, fontWeight:700, color:C.amber }}>Resta: ${formatCLP(pendingAmount)}</div>
          )}
        </div>

        <div style={{ padding:"14px 18px", display:"flex", flexDirection:"column", gap:12 }}>

          {/* ── Single payment method ── */}
          {payRows.length === 1 && (
            <>
              <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:6 }}>
                {PAY_METHODS.map(m => {
                  const active = payRows[0].method === m.value;
                  return (
                    <button key={m.value} type="button"
                      onClick={() => onPayRowsChange([{ method: m.value, amount: payRows[0].amount }])}
                      style={{
                        display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center",
                        gap:4, padding:"12px 4px", borderRadius:C.r, cursor:"pointer", fontFamily:"inherit",
                        fontSize:11, fontWeight:700, transition:"all .15s ease",
                        border: active ? `2px solid ${C.accent}` : `1px solid ${C.border}`,
                        background: active ? C.accentBg : C.surface,
                        color: active ? C.accent : C.mid,
                      }}>
                      <span style={{ fontSize:22 }}>{m.icon}</span>
                      {m.label}
                    </button>
                  );
                })}
              </div>

              {/* Amount input */}
              <div style={{ position:"relative" }}>
                <input
                  value={payRows[0].amount}
                  onChange={e => onPayRowsChange([{ ...payRows[0], amount: e.target.value }])}
                  placeholder={`$${formatCLP(grandTotal)}`}
                  inputMode="decimal"
                  style={{
                    width:"100%", height:52, padding:"0 52px 0 16px", boxSizing:"border-box",
                    border:`2px solid ${payRows[0].amount ? C.accent : C.border}`,
                    borderRadius:C.rMd, fontSize:22, fontWeight:800, textAlign:"right",
                    background: payRows[0].amount ? C.accentBg : C.bg, outline:"none", fontFamily:C.mono,
                  }}
                />
                <button type="button" title="Cobrar total"
                  onClick={() => onPayRowsChange([{ ...payRows[0], amount: String(grandTotal) }])}
                  disabled={grandTotal <= 0}
                  style={{
                    position:"absolute", right:8, top:"50%", transform:"translateY(-50%)",
                    height:36, width:36, borderRadius:8, border:"none",
                    background: grandTotal > 0 ? C.accent : C.border, color:"#fff",
                    cursor: grandTotal > 0 ? "pointer" : "default", display:"flex",
                    alignItems:"center", justifyContent:"center",
                    opacity: grandTotal <= 0 ? 0.3 : 1,
                  }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </button>
              </div>

              {/* Split payment button */}
              <button type="button"
                onClick={() => {
                  const used = payRows[0].method;
                  const next = PAY_METHODS.find(m => m.value !== used);
                  if (next) onPayRowsChange([...payRows, { method: next.value, amount: "" }]);
                }}
                style={{
                  background:"none", border:`1px dashed ${C.borderMd}`, borderRadius:C.r,
                  padding:"8px 0", cursor:"pointer", color:C.mid, fontSize:12,
                  fontWeight:600, fontFamily:"inherit", textAlign:"center",
                }}>
                + Dividir pago
              </button>
            </>
          )}

          {/* ── Split payment (multiple methods) ── */}
          {payRows.length > 1 && (
            <>
              {payRows.map((row, i) => {
                const used = new Set(payRows.map(r => r.method));
                const available = PAY_METHODS.filter(m => m.value === row.method || !used.has(m.value));
                return (
                  <div key={`pay-${i}`} style={{ display:"flex", gap:8, alignItems:"center" }}>
                    {/* Method selector */}
                    <select
                      value={row.method}
                      onChange={e => onPayRowsChange(payRows.map((r, j) => j === i ? { ...r, method: e.target.value } : r))}
                      style={{
                        width:130, height:44, padding:"0 8px", border:`1px solid ${C.border}`,
                        borderRadius:C.r, fontSize:13, fontWeight:600, background:C.surface,
                        fontFamily:"inherit", cursor:"pointer",
                      }}>
                      {available.map(m => (
                        <option key={m.value} value={m.value}>{m.icon} {m.label}</option>
                      ))}
                    </select>
                    {/* Amount */}
                    <div style={{ flex:1, position:"relative" }}>
                      <input
                        value={row.amount}
                        onChange={e => onPayRowsChange(payRows.map((r, j) => j === i ? { ...r, amount: e.target.value } : r))}
                        placeholder="$0"
                        inputMode="decimal"
                        style={{
                          width:"100%", height:44, padding:"0 44px 0 12px", boxSizing:"border-box",
                          border:`1px solid ${row.amount ? C.accent : C.border}`,
                          borderRadius:C.r, fontSize:18, fontWeight:700, textAlign:"right",
                          background: row.amount ? C.accentBg : C.bg, outline:"none", fontFamily:C.mono,
                        }}
                      />
                      <button type="button" title="Cobrar restante"
                        onClick={() => onPayRowsChange(payRows.map((r, j) => j === i ? { ...r, amount: String((Number(r.amount)||0) + pendingAmount) } : r))}
                        disabled={pendingAmount <= 0}
                        style={{
                          position:"absolute", right:4, top:"50%", transform:"translateY(-50%)",
                          height:32, width:32, borderRadius:6, border:"none",
                          background: pendingAmount > 0 ? C.accent : C.border, color:"#fff",
                          cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center",
                          opacity: pendingAmount <= 0 ? 0.3 : 1,
                        }}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                      </button>
                    </div>
                    {/* Remove */}
                    <button type="button"
                      onClick={() => onPayRowsChange(payRows.filter((_, j) => j !== i))}
                      style={{
                        width:32, height:32, borderRadius:6, border:`1px solid ${C.border}`,
                        background:C.bg, color:C.mute, cursor:"pointer", display:"flex",
                        alignItems:"center", justifyContent:"center", fontSize:14, flexShrink:0,
                      }}>✕</button>
                  </div>
                );
              })}
              {/* Add another method */}
              {payRows.length < PAY_METHODS.length && (
                <button type="button"
                  onClick={() => {
                    const used = new Set(payRows.map(r => r.method));
                    const next = PAY_METHODS.find(m => !used.has(m.value));
                    if (next) onPayRowsChange([...payRows, { method: next.value, amount: "" }]);
                  }}
                  style={{
                    background:"none", border:`1px dashed ${C.borderMd}`, borderRadius:C.r,
                    padding:"7px 0", cursor:"pointer", color:C.mid, fontSize:12,
                    fontWeight:600, fontFamily:"inherit", textAlign:"center",
                  }}>
                  + Agregar metodo
                </button>
              )}
            </>
          )}

          {/* ── Tip ── */}
          <div style={{ display:"flex", alignItems:"center", gap:10, paddingTop:10, borderTop:`1px solid ${C.border}` }}>
            <div style={{ flexShrink:0, display:"flex", alignItems:"center", gap:6, fontSize:13, fontWeight:600, color:C.mid }}>
              <span style={{ fontSize:16 }}>🤝</span> Propina
            </div>
            <input
              value={tipAmount}
              onChange={e => onTipChange(e.target.value)}
              placeholder="$0 (opcional)"
              inputMode="decimal"
              style={{
                flex:1, height:mob?44:36, padding:"0 12px",
                border:`1px solid ${tipAmount && Number(tipAmount) > 0 ? C.amberBd : C.border}`,
                borderRadius:C.r, fontSize:14, fontWeight:600, textAlign:"right",
                background: tipAmount && Number(tipAmount) > 0 ? C.amberBg : C.bg,
              }}
            />
          </div>
          {tip > 0 && (
            <div style={{ padding:"8px 12px", borderRadius:C.r, background:C.amberBg, border:`1px solid ${C.amberBd}`, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
              <span style={{ fontSize:12, color:C.amber, fontWeight:600 }}>Total con propina</span>
              <span style={{ fontSize:16, fontWeight:800, color:C.amber, fontVariantNumeric:"tabular-nums" }}>${formatCLP(grandTotal)}</span>
            </div>
          )}

          {/* ── Change / Exact payment ── */}
          {change !== null && change > 0 && (
            <div style={{ padding:"14px 16px", borderRadius:10, background:"#ECFDF5", border:"2px solid #16A34A", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
              <div>
                <div style={{ fontSize:11, fontWeight:700, color:"#16A34A", textTransform:"uppercase", letterSpacing:".05em" }}>Vuelto</div>
                <div style={{ fontSize:10, color:"#52525B", marginTop:2 }}>Devolver al cliente</div>
              </div>
              <span style={{ fontSize:28, fontWeight:900, color:"#16A34A", fontVariantNumeric:"tabular-nums" }}>${formatCLP(change)}</span>
            </div>
          )}
          {change !== null && change === 0 && (
            <div style={{ padding:"10px 14px", borderRadius:10, background:"#EEF2FF", border:"1.5px solid #C7D2FE", textAlign:"center" }}>
              <span style={{ fontSize:13, fontWeight:700, color:"#4F46E5" }}>✓ Pago exacto</span>
            </div>
          )}
        </div>
      </div>

      {/* Confirm */}
      <Btn variant="primary" size="lg" full onClick={onSubmit}
        disabled={busy || !!meErr || cart.length === 0 || !warehouseId || totalPaid < grandTotal}>
        {busy ? <><Spinner size={16}/>Procesando...</> : (
          <>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            Confirmar venta · ${formatCLP(grandTotal)}
          </>
        )}
      </Btn>

      {lastSaleId && (
        <Link href={`/dashboard/pos/receipt/${lastSaleId}`} style={{
          display:"flex", alignItems:"center", justifyContent:"center", gap:6,
          fontSize:13, fontWeight:600, color:C.mid, textDecoration:"none", padding:"6px 0",
        }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
          </svg>
          Ver ultimo recibo
        </Link>
      )}
    </div>
  );
}
