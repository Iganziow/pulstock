"use client";

import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";

/* ═══════════════════════════════════════════════════════════════════════════
   DESIGN TOKENS
   ═══════════════════════════════════════════════════════════════════════════ */

const MOBILE_BP = 768;
function useIsMobile() {
  const [m, setM] = useState(false);
  useEffect(() => { const c = () => setM(window.innerWidth < MOBILE_BP); c(); window.addEventListener("resize", c); return () => window.removeEventListener("resize", c); }, []);
  return m;
}

function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
      style={{ animation: "spin .7s linear infinite", display: "inline-block", verticalAlign: "middle" }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   FORMATTERS & TYPES
   ═══════════════════════════════════════════════════════════════════════════ */
const fmt = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "0" : Math.round(n).toLocaleString("es-CL"); };
const fmtDec = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "0" : n.toFixed(1); };
const fmtMoney = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL"); };

// Limpiador de decimales infinitos
const cleanReasoning = (text: string) => {
  if (!text) return "";
  return text.replace(/\d+\.\d+/g, (match) => {
    const num = parseFloat(match);
    return Math.round(num).toLocaleString("es-CL");
  });
};

type SugLine = { product_id: number; product_name: string; current_stock: string; avg_daily_demand: string; days_to_stockout: number | null; suggested_qty: string; estimated_cost: string; reasoning: string; };
type Suggestion = { id: number; warehouse_id: number; supplier_name: string; status: string; priority: string; total_estimated: string; generated_at: string; approved_at: string | null; purchase_id: number | null; lines_count: number; lines: SugLine[]; };

/* ═══════════════════════════════════════════════════════════════════════════
   HELPERS UI
   ═══════════════════════════════════════════════════════════════════════════ */
function dtoColor(dto: number | null): string {
  if (dto === null) return C.green;
  if (dto <= 3) return C.red;
  if (dto <= 7) return C.amber;
  return C.accent;
}

function dtoLabel(dto: number | null): string {
  if (dto === null) return "Estable";
  if (dto === 0) return "Sin stock";
  if (dto === 1) return "1 día";
  return `${dto} días`;
}

function priorityIcon(p: string) { return p === "CRITICAL" ? "🔴" : p === "HIGH" ? "🟠" : "🔵"; }
function priorityShort(p: string) { return p === "CRITICAL" ? "Urgente" : p === "HIGH" ? "Importante" : "Preventivo"; }

