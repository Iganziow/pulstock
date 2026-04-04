"use client";

import { useEffect, useRef, useState } from "react";
import { C } from "@/lib/theme";
import { formatCLP } from "@/lib/format";
import type { CartLine, PromoInfo } from "./types";
import { lineDiscount, lineSubtotal } from "./types";

/* ── DiscountCell (per line) ───────────────────────────────────────────────── */

function DiscountCell({ line, onChange, disabled }: {
  line: CartLine;
  onChange: (type: CartLine["discountType"], value: number) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const discount = lineDiscount(line);
  const hasDiscount = line.discountType !== "none" && line.discountValue > 0;

  return (
    <div ref={ref} style={{ position:"relative" }}>
      <button
        type="button"
        onClick={() => !disabled && setOpen((o) => !o)}
        className="xb"
        style={{
          height:34, padding:"0 10px", borderRadius:C.r, fontSize:11, fontWeight:600,
          border:`1px solid ${hasDiscount ? C.amberBd : C.border}`,
          background:hasDiscount ? C.amberBg : C.bg,
          color:hasDiscount ? C.amber : C.mute,
          display:"flex", alignItems:"center", gap:4,
        }}
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/>
          <line x1="7" y1="7" x2="7.01" y2="7"/>
        </svg>
        {hasDiscount
          ? line.discountType === "pct"
            ? `-${line.discountValue}%`
            : `-$${formatCLP(line.discountValue)}`
          : "Dscto."}
      </button>

      {open && (
        <div className="dd-in" style={{
          position:"absolute", top:"calc(100% + 6px)", right:0, zIndex:50,
          background:C.surface, border:`1px solid ${C.border}`,
          borderRadius:C.rMd, boxShadow:C.shMd, padding:12,
          width:200, display:"flex", flexDirection:"column", gap:10,
        }}>
          <div style={{ fontSize:11, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.06em" }}>
            Descuento por linea
          </div>

          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:4 }}>
            {(["none","pct","amt"] as const).map((t) => (
              <button key={t} type="button" onClick={() => onChange(t, t==="none"?0:line.discountValue)} className="xb" style={{
                padding:"5px 0", borderRadius:C.r, fontSize:11, fontWeight:600,
                border:`1px solid ${line.discountType===t ? C.accent : C.border}`,
                background:line.discountType===t ? C.accentBg : C.bg,
                color:line.discountType===t ? C.accent : C.mid,
              }}>
                {t==="none"?"Ninguno":t==="pct"?"% desc.":"$ monto"}
              </button>
            ))}
          </div>

          {line.discountType !== "none" && (
            <div>
              <label style={{ fontSize:11, fontWeight:700, color:C.mid, display:"block", marginBottom:4 }}>
                {line.discountType === "pct" ? "Porcentaje (%)" : "Monto ($)"}
              </label>
              <input
                type="number"
                min={0}
                max={line.discountType==="pct"?100:undefined}
                value={line.discountValue || ""}
                onChange={(e) => onChange(line.discountType, Math.max(0, Number(e.target.value)))}
                placeholder={line.discountType==="pct"?"10":"500"}
                autoFocus
                style={{
                  width:"100%", height:34, padding:"0 10px",
                  border:`1px solid ${C.border}`, borderRadius:C.r,
                  fontSize:13, fontWeight:600,
                }}
              />
              {discount > 0 && (
                <div style={{ fontSize:11, color:C.amber, marginTop:4, fontWeight:600 }}>
                  - ${formatCLP(discount)} de descuento
                </div>
              )}
            </div>
          )}

          <button type="button" onClick={() => setOpen(false)} className="xb" style={{
            alignSelf:"flex-end", fontSize:11, fontWeight:600, color:C.mid,
            background:"none", border:"none", padding:0, cursor:"pointer",
          }}>
            Cerrar
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Props ─────────────────────────────────────────────────────────────────── */

interface CartTableProps {
  cart: CartLine[];
  onUpdateQty: (id: number, qty: number) => void;
  onUpdateUnitPrice: (id: number, price: number) => void;
  onRemove: (id: number) => void;
  onUpdateDiscount: (id: number, type: CartLine["discountType"], value: number) => void;
  mob: boolean;
  promoMap: Record<number, PromoInfo>;
  busy?: boolean;
  /* Global discount & totals */
  globalDiscountType: "none"|"pct"|"amt";
  globalDiscountValue: number;
  globalDiscountAmt: number;
  onGlobalDiscountTypeChange: (t: "none"|"pct"|"amt") => void;
  onGlobalDiscountValueChange: (v: number) => void;
  total: number;
  itemsCount: number;
  totalLineDiscounts: number;
  /* Note */
  saleNote: string;
  showNote: boolean;
  onShowNoteToggle: () => void;
  onNoteChange: (v: string) => void;
}

export function CartTable({
  cart, onUpdateQty, onUpdateUnitPrice, onRemove, onUpdateDiscount,
  mob, promoMap, busy,
  globalDiscountType, globalDiscountValue, globalDiscountAmt,
  onGlobalDiscountTypeChange, onGlobalDiscountValueChange,
  total, itemsCount, totalLineDiscounts,
  saleNote, showNote, onShowNoteToggle, onNoteChange,
}: CartTableProps) {

  return (
    <>
      {/* ── CART TABLE ───────────────────────────────────────────── */}
      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>
       <div style={{ overflowX:mob?undefined:"auto" }}>
        {/* Header (desktop only) */}
        {!mob && (
          <div style={{
            display:"grid", gridTemplateColumns:"1fr 90px 120px 90px 80px 100px 36px",
            columnGap:10, padding:"10px 16px", background:C.bg,
            borderBottom:`1px solid ${C.border}`,
            fontSize:10.5, fontWeight:700, color:C.mute,
            textTransform:"uppercase", letterSpacing:"0.08em",
          }}>
            <div>Producto</div><div>SKU</div>
            <div style={{ textAlign:"right" }}>Precio unit.</div>
            <div style={{ textAlign:"center" }}>Cant.</div>
            <div style={{ textAlign:"center" }}>Dscto.</div>
            <div style={{ textAlign:"right" }}>Subtotal</div>
            <div/>
          </div>
        )}

        {cart.length === 0 ? (
          <div style={{ padding:mob?"40px 16px":"56px 24px", textAlign:"center" }}>
            <div style={{ fontSize:mob?28:36, marginBottom:10 }}>🛒</div>
            <div style={{ fontSize:mob?14:15, fontWeight:700, color:C.text, marginBottom:4 }}>Carrito vacio</div>
            <div style={{ fontSize:mob?12:13, color:C.mute }}>Escanea un producto o buscalo por nombre</div>
          </div>
        ) : (
          <>
            {cart.map((line, i) => {
              const p        = line.product;
              const subtotal = lineSubtotal(line);
              const disc     = lineDiscount(line);

              if (mob) {
                /* ── MOBILE CARD LAYOUT ── */
                return (
                  <div key={p.id} style={{
                    padding:"12px 14px",
                    borderBottom:i<cart.length-1?`1px solid ${C.border}`:"none",
                  }}>
                    {/* Row 1: name + remove */}
                    <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", gap:8, marginBottom:8 }}>
                      <div style={{ flex:1, minWidth:0 }}>
                        <div style={{ fontWeight:600, fontSize:13, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{p.name}</div>
                        <div style={{ fontSize:11, color:C.mute, marginTop:2 }}>
                          {p.sku && <span style={{ fontFamily:C.mono, marginRight:6 }}>{p.sku}</span>}
                          {p.category?.name ?? "Sin categoria"}
                        </div>
                      </div>
                      <button type="button" onClick={() => onRemove(p.id)} disabled={busy} className="xb" style={{
                        width:32, height:32, borderRadius:C.r, border:`1px solid ${C.border}`,
                        background:C.surface, color:C.mute, fontSize:14, flexShrink:0,
                        display:"flex", alignItems:"center", justifyContent:"center",
                      }}>✕</button>
                    </div>
                    {/* Row 2: price input + qty stepper + discount + subtotal */}
                    <div style={{ display:"flex", alignItems:"center", gap:8, flexWrap:"wrap" }}>
                      {/* Price */}
                      <input
                        value={Number.isFinite(line.unitPrice) ? String(line.unitPrice) : "0"}
                        onChange={(e) => onUpdateUnitPrice(p.id, Number(e.target.value))}
                        inputMode="decimal"
                        style={{
                          width:80, height:36, padding:"0 8px",
                          textAlign:"right", fontWeight:700, fontSize:13,
                          border:`1px solid ${C.border}`, borderRadius:C.r,
                          background:C.bg, fontFamily:C.font,
                        }}
                        disabled={busy}
                      />
                      {/* Qty */}
                      <div style={{ display:"flex", alignItems:"center", gap:3 }}>
                        <button type="button" onClick={() => onUpdateQty(p.id, line.qty-1)} disabled={busy} className="xb" style={{
                          width:36, height:36, borderRadius:C.r, border:`1px solid ${C.border}`,
                          background:C.surface, fontSize:15, fontWeight:700, color:C.mid,
                          display:"flex", alignItems:"center", justifyContent:"center",
                        }}>−</button>
                        <input
                          value={line.qty}
                          onChange={(e) => { const v = Number(e.target.value); onUpdateQty(p.id, Number.isFinite(v)?v:line.qty); }}
                          style={{
                            width:40, height:36, textAlign:"center", fontSize:13, fontWeight:700,
                            border:`1px solid ${C.border}`, borderRadius:C.r, background:C.bg,
                          }}
                          inputMode="numeric" disabled={busy}
                        />
                        <button type="button" onClick={() => onUpdateQty(p.id, line.qty+1)} disabled={busy} className="xb" style={{
                          width:36, height:36, borderRadius:C.r, border:`1px solid ${C.border}`,
                          background:C.surface, fontSize:15, fontWeight:700, color:C.mid,
                          display:"flex", alignItems:"center", justifyContent:"center",
                        }}>+</button>
                      </div>
                      {/* Discount */}
                      <DiscountCell
                        line={line}
                        onChange={(type, value) => onUpdateDiscount(p.id, type, value)}
                        disabled={!!busy}
                      />
                      {/* Subtotal */}
                      <div style={{ marginLeft:"auto", textAlign:"right" }}>
                        {disc > 0 && (
                          <div style={{ fontSize:10, color:C.mute, textDecoration:"line-through", fontVariantNumeric:"tabular-nums" }}>
                            ${formatCLP(line.unitPrice * line.qty)}
                          </div>
                        )}
                        <div style={{ fontWeight:800, fontSize:14, fontVariantNumeric:"tabular-nums", color:disc>0?C.amber:C.text }}>
                          ${formatCLP(subtotal)}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              }

              /* ── DESKTOP ROW LAYOUT ── */
              return (
                <div key={p.id} className="prow" style={{
                  display:"grid", gridTemplateColumns:"1fr 90px 120px 90px 80px 100px 36px",
                  columnGap:10, padding:"12px 16px",
                  borderBottom:i<cart.length-1?`1px solid ${C.border}`:"none",
                  alignItems:"center",
                }}>
                  {/* Product */}
                  <div style={{ minWidth:0 }}>
                    <div style={{ fontWeight:600, fontSize:14, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{p.name}</div>
                    <div style={{ fontSize:11, color:C.mute, marginTop:2 }}>
                      {p.category?.name ?? "Sin categoria"}
                      {p.barcodes?.[0]?.code && <span style={{ fontFamily:C.mono, marginLeft:6 }}>{p.barcodes[0].code}</span>}
                    </div>
                  </div>

                  {/* SKU */}
                  <div style={{ fontFamily:C.mono, fontSize:12, color:C.mid }}>{p.sku ?? "—"}</div>

                  {/* Unit price */}
                  <div style={{ display:"flex", justifyContent:"flex-end" }}>
                    <input
                      value={Number.isFinite(line.unitPrice) ? String(line.unitPrice) : "0"}
                      onChange={(e) => onUpdateUnitPrice(p.id, Number(e.target.value))}
                      inputMode="decimal"
                      style={{
                        width:110, height:32, padding:"0 8px",
                        textAlign:"right", fontWeight:700, fontSize:13,
                        border:`1px solid ${C.border}`, borderRadius:C.r,
                        background:C.bg, fontFamily:C.font,
                      }}
                      disabled={busy}
                    />
                  </div>

                  {/* Qty stepper */}
                  <div style={{ display:"flex", alignItems:"center", justifyContent:"center", gap:3 }}>
                    <button type="button" onClick={() => onUpdateQty(p.id, line.qty-1)} disabled={busy} className="xb" style={{
                      width:24, height:24, borderRadius:C.r, border:`1px solid ${C.border}`,
                      background:C.surface, fontSize:13, fontWeight:700, color:C.mid,
                    }}>−</button>
                    <input
                      value={line.qty}
                      onChange={(e) => { const v = Number(e.target.value); onUpdateQty(p.id, Number.isFinite(v)?v:line.qty); }}
                      style={{
                        width:36, height:24, textAlign:"center", fontSize:12, fontWeight:700,
                        border:`1px solid ${C.border}`, borderRadius:C.r, background:C.bg,
                      }}
                      inputMode="numeric" disabled={busy}
                    />
                    <button type="button" onClick={() => onUpdateQty(p.id, line.qty+1)} disabled={busy} className="xb" style={{
                      width:24, height:24, borderRadius:C.r, border:`1px solid ${C.border}`,
                      background:C.surface, fontSize:13, fontWeight:700, color:C.mid,
                    }}>+</button>
                  </div>

                  {/* Discount cell */}
                  <div style={{ display:"flex", justifyContent:"center" }}>
                    <DiscountCell
                      line={line}
                      onChange={(type, value) => onUpdateDiscount(p.id, type, value)}
                      disabled={!!busy}
                    />
                  </div>

                  {/* Subtotal */}
                  <div style={{ textAlign:"right" }}>
                    {disc > 0 && (
                      <div style={{ fontSize:11, color:C.mute, textDecoration:"line-through", fontVariantNumeric:"tabular-nums" }}>
                        ${formatCLP(line.unitPrice * line.qty)}
                      </div>
                    )}
                    <div style={{ fontWeight:800, fontSize:14, fontVariantNumeric:"tabular-nums", color:disc>0?C.amber:C.text }}>
                      ${formatCLP(subtotal)}
                    </div>
                  </div>

                  {/* Remove */}
                  <div style={{ display:"flex", justifyContent:"center" }}>
                    <button type="button" onClick={() => onRemove(p.id)} disabled={busy} className="xb" style={{
                      width:28, height:28, borderRadius:C.r, border:`1px solid ${C.border}`,
                      background:C.surface, color:C.mute, fontSize:14,
                      display:"flex", alignItems:"center", justifyContent:"center",
                    }}>✕</button>
                  </div>
                </div>
              );
            })}

            {/* ── Cart footer ─────────────────────────────────── */}
            <div style={{ padding:"12px 16px", background:C.bg, borderTop:`1px solid ${C.border}` }}>
              {/* Global discount row */}
              <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", gap:mob?8:12, marginBottom:10, flexWrap:mob?"wrap":undefined }}>
                <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.amber} strokeWidth="2.5" strokeLinecap="round">
                    <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/>
                    <line x1="7" y1="7" x2="7.01" y2="7"/>
                  </svg>
                  <span style={{ fontSize:12, fontWeight:700, color:C.mid }}>Descuento global</span>
                </div>
                <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                  {/* Type toggle */}
                  <div style={{ display:"flex", gap:3 }}>
                    {(["none","pct","amt"] as const).map((t) => (
                      <button key={t} type="button" onClick={() => { onGlobalDiscountTypeChange(t); if(t==="none") onGlobalDiscountValueChange(0); }} className="xb" style={{
                        height:26, padding:"0 8px", borderRadius:C.r, fontSize:11, fontWeight:600,
                        border:`1px solid ${globalDiscountType===t ? C.accent : C.border}`,
                        background:globalDiscountType===t ? C.accentBg : C.surface,
                        color:globalDiscountType===t ? C.accent : C.mute,
                      }}>
                        {t==="none"?"Ninguno":t==="pct"?"%":"$"}
                      </button>
                    ))}
                  </div>
                  {globalDiscountType !== "none" && (
                    <input
                      type="number" min={0}
                      max={globalDiscountType==="pct"?100:undefined}
                      value={globalDiscountValue || ""}
                      onChange={(e) => onGlobalDiscountValueChange(Math.max(0, Number(e.target.value)))}
                      placeholder={globalDiscountType==="pct"?"10":"500"}
                      style={{
                        width:80, height:26, padding:"0 8px",
                        border:`1px solid ${C.border}`, borderRadius:C.r,
                        fontSize:12, fontWeight:700, textAlign:"right",
                      }}
                    />
                  )}
                  {globalDiscountAmt > 0 && (
                    <span style={{ fontSize:12, fontWeight:700, color:C.amber }}>
                      -${formatCLP(globalDiscountAmt)}
                    </span>
                  )}
                </div>
              </div>

              {/* Totals summary */}
              <div style={{ display:"flex", justifyContent:"space-between", alignItems:mob?"flex-start":"center", flexDirection:mob?"column":"row", gap:mob?6:0 }}>
                <div style={{ fontSize:12, color:C.mute, display:"flex", gap:mob?8:14, flexWrap:"wrap" }}>
                  <span>{itemsCount} unidad{itemsCount!==1?"es":""}</span>
                  {(totalLineDiscounts + globalDiscountAmt) > 0 && (
                    <span style={{ color:C.amber, fontWeight:600 }}>
                      Ahorro total: -${formatCLP(totalLineDiscounts + globalDiscountAmt)}
                    </span>
                  )}
                </div>
                <span style={{ fontSize:15, fontWeight:800, color:C.text, fontVariantNumeric:"tabular-nums", alignSelf:mob?"flex-end":undefined }}>
                  Total:{" "}
                  <span style={{ color:C.accent, fontSize:18 }}>${formatCLP(total)}</span>
                </span>
              </div>
            </div>
          </>
        )}
       </div>
      </div>

      {/* ── NOTE ─────────────────────────────────────────────────── */}
      {cart.length > 0 && (
        <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>
          <button
            type="button"
            onClick={onShowNoteToggle}
            className="xb"
            style={{
              width:"100%", padding:"10px 16px", background:"transparent", border:"none", cursor:"pointer",
              display:"flex", alignItems:"center", justifyContent:"space-between", gap:8,
            }}
          >
            <div style={{ display:"flex", alignItems:"center", gap:8 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={saleNote ? C.accent : C.mute} strokeWidth="2.5" strokeLinecap="round">
                <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
              <span style={{ fontSize:13, fontWeight:600, color:saleNote ? C.accent : C.mid }}>
                Nota de venta {saleNote ? `· "${saleNote.slice(0,30)}${saleNote.length>30?"...":""}"` : "(opcional)"}
              </span>
            </div>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round"
              style={{ transition:"transform 0.15s", transform:showNote?"rotate(180deg)":"none" }}>
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
          {showNote && (
            <div style={{ padding:"0 16px 14px" }}>
              <textarea
                value={saleNote}
                onChange={(e) => onNoteChange(e.target.value)}
                placeholder="Ej: Mesa 4, Pedido #320, Nombre del cliente, instrucciones especiales..."
                rows={3}
                maxLength={300}
                style={{
                  width:"100%", padding:"10px 12px", resize:"vertical",
                  border:`1px solid ${C.border}`, borderRadius:C.r,
                  fontSize:13, lineHeight:1.55, fontFamily:C.font,
                }}
                autoFocus
              />
              <div style={{ fontSize:11, color:C.mute, textAlign:"right", marginTop:4 }}>
                {saleNote.length}/300
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
