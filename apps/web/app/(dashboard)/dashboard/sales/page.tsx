"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";

// ─── Responsive hook ─────────────────────────────────────────────────────────

function useIsMobile(){const[m,setM]=useState(false);useEffect(()=>{const fn=()=>setM(window.innerWidth<768);fn();window.addEventListener("resize",fn);return()=>window.removeEventListener("resize",fn);},[]);return m;}

// ─── Types ────────────────────────────────────────────────────────────────────

type SaleRow = {
  id: number;
  sale_number?: number | null;
  created_at: string;
  store_id: number;
  warehouse_id: number;
  subtotal: string;
  total: string;
  total_cost: string;
  gross_profit: string;
  status: string;
  created_by_id: number;
  open_order_id?: number | null;
  table_name?: string | null;
};

type Product = { id: number; name: string; sku?: string | null };
type SaleLine = {
  id: number;
  product: Product;
  qty: string;
  unit_price: string;
  line_total: string;
  unit_cost_snapshot?: string | null;
  line_cost?: string | null;
  line_profit?: string | null;
};
type SalePayment = { method: "cash" | "card" | "debit" | "transfer"; amount: string };
type SaleDetail = {
  id: number;
  sale_number?: number | null;
  created_at: string;
  store_id: number;
  warehouse_id: number;
  subtotal: string;
  total: string;
  total_cost: string;
  gross_profit: string;
  status: string;
  payments: SalePayment[];
  lines: SaleLine[];
};

type Warehouse = { id: number; name: string; is_active: boolean; warehouse_type?: string };

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toNum(v: string | number | null | undefined): number {
  if (v == null) return 0;
  const n = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(n) ? n : 0;
}
function fCLP(v: string | number | null | undefined): string {
  return Math.round(toNum(v)).toLocaleString("es-CL");
}
function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
function fDateTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-CL", { day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit" });
}
function fDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("es-CL", { day:"2-digit", month:"2-digit", year:"numeric" });
}
function profitPct(profit: string, total: string): number | null {
  const t = toNum(total); const p = toNum(profit);
  if (t === 0) return null;
  return Math.round((p / t) * 100);
}

// ─── Mini-components ──────────────────────────────────────────────────────────

function Spinner({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
      style={{ animation:"spin 0.7s linear infinite", display:"block", flexShrink:0 }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
    </svg>
  );
}

type BtnV = "primary"|"secondary"|"ghost"|"danger"|"success";
function Btn({ children, onClick, variant="secondary", disabled, size="md", full }: {
  children: React.ReactNode; onClick?: ()=>void;
  variant?: BtnV; disabled?: boolean; size?: "sm"|"md"|"lg"; full?: boolean;
}) {
  const vs: Record<BtnV,React.CSSProperties> = {
    primary:   { background:C.accent,  color:"#fff", border:`1px solid ${C.accent}` },
    secondary: { background:C.surface, color:C.text, border:`1px solid ${C.borderMd}` },
    ghost:     { background:"transparent", color:C.mid, border:"1px solid transparent" },
    danger:    { background:C.redBg,   color:C.red,  border:`1px solid ${C.redBd}` },
    success:   { background:C.greenBg, color:C.green,border:`1px solid ${C.greenBd}` },
  };
  const h = size==="lg"?46:size==="sm"?30:38;
  const px = size==="lg"?"0 20px":size==="sm"?"0 10px":"0 14px";
  const fs = size==="lg"?14:size==="sm"?11:13;
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="xb" style={{
      ...vs[variant], display:"inline-flex", alignItems:"center", justifyContent:"center", gap:6,
      height:h, padding:px, borderRadius:C.r, fontSize:fs, fontWeight:600,
      letterSpacing:"0.01em", whiteSpace:"nowrap", width:full?"100%":undefined,
    }}>{children}</button>
  );
}