function priorityDesc(p: string, linesCount: number, critCount: number) {
  if (p === "CRITICAL") return `Atención: ${critCount} producto${critCount > 1 ? "s" : ""} requiere reposición inmediata.`;
  if (p === "HIGH") return `${linesCount} producto${linesCount > 1 ? "s" : ""} próximo a agotarse esta semana.`;
  return `Sugerencia de compra preventiva para ${linesCount} producto${linesCount > 1 ? "s" : ""}.`;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
export default function SuggestionsPage() {
  const mob = useIsMobile();
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<number | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"PENDING" | "APPROVED" | "DISMISSED">("PENDING");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [confirmAction, setConfirmAction] = useState<{ id: number; action: "approve" | "dismiss" } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/forecast/suggestions/");
      const results: Suggestion[] = data?.results || [];
      setSuggestions(results);
      const firstPending = results.find(s => s.status === "PENDING");
      if (firstPending && expandedId === null) setExpandedId(firstPending.id);
    } catch (e: any) { setError(e?.message || "Error cargando sugerencias"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!confirmAction) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") setConfirmAction(null); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [confirmAction]);

  const handleApprove = async (id: number) => {
    setActing(id); setError(null); setConfirmAction(null);
    try {
      const res = await apiFetch(`/forecast/suggestions/${id}/approve/`, { method: "POST" });
      setSuccess(`✅ Orden de compra #${res.purchase_id} creada exitosamente.`);
      await load();
      setTimeout(() => setSuccess(null), 5000);
    } catch (e: any) { setError(e?.data?.detail || e?.message || "Error al aprobar"); }
    finally { setActing(null); }
  };

  const handleDismiss = async (id: number) => {
    setActing(id); setError(null); setConfirmAction(null);
    try {
      await apiFetch(`/forecast/suggestions/${id}/dismiss/`, { method: "POST" });
      setSuccess("Sugerencia descartada.");
      await load();
      setTimeout(() => setSuccess(null), 4000);
    } catch (e: any) { setError(e?.data?.detail || e?.message || "Error al descartar"); }
    finally { setActing(null); }
  };

  const filtered = suggestions.filter(s => s.status === tab);
  const pending = suggestions.filter(s => s.status === "PENDING");
  const approved = suggestions.filter(s => s.status === "APPROVED");
  const dismissed = suggestions.filter(s => s.status === "DISMISSED");

  const totalPendingCost = pending.reduce((s, p) => s + parseFloat(p.total_estimated || "0"), 0);
  const totalPendingProducts = pending.reduce((s, p) => s + p.lines_count, 0);
  const criticalCount = pending.filter(p => p.priority === "CRITICAL").length;

  return (
    <div style={{
      fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh",
      padding: mob ? "20px 16px" : "40px 48px",
      display: "flex", flexDirection: "column", gap: 24,
    }}>

      {/* ── HEADER ── */}
      <div>
        <Link href="/dashboard/forecast" style={{
          fontSize: 13, color: C.mute, textDecoration: "none",
          display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 12,
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
          Volver a predicción
        </Link>
        <h1 style={{ margin: 0, fontSize: mob ? 24 : 32, fontWeight: 700, letterSpacing: "-.02em", color: C.text }}>
          Pedidos sugeridos
        </h1>
        <p style={{ margin: "6px 0 0", fontSize: 15, color: C.mute }}>
          Recomendaciones automatizadas basadas en tu ritmo de ventas.
        </p>
      </div>

      {/* ── MESSAGES ── */}
      {error && (
        <div style={{ padding: "12px 16px", background: C.redBg, borderLeft: `4px solid ${C.red}`, borderRadius: 6, fontSize: 14, color: C.red, display: "flex", justifyContent: "space-between" }}>
          <span>{error}</span>
          <button onClick={() => setError(null)} style={{ background: "none", border: "none", cursor: "pointer", color: C.red, fontSize: 18 }}>×</button>
        </div>
      )}
      {success && (
        <div style={{ padding: "12px 16px", background: C.greenBg, borderLeft: `4px solid ${C.green}`, borderRadius: 6, fontSize: 14, color: C.green, fontWeight: 500 }}>
          {success}
        </div>
      )}

      {/* ── SKELETON LOADING ── */}
      {loading && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 12 }}>
          {/* Esqueletos de las Summary Cards */}
          <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(3, 1fr)", gap: 16, marginBottom: 16 }}>
             {[1, 2, 3].map(i => (
               <div key={`sum-skel-${i}`} style={{ background: C.surface, borderRadius: C.r, padding: "20px", boxShadow: C.sh, gridColumn: mob && i === 3 ? "1 / -1" : "auto" }}>
                 <div className="skeleton" style={{ width: "40%", height: 12, marginBottom: 12 }} />
                 <div className="skeleton" style={{ width: "60%", height: 32, marginBottom: 8 }} />
                 <div className="skeleton" style={{ width: "80%", height: 12 }} />
               </div>
             ))}
          </div>
          
          {/* Esqueletos de las Tarjetas de Productos */}
          {[1, 2, 3].map(i => (
            <div key={`card-skel-${i}`} style={{ background: C.surface, borderRadius: C.r, padding: mob ? "16px" : "20px 24px", border: `1px solid ${C.border}`, boxShadow: C.sh }}>
              <div style={{ display: "flex", gap: 12, marginBottom: 16, alignItems: "center" }}>
                <div className="skeleton" style={{ width: 24, height: 24, borderRadius: "50%" }} />
                <div style={{ flex: 1 }}>
                  <div className="skeleton" style={{ width: mob ? "60%" : "30%", height: 16, marginBottom: 6 }} />
                  <div className="skeleton" style={{ width: mob ? "80%" : "50%", height: 12 }} />
                </div>
              </div>
              <div style={{ display: "flex", gap: 24, paddingTop: 12, borderTop: `1px dashed ${C.border}` }}>
                <div className="skeleton" style={{ width: 60, height: 36 }} />
                <div className="skeleton" style={{ width: 60, height: 36 }} />
                <div className="skeleton" style={{ width: 80, height: 36 }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── CONTENIDO PRINCIPAL ── */}
      {!loading && (
        <>
          {/* SUMMARY CARDS */}
          {pending.length > 0 && tab === "PENDING" && (
            <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(3, 1fr)", gap: 16 }}>
              <div style={{ background: C.surface, borderRadius: C.r, padding: "20px", boxShadow: C.sh }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em" }}>Pendientes</div>
                <div style={{ fontSize: 32, fontWeight: 700, color: C.text, marginTop: 8 }}>{pending.length}</div>
                <div style={{ fontSize: 13, color: criticalCount > 0 ? C.red : C.mute, marginTop: 4, fontWeight: criticalCount > 0 ? 600 : 400 }}>
                  {criticalCount > 0 ? `⚠️ ${criticalCount} requieren atención hoy` : "Sin urgencias inmediatas"}
                </div>
              </div>
              <div style={{ background: C.surface, borderRadius: C.r, padding: "20px", boxShadow: C.sh }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em" }}>Productos</div>
                <div style={{ fontSize: 32, fontWeight: 700, color: C.text, marginTop: 8 }}>{totalPendingProducts}</div>
                <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>Para reponer en total</div>
              </div>
              <div style={{ background: C.surface, borderRadius: C.r, padding: "20px", boxShadow: C.sh, gridColumn: mob ? "1 / -1" : "auto" }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em" }}>Inversión Estimada</div>
                <div style={{ fontSize: 32, fontWeight: 700, color: C.text, marginTop: 8 }}>{fmtMoney(totalPendingCost)}</div>
                <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>Al aprobar todos los pedidos</div>
              </div>
            </div>
          )}

          {/* TABS */}
          <div style={{ display: "flex", gap: 24, borderBottom: `1px solid ${C.border}` }}>
            {([
              { key: "PENDING" as const, label: "Pendientes", count: pending.length },
              { key: "APPROVED" as const, label: "Aprobados", count: approved.length },
              { key: "DISMISSED" as const, label: "Descartados", count: dismissed.length },
            ]).map(t => (
              <button key={t.key} onClick={() => setTab(t.key)} style={{
                padding: "0 0 12px 0", fontSize: 14,
                fontWeight: tab === t.key ? 600 : 400,
                color: tab === t.key ? C.accent : C.mute,
                background: "none", border: "none", cursor: "pointer",
                borderBottom: tab === t.key ? `2px solid ${C.accent}` : "2px solid transparent",
                marginBottom: -1, fontFamily: C.font,
                display: "flex", alignItems: "center", gap: 8, transition: "all .2s"
              }}>
                {t.label}
                {t.count > 0 && (
                  <span style={{
                    fontSize: 11, fontWeight: 600, padding: "2px 8px",
                    borderRadius: 12, background: tab === t.key ? C.accentBg : "#F4F4F5",
                    color: tab === t.key ? C.accent : C.mute,
                  }}>{t.count}</span>
                )}
              </button>
            ))}
          </div>

          {/* ── EMPTY STATES CON CALL TO ACTION ── */}
          {filtered.length === 0 && (
            <div style={{ background: C.surface, borderRadius: C.r, padding: "64px 20px", textAlign: "center", boxShadow: C.sh }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>
                {tab === "PENDING" ? "☕" : tab === "APPROVED" ? "📦" : "🗂"}
              </div>
              <div style={{ fontWeight: 600, fontSize: 18, color: C.text }}>
                {tab === "PENDING" && "Todo al día, no hay pedidos pendientes"}
                {tab === "APPROVED" && "Aún no has aprobado sugerencias"}
                {tab === "DISMISSED" && "No hay sugerencias descartadas"}
              </div>
              <div style={{ fontSize: 14, color: C.mute, marginTop: 8, maxWidth: 400, margin: "8px auto 0", lineHeight: 1.6 }}>
                {tab === "PENDING" && "El sistema está monitoreando tu inventario. Te avisaremos cuando sea momento de reponer."}
                {tab === "APPROVED" && "Cuando apruebes una sugerencia, se convertirá en una orden de compra."}
              </div>
              
              {tab === "PENDING" && (
                <div style={{ marginTop: 24 }}>
                  <Link href="/dashboard/inventory" style={{ 
                    padding: "10px 20px", background: C.surface, border: `1px solid ${C.border}`, 
                    borderRadius: 8, color: C.text, textDecoration: "none", fontWeight: 600, 
                    fontSize: 14, display: "inline-flex", alignItems: "center", gap: 8,
                    boxShadow: C.sh, transition: "all .2s"
                  }} className="btn-secondary">
                    📦 Revisar mi inventario
                  </Link>
                </div>
              )}
              {tab === "APPROVED" && (
                <div style={{ marginTop: 24 }}>
                  <Link href="/dashboard/purchases" style={{ 
                    padding: "10px 20px", background: C.accent, borderRadius: 8, color: "#fff", 
                    textDecoration: "none", fontWeight: 600, fontSize: 14, display: "inline-flex", 
                    alignItems: "center", gap: 8, boxShadow: "0 2px 8px rgba(79,70,229,.25)",
                    transition: "all .2s"
                  }} className="btn-primary">
                    Ir a Órdenes de Compra →
                  </Link>
                </div>
              )}
            </div>
          )}

          {/* SUGGESTION CARDS */}
          {filtered.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {filtered.map(s => {
                const expanded = expandedId === s.id;
                const isPending = s.status === "PENDING";
                const isApproved = s.status === "APPROVED";
                const isActing = acting === s.id;
                const critLines = s.lines.filter(l => l.days_to_stockout !== null && l.days_to_stockout <= 3);
                const totalQty = s.lines.reduce((sum, l) => sum + parseFloat(l.suggested_qty || "0"), 0);

                return (
                  <div key={s.id} style={{
                    background: C.surface,
                    borderRadius: C.r,
                    boxShadow: C.sh,
                    border: `1px solid ${C.border}`,
                    overflow: "hidden",
                  }}>
                    {/* CARD HEADER */}
                    <div
                      onClick={() => setExpandedId(expanded ? null : s.id)}
                      className="sug-header"
                      style={{ padding: mob ? "16px" : "20px 24px", cursor: "pointer", display: "flex", flexDirection: "column", gap: 12 }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                            <span style={{ fontSize: 14 }}>{priorityIcon(s.priority)}</span>
                            <span style={{ fontSize: 14, fontWeight: 600, color: C.text }}>{priorityShort(s.priority)}</span>
                            {isApproved && <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 12, background: C.greenBg, color: C.green }}>Aprobado</span>}
                            {s.status === "DISMISSED" && <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 12, background: "#F4F4F5", color: C.mute }}>Descartado</span>}
                          </div>
                          <div style={{ fontSize: 14, color: C.mute }}>
                            {priorityDesc(s.priority, s.lines_count, critLines.length)}
                          </div>
                        </div>
                        <div style={{
                          width: 28, height: 28, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                          background: expanded ? C.bg : "transparent", transition: "transform .2s", transform: expanded ? "rotate(180deg)" : "rotate(0)", color: C.mute,
                        }}>▾</div>
                      </div>

                      <div style={{ display: "flex", flexWrap: "wrap", gap: 24, paddingTop: 8, borderTop: `1px dashed ${C.border}` }}>
                        <div>
                          <div style={{ fontSize: 11, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em" }}>Productos</div>
                          <div style={{ fontSize: 16, fontWeight: 600, marginTop: 2 }}>{s.lines_count}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: 11, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em" }}>Unidades</div>
                          <div style={{ fontSize: 16, fontWeight: 600, marginTop: 2 }}>{fmt(totalQty)}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: 11, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em" }}>Costo Total</div>
                          <div style={{ fontSize: 16, fontWeight: 600, marginTop: 2, color: C.text }}>{fmtMoney(s.total_estimated)}</div>
                        </div>
                      </div>
                    </div>

                    {/* EXPANDED AREA */}
                    {expanded && (
                      <div style={{ borderTop: `1px solid ${C.border}` }}>
                        {s.lines.map((l, i) => {
                          const dto = l.days_to_stockout;
                          const isUrgent = dto !== null && dto <= 3;
                          const isLast = i === s.lines.length - 1;

                          return (
                            <div key={l.product_id} style={{
                              padding: mob ? "16px" : "20px 24px",
                              borderBottom: isLast ? "none" : `1px solid ${C.border}`,
                              display: "flex",
                              flexDirection: mob ? "column" : "row",
                              justifyContent: "space-between",
                              alignItems: mob ? "flex-start" : "center",
                              gap: mob ? 16 : 24,
                              background: isUrgent ? C.redBg : C.bg, 
                              transition: "background 0.2s"
                            }}>
                              
                              <div style={{ flex: 1, width: "100%" }}>
                                <div style={{ fontWeight: 600, fontSize: 15, color: C.text }}>
                                  {l.product_name}
                                </div>
                                
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 6, fontSize: 13, color: C.mute }}>
                                  <span>📦 En bodega: <b style={{ color: C.text }}>{fmt(l.current_stock)}</b></span>
                                  <span style={{ display: "flex", alignItems: "center", gap: 4, color: dtoColor(dto), fontWeight: 600 }}>
                                    ⏳ {dtoLabel(dto)}
                                  </span>
                                </div>

                                <div style={{ 
                                  marginTop: 10, fontSize: 13, color: C.mid, background: isUrgent ? "#FFFFFF" : C.surface, 
                                  padding: "10px 14px", borderRadius: 8, borderLeft: `3px solid ${C.accent}`,
                                  boxShadow: C.sh, lineHeight: 1.5
                                }}>
                                  💡 <b>¿Por qué pedir {fmt(l.suggested_qty)} unidades?</b> {cleanReasoning(l.reasoning)}
                                </div>
                              </div>

                              <div style={{ 
                                textAlign: mob ? "left" : "right", 
                                minWidth: mob ? "100%" : 140,
                                background: mob ? C.surface : "transparent",
                                padding: mob ? "12px 16px" : 0,
                                borderRadius: mob ? 8 : 0,
                                border: mob ? `1px solid ${C.border}` : "none",
                                display: mob ? "flex" : "block",
                                justifyContent: mob ? "space-between" : "initial",
                                alignItems: mob ? "center" : "initial",
                              }}>
                                <div>
                                  <div style={{ fontSize: 12, color: C.mute, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: mob ? 2 : 4 }}>
                                    Sugerencia
                                  </div>
                                  <div style={{ fontWeight: 700, fontSize: mob ? 20 : 24, color: C.text }}>
                                    {fmt(l.suggested_qty)} <span style={{ fontSize: 14, fontWeight: 500, color: C.mute }}>u.</span>
                                  </div>
                                </div>
                                <div style={{ textAlign: mob ? "right" : "right" }}>
                                  {mob && <div style={{ fontSize: 11, color: C.mute, marginBottom: 2 }}>Subtotal</div>}
                                  <div style={{ fontSize: 15, fontWeight: 600, color: C.amber, marginTop: mob ? 0 : 4 }}>
                                    {fmtMoney(l.estimated_cost)}
                                  </div>
                                </div>
                              </div>

                            </div>
                          );
                        })}

                        {/* ACTIONS PENDIENTES */}
                        {isPending && (
                          <div style={{ padding: mob ? "16px" : "20px 24px", background: C.surface, display: "flex", justifyContent: "flex-end", gap: 12, borderTop: `1px solid ${C.border}` }}>
                            <button
                              onClick={e => { e.stopPropagation(); setConfirmAction({ id: s.id, action: "dismiss" }); }}
                              disabled={isActing}
                              className="btn-dismiss"
                              style={{ padding: "10px 20px", fontSize: 14, fontWeight: 500, cursor: "pointer", background: "transparent", border: `1px solid ${C.border}`, borderRadius: 8, color: C.mid, transition: "all .2s" }}
                            >
                              Descartar
                            </button>
                            <button
                              onClick={e => { e.stopPropagation(); setConfirmAction({ id: s.id, action: "approve" }); }}
                              disabled={isActing}
                              className="btn-approve"
                              style={{ padding: "10px 24px", fontSize: 14, fontWeight: 600, cursor: "pointer", background: C.accent, border: "none", borderRadius: 8, color: "#fff", display: "inline-flex", alignItems: "center", gap: 8, transition: "all .2s" }}
                            >
                              {isActing ? <><Spinner size={16} /> Procesando...</> : "Aprobar pedido"}
                            </button>
                          </div>
                        )}

                        {/* INFO Y ENLACE A ORDEN APROBADA */}
                        {isApproved && s.purchase_id && (
                          <div style={{ 
                            padding: mob ? "16px" : "20px 24px", background: C.greenBg, 
                            display: "flex", flexDirection: mob ? "column" : "row", 
                            justifyContent: "space-between", alignItems: mob ? "flex-start" : "center", 
                            gap: 16, borderTop: `1px solid ${C.greenBd}` 
                          }}>
                            <div style={{ fontSize: 14, color: C.green, fontWeight: 500 }}>
                              ✅ <b>Borrador creado.</b> Esta sugerencia ya fue convertida en una orden de compra.
                            </div>
                            <Link
                              href={`/dashboard/purchases`}
                              style={{ 
                                padding: "10px 20px", fontSize: 14, fontWeight: 600, 
                                background: C.green, color: "#fff", border: "none", borderRadius: 8, 
                                textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 8,
                                transition: "filter .2s"
                              }}
                              className="btn-approve"
                            >
                              Ver y editar orden #{s.purchase_id} →
                            </Link>
                          </div>
                        )}

                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* ── CONFIRM MODAL ── */}
      {confirmAction && (() => {
        const s = suggestions.find(x => x.id === confirmAction.id);
        if (!s) return null;
        const isApprove = confirmAction.action === "approve";

        return (
          <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.3)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center", padding: 16, animation: "fadeIn .2s ease-out" }} onClick={() => setConfirmAction(null)}>
            <div onClick={e => e.stopPropagation()} style={{ background: C.surface, borderRadius: 16, padding: mob ? "24px" : "32px", maxWidth: 400, width: "100%", boxShadow: "0 20px 25px -5px rgba(0,0,0,.1)", animation: "slideUp .2s ease-out" }}>
              <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 12, color: C.text }}>
                {isApprove ? "Aprobar pedido" : "Descartar sugerencia"}
              </div>
              <div style={{ fontSize: 14, color: C.mute, lineHeight: 1.5, marginBottom: 24 }}>
                {isApprove ? `Crearemos un borrador de compra por ${fmtMoney(s.total_estimated)}. Podrás revisarlo antes de enviarlo.` : "Ocultaremos esta sugerencia. El sistema generará una nueva si el stock vuelve a ser crítico."}
              </div>
              <div style={{ display: "flex", gap: 12, justifyContent: "flex-end", flexWrap: "wrap" }}>
                <button onClick={() => setConfirmAction(null)} style={{ padding: "10px 16px", fontSize: 14, fontWeight: 500, background: "transparent", border: "none", color: C.mute, cursor: "pointer", flex: mob ? "1 1 auto" : "initial" }}>Cancelar</button>
                <button onClick={() => isApprove ? handleApprove(s.id) : handleDismiss(s.id)} disabled={acting === s.id} style={{ padding: "10px 20px", fontSize: 14, fontWeight: 600, background: isApprove ? C.accent : C.red, color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, flex: mob ? "1 1 auto" : "initial" }}>
                  {acting === s.id ? <><Spinner size={16} /> Cargando...</> : isApprove ? "Confirmar" : "Sí, descartar"}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }
        @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(10px) } to { opacity: 1; transform: translateY(0) } }
        
        /* Animación para el Loading Skeleton */
        @keyframes skeleton-pulse {
          0% { background-color: #E4E4E7; }
          50% { background-color: #F4F4F5; }
          100% { background-color: #E4E4E7; }
        }
        .skeleton { animation: skeleton-pulse 1.5s ease-in-out infinite; border-radius: 6px; }
        
        .sug-header:hover { background: #F8FAFC !important; }
        .btn-dismiss:hover { background: #F4F4F5 !important; }
        .btn-approve:hover, .btn-primary:hover { filter: brightness(1.1); }
        .btn-secondary:hover { background: #F8FAFC !important; }
      `}</style>
    </div>
  );
}