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

          {sale && (
            <>
              {/* Void warning */}
              {isVoid && (
                <div style={{ padding:"10px 12px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, fontSize:13, color:C.red, fontWeight:600 }}>
                  Venta anulada — el total no contabiliza y el stock fue revertido.
                </div>
              )}

              {/* Metadata */}
              <div style={{ background:C.bg, borderRadius:C.r, padding:"12px 14px", display:"flex", flexDirection:"column", gap:8 }}>
                {[
                  { label:"Fecha",    value:fDateTime(sale.created_at) },
                  { label:"Bodega",   value:whName ?? `#${sale.warehouse_id}` },
                  { label:"Store ID", value:String(sale.store_id) },
                ].map(f => (
                  <div key={f.label} style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline", gap:8 }}>
                    <span style={{ fontSize:12, color:C.mute }}>{f.label}</span>
                    <span style={{ fontSize:13, fontWeight:600, color:C.text }}>{f.value}</span>
                  </div>
                ))}
              </div>

              {/* Payments */}
              {sale.payments?.length > 0 && (
                <div style={{ background:C.bg, borderRadius:C.r, padding:"12px 14px" }}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:8 }}>
                    <div style={{ fontSize:10, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.06em" }}>
                      Metodo de pago
                    </div>
                    {!isVoid && (
                      <button
                        type="button"
                        onClick={() => setShowEditPayments(true)}
                        title="Editar pagos"
                        className="xb"
                        style={{
                          background:"transparent", border:`1px solid ${C.border}`,
                          borderRadius:4, padding:"3px 6px", cursor:"pointer",
                          display:"inline-flex", alignItems:"center", color:C.mid,
                        }}
                      >
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                          <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>
                        </svg>
                      </button>
                    )}
                  </div>
                  <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                    {sale.payments.map((p, i) => {
                      const labels: Record<string, string> = { cash:"Efectivo", debit:"Debito", card:"Credito", transfer:"Transferencia" };
                      return (
                        <div key={i} style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline" }}>
                          <span style={{ fontSize:12, color:C.mid }}>{labels[p.method] ?? p.method}</span>
                          <span style={{ fontSize:13, fontWeight:700, fontVariantNumeric:"tabular-nums" }}>${fCLP(p.amount)}</span>
                        </div>
                      );
                    })}
                    {sale.payments.length > 1 && (
                      <div style={{ borderTop:`1px solid ${C.border}`, paddingTop:6, display:"flex", justifyContent:"space-between" }}>
                        <span style={{ fontSize:12, color:C.mute }}>Total pagado</span>
                        <span style={{ fontSize:13, fontWeight:800, color:C.accent, fontVariantNumeric:"tabular-nums" }}>
                          ${fCLP(sale.payments.reduce((s, p) => s + toNum(p.amount), 0))}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Propina — apartado separado para que se pueda cuadrar
                  con lo que entró al banco/caja. Muestra el desglose
                  por método de pago (Mario lo pidió: "ahora aca aparece
                  la propina pero no sale si la dejaron en debito
                  efectivo credito transferencia, esto es importante
                  para validar el cierre de caja"). */}
              {/* Si tip = 0 mostrar UI compacta con botón "Agregar" */}
              {(!sale.tip || toNum(sale.tip) === 0) && !isVoid && (
                <div style={{
                  background: C.bg, borderRadius: C.r, padding: "10px 14px",
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 16 }}>💵</span>
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                        Propina
                      </div>
                      <div style={{ fontSize: 12, color: C.mute, marginTop: 1 }}>Sin propina</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowEditTip(true)}
                    className="xb"
                    style={{
                      background: C.amberBg, color: C.amber, border: `1px solid ${C.amberBd}`,
                      borderRadius: 4, padding: "4px 10px", cursor: "pointer",
                      fontSize: 11, fontWeight: 600,
                    }}
                  >+ Agregar</button>
                </div>
              )}

              {sale.tip && toNum(sale.tip) > 0 && (() => {
                // Daniel 29/04/26: ahora `sale.tips` es la fuente de
                // verdad (relacional). Una venta puede tener N filas,
                // cada una con su método. Si está vacío (legacy), caemos
                // al cálculo proporcional desde payments para no romper
                // ventas viejas que no fueron migradas.
                const tipNum = toNum(sale.tip);
                const tipMethodLabels: Record<string, string> = {
                  cash: "Efectivo", debit: "Débito", card: "Crédito", transfer: "Transferencia",
                };
                const tipMethodIcons: Record<string, string> = {
                  cash: "💵", debit: "💳", card: "💳", transfer: "🏦",
                };

                let tipRows: Array<{ method: string; amount: number }> = [];
                if (Array.isArray(sale.tips) && sale.tips.length > 0) {
                  tipRows = sale.tips
                    .filter(t => toNum(t.amount) > 0)
                    .map(t => ({ method: t.method, amount: toNum(t.amount) }));
                } else {
                  // Fallback legacy: reparto proporcional según payments
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
                    const lastShare = tipNum - running;
                    tipByMethod[last.method] = (tipByMethod[last.method] || 0) + lastShare;
                  }
                  tipRows = Object.entries(tipByMethod)
                    .filter(([_, amt]) => amt > 0)
                    .map(([method, amount]) => ({ method, amount }));
                }
                tipRows.sort((a, b) => b.amount - a.amount);

                return (
                  <div style={{
                    background: C.amberBg, borderRadius: C.r,
                    padding: "12px 14px",
                    border: `1px solid ${C.amberBd}`,
                  }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent:"space-between", gap: 8, marginBottom: 8 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 18 }}>💵</span>
                        <div style={{ fontSize: 10, fontWeight: 700, color: C.amber, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                          Propina cobrada
                        </div>
                      </div>
                      {!isVoid && (
                        <button
                          type="button"
                          onClick={() => setShowEditTip(true)}
                          title="Editar propina"
                          className="xb"
                          style={{
                            background:"transparent", border:`1px solid ${C.amberBd}`,
                            borderRadius:4, padding:"3px 6px", cursor:"pointer",
                            display:"inline-flex", alignItems:"center", color:C.amber,
                          }}
                        >
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                            <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>
                          </svg>
                        </button>
                      )}
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.mid }}>
                        <span>Total de la venta</span>
                        <span style={{ fontWeight: 600, color: C.text, fontVariantNumeric: "tabular-nums" }}>${fCLP(sale.total)}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.mid }}>
                        <span>Propina</span>
                        <span style={{ fontWeight: 700, color: C.amber, fontVariantNumeric: "tabular-nums" }}>+${fCLP(sale.tip)}</span>
                      </div>

                      {/* Desglose por método. Cada SaleTip es una fila
                          individual (split soportado). Si solo hay 1 fila
                          mostramos "Pagada con X" para mejor legibilidad. */}
                      {tipRows.length > 0 && (
                        <div style={{ marginTop: 4, paddingLeft: 12, borderLeft: `2px solid ${C.amberBd}`, display: "flex", flexDirection: "column", gap: 2 }}>
                          {tipRows.map((row, idx) => (
                            <div key={`${row.method}-${idx}`} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: C.mid }}>
                              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                <span style={{ fontSize: 12 }}>{tipMethodIcons[row.method] || "💰"}</span>
                                {tipRows.length === 1 ? "Pagada con " : ""}{tipMethodLabels[row.method] || row.method}
                              </span>
                              <span style={{ fontWeight: 700, color: C.amber, fontVariantNumeric: "tabular-nums" }}>
                                ${fCLP(row.amount)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

                      <div style={{
                        display: "flex", justifyContent: "space-between",
                        fontSize: 13, fontWeight: 800, color: C.text,
                        paddingTop: 6, marginTop: 4, borderTop: `1px dashed ${C.amberBd}`,
                      }}>
                        <span>Total cobrado al cliente</span>
                        <span style={{ fontVariantNumeric: "tabular-nums" }}>
                          ${fCLP(toNum(sale.total) + toNum(sale.tip))}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* Financials */}
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
                {[
                  { label:"Subtotal",   value:`$${fCLP(sale.subtotal)}`,    color:C.text },
                  { label:"Total",      value:`$${fCLP(sale.total)}`,       color:C.accent },
                  { label:"Costo",      value:`$${fCLP(sale.total_cost)}`,  color:C.mid },
                  { label:"Utilidad",   value:pct !== null ? `$${fCLP(sale.gross_profit)} (${pct}%)` : `$${fCLP(sale.gross_profit)}`,
                    color:toNum(sale.gross_profit) >= 0 ? C.green : C.red },
                ].map(f => (
                  <div key={f.label} style={{ background:C.bg, borderRadius:C.r, padding:"10px 12px" }}>
                    <div style={{ fontSize:10, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.06em" }}>{f.label}</div>
                    <div style={{ fontSize:14, fontWeight:800, color:f.color, marginTop:4, fontVariantNumeric:"tabular-nums" }}>{f.value}</div>
                  </div>
                ))}
              </div>

              {/* Lines */}
              <div>
                <div style={{ fontSize:11, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8 }}>
                  Lineas ({sale.lines?.length ?? 0})
                </div>
                <div style={{ border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden" }}>
                  {/* header */}
                  <div style={{
                    display:"grid", gridTemplateColumns:"1fr 44px 80px 80px",
                    columnGap:8, padding:"8px 12px",
                    background:C.bg, borderBottom:`1px solid ${C.border}`,
                    fontSize:10, fontWeight:700, color:C.mute,
                    textTransform:"uppercase", letterSpacing:"0.07em",
                  }}>
                    <div>Producto</div>
                    <div style={{ textAlign:"center" }}>Qty</div>
                    <div style={{ textAlign:"right" }}>P. Unit</div>
                    <div style={{ textAlign:"right" }}>Total</div>
                  </div>
                  {sale.lines?.map((l, i) => {
                    const profit = toNum(l.line_profit);
                    return (
                      <div key={l.id} style={{
                        display:"grid", gridTemplateColumns:"1fr 44px 80px 80px",
                        columnGap:8, padding:"10px 12px",
                        borderBottom:i < sale.lines.length-1 ? `1px solid ${C.border}` : "none",
                        alignItems:"start",
                      }}>
                        <div>
                          <div style={{ fontWeight:600, fontSize:13 }}>{l.product?.name ?? "Producto"}</div>
                          {l.product?.sku && (
                            <div style={{ fontSize:10, color:C.mute, fontFamily:C.mono, marginTop:1 }}>{l.product.sku}</div>
                          )}
                          {l.line_profit != null && (
                            <div style={{ fontSize:10, marginTop:3, color:profit >= 0 ? C.green : C.red, fontWeight:600 }}>
                              Utilidad: ${fCLP(l.line_profit)}
                            </div>
                          )}
                        </div>
                        <div style={{ textAlign:"center", fontSize:13, fontWeight:600, color:C.mid }}>
                          {(() => {
                            // Mostrar qty sin ceros decimales innecesarios.
                            // "1.000" → "1", "1.500" → "1.5"
                            const n = Number(l.qty);
                            return Number.isInteger(n) ? String(n) : String(parseFloat(n.toFixed(3)));
                          })()}
                          {/* Anti-fraude (Daniel 29/04/26): NO se puede editar
                              cantidad de líneas post-venta. Si se necesita
                              corregir un error de cantidad, se anula la venta
                              entera y se crea una nueva. Sin esta restricción
                              una cajera podría vender 2, cobrar y luego editar
                              a 1 quedándose con la diferencia. */}
                        </div>
                        <div style={{ textAlign:"right", fontSize:12, color:C.mid, fontVariantNumeric:"tabular-nums" }}>
                          ${fCLP(l.unit_price)}
                        </div>
                        <div style={{ textAlign:"right", fontWeight:700, fontSize:13, fontVariantNumeric:"tabular-nums" }}>
                          ${fCLP(l.line_total)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {showVoid && sale && (
        <VoidModal
          saleId={sale.id}
          onClose={() => setShowVoid(false)}
          onDone={() => { setShowVoid(false); onVoided(); }}
        />
      )}

      {/* Edit modals — estilo Fudo: ✏️ inline en cada sección */}
      {sale && (
        <EditPaymentsModal
          open={showEditPayments}
          saleId={sale.id}
          currentPayments={sale.payments?.map(p => ({ method: p.method as any, amount: p.amount })) ?? []}
          total={toNum(sale.total)}
          tip={toNum(sale.tip ?? "0")}
          onClose={() => setShowEditPayments(false)}
          onSaved={refresh}
        />
      )}
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