function StatusBadge({ status }: { status: string }) {
  const s = (status || "").toUpperCase();
  const isVoid = s === "VOID";
  return (
    <span style={{
      display:"inline-flex", alignItems:"center", gap:5,
      padding:"3px 9px", borderRadius:99, fontSize:11, fontWeight:700,
      border:`1px solid ${isVoid ? C.redBd : C.greenBd}`,
      background:isVoid ? C.redBg : C.greenBg,
      color:isVoid ? C.red : C.green,
      letterSpacing:"0.03em",
    }}>
      <span style={{ width:6, height:6, borderRadius:"50%", background:"currentColor", display:"inline-block" }}/>
      {isVoid ? "Anulada" : "Completada"}
    </span>
  );
}

function StatCard({ label, value, sub, color, icon }: {
  label: string; value: string; sub?: string;
  color: string; icon: React.ReactNode;
}) {
  return (
    <div style={{
      background:C.surface, border:`1px solid ${C.border}`,
      borderRadius:C.rMd, padding:"14px 18px", boxShadow:C.sh,
      display:"flex", flexDirection:"column", gap:8,
    }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
        <div style={{ fontSize:10.5, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.07em" }}>{label}</div>
        <div style={{ color, opacity:0.7 }}>{icon}</div>
      </div>
      <div style={{ fontSize:22, fontWeight:800, color, letterSpacing:"-0.03em", fontVariantNumeric:"tabular-nums" }}>{value}</div>
      {sub && <div style={{ fontSize:11, color:C.mute }}>{sub}</div>}
    </div>
  );
}

// ─── Void modal ───────────────────────────────────────────────────────────────

function VoidModal({ saleId, onClose, onDone }: { saleId: number; onClose: ()=>void; onDone: ()=>void }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy]     = useState(false);
  const [err, setErr]       = useState<string|null>(null);

  async function doVoid() {
    if (!reason.trim()) { setErr("Debes ingresar un motivo."); return; }
    setBusy(true); setErr(null);
    try {
      await apiFetch(`/sales/sales/${saleId}/void/`, { method:"POST", body:JSON.stringify({ reason: reason.trim() }) });
      onDone();
    } catch (e: any) {
      setErr(e instanceof ApiError ? e.message : (e?.message ?? "No se pudo anular"));
    } finally { setBusy(false); }
  }

  return (
    <div className="bd-in" style={{
      position:"fixed", inset:0, background:"rgba(0,0,0,0.4)",
      display:"grid", placeItems:"center", padding:20, zIndex:60,
    }}>
      <div className="m-in" style={{
        width:"min(520px,100%)", background:C.surface,
        borderRadius:C.rLg, border:`1px solid ${C.border}`,
        boxShadow:C.shLg, overflow:"hidden",
      }}>
        {/* Accent bar */}
        <div style={{ height:3, background:C.red }}/>
        <div style={{ padding:"20px 24px" }}>
          <div style={{ fontSize:15, fontWeight:700, color:C.text, marginBottom:4 }}>Anular venta #{saleId}</div>
          <div style={{ fontSize:13, color:C.mute, marginBottom:16 }}>
            Esta acción revertirá el stock de todos los productos. Ingresa un motivo obligatorio.
          </div>

          <label style={{ fontSize:11, fontWeight:700, color:C.mid, textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:6 }}>
            Motivo <span style={{ color:C.red }}>*</span>
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Ej: Error en el cobro, devolución del cliente…"
            rows={3}
            disabled={busy}
            autoFocus
            style={{
              width:"100%", padding:"10px 12px", resize:"vertical",
              border:`1px solid ${C.border}`, borderRadius:C.r,
              fontSize:13, fontFamily:C.font, lineHeight:1.55,
            }}
          />

          {err && (
            <div style={{ marginTop:10, padding:"9px 12px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, color:C.red, fontSize:13 }}>
              {err}
            </div>
          )}

          <div style={{ display:"flex", justifyContent:"flex-end", gap:8, marginTop:16 }}>
            <Btn variant="ghost" onClick={onClose} disabled={busy}>Cancelar</Btn>
            <Btn variant="danger" onClick={doVoid} disabled={busy || !reason.trim()}>
              {busy ? <><Spinner/>Anulando…</> : "Confirmar anulación"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Detail Panel ─────────────────────────────────────────────────────────────

function DetailPanel({ saleId, onClose, onVoided, warehouses, mob }: {
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

  useEffect(() => {
    setSale(null); setLoading(true); setErr(null);
    (async () => {
      try {
        const data = (await apiFetch(`/sales/sales/${saleId}/`)) as SaleDetail;
        setSale(data);
      } catch (e:any) { setErr(e?.message ?? "Error cargando detalle"); }
      finally { setLoading(false); }
    })();
  }, [saleId]);

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
            {sale && <div style={{ marginTop:3 }}><StatusBadge status={sale.status}/></div>}
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
            <button onClick={onClose} className="xb" style={{
              width:mob?36:30, height:mob?36:30, borderRadius:C.r, border:`1px solid ${C.border}`,
              background:C.bg, color:C.mute, fontSize:mob?20:16, display:"flex", alignItems:"center", justifyContent:"center",
            }}>{mob?"← Volver":"✕"}</button>
          </div>
        </div>

        {/* Body — scrollable */}
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
                  ⚠️ Venta anulada — el total no contabiliza y el stock fue revertido.
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
                  <div style={{ fontSize:10, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8 }}>
                    Método de pago
                  </div>
                  <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                    {sale.payments.map((p, i) => {
                      const labels: Record<string, string> = { cash:"💵 Efectivo", debit:"💳 Débito", card:"💳 Crédito", transfer:"🏦 Transferencia" };
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
                  Líneas ({sale.lines?.length ?? 0})
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
                        <div style={{ textAlign:"center", fontSize:13, fontWeight:600, color:C.mid }}>{l.qty}</div>
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
    </>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

const PAGE_CSS = `
.prow.active{background:#EEF2FF}
.panel-in{animation:panelIn 0.2s cubic-bezier(0.4,0,0.2,1) both}
@keyframes panelIn{from{opacity:0;transform:translateX(12px)}to{opacity:1;transform:none}}
`;

export default function SalesPage() {
  useGlobalStyles(PAGE_CSS);
  const mob = useIsMobile();

  const [items, setItems]       = useState<SaleRow[]>([]);
  const [loading, setLoading]   = useState(true);
  const [err, setErr]           = useState<string|null>(null);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);

  // Filters
  const [q, setQ]               = useState("");
  const [status, setStatus]     = useState<"ALL"|"COMPLETED"|"VOID">("ALL");
  const [range, setRange]       = useState<"TODAY"|"7D"|"30D"|"ALL">("30D");
  const [warehouseId, setWarehouseId] = useState<number|"ALL">("ALL");

  // Selected row → detail panel
  const [selectedId, setSelectedId] = useState<number|null>(null);

  // Endpoint
  const endpoint = useMemo(() => {
    const base = "/sales/sales/list/";
    const p    = new URLSearchParams();
    const qq   = q.trim();
    if (qq) p.set("q", qq);
    if (status !== "ALL") p.set("status", status);
    if (warehouseId !== "ALL") p.set("warehouse_id", String(warehouseId));
    if (range !== "ALL") {
      const now = new Date();
      let start = new Date(now);
      if (range === "TODAY") start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      else if (range === "7D") start.setDate(now.getDate()-7);
      else if (range === "30D") start.setDate(now.getDate()-30);
      p.set("date_from", isoDate(start));
      p.set("date_to", isoDate(now));
    }
    const qs = p.toString();
    return qs ? `${base}?${qs}` : base;
  }, [q, status, range, warehouseId]);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const data = await apiFetch(endpoint);
      setItems(data?.results ?? data ?? []);
    } catch (e:any) { setErr(e?.message ?? "Error cargando ventas"); setItems([]); }
    finally { setLoading(false); }
  }, [endpoint]);

  useEffect(() => {
    (async () => {
      try {
        const ws = (await apiFetch("/core/warehouses/")) as Warehouse[];
        setWarehouses(Array.isArray(ws) ? ws : []);
      } catch { setWarehouses([]); }
    })();
  }, []);

  useEffect(() => {
    const t = setTimeout(() => load(), 250);
    return () => clearTimeout(t);
  }, [load]);

  // ── Metrics ─────────────────────────────────────────────────────────────────
  const metrics = useMemo(() => {
    const completed = items.filter(s => s.status.toUpperCase() === "COMPLETED");
    const total     = completed.reduce((a, s) => a + toNum(s.total), 0);
    const cost      = completed.reduce((a, s) => a + toNum(s.total_cost), 0);
    const profit    = completed.reduce((a, s) => a + toNum(s.gross_profit), 0);
    const pct       = total > 0 ? Math.round((profit / total) * 100) : 0;
    return {
      ventas:    items.length,
      completadas: completed.length,
      total,
      profit,
      pct,
      anuladas:  items.filter(s => s.status.toUpperCase() === "VOID").length,
    };
  }, [items]);

  // ─────────────────────────────── RENDER ──────────────────────────────────

  return (
    <div style={{ fontFamily:C.font, color:C.text, background:C.bg, minHeight:"100vh", padding:mob?"16px 12px":"24px 28px", display:"flex", flexDirection:"column", gap:16 }}>

      {/* ── HEADER ─────────────────────────────────────────────────────── */}
      <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between", gap:12, flexWrap:"wrap" }}>
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:4 }}>
            <div style={{ width:4, height:26, background:C.accent, borderRadius:2 }}/>
            <h1 style={{ margin:0, fontSize:mob?18:22, fontWeight:800, color:C.text, letterSpacing:"-0.04em" }}>Ventas</h1>
          </div>
          {!mob && <p style={{ margin:0, fontSize:13, color:C.mute, paddingLeft:14 }}>
            Historial de ventas · haz clic en una fila para ver el detalle
          </p>}
        </div>
        <Btn variant="secondary" size="sm" onClick={load} disabled={loading}>
          {loading ? <Spinner/> : (
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
            </svg>
          )}
          {loading ? "Cargando…" : "Recargar"}
        </Btn>
      </div>

      {/* ── STAT CARDS ─────────────────────────────────────────────────── */}
      <div style={{ display:"grid", gridTemplateColumns:mob?"1fr 1fr":"repeat(auto-fit, minmax(160px,1fr))", gap:10 }}>
        <StatCard label="Total ventas" value={String(metrics.ventas)}
          sub={`${metrics.completadas} completadas · ${metrics.anuladas} anuladas`}
          color={C.accent}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 01-8 0"/></svg>}
        />
        <StatCard label="Ingresos" value={`$${fCLP(metrics.total)}`}
          sub="Solo ventas completadas"
          color={C.accent}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>}
        />
        <StatCard label="Utilidad bruta" value={`$${fCLP(metrics.profit)}`}
          sub={`Margen ${metrics.pct}%`}
          color={metrics.profit >= 0 ? C.green : C.red}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>}
        />
        <StatCard label="Anuladas" value={String(metrics.anuladas)}
          color={C.red}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>}
        />
      </div>

      {/* ── FILTERS ────────────────────────────────────────────────────── */}
      <div style={{
        background:C.surface, border:`1px solid ${C.border}`,
        borderRadius:C.rMd, padding:"12px 16px", boxShadow:C.sh,
        display:"flex", gap:10, alignItems:"center", flexWrap:"wrap",
      }}>
        {/* Search */}
        <div style={{ position:"relative", flex:1, minWidth:200 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round"
            style={{ position:"absolute", left:10, top:"50%", transform:"translateY(-50%)", pointerEvents:"none" }}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Buscar por # venta o ID…"
            style={{
              width:"100%", height:36, padding:"0 10px 0 34px",
              border:`1px solid ${C.border}`, borderRadius:C.r,
              fontSize:13, background:C.bg,
            }}
          />
        </div>

        <div style={{ width:1, height:24, background:C.border }}/>

        {/* Range */}
        {([
          { v:"TODAY", l:"Hoy" },
          { v:"7D",    l:"7 días" },
          { v:"30D",   l:"30 días" },
          { v:"ALL",   l:"Todo" },
        ] as const).map(b => (
          <button key={b.v} type="button" onClick={() => setRange(b.v)} className="xb" style={{
            height:32, padding:"0 12px", borderRadius:C.r, fontSize:12, fontWeight:600,
            border:`1px solid ${range===b.v ? C.accent : C.border}`,
            background:range===b.v ? C.accentBg : C.surface,
            color:range===b.v ? C.accent : C.mid,
          }}>{b.l}</button>
        ))}

        <div style={{ width:1, height:24, background:C.border }}/>

        {/* Status */}
        <select value={status} onChange={e => setStatus(e.target.value as any)} style={{
          height:36, padding:"0 10px", border:`1px solid ${C.border}`,
          borderRadius:C.r, fontSize:13, background:C.bg,
        }}>
          <option value="ALL">Todos los estados</option>
          <option value="COMPLETED">Completadas</option>
          <option value="VOID">Anuladas</option>
        </select>

        {/* Warehouse */}
        {warehouses.length > 0 && (
          <select value={warehouseId} onChange={e => setWarehouseId(e.target.value === "ALL" ? "ALL" : Number(e.target.value))} style={{
            height:36, padding:"0 10px", border:`1px solid ${C.border}`,
            borderRadius:C.r, fontSize:13, background:C.bg,
          }}>
            <option value="ALL">Todas las bodegas</option>
            {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}{w.warehouse_type==="sales_floor"?" (Sala)":" (Bodega)"}</option>)}
          </select>
        )}
      </div>

      {/* ── MAIN: TABLE + PANEL ─────────────────────────────────────────── */}
      <div style={{ display:"flex", gap:14, alignItems:"flex-start", flexDirection:mob?"column":"row" }}>

        {/* TABLE */}
        <div style={{ flex:1, minWidth:0, display:"flex", flexDirection:"column", gap:0, width:mob?"100%":undefined }}>
          <div style={{
            background:C.surface, border:`1px solid ${C.border}`,
            borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh,
          }}>
          <div style={{ overflowX:"auto" }}>
            {/* Header */}
            <div style={{
              display:"grid", gridTemplateColumns:mob?"60px 1fr 90px 80px":"80px 1fr 80px 140px 120px 120px 110px",
              columnGap:mob?8:12, padding:mob?"10px 12px":"10px 18px",
              background:C.bg, borderBottom:`1px solid ${C.border}`,
              fontSize:10.5, fontWeight:700, color:C.mute,
              textTransform:"uppercase", letterSpacing:"0.08em",
            }}>
              <div>Folio</div>
              <div>Fecha</div>
              {!mob && <div>Origen</div>}
              {!mob && <div>Bodega</div>}
              <div style={{ textAlign:"right" }}>Total</div>
              {!mob && <div style={{ textAlign:"right" }}>Utilidad</div>}
              <div style={{ textAlign:"center" }}>Estado</div>
            </div>

            {loading && (
              <div style={{ padding:"52px 0", display:"flex", alignItems:"center", justifyContent:"center", gap:10, color:C.mute }}>
                <Spinner size={16}/><span style={{ fontSize:13 }}>Cargando ventas…</span>
              </div>
            )}

            {err && (
              <div style={{ padding:"20px 18px" }}>
                <div style={{ padding:"11px 14px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, color:C.red, fontSize:13 }}>
                  {err}
                </div>
              </div>
            )}

            {!loading && !err && items.length === 0 && (
              <div style={{ padding:"56px 24px", textAlign:"center" }}>
                <div style={{ fontSize:36, marginBottom:10 }}>📋</div>
                <div style={{ fontSize:15, fontWeight:700, color:C.text, marginBottom:4 }}>No hay ventas</div>
                <div style={{ fontSize:13, color:C.mute }}>Cambia los filtros o el rango de fechas</div>
              </div>
            )}

            {!loading && !err && items.map((s, i) => {
              const isSelected = s.id === selectedId;
              const isVoid     = s.status.toUpperCase() === "VOID";
              const profit     = toNum(s.gross_profit);
              const pct        = profitPct(s.gross_profit, s.total);
              const whName     = warehouses.find(w => w.id === s.warehouse_id)?.name ?? `#${s.warehouse_id}`;
              return (
                <div
                  key={s.id}
                  className={`prow${isSelected ? " active" : ""}`}
                  onClick={() => setSelectedId(isSelected ? null : s.id)}
                  style={{
                    display:"grid", gridTemplateColumns:mob?"60px 1fr 90px 80px":"80px 1fr 80px 140px 120px 120px 110px",
                    columnGap:mob?8:12, padding:mob?"11px 12px":"13px 18px",
                    borderBottom:i<items.length-1?`1px solid ${C.border}`:"none",
                    alignItems:"center",
                    opacity:isVoid ? 0.6 : 1,
                    borderLeft:isSelected ? `3px solid ${C.accent}` : "3px solid transparent",
                  }}
                >
                  {/* Folio */}
                  <div style={{ fontFamily:C.mono, fontWeight:700, fontSize:mob?12:13, color:isSelected?C.accent:C.text }}>
                    #{s.sale_number ?? s.id}
                  </div>

                  {/* Date */}
                  <div>
                    <div style={{ fontSize:mob?12:13, fontWeight:500 }}>{fDate(s.created_at)}</div>
                    <div style={{ fontSize:11, color:C.mute, marginTop:1 }}>
                      {new Date(s.created_at).toLocaleTimeString("es-CL", { hour:"2-digit", minute:"2-digit" })}
                    </div>
                  </div>

                  {/* Origin */}
                  {!mob && <div>
                    {s.open_order_id ? (
                      <span style={{ fontSize:10, padding:"2px 7px", borderRadius:99, background:"#FFFBEB", color:"#D97706", border:"1px solid #FDE68A", fontWeight:600 }}>
                        {s.table_name || "Mesa"}
                      </span>
                    ) : (
                      <span style={{ fontSize:10, padding:"2px 7px", borderRadius:99, background:"#EEF2FF", color:"#4F46E5", border:"1px solid #C7D2FE", fontWeight:600 }}>
                        POS
                      </span>
                    )}
                  </div>}

                  {/* Warehouse */}
                  {!mob && <div style={{ fontSize:12, color:C.mid }}>{whName}</div>}

                  {/* Total */}
                  <div style={{ textAlign:"right", fontWeight:800, fontSize:mob?13:14, fontVariantNumeric:"tabular-nums" }}>
                    {isVoid ? <span style={{ textDecoration:"line-through", color:C.mute }}>${fCLP(s.total)}</span> : `$${fCLP(s.total)}`}
                  </div>

                  {/* Profit */}
                  {!mob && <div style={{ textAlign:"right" }}>
                    {!isVoid && (
                      <>
                        <div style={{ fontWeight:700, fontSize:13, color:profit>=0?C.green:C.red, fontVariantNumeric:"tabular-nums" }}>
                          ${fCLP(s.gross_profit)}
                        </div>
                        {pct !== null && (
                          <div style={{ fontSize:10, color:C.mute, marginTop:1 }}>{pct}%</div>
                        )}
                      </>
                    )}
                  </div>}

                  {/* Status */}
                  <div style={{ display:"flex", justifyContent:"center" }}>
                    <StatusBadge status={s.status}/>
                  </div>
                </div>
              );
            })}
          </div>
          </div>

          {!loading && items.length > 0 && (
            <div style={{ padding:"10px 4px", fontSize:12, color:C.mute }}>
              {items.length} venta{items.length!==1?"s":""} · haz clic en una fila para ver el detalle
            </div>
          )}
        </div>

        {/* DETAIL PANEL */}
        {selectedId !== null && (
          <DetailPanel
            saleId={selectedId}
            warehouses={warehouses}
            mob={mob}
            onClose={() => setSelectedId(null)}
            onVoided={() => { load(); setSelectedId(null); }}
          />
        )}
      </div>
    </div>
  );
}