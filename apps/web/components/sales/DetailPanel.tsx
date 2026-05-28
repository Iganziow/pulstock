"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Btn, Spinner } from "@/components/ui";
import { SaleStatusBadge } from "./SaleStatusBadge";
import { VoidModal } from "./VoidModal";
import { EditPaymentsModal, EditTipModal } from "./SaleEditModals";
import { toNum, fCLP, fDateTime, profitPct } from "./helpers";
import type { SaleDetail, Warehouse } from "./types";

export function DetailPanel({ saleId, onClose, onVoided, warehouses, mob }: {
  saleId: number;
  onClose: ()=>void;
  onVoided: ()=>void;
  warehouses: Warehouse[];
  mob?: boolean;
}) {
  const [sale, setSale]       = useState<SaleDetail|null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr]         = useState<string|null>(null);
  const [showVoid, setShowVoid] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  // Modales de edición tipo Fudo. Solo pagos y propina son editables;
  // la cantidad de items NO se permite editar (anti-fraude — ver
  // comentario en la tabla de líneas).
  const [showEditPayments, setShowEditPayments] = useState(false);
  const [showEditTip, setShowEditTip]           = useState(false);

  function refresh() { setRefreshKey(k => k + 1); }

  useEffect(() => {
    setSale(null); setLoading(true); setErr(null);
    (async () => {
      try {
        const data = (await apiFetch(`/sales/sales/${saleId}/`)) as SaleDetail;
        setSale(data);
      } catch (e:any) { setErr(e?.message ?? "Error cargando detalle"); }
      finally { setLoading(false); }
    })();
  }, [saleId, refreshKey]);

  const isVoid    = (sale?.status ?? "").toUpperCase() === "VOID";
  const pct       = sale ? profitPct(sale.gross_profit, sale.total) : null;
  const whName    = warehouses.find(w => w.id === sale?.warehouse_id)?.name;

  return (
    <>
      {mob && <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.4)", zIndex:49 }} onClick={onClose}/>}
      <div className="panel-in" style={{
        ...(mob ? {
          position:"fixed", inset:0, zIndex:50, width:"100%",
          borderRadius:0, maxHeight:"100vh",
        } : {
          width:400, flexShrink:0,
          borderRadius:C.rMd,
          maxHeight:"calc(100vh - 140px)",
          position:"sticky" as const, top:24,
        }),
        background:C.surface, border:`1px solid ${C.border}`,
        boxShadow:C.shMd,
        display:"flex", flexDirection:"column",
        overflow:"hidden",
      }}>
        {/* Header */}
        <div style={{
          padding:"14px 18px", borderBottom:`1px solid ${C.border}`,
          display:"flex", alignItems:"center", justifyContent:"space-between", gap:8, flexShrink:0,
        }}>
          <div>
            <div style={{ fontSize:13, fontWeight:700, color:C.text }}>
              Venta <span style={{ fontFamily:C.mono }}>#{sale?.sale_number ?? saleId}</span>
            </div>
            {sale && <div style={{ marginTop:3 }}><SaleStatusBadge status={sale.status}/></div>}
          </div>
          <div style={{ display:"flex", gap:6 }}>
            {sale && !isVoid && (
              <Btn variant="danger" size="sm" onClick={() => setShowVoid(true)}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
                </svg>
                Anular
              </Btn>
            )}
            <Link href={`/dashboard/pos/receipt/${saleId}`} target="_blank" style={{
              display:"inline-flex", alignItems:"center", gap:5,
              height:30, padding:"0 10px", borderRadius:C.r, fontSize:11, fontWeight:600,
              border:`1px solid ${C.borderMd}`, background:C.surface, color:C.mid,
              textDecoration:"none", whiteSpace:"nowrap",
            }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/>
                <rect x="6" y="14" width="12" height="8"/>
              </svg>
              Imprimir
            </Link>
            <button type="button" aria-label="Cerrar" onClick={onClose} className="xb" style={{
              width:mob?36:30, height:mob?36:30, borderRadius:C.r, border:`1px solid ${C.border}`,
              background:C.bg, color:C.mute, fontSize:mob?20:16, display:"flex", alignItems:"center", justifyContent:"center",
            }}>{mob?"← Volver":"✕"}</button>
          </div>
        </div>

        {/* Body -- scrollable */}
        <div style={{ flex:1, overflowY:"auto", padding:"16px 18px", display:"flex", flexDirection:"column", gap:14 }}>
          {loading && (
            <div style={{ display:"flex", alignItems:"center", justifyContent:"center", gap:8, padding:40, color:C.mute }}>
              <Spinner size={16}/><span style={{ fontSize:13 }}>Cargando…</span>
            </div>
          )}

          {err && (
            <div style={{ padding:"10px 12px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, color:C.red, fontSize:13 }}>
              {err}
            </div>
          )}

          {sale && (() => {
            // ---- Cálculos compartidos (orden nuevo: hero → líneas → métricas → pago → propina → meta)
            const tipNum    = toNum(sale.tip);
            const totalNum  = toNum(sale.total);
            const grandNum  = totalNum + tipNum;
            const profitNum = toNum(sale.gross_profit);

            const payLabels: Record<string, string> = {
              cash: "Efectivo", debit: "Débito", card: "Crédito", transfer: "Transferencia",
            };
            const payIcons: Record<string, string> = {
              cash: "💵", debit: "💳", card: "💳", transfer: "🏦",
            };

            // Tip rows (relacional con fallback legacy)
            let tipRows: Array<{ method: string; amount: number }> = [];
            if (tipNum > 0) {
              if (Array.isArray(sale.tips) && sale.tips.length > 0) {
                tipRows = sale.tips
                  .filter(t => toNum(t.amount) > 0)
                  .map(t => ({ method: t.method, amount: toNum(t.amount) }));
              } else {
                const payments = sale.payments || [];
                const totalPaid = payments.reduce((s, p) => s + toNum(p.amount), 0);
                const tipByMethod: Record<string, number> = {};
                if (payments.length > 0 && totalPaid > 0) {
                  let running = 0;
                  for (let i = 0; i < payments.length - 1; i++) {
                    const p = payments[i];
                    const share = Math.round(tipNum * toNum(p.amount) / totalPaid);
                    tipByMethod[p.method] = (tipByMethod[p.method] || 0) + share;
                    running += share;
                  }
                  const last = payments[payments.length - 1];
                  tipByMethod[last.method] = (tipByMethod[last.method] || 0) + (tipNum - running);
                }
                tipRows = Object.entries(tipByMethod)
                  .filter(([_, amt]) => amt > 0)
                  .map(([method, amount]) => ({ method, amount }));
              }
              tipRows.sort((a, b) => b.amount - a.amount);
            }

            const rawPayments = sale.payments ?? [];
            const totalPaymentsRaw = rawPayments.reduce((s, p) => s + toNum(p.amount), 0);

            // ── Detección de venta LEGACY ──
            // Ventas previas a Fase A (Tips Fudo-style) guardan
            // SalePayment.amount = subtotal + propina MEZCLADOS. En Fase A
            // SalePayment.amount = solo el subtotal de la venta.
            // Si sum(payments) > total con tolerancia → legacy.
            const isLegacyMixedPayment = totalPaymentsRaw > totalNum + 0.5;

            // Pagos NETOS (solo la parte de venta). Para Fase A coinciden
            // con sale.payments. Para legacy, prorrateamos cada pago:
            // pago_neto[i] = pago_raw[i] × (total / sum_raw)
            // Esto es lo que se muestra y lo que se pre-rellena al editar
            // para que Mario edite siempre el "monto de venta" claro.
            const netPayments = rawPayments.map((p, idx) => {
              if (!isLegacyMixedPayment || totalPaymentsRaw <= 0) {
                return { method: p.method, amount: toNum(p.amount), raw: toNum(p.amount) };
              }
              // Prorrateo, ajustando el último para que sume exacto al total.
              const isLast = idx === rawPayments.length - 1;
              if (isLast) {
                const accSoFar = rawPayments.slice(0, idx).reduce((s, pp) => {
                  return s + Math.round(toNum(pp.amount) * totalNum / totalPaymentsRaw);
                }, 0);
                return { method: p.method, amount: Math.max(0, totalNum - accSoFar), raw: toNum(p.amount) };
              }
              return {
                method: p.method,
                amount: Math.round(toNum(p.amount) * totalNum / totalPaymentsRaw),
                raw: toNum(p.amount),
              };
            });
            const totalPaymentsNet = netPayments.reduce((s, p) => s + p.amount, 0);

            return (
              <>
                {/* Void warning */}
                {isVoid && (
                  <div style={{ padding:"10px 12px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, fontSize:13, color:C.red, fontWeight:600 }}>
                    Venta anulada — el total no contabiliza y el stock fue revertido.
                  </div>
                )}

                {/* ───────── HERO: Total cobrado al cliente ───────── */}
                <div style={{
                  background: tipNum > 0 ? C.amberBg : C.bg,
                  border: `1px solid ${tipNum > 0 ? C.amberBd : C.border}`,
                  borderRadius: C.rMd, padding: "14px 16px",
                }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: tipNum > 0 ? C.amber : C.mute, textTransform: "uppercase", letterSpacing: "0.07em" }}>
                    {tipNum > 0 ? "Total cobrado al cliente" : "Total de la venta"}
                  </div>
                  <div style={{ fontSize: 26, fontWeight: 800, color: C.text, marginTop: 2, fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}>
                    ${fCLP(grandNum)}
                  </div>
                  {tipNum > 0 && (
                    <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap", fontSize: 11 }}>
                      <span style={{ background: C.surface, border: `1px solid ${C.amberBd}`, borderRadius: 999, padding: "3px 9px", color: C.mid, fontWeight: 600 }}>
                        Venta <span style={{ color: C.text, fontVariantNumeric: "tabular-nums" }}>${fCLP(sale.total)}</span>
                      </span>
                      <span style={{ background: C.surface, border: `1px solid ${C.amberBd}`, borderRadius: 999, padding: "3px 9px", color: C.amber, fontWeight: 700 }}>
                        + Propina <span style={{ fontVariantNumeric: "tabular-nums" }}>${fCLP(sale.tip)}</span>
                      </span>
                    </div>
                  )}
                </div>

                {/* ───────── LÍNEAS (contenido principal arriba) ───────── */}
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
                    Productos ({sale.lines?.length ?? 0})
                  </div>
                  <div style={{ border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden" }}>
                    <div style={{
                      display: "grid", gridTemplateColumns: "1fr 44px 80px 80px",
                      columnGap: 8, padding: "8px 12px",
                      background: C.bg, borderBottom: `1px solid ${C.border}`,
                      fontSize: 10, fontWeight: 700, color: C.mute,
                      textTransform: "uppercase", letterSpacing: "0.07em",
                    }}>
                      <div>Producto</div>
                      <div style={{ textAlign: "center" }}>Cant.</div>
                      <div style={{ textAlign: "right" }}>P. Unit</div>
                      <div style={{ textAlign: "right" }}>Total</div>
                    </div>
                    {sale.lines?.map((l, i) => {
                      const profit = toNum(l.line_profit);
                      const qtyN = Number(l.qty);
                      const qtyTxt = Number.isInteger(qtyN) ? String(qtyN) : String(parseFloat(qtyN.toFixed(3)));
                      return (
                        <div key={l.id} style={{
                          display: "grid", gridTemplateColumns: "1fr 44px 80px 80px",
                          columnGap: 8, padding: "10px 12px",
                          borderBottom: i < sale.lines.length - 1 ? `1px solid ${C.border}` : "none",
                          alignItems: "start",
                        }}>
                          <div>
                            <div style={{ fontWeight: 600, fontSize: 13 }}>{l.product?.name ?? "Producto"}</div>
                            {l.product?.sku && (
                              <div style={{ fontSize: 10, color: C.mute, fontFamily: C.mono, marginTop: 1 }}>{l.product.sku}</div>
                            )}
                            {l.line_profit != null && (
                              <div style={{ fontSize: 10, marginTop: 3, color: profit >= 0 ? C.green : C.red, fontWeight: 600 }}>
                                Utilidad: ${fCLP(l.line_profit)}
                              </div>
                            )}
                          </div>
                          {/* Cantidad — Anti-fraude: NO editable post-venta. Para
                              corregir errores, se anula y se rehace la venta. Sin
                              esta restricción una cajera podría cobrar 2 y luego
                              bajarlo a 1, quedándose con la diferencia. */}
                          <div style={{ textAlign: "center", fontSize: 13, fontWeight: 600, color: C.mid }}>{qtyTxt}</div>
                          <div style={{ textAlign: "right", fontSize: 12, color: C.mid, fontVariantNumeric: "tabular-nums" }}>${fCLP(l.unit_price)}</div>
                          <div style={{ textAlign: "right", fontWeight: 700, fontSize: 13, fontVariantNumeric: "tabular-nums" }}>${fCLP(l.line_total)}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* ───────── MÉTRICAS COMPACTAS (3 col) ───────── */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                  {[
                    { label: "Subtotal", value: `$${fCLP(sale.subtotal)}`, color: C.text },
                    { label: "Costo",    value: `$${fCLP(sale.total_cost)}`, color: C.mid },
                    { label: "Utilidad", value: pct !== null ? `${pct}%` : `$${fCLP(sale.gross_profit)}`,
                      color: profitNum >= 0 ? C.green : C.red,
                      sub: pct !== null ? `$${fCLP(sale.gross_profit)}` : null },
                  ].map(f => (
                    <div key={f.label} style={{ background: C.bg, borderRadius: C.r, padding: "8px 10px" }}>
                      <div style={{ fontSize: 9, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em" }}>{f.label}</div>
                      <div style={{ fontSize: 14, fontWeight: 800, color: f.color, marginTop: 3, fontVariantNumeric: "tabular-nums" }}>{f.value}</div>
                      {f.sub && (
                        <div style={{ fontSize: 10, color: C.mute, marginTop: 1, fontVariantNumeric: "tabular-nums" }}>{f.sub}</div>
                      )}
                    </div>
                  ))}
                </div>

                {/* ───────── PAGO (siempre monto NETO de venta) ───────── */}
                {rawPayments.length > 0 && (
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                        Cómo pagó la venta
                      </div>
                      {!isVoid && (
                        <button
                          type="button"
                          onClick={() => setShowEditPayments(true)}
                          title="Editar pagos"
                          className="xb"
                          style={{
                            background: "transparent", border: `1px solid ${C.border}`,
                            borderRadius: 4, padding: "3px 8px", cursor: "pointer",
                            display: "inline-flex", alignItems: "center", gap: 4,
                            color: C.mid, fontSize: 11, fontWeight: 600,
                          }}
                        >
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                            <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>
                          </svg>
                          Editar
                        </button>
                      )}
                    </div>
                    <div style={{ background: C.bg, borderRadius: C.r, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
                      {netPayments.map((p, i) => (
                        <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: C.mid }}>
                            <span style={{ fontSize: 14 }}>{payIcons[p.method] ?? "💰"}</span>
                            {payLabels[p.method] ?? p.method}
                          </span>
                          <span style={{ fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>${fCLP(p.amount)}</span>
                        </div>
                      ))}
                      {netPayments.length > 1 && (
                        <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 6, display: "flex", justifyContent: "space-between" }}>
                          <span style={{ fontSize: 12, color: C.mute }}>Total venta</span>
                          <span style={{ fontSize: 13, fontWeight: 800, color: C.accent, fontVariantNumeric: "tabular-nums" }}>
                            ${fCLP(totalPaymentsNet)}
                          </span>
                        </div>
                      )}
                    </div>
                    {isLegacyMixedPayment && (
                      <div style={{
                        marginTop: 6, padding: "6px 10px",
                        background: C.amberBg, border: `1px solid ${C.amberBd}`,
                        borderRadius: 6, fontSize: 11, color: C.amber, lineHeight: 1.4,
                        display: "flex", alignItems: "flex-start", gap: 6,
                      }}>
                        <span style={{ fontSize: 12 }}>ⓘ</span>
                        <span>
                          <b>Venta antigua:</b> el pago original venía con la propina sumada (${fCLP(totalPaymentsRaw)}).
                          Mostramos sólo la parte de venta para que sea claro qué editar.
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {/* ───────── PROPINA (sin propina) ───────── */}
                {tipNum === 0 && !isVoid && (
                  <div style={{
                    background: C.bg, borderRadius: C.r, padding: "8px 12px",
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    border: `1px dashed ${C.border}`,
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 14 }}>💵</span>
                      <span style={{ fontSize: 12, color: C.mute }}>Sin propina</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowEditTip(true)}
                      className="xb"
                      style={{
                        background: C.amberBg, color: C.amber, border: `1px solid ${C.amberBd}`,
                        borderRadius: 4, padding: "4px 10px", cursor: "pointer",
                        fontSize: 11, fontWeight: 700,
                      }}
                    >+ Agregar propina</button>
                  </div>
                )}

                {/* ───────── PROPINA (con desglose por método) ───────── */}
                {tipNum > 0 && (
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: C.amber, textTransform: "uppercase", letterSpacing: "0.06em", display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 14 }}>💵</span>
                        Propina <span style={{ color: C.mute, fontWeight: 600 }}>· ${fCLP(sale.tip)}</span>
                      </div>
                      {!isVoid && (
                        <button
                          type="button"
                          onClick={() => setShowEditTip(true)}
                          title="Editar propina"
                          className="xb"
                          style={{
                            background: "transparent", border: `1px solid ${C.amberBd}`,
                            borderRadius: 4, padding: "3px 8px", cursor: "pointer",
                            display: "inline-flex", alignItems: "center", gap: 4,
                            color: C.amber, fontSize: 11, fontWeight: 600,
                          }}
                        >
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                            <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>
                          </svg>
                          Editar
                        </button>
                      )}
                    </div>
                    <div style={{ background: C.amberBg, border: `1px solid ${C.amberBd}`, borderRadius: C.r, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
                      {tipRows.map((row, idx) => (
                        <div key={`${row.method}-${idx}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: C.mid }}>
                            <span style={{ fontSize: 14 }}>{payIcons[row.method] || "💰"}</span>
                            {payLabels[row.method] || row.method}
                          </span>
                          <span style={{ fontSize: 13, fontWeight: 700, color: C.amber, fontVariantNumeric: "tabular-nums" }}>
                            ${fCLP(row.amount)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* ───────── METADATA (al final, compacta) ───────── */}
                <div style={{
                  display: "flex", flexWrap: "wrap", gap: "4px 14px",
                  paddingTop: 8, borderTop: `1px solid ${C.border}`,
                  fontSize: 11, color: C.mute,
                }}>
                  <span><span style={{ color: C.mute }}>Fecha · </span><span style={{ color: C.mid, fontWeight: 600 }}>{fDateTime(sale.created_at)}</span></span>
                  <span><span style={{ color: C.mute }}>Bodega · </span><span style={{ color: C.mid, fontWeight: 600 }}>{whName ?? `#${sale.warehouse_id}`}</span></span>
                </div>
              </>
            );
          })()}
        </div>
      </div>

      {showVoid && sale && (
        <VoidModal
          saleId={sale.id}
          onClose={() => setShowVoid(false)}
          onDone={() => { setShowVoid(false); onVoided(); }}
        />
      )}

      {/* Edit modals — estilo Fudo: ✏️ inline en cada sección.
          IMPORTANTE: pre-rellenamos con los pagos NETOS (sin propina embebida).
          En ventas legacy SalePayment.amount viene con la propina sumada;
          mostrarlo así al editar confunde y permite guardar inconsistencia
          (pagos > subtotal + tip de SaleTip). Pasamos el net + flag para
          que el modal explique. */}
      {sale && (() => {
        const totalNum = toNum(sale.total);
        const rawPayments = sale.payments ?? [];
        const totalRaw = rawPayments.reduce((s, p) => s + toNum(p.amount), 0);
        const isLegacy = totalRaw > totalNum + 0.5;
        const netForModal = rawPayments.map((p, idx) => {
          if (!isLegacy || totalRaw <= 0) return { method: p.method as any, amount: String(Math.round(toNum(p.amount))) };
          const isLast = idx === rawPayments.length - 1;
          if (isLast) {
            const acc = rawPayments.slice(0, idx).reduce((s, pp) => s + Math.round(toNum(pp.amount) * totalNum / totalRaw), 0);
            return { method: p.method as any, amount: String(Math.max(0, Math.round(totalNum - acc))) };
          }
          return { method: p.method as any, amount: String(Math.round(toNum(p.amount) * totalNum / totalRaw)) };
        });
        return (
          <EditPaymentsModal
            open={showEditPayments}
            saleId={sale.id}
            currentPayments={netForModal}
            total={totalNum}
            tip={toNum(sale.tip ?? "0")}
            isLegacy={isLegacy}
            legacyRawTotal={totalRaw}
            onClose={() => setShowEditPayments(false)}
            onSaved={refresh}
          />
        );
      })()}
      {sale && (
        <EditTipModal
          open={showEditTip}
          saleId={sale.id}
          currentTips={
            // Si hay filas SaleTip, usarlas. Si no (legacy con sale.tip > 0),
            // inicializar el modal con 1 fila cash con el monto total para
            // que el dueño pueda editarlo y al guardar quede convertido a
            // SaleTip relacional automáticamente.
            Array.isArray(sale.tips) && sale.tips.length > 0
              ? sale.tips.map(t => ({ method: t.method, amount: t.amount }))
              : (toNum(sale.tip ?? "0") > 0
                  ? [{ method: ((sale.tip_method as any) || "cash") as any, amount: String(sale.tip ?? "0") }]
                  : [])
          }
          total={toNum(sale.total)}
          totalPaid={(sale.payments ?? []).reduce((s, p) => s + toNum(p.amount), 0)}
          onClose={() => setShowEditTip(false)}
          onSaved={refresh}
        />
      )}
    </>
  );
}
