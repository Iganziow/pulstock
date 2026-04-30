"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";
import { EditPaymentsModal, EditTipModal } from "@/components/sales/SaleEditModals";

// ─── Types ────────────────────────────────────────────────────────────────────

type Product = { id: number; name: string; sku?: string | null };
type SaleLine = {
  id: number; product: Product; qty: string; unit_price: string; line_total: string;
  unit_cost_snapshot?: string | null;
  line_cost?: string | null;
  line_profit?: string | null;
};
type SalePayment = { method: "cash" | "card" | "debit" | "transfer"; amount: string };
type Sale = {
  id: number; sale_number?: number | null; created_at: string; store_id: number; warehouse_id: number;
  subtotal: string; total: string; total_cost: string; gross_profit: string;
  tip?: string; tip_method?: string;
  status: string; payments: SalePayment[]; lines: SaleLine[];
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toNum(v: string | number | null | undefined): number {
  if (v == null) return 0;
  const n = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(n) ? n : 0;
}
function fCLP(v: string | number | null | undefined): string {
  return Math.round(toNum(v)).toLocaleString("es-CL");
}
function fDateTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-CL", { day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit" });
}

// ─── Components ──────────────────────────────────────────────────────────────

type BtnV = "primary"|"secondary"|"ghost"|"danger";
function Btn({ children, onClick, variant="secondary", disabled, size="md" }: {
  children: React.ReactNode; onClick?: ()=>void;
  variant?: BtnV; disabled?: boolean; size?: "sm"|"md"|"lg";
}) {
  const vs: Record<BtnV, React.CSSProperties> = {
    primary:   { background:C.accent,  color:"#fff", border:`1px solid ${C.accent}` },
    secondary: { background:C.surface, color:C.text, border:`1px solid ${C.borderMd}` },
    ghost:     { background:"transparent", color:C.mid, border:"1px solid transparent" },
    danger:    { background:C.redBg,   color:C.red,  border:`1px solid ${C.redBd}` },
  };
  const h = size==="lg"?46:size==="sm"?30:38;
  const px = size==="lg"?"0 20px":size==="sm"?"0 10px":"0 14px";
  const fs = size==="lg"?14:size==="sm"?11:13;
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="xb" style={{
      ...vs[variant], display:"inline-flex", alignItems:"center", justifyContent:"center", gap:6,
      height:h, padding:px, borderRadius:C.r, fontSize:fs, fontWeight:600, letterSpacing:"0.01em", whiteSpace:"nowrap",
    }}>{children}</button>
  );
}

function StatusBadge({ status }: { status: string }) {
  const s = (status || "").toUpperCase();
  const isVoid = s === "VOID";
  return (
    <span style={{
      display:"inline-flex", alignItems:"center", gap:5,
      padding:"4px 10px", borderRadius:99, fontSize:12, fontWeight:700,
      border:`1px solid ${isVoid ? C.redBd : C.greenBd}`,
      background:isVoid ? C.redBg : C.greenBg,
      color:isVoid ? C.red : C.green, letterSpacing:"0.03em",
    }}>
      <span style={{ width:7, height:7, borderRadius:"50%", background:"currentColor", display:"inline-block" }}/>
      {isVoid ? "Anulada" : "Completada"}
    </span>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function SaleDetailPage() {
  useGlobalStyles();
  const mob = useIsMobile();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id     = Number(params?.id);

  const [sale, setSale]         = useState<Sale|null>(null);
  const [loading, setLoading]   = useState(true);
  const [err, setErr]           = useState<string|null>(null);
  const [showVoid, setShowVoid] = useState(false);
  const [reason, setReason]     = useState("");
  const [voidBusy, setVoidBusy] = useState(false);
  const [voidErr, setVoidErr]   = useState<string|null>(null);

  // Modales de edición. Solo pagos y propina (la cantidad NO se edita
  // por anti-fraude — Daniel 29/04/26).
  const [showEditPayments, setShowEditPayments] = useState(false);
  const [showEditTip, setShowEditTip]           = useState(false);

  async function load() {
    if (!id) { setErr("ID inválido"); setLoading(false); return; }
    setLoading(true); setErr(null);
    try {
      const data = (await apiFetch(`/sales/sales/${id}/`)) as Sale;
      setSale(data);
    } catch (e:any) {
      const msg = e?.message ?? "";
      const friendly = msg.includes("matches the given query") ? "No se encontró la venta solicitada." : (msg || "No se pudo cargar el detalle");
      setErr(friendly); setSale(null);
    }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, [id]); // eslint-disable-line

  const isVoid     = useMemo(() => (sale?.status ?? "").toUpperCase() === "VOID", [sale?.status]);
  const pct        = useMemo(() => {
    if (!sale) return null;
    const t = toNum(sale.total); const p = toNum(sale.gross_profit);
    return t > 0 ? Math.round((p / t) * 100) : 0;
  }, [sale]);

  async function doVoid() {
    if (!reason.trim()) { setVoidErr("Debes ingresar un motivo."); return; }
    setVoidBusy(true); setVoidErr(null);
    try {
      await apiFetch(`/sales/sales/${id}/void/`, { method:"POST", body:JSON.stringify({ reason: reason.trim() }) });
      setShowVoid(false); setReason("");
      await load();
    } catch (e:any) {
      setVoidErr(e instanceof ApiError ? e.message : (e?.message ?? "No se pudo anular"));
    } finally { setVoidBusy(false); }
  }

  // ── Loading / error states ─────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={{ fontFamily:C.font, color:C.text, background:C.bg, minHeight:"100vh", display:"grid", placeItems:"center" }}>
        <div style={{ display:"flex", alignItems:"center", gap:10, color:C.mute }}>
          <Spinner size={18}/><span style={{ fontSize:14 }}>Cargando venta…</span>
        </div>
      </div>
    );
  }

  if (err || !sale) {
    return (
      <div style={{ fontFamily:C.font, color:C.text, background:C.bg, minHeight:"100vh", display:"grid", placeItems:"center" }}>
        <div style={{ textAlign:"center", padding:32 }}>
          <div style={{ fontSize:36, marginBottom:12 }}>⚠️</div>
          <div style={{ fontSize:15, fontWeight:700, marginBottom:6 }}>No se pudo cargar la venta</div>
          <div style={{ fontSize:13, color:C.mute, marginBottom:20 }}>{err}</div>
          <Btn variant="secondary" onClick={() => router.back()}>← Volver</Btn>
        </div>
      </div>
    );
  }

  // ── Main render ────────────────────────────────────────────────────────────
  return (
    <div style={{ fontFamily:C.font, color:C.text, background:C.bg, minHeight:"100vh", padding:mob?"16px 12px":"24px 28px", display:"flex", flexDirection:"column", gap:16 }}>

      {/* HEADER */}
      <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between", gap:12, flexWrap:"wrap" }}>
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:6 }}>
            <div style={{ width:4, height:26, background:C.accent, borderRadius:2 }}/>
            <h1 style={{ margin:0, fontSize:mob?20:22, fontWeight:800, letterSpacing:"-0.04em" }}>
              Venta <span style={{ fontFamily:C.mono }}>#{sale.sale_number ?? sale.id}</span>
            </h1>
            <StatusBadge status={sale.status}/>
          </div>
          <p style={{ margin:0, fontSize:13, color:C.mute, paddingLeft:14 }}>
            {fDateTime(sale.created_at)}
          </p>
        </div>

        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          <Btn variant="ghost" onClick={() => router.back()}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            Volver
          </Btn>
          <Link href={`/dashboard/pos/receipt/${id}`} target="_blank" style={{
            display:"inline-flex", alignItems:"center", gap:6,
            height:38, padding:"0 14px", borderRadius:C.r, fontSize:13, fontWeight:600,
            border:`1px solid ${C.borderMd}`, background:C.surface, color:C.mid,
            textDecoration:"none", whiteSpace:"nowrap",
          }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/>
              <rect x="6" y="14" width="12" height="8"/>
            </svg>
            Imprimir
          </Link>
          {!isVoid && (
            <Btn variant="danger" onClick={() => { setVoidErr(null); setShowVoid(true); }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
              </svg>
              Anular venta
            </Btn>
          )}
        </div>
      </div>

      {/* VOID BANNER */}
      {isVoid && (
        <div style={{ padding:"12px 16px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, color:C.red, fontWeight:600, fontSize:13, display:"flex", gap:8 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink:0, marginTop:1 }}>
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          Venta anulada — el total no contabiliza en ingresos y el stock fue revertido.
        </div>
      )}

      {/* MAIN GRID */}
      <div style={{ display:"grid", gridTemplateColumns:mob?"1fr":"1fr 300px", gap:16, alignItems:"start" }}>

        {/* LEFT: lines */}
        <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
          <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh, overflowX:"auto" as const }}>
            <div style={{
              display:"grid", gridTemplateColumns:"1fr 60px 110px 80px 100px",
              columnGap:12, padding:mob?"10px 12px":"10px 18px", minWidth:mob?550:undefined,
              background:C.bg, borderBottom:`1px solid ${C.border}`,
              fontSize:10.5, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.08em",
            }}>
              <div>Producto</div>
              <div style={{ textAlign:"center" }}>Cantidad</div>
              <div style={{ textAlign:"right" }}>Precio unit.</div>
              <div style={{ textAlign:"right" }}>Costo</div>
              <div style={{ textAlign:"right" }}>Subtotal</div>
            </div>

            {sale.lines?.map((l, i) => {
              const profit = toNum(l.line_profit);
              return (
                <div key={l.id} style={{
                  display:"grid", gridTemplateColumns:"1fr 60px 110px 80px 100px",
                  columnGap:12, padding:mob?"13px 12px":"13px 18px", minWidth:mob?550:undefined,
                  borderBottom:i<sale.lines.length-1?`1px solid ${C.border}`:"none",
                  alignItems:"center",
                }}>
                  <div>
                    <div style={{ fontWeight:600, fontSize:14 }}>{l.product?.name ?? "Producto"}</div>
                    {l.product?.sku && <div style={{ fontSize:11, color:C.mute, fontFamily:C.mono, marginTop:2 }}>{l.product.sku}</div>}
                    {l.line_profit != null && (
                      <div style={{ fontSize:11, marginTop:4, color:profit>=0?C.green:C.red, fontWeight:600 }}>
                        Utilidad: ${fCLP(l.line_profit)} {pct !== null && `(${Math.round((profit/toNum(l.line_total))*100)}%)`}
                      </div>
                    )}
                  </div>
                  <div style={{ textAlign:"center", fontWeight:600, fontSize:14, color:C.mid }}>
                    {l.qty}
                  </div>
                  <div style={{ textAlign:"right", fontSize:13, fontVariantNumeric:"tabular-nums" }}>${fCLP(l.unit_price)}</div>
                  <div style={{ textAlign:"right", fontSize:12, color:C.mute, fontVariantNumeric:"tabular-nums" }}>
                    {l.line_cost != null ? `$${fCLP(l.line_cost)}` : "—"}
                  </div>
                  <div style={{ textAlign:"right", fontWeight:800, fontSize:14, fontVariantNumeric:"tabular-nums" }}>
                    ${fCLP(l.line_total)}
                  </div>
                </div>
              );
            })}

            {/* Footer */}
            <div style={{ padding:"12px 18px", background:C.bg, borderTop:`1px solid ${C.border}`, display:"flex", justifyContent:"flex-end", alignItems:"baseline", gap:6 }}>
              <span style={{ fontSize:13, color:C.mute }}>Total:</span>
              <span style={{ fontSize:18, fontWeight:800, color:C.accent, fontVariantNumeric:"tabular-nums" }}>${fCLP(sale.total)}</span>
            </div>
          </div>
        </div>

        {/* RIGHT: metadata + financials */}
        <div style={{ display:"flex", flexDirection:"column", gap:12 }}>

          {/* Metadata */}
          <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>
            <div style={{ padding:"12px 16px", background:C.bg, borderBottom:`1px solid ${C.border}` }}>
              <div style={{ fontSize:11, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.07em" }}>Información</div>
            </div>
            <div style={{ padding:"14px 16px", display:"flex", flexDirection:"column", gap:10 }}>
              {[
                { label:"Fecha",    value:fDateTime(sale.created_at) },
                { label:"Bodega",   value:`#${sale.warehouse_id}` },
                { label:"Store",    value:`#${sale.store_id}` },
                { label:"Estado",   value:<StatusBadge status={sale.status}/> },
              ].map(f => (
                <div key={f.label} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", gap:8 }}>
                  <span style={{ fontSize:12, color:C.mute }}>{f.label}</span>
                  <span style={{ fontSize:13, fontWeight:600 }}>{f.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Payments */}
          {sale.payments?.length > 0 && (
            <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>
              <div style={{ padding:"12px 16px", background:C.bg, borderBottom:`1px solid ${C.border}`, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                <div style={{ fontSize:11, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.07em" }}>Método de pago</div>
                {!isVoid && (
                  <button
                    type="button"
                    onClick={() => setShowEditPayments(true)}
                    title="Editar pagos"
                    style={{
                      background:"transparent", border:`1px solid ${C.border}`,
                      borderRadius:4, padding:"2px 8px", cursor:"pointer",
                      fontSize:11, color:C.mid, fontWeight:600,
                    }}
                  >Editar</button>
                )}
              </div>
              <div style={{ padding:"14px 16px", display:"flex", flexDirection:"column", gap:10 }}>
                {sale.payments.map((p, i) => {
                  const labels: Record<string, string> = { cash:"💵 Efectivo", debit:"💳 Tarj. Débito", card:"💳 Tarj. Crédito", transfer:"🏦 Transferencia" };
                  return (
                    <div key={i} style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline", gap:8 }}>
                      <span style={{ fontSize:13, color:C.mid }}>{labels[p.method] ?? p.method}</span>
                      <span style={{ fontSize:14, fontWeight:700, fontVariantNumeric:"tabular-nums" }}>${fCLP(p.amount)}</span>
                    </div>
                  );
                })}
                {sale.payments.length > 1 && (
                  <div style={{ borderTop:`1px solid ${C.border}`, paddingTop:8, display:"flex", justifyContent:"space-between", alignItems:"baseline", gap:8 }}>
                    <span style={{ fontSize:12, color:C.mute }}>Total pagado</span>
                    <span style={{ fontSize:14, fontWeight:800, color:C.accent, fontVariantNumeric:"tabular-nums" }}>
                      ${fCLP(sale.payments.reduce((s, p) => s + toNum(p.amount), 0))}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Tip — sección separada porque la propina es del equipo, no del local */}
          <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>
            <div style={{ padding:"12px 16px", background:C.bg, borderBottom:`1px solid ${C.border}`, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
              <div style={{ fontSize:11, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.07em" }}>💵 Propina</div>
              {!isVoid && (
                <button
                  type="button"
                  onClick={() => setShowEditTip(true)}
                  title="Editar propina"
                  style={{
                    background:"transparent", border:`1px solid ${C.border}`,
                    borderRadius:4, padding:"2px 8px", cursor:"pointer",
                    fontSize:11, color:C.mid, fontWeight:600,
                  }}
                >Editar</button>
              )}
            </div>
            <div style={{ padding:"14px 16px" }}>
              <div style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline", gap:8 }}>
                <span style={{ fontSize:12, color:C.mute }}>Monto</span>
                <span style={{ fontSize:14, fontWeight:800, color:toNum(sale.tip ?? 0) > 0 ? C.amber : C.mute, fontVariantNumeric:"tabular-nums" }}>
                  ${fCLP(sale.tip ?? "0")}
                </span>
              </div>
              <div style={{ fontSize:10.5, color:C.mute, marginTop:6, lineHeight:1.4 }}>
                Las propinas no se mezclan con el ingreso del local.
              </div>
            </div>
          </div>

          {/* Financials */}
          <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>
            <div style={{ padding:"12px 16px", background:C.bg, borderBottom:`1px solid ${C.border}` }}>
              <div style={{ fontSize:11, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.07em" }}>Financiero</div>
            </div>
            <div style={{ padding:"14px 16px", display:"flex", flexDirection:"column", gap:10 }}>
              {[
                { label:"Subtotal",       value:`$${fCLP(sale.subtotal)}`,     color:C.text },
                { label:"Total",          value:`$${fCLP(sale.total)}`,        color:C.accent },
                { label:"Costo total",    value:`$${fCLP(sale.total_cost)}`,   color:C.mid },
                { label:"Utilidad bruta", value:pct !== null ? `$${fCLP(sale.gross_profit)} (${pct}%)` : `$${fCLP(sale.gross_profit)}`,
                  color:toNum(sale.gross_profit)>=0?C.green:C.red },
              ].map(f => (
                <div key={f.label} style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline", gap:8 }}>
                  <span style={{ fontSize:12, color:C.mute }}>{f.label}</span>
                  <span style={{ fontSize:14, fontWeight:800, color:f.color, fontVariantNumeric:"tabular-nums" }}>{f.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* VOID MODAL */}
      {showVoid && (
        <div className="bd-in" style={{
          position:"fixed", inset:0, background:"rgba(0,0,0,0.4)",
          display:"grid", placeItems:"center", padding:20, zIndex:60,
        }}>
          <div className="m-in" style={{
            width:"min(520px,100%)", background:C.surface,
            borderRadius:C.rLg, border:`1px solid ${C.border}`, boxShadow:C.shLg, overflow:"hidden",
          }}>
            <div style={{ height:3, background:C.red }}/>
            <div style={{ padding:"20px 24px" }}>
              <div style={{ fontSize:15, fontWeight:700, marginBottom:4 }}>Anular venta #{id}</div>
              <div style={{ fontSize:13, color:C.mute, marginBottom:16 }}>
                Esta acción revertirá el stock de todos los productos. Ingresa un motivo obligatorio.
              </div>

              <label style={{ fontSize:11, fontWeight:700, color:C.mid, textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:6 }}>
                Motivo <span style={{ color:C.red }}>*</span>
              </label>
              <textarea
                value={reason}
                onChange={e => setReason(e.target.value)}
                placeholder="Ej: Error en el cobro, devolución del cliente…"
                rows={3} disabled={voidBusy} autoFocus
                style={{
                  width:"100%", padding:"10px 12px", resize:"vertical",
                  border:`1px solid ${C.border}`, borderRadius:C.r,
                  fontSize:13, fontFamily:C.font, lineHeight:1.55,
                }}
              />

              {voidErr && (
                <div style={{ marginTop:10, padding:"9px 12px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, color:C.red, fontSize:13 }}>
                  {voidErr}
                </div>
              )}

              <div style={{ display:"flex", justifyContent:"flex-end", gap:8, marginTop:16 }}>
                <Btn variant="ghost" onClick={() => { setShowVoid(false); setVoidErr(null); }} disabled={voidBusy}>Cancelar</Btn>
                <Btn variant="danger" onClick={doVoid} disabled={voidBusy || !reason.trim()}>
                  {voidBusy ? <><Spinner/>Anulando…</> : "Confirmar anulación"}
                </Btn>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* EDIT MODALS */}
      <EditPaymentsModal
        open={showEditPayments}
        saleId={sale.id}
        currentPayments={sale.payments?.map(p => ({ method: p.method as any, amount: p.amount })) ?? []}
        total={toNum(sale.total)}
        tip={toNum(sale.tip ?? "0")}
        onClose={() => setShowEditPayments(false)}
        onSaved={load}
      />
      <EditTipModal
        open={showEditTip}
        saleId={sale.id}
        currentTips={
          // SaleTip relacional → fuente de verdad. Fallback legacy si la
          // venta tiene sale.tip > 0 pero no fue migrada (1 fila inicial).
          Array.isArray((sale as any).tips) && (sale as any).tips.length > 0
            ? (sale as any).tips.map((t: any) => ({ method: t.method, amount: t.amount }))
            : (toNum(sale.tip ?? "0") > 0
                ? [{ method: ((sale.tip_method as any) || "cash") as any, amount: String(sale.tip ?? "0") }]
                : [])
        }
        total={toNum(sale.total)}
        totalPaid={(sale.payments ?? []).reduce((s, p) => s + toNum(p.amount), 0)}
        onClose={() => setShowEditTip(false)}
        onSaved={load}
      />
    </div>
  );
}