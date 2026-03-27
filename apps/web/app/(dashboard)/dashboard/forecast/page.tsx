"use client";

import Link from "next/link";
import { useEffect, useState, useCallback, useRef } from "react";
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

/* ═══════════════════════════════════════════════════════════════════════════
   SHARED UI
   ═══════════════════════════════════════════════════════════════════════════ */
function Spinner({ size = 16 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ animation: "spin .7s linear infinite" }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" /></svg>;
}

function Pill({ color, children }: { color: "red" | "amber" | "green" | "gray" | "accent"; children: React.ReactNode }) {
  const m: Record<string, { bg: string; bd: string; fg: string }> = {
    red: { bg: C.redBg, bd: C.redBd, fg: C.red },
    amber: { bg: C.amberBg, bd: C.amberBd, fg: C.amber },
    green: { bg: C.greenBg, bd: C.greenBd, fg: C.green },
    accent: { bg: C.accentBg, bd: C.accentBd, fg: C.accent },
    gray: { bg: "#F4F4F5", bd: "#D4D4D8", fg: C.mid },
  };
  const c = m[color] || m.gray;
  return <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 99, background: c.bg, border: `1px solid ${c.bd}`, color: c.fg, whiteSpace: "nowrap" }}>{children}</span>;
}

function StatusBadge({ days }: { days: number | null }) {
  if (days === null) return <Pill color="green">Bien</Pill>;
  if (days === 0) return <Pill color="red">Sin stock</Pill>;
  if (days <= 3) return <Pill color="red">{days} día{days > 1 ? "s" : ""}</Pill>;
  if (days <= 7) return <Pill color="amber">{days} días</Pill>;
  if (days <= 14) return <Pill color="accent">{days} días</Pill>;
  return <Pill color="green">Bien</Pill>;
}

function UrgencyBar({ days, style: s }: { days: number | null; style?: React.CSSProperties }) {
  let pct = 100;
  let color: string = C.green; // <- importante (widen)
  if (days !== null) {
    if (days === 0) { pct = 100; color = C.red; }
    else if (days <= 3) { pct = 90; color = C.red; }
    else if (days <= 7) { pct = 60; color = C.amber; }
    else if (days <= 14) { pct = 35; color = C.accent; }
    else { pct = 10; color = C.green; }
  } else { pct = 5; }
  return (
    <div style={{ height: 4, borderRadius: 2, background: "#E4E4E7", overflow: "hidden", width: "100%", ...s }}>
      <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 2, transition: "width .3s" }} />
    </div>
  );
}

const fmt = (v: string | number) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "0" : Math.round(n).toLocaleString("es-CL");
};
const fmtDec = (v: string | number, d = 1) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "0" : n.toFixed(d);
};
const fmtMoney = (v: string | number) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL");
};

/* ═══════════════════════════════════════════════════════════════════════════
   TYPES
   ═══════════════════════════════════════════════════════════════════════════ */
type KPIs = {
  at_risk_7d: number; imminent_3d: number; value_at_risk: string;
  avg_mape: number; model_count: number; pending_suggestions: number;
  products_with_forecast: number; products_without_forecast: number;
};
type FP = {
  product_id: number; product_name: string; sku: string | null;
  category: string | null; warehouse_id: number; on_hand: string;
  avg_daily_demand: string; demand_7d: string; avg_cost?: string;
  days_to_stockout: number | null; algorithm: string;
  mape: number | null; data_points: number; trained_at?: string;
  is_recipe_ingredient?: boolean;
};
type Detail = {
  product: { id: number; name: string; sku: string; category: string | null };
  stock: { on_hand: string; avg_cost: string; stock_value?: string };
  model: { algorithm: string; version?: number; metrics: any; data_points: number; trained_at?: string; params?: any; demand_pattern?: string } | null;
  suggestion: { suggested_qty: string; target_days: number; estimated_cost: string; reasoning: string | null; priority: string | null; is_estimate?: boolean } | null;
  history: { date: string; qty_sold: string; revenue?: string; qty_lost?: string; qty_received?: string }[];
  forecast: { date: string; qty_predicted: string; lower_bound: string; upper_bound: string; days_to_stockout: number | null; confidence?: string }[];
};
type PageMeta = { count: number; page: number; page_size: number; total_pages: number; categories: string[] };

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
export default function ForecastPage() {
  const mob = useIsMobile();
  const [kpis, setKpis] = useState<KPIs | null>(null);
  const [products, setProducts] = useState<FP[]>([]);
  const [meta, setMeta] = useState<PageMeta>({ count: 0, page: 1, page_size: 50, total_pages: 0, categories: [] });
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [selId, setSelId] = useState<number | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [detLoad, setDetLoad] = useState(false);

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [risk, setRisk] = useState("");
  const [sort, setSort] = useState("stockout");
  const [page, setPage] = useState(1);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    apiFetch("/forecast/dashboard/").then((d: any) => setKpis(d?.kpis || null)).catch(() => {});
  }, []);

  const loadProducts = useCallback(async (p: number, s: string, cat: string, r: string, srt: string) => {
    setTableLoading(true);
    try {
      const params = new URLSearchParams({ page: String(p), page_size: "50", sort: srt });
      if (s) params.set("search", s);
      if (cat) params.set("category", cat);
      if (r) params.set("risk", r);
      const data = await apiFetch(`/forecast/products/?${params}`);
      setProducts(data?.results || []);
      setMeta({
        count: data?.count || 0, page: data?.page || p,
        page_size: data?.page_size || 50, total_pages: data?.total_pages || 0,
        categories: data?.categories || meta.categories,
      });
    } catch (e) { console.error(e); }
    finally { setTableLoading(false); setLoading(false); }
  }, []);

  useEffect(() => { loadProducts(page, search, category, risk, sort); }, [page, category, risk, sort]);

  const onSearch = (val: string) => {
    setSearch(val);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => { setPage(1); loadProducts(1, val, category, risk, sort); }, 350);
  };

  useEffect(() => {
    if (selId === null) { setDetail(null); return; }
    let c = false;
    setDetLoad(true);
    apiFetch(`/forecast/products/${selId}/`).then((r: any) => { if (!c) setDetail(r); })
      .catch(() => {}).finally(() => { if (!c) setDetLoad(false); });
    return () => { c = true; };
  }, [selId]);

  const hasUrgent = kpis ? kpis.imminent_3d > 0 : false;

  const iS: React.CSSProperties = {
    padding: "8px 12px", border: `1px solid ${C.border}`, borderRadius: 8,
    fontSize: 13, fontFamily: C.font, background: C.surface, outline: "none",
  };

  return (
    <div style={{
      fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh",
      padding: mob ? "14px 10px" : "24px 28px",
      display: "flex", flexDirection: "column", gap: mob ? 14 : 18,
    }}>

  <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: mob ? 19 : 23, fontWeight: 800, letterSpacing: "-.04em" }}>
            ¿Qué productos necesito reponer?
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: C.mute }}>
            El sistema analiza tus ventas y te avisa antes de que se acabe el stock
          </p>
        </div>
        
        {/* Botón permanente para ir a las Sugerencias de Pedido */}
        <Link href="/dashboard/forecast/suggestions" style={{ 
          padding: "10px 18px", background: C.surface, border: `1px solid ${C.border}`, 
          borderRadius: 8, color: C.text, textDecoration: "none", fontWeight: 600, 
          fontSize: 14, display: "inline-flex", alignItems: "center", gap: 8,
          boxShadow: C.sh, transition: "all .2s"
        }} className="btn-secondary">
          📋 Ver pedidos sugeridos
        </Link>
      </div>

      {loading && (
        <div style={{ padding: "48px 0", display: "flex", alignItems: "center", justifyContent: "center", gap: 10, color: C.mute }}>
          <Spinner /><span style={{ fontSize: 13 }}>Analizando tu inventario…</span>
        </div>
      )}

      {kpis && kpis.imminent_3d > 0 && (
        <div style={{ background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: C.r, padding: mob ? "12px 14px" : "14px 20px", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div style={{ width: 36, height: 36, borderRadius: "50%", background: C.red, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 18, flexShrink: 0 }}>!</div>
          <div style={{ flex: 1, minWidth: 180 }}>
            <div style={{ fontWeight: 700, fontSize: 14, color: C.red }}>
              {kpis.imminent_3d} producto{kpis.imminent_3d > 1 ? "s se van a agotar" : " se va a agotar"} en menos de 3 días
            </div>
            <div style={{ fontSize: 12, color: C.mid, marginTop: 2 }}>
              Valor en riesgo: <b>{fmtMoney(kpis.value_at_risk)}</b> · Revisa la lista abajo y haz tu pedido
            </div>
          </div>
        </div>
      )}

      {kpis && !loading && (
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(3, 1fr)", gap: 10 }}>
          <div style={{ background: C.surface, border: `1px solid ${hasUrgent ? C.redBd : C.border}`, borderRadius: C.r, padding: "14px 16px", boxShadow: C.sh }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 6 }}>Necesitan reposición</div>
            <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-.03em", color: hasUrgent ? C.red : C.green, fontVariantNumeric: "tabular-nums" }}>{kpis.at_risk_7d + kpis.imminent_3d}</div>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{hasUrgent ? `${kpis.imminent_3d} crítico${kpis.imminent_3d !== 1 ? "s" : ""} · ${kpis.at_risk_7d} en riesgo` : "Todo bajo control"}</div>
          </div>
          <div style={{ background: C.surface, border: `1px solid ${kpis.pending_suggestions > 0 ? C.amberBd : C.border}`, borderRadius: C.r, padding: "14px 16px", boxShadow: C.sh }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 6 }}>Pedidos sugeridos</div>
            <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-.03em", color: kpis.pending_suggestions > 0 ? C.amber : C.mute, fontVariantNumeric: "tabular-nums" }}>{kpis.pending_suggestions}</div>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{kpis.pending_suggestions > 0 ? "Listos para aprobar" : "Sin pedidos pendientes"}</div>
          </div>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "14px 16px", boxShadow: C.sh, gridColumn: mob ? "1 / -1" : "auto" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 6 }}>Productos analizados</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-.03em", color: C.accent, fontVariantNumeric: "tabular-nums" }}>{kpis.products_with_forecast}</span>
              <span style={{ fontSize: 13, color: C.mute }}>de {kpis.products_with_forecast + kpis.products_without_forecast}</span>
            </div>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>
              {kpis.avg_mape > 0 ? `Precisión: ${kpis.avg_mape < 25 ? "alta" : kpis.avg_mape < 40 ? "buena" : "mejorando"} (${Math.round(100 - kpis.avg_mape)}%)` : "Acumulando datos…"}
            </div>
          </div>
        </div>
      )}

      {kpis && kpis.pending_suggestions > 0 && (
        <Link href="/dashboard/forecast/suggestions" style={{
          display: "flex", alignItems: "center", gap: 12, padding: mob ? "12px 14px" : "14px 20px",
          background: "linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 100%)",
          border: `1px solid ${C.amberBd}`, borderRadius: C.r,
          textDecoration: "none", color: C.text, boxShadow: C.sh,
        }}>
          <div style={{ width: 36, height: 36, borderRadius: C.r, background: C.amber, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 16, flexShrink: 0, fontWeight: 800 }}>📋</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 14 }}>Tienes {kpis.pending_suggestions} pedido{kpis.pending_suggestions > 1 ? "s" : ""} listo{kpis.pending_suggestions > 1 ? "s" : ""} para aprobar</div>
            <div style={{ fontSize: 12, color: C.mid, marginTop: 1 }}>Armados automáticamente según lo que necesitas reponer</div>
          </div>
          <div style={{ fontWeight: 700, color: C.amber, fontSize: 20, flexShrink: 0 }}>→</div>
        </Link>
      )}

      {!loading && meta.count === 0 && !search && !category && !risk && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "48px 24px", textAlign: "center", boxShadow: C.sh }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>📊</div>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>Todavía no hay predicciones</div>
          <div style={{ fontSize: 13, color: C.mute, maxWidth: 400, margin: "0 auto", lineHeight: 1.7 }}>
            El sistema necesita al menos 2 semanas de ventas registradas para empezar a predecir. Sigue vendiendo normalmente y las predicciones aparecerán automáticamente.
          </div>
        </div>
      )}

      {/* SEARCH + FILTERS */}
      {(meta.count > 0 || search || category || risk) && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <div style={{ position: "relative", flex: mob ? "1 1 100%" : "1 1 220px", maxWidth: mob ? "100%" : 300 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }}>
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input value={search} onChange={e => onSearch(e.target.value)} placeholder="Buscar producto…" style={{ ...iS, width: "100%", paddingLeft: 32 }} />
            {search && (
              <button onClick={() => { setSearch(""); setPage(1); loadProducts(1, "", category, risk, sort); }}
                style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: C.mute, fontSize: 16 }}>×</button>
            )}
          </div>
          {meta.categories.length > 0 && (
            <select value={category} onChange={e => { setCategory(e.target.value); setPage(1); }}
              style={{ ...iS, width: "auto", minWidth: 140, color: category ? C.text : C.mute, cursor: "pointer" }}>
              <option value="">Todas las categorías</option>
              {meta.categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          )}
          <select value={risk} onChange={e => { setRisk(e.target.value); setPage(1); }}
            style={{ ...iS, width: "auto", minWidth: 130, color: risk ? C.text : C.mute, cursor: "pointer" }}>
            <option value="">Todos</option>
            <option value="urgent">En riesgo</option>
            <option value="ok">Sin riesgo</option>
          </select>
          <select value={sort} onChange={e => { setSort(e.target.value); setPage(1); }}
            style={{ ...iS, width: "auto", minWidth: 140, cursor: "pointer" }}>
            <option value="stockout">Más urgente primero</option>
            <option value="demand">Más vendido primero</option>
            <option value="name">Nombre A-Z</option>
          </select>
          <div style={{ fontSize: 12, color: C.mute, marginLeft: "auto" }}>
            {tableLoading ? <Spinner size={14} /> : `${meta.count} producto${meta.count !== 1 ? "s" : ""}`}
          </div>
        </div>
      )}

      {/* PRODUCT TABLE */}
      {products.length > 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", boxShadow: C.sh, opacity: tableLoading ? 0.6 : 1, transition: "opacity .2s" }}>
          {!mob && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 80px 100px 90px 120px", columnGap: 8, padding: "10px 18px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontSize: 10.5, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".07em" }}>
              <div>Producto</div>
              <div style={{ textAlign: "right" }}>En stock</div>
              <div style={{ textAlign: "right" }}>Venta / día</div>
              <div style={{ textAlign: "center" }}>Estado</div>
              <div>Urgencia</div>
            </div>
          )}

          {products.map((p, i) => {
            const sel = selId === p.product_id;
            const stock = parseFloat(p.on_hand);
            const dto = p.days_to_stockout;
            const isU = dto !== null && dto <= 3;
            const isW = dto !== null && dto <= 7 && dto > 3;
            const bL = isU ? `3px solid ${C.red}` : isW ? `3px solid ${C.amber}` : "3px solid transparent";

            if (mob) return (
              <div key={p.product_id}>
                <div onClick={() => setSelId(sel ? null : p.product_id)} style={{ padding: "11px 12px", cursor: "pointer", borderBottom: i < products.length - 1 ? `1px solid ${C.border}` : "none", borderLeft: bL, background: sel ? C.accentBg : "transparent" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.product_name}</div>
                      <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>
                        Quedan <b style={{ color: C.text }}>{fmt(stock)}</b> · Se venden <b style={{ color: C.text }}>{fmtDec(p.avg_daily_demand)}</b> al día
                      </div>
                    </div>
                    <StatusBadge days={dto} />
                  </div>
                  <UrgencyBar days={dto} style={{ marginTop: 8 }} />
                </div>
                {sel && <DetailPanel detail={detail} loading={detLoad} mob />}
              </div>
            );

            return (
              <div key={p.product_id}>
                <div onClick={() => setSelId(sel ? null : p.product_id)} className="prow" style={{ display: "grid", gridTemplateColumns: "1fr 80px 100px 90px 120px", columnGap: 8, padding: "11px 18px", cursor: "pointer", borderBottom: i < products.length - 1 ? `1px solid ${C.border}` : "none", borderLeft: bL, background: sel ? C.accentBg : "transparent", alignItems: "center", transition: "background .1s" }}>
                  <div>
                    <div style={{ display:"flex", alignItems:"center", gap:6, flexWrap:"wrap" }}>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{p.product_name}</span>
                      {p.is_recipe_ingredient && (
                        <span style={{ fontSize:10, fontWeight:700, padding:"2px 7px", borderRadius:99, background:"#FFFBEB", border:"1px solid #FDE68A", color:"#D97706", letterSpacing:"0.03em" }}>🥄 Ingrediente</span>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: C.mute, marginTop: 1 }}>
                      {p.sku && <span style={{ fontFamily: C.mono }}>{p.sku}</span>}
                      {p.category && <span style={{ marginLeft: p.sku ? 6 : 0 }}>{p.category}</span>}
                    </div>
                  </div>
                  <div style={{ textAlign: "right", fontWeight: 700, fontSize: 13, fontVariantNumeric: "tabular-nums" }}>{fmt(stock)}</div>
                  <div style={{ textAlign: "right", fontSize: 13, fontVariantNumeric: "tabular-nums", color: C.mid }}>{fmtDec(p.avg_daily_demand)}</div>
                  <div style={{ textAlign: "center" }}><StatusBadge days={dto} /></div>
                  <UrgencyBar days={dto} />
                </div>
                {sel && <DetailPanel detail={detail} loading={detLoad} mob={false} />}
              </div>
            );
          })}
        </div>
      )}

      {!loading && products.length === 0 && (search || category || risk) && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "32px 20px", textAlign: "center" }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🔍</div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>Sin resultados</div>
          <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>
            No hay productos con esos filtros.{" "}
            <button onClick={() => { setSearch(""); setCategory(""); setRisk(""); setPage(1); loadProducts(1, "", "", "", sort); }}
              style={{ background: "none", border: "none", color: C.accent, fontWeight: 600, cursor: "pointer", fontSize: 13 }}>Limpiar filtros</button>
          </div>
        </div>
      )}

      {/* PAGINATION */}
      {meta.total_pages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 6 }}>
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
            style={{ ...iS, width: 36, padding: "6px", textAlign: "center", cursor: page <= 1 ? "default" : "pointer", opacity: page <= 1 ? .4 : 1 }}>‹</button>
          {Array.from({ length: Math.min(meta.total_pages, 7) }, (_, i) => {
            let p: number;
            if (meta.total_pages <= 7) p = i + 1;
            else if (page <= 4) p = i + 1;
            else if (page >= meta.total_pages - 3) p = meta.total_pages - 6 + i;
            else p = page - 3 + i;
            return (
              <button key={p} onClick={() => setPage(p)} style={{
                ...iS, width: 36, padding: "6px", textAlign: "center", cursor: "pointer",
                background: p === page ? C.accent : C.surface, color: p === page ? "#fff" : C.mid,
                fontWeight: p === page ? 700 : 500, border: p === page ? "none" : `1px solid ${C.border}`,
              }}>{p}</button>
            );
          })}
          <button disabled={page >= meta.total_pages} onClick={() => setPage(p => p + 1)}
            style={{ ...iS, width: 36, padding: "6px", textAlign: "center", cursor: page >= meta.total_pages ? "default" : "pointer", opacity: page >= meta.total_pages ? .4 : 1 }}>›</button>
        </div>
      )}

      <style>{`
        @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
        .prow:hover{background:${C.accentBg}!important}
      `}</style>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   INSIGHTS SECTION — explains WHY the system predicts what it predicts
   ═══════════════════════════════════════════════════════════════════════════ */

const ALG_LABELS: Record<string, string> = {
  simple_avg: "Promedio simple de ventas históricas",
  moving_avg: "Media móvil ponderada (más peso a días recientes)",
  holt_winters: "Modelo Holt-Winters (captura tendencia + estacionalidad)",
  category_prior: "Basado en productos similares de la categoría",
  croston: "Método Croston (especializado en demanda intermitente)",
  croston_sba: "Método Croston SBA (demanda intermitente, corregido)",
  ensemble: "Combinación de múltiples modelos (ensemble)",
};

const PATTERN_LABELS: Record<string, { label: string; desc: string; color: string }> = {
  smooth: { label: "Regular", desc: "Se vende de forma constante", color: C.green },
  intermittent: { label: "Intermitente", desc: "Ventas espaciadas con períodos sin movimiento", color: C.amber },
  lumpy: { label: "Irregular", desc: "Ventas infrecuentes y con cantidades muy variables", color: C.red },
  insufficient: { label: "Datos insuficientes", desc: "Muy pocos días de historial para clasificar", color: C.mute },
};

function InsightsSection({ model, history, avgDemand, mob }: {
  model: Detail["model"]; history: Detail["history"]; avgDemand: number; mob: boolean;
}) {
  if (!model) return null;
  const p = model.params || {};
  const m = model.metrics || {};

  const insights: { icon: string; text: string }[] = [];

  // 1. Algorithm
  const algLabel = ALG_LABELS[model.algorithm] || model.algorithm;
  insights.push({ icon: "🧠", text: `Método: ${algLabel}` });

  // 2. Demand pattern
  const dp = model.demand_pattern || p.demand_pattern;
  if (dp && PATTERN_LABELS[dp]) {
    const pl = PATTERN_LABELS[dp];
    insights.push({ icon: "📊", text: `Patrón de demanda: ${pl.label} — ${pl.desc}` });
  }

  // 3. Accuracy
  const mape = m.mape;
  if (mape != null) {
    const acc = Math.round(100 - mape);
    const label = acc >= 85 ? "Excelente" : acc >= 70 ? "Buena" : acc >= 50 ? "Aceptable" : "Baja";
    insights.push({ icon: acc >= 70 ? "✅" : "⚠️", text: `Precisión del modelo: ${acc}% (${label}) — error promedio ${Math.round(mape)}%` });
  }

  // 4. Trend
  const trend = p.trend;
  if (trend && trend.direction && trend.direction !== "flat") {
    const pct = trend.slope && avgDemand > 0 ? Math.abs(Math.round((trend.slope / avgDemand) * 30 * 100)) : null;
    const dir = trend.direction === "up" ? "subiendo" : "bajando";
    const txt = pct ? `Tendencia: la demanda viene ${dir} (~${pct}% mensual)` : `Tendencia: la demanda viene ${dir}`;
    insights.push({ icon: trend.direction === "up" ? "📈" : "📉", text: txt });
  }

  // 5. Monthly seasonality (payday effect)
  const ms = p.monthly_seasonality;
  if (ms && typeof ms === "object") {
    const values = Object.values(ms) as number[];
    const max = Math.max(...values);
    const min = Math.min(...values);
    if (max / Math.max(min, 0.01) > 1.15) {
      const peakKey = Object.keys(ms).find(k => ms[k] === max);
      const bucketLabels: Record<string, string> = { early: "inicio de mes (1-5)", mid_early: "primera quincena (6-12)", mid: "mediados (13-19)", mid_late: "antes del día de pago (20-25)", late: "fin de mes (26-31)" };
      const peakLabel = peakKey ? bucketLabels[peakKey] || peakKey : "";
      const boost = Math.round((max - 1) * 100);
      insights.push({ icon: "💰", text: `Efecto día de pago: vende ${boost}% más a ${peakLabel}` });
    }
  }

  // 6. Day of week
  const dow = p.dow_factors;
  if (dow && typeof dow === "object") {
    const dayNames = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
    const entries = Object.entries(dow).map(([k, v]) => ({ day: parseInt(k), factor: v as number }));
    if (entries.length >= 5) {
      const best = entries.reduce((a, b) => b.factor > a.factor ? b : a);
      const worst = entries.reduce((a, b) => b.factor < a.factor ? b : a);
      if (best.factor / Math.max(worst.factor, 0.01) > 1.3) {
        insights.push({ icon: "📅", text: `Mejor día: ${dayNames[best.day] || best.day} (${Math.round((best.factor - 1) * 100)}% sobre promedio) · Peor: ${dayNames[worst.day] || worst.day}` });
      }
    }
  }

  // 7. YoY growth
  const yoy = p.yoy_growth;
  if (yoy && Math.abs(yoy) > 0.05) {
    const pct = Math.round(yoy * 100);
    insights.push({ icon: pct > 0 ? "🚀" : "⬇️", text: `Crecimiento anual: ${pct > 0 ? "+" : ""}${pct}% respecto al año pasado` });
  }

  // 8. Bias correction
  const bias = p.bias_correction;
  if (bias && Math.abs(bias) > 0.1) {
    insights.push({ icon: "🔧", text: `Auto-corrección aplicada: el modelo ajustó ${bias > 0 ? "hacia arriba" : "hacia abajo"} para compensar predicciones recientes` });
  }

  // 9. Price sensitivity
  const ps = p.price_sensitivity;
  if (ps && ps.is_sensitive) {
    insights.push({ icon: "💲", text: "Producto sensible al precio: cambios de precio afectan la demanda" });
  }

  // 10. Data quality
  if (model.data_points < 14) {
    insights.push({ icon: "⏳", text: `Solo ${model.data_points} días de datos — la predicción mejorará con más historial` });
  }

  if (insights.length === 0) return null;

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: mob ? "10px 10px" : "14px 16px" }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, marginBottom: 8 }}>
        🔍 ¿Por qué el sistema predice esto?
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {insights.map((ins, i) => (
          <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12, color: C.text, lineHeight: 1.5 }}>
            <span style={{ flexShrink: 0, fontSize: 13 }}>{ins.icon}</span>
            <span>{ins.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   DETAIL PANEL
   ───────────────────────────────────────────────────────────────────────────
   FILOSOFÍA: El dueño de negocio NO sabe qué es MAPE, data points, ni
   algoritmos. Solo necesita saber:
   1. ¿Cuánto me queda?
   2. ¿Cuánto vendo?
   3. ¿Cuándo se me acaba?
   4. ¿Cuánto tengo que pedir?
   
   El gráfico muestra:
   - Línea azul sólida = "lo que vendiste" (datos reales)
   - Línea naranja punteada = "lo que el sistema cree que vas a vender"
   - Línea roja punteada = "tu stock bajando día a día"
   - Etiqueta roja = "¡SE ACABA!" donde el stock llega a 0
   - Banda naranja suave = "podría variar entre estos valores"
   ═══════════════════════════════════════════════════════════════════════════ */
function DetailPanel({ detail, loading, mob }: { detail: Detail | null; loading: boolean; mob: boolean }) {
  if (loading) return (
    <div style={{ padding: 24, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, color: C.mute, borderBottom: `1px solid ${C.border}` }}>
      <Spinner /> <span style={{ fontSize: 12 }}>Cargando detalle…</span>
    </div>
  );
  if (!detail) return null;

  const history = detail.history || [];
  const forecast = detail.forecast || [];
  const stockLevel = parseFloat(detail.stock.on_hand);
  const avgCost = parseFloat(detail.stock.avg_cost || "0");
  const daysOut = forecast.length > 0 && forecast[0].days_to_stockout !== null ? forecast[0].days_to_stockout : null;
  const avgDemand = forecast.length > 0 ? forecast.reduce((s, f) => s + parseFloat(f.qty_predicted), 0) / forecast.length : 0;

  const sug = detail.suggestion;
  const targetDays = sug?.target_days ?? 14;
  const reorderQty = sug ? Math.max(0, Math.ceil(parseFloat(sug.suggested_qty))) : Math.max(0, Math.ceil(avgDemand * targetDays - stockLevel));
  const reorderCost = sug ? parseFloat(sug.estimated_cost) : reorderQty * avgCost;
  const coverageLabel = targetDays === 7 ? "1 semana" : targetDays === 10 ? "10 días" : targetDays === 14 ? "2 semanas" : `${targetDays} días`;

  const totalSold = history.reduce((s, h) => s + parseFloat(h.qty_sold), 0);
  const totalRevenue = history.reduce((s, h) => s + parseFloat(h.revenue || "0"), 0);

  // Chart
  const allPts = [
    ...history.map(h => ({ label: h.date.slice(5), actual: parseFloat(h.qty_sold), pred: null as number | null, upper: null as number | null, lower: null as number | null, isFc: false })),
    ...forecast.map(f => ({ label: f.date.slice(5), actual: null as number | null, pred: parseFloat(f.qty_predicted), upper: parseFloat(f.upper_bound), lower: parseFloat(f.lower_bound), isFc: true })),
  ];
  if (allPts.length === 0) return null;

  const maxV = Math.max(...allPts.map(d => Math.max(d.actual || 0, d.upper || d.pred || 0)), 1) * 1.2;
  const W = mob ? 340 : 680, H = mob ? 150 : 190;
  const pL = 36, pR = 14, pT = 28, pB = 28;
  const plotW = W - pL - pR, plotH = H - pT - pB;
  const n = allPts.length, dx = plotW / Math.max(n - 1, 1);
  const xp = (i: number) => pL + i * dx;
  const yp = (v: number) => pT + plotH * (1 - v / maxV);

  const actLine = allPts.map((p, i) => p.actual !== null ? `${xp(i)},${yp(p.actual)}` : null).filter(Boolean).join(" ");
  const predLine = allPts.map((p, i) => p.pred !== null ? `${xp(i)},${yp(p.pred)}` : null).filter(Boolean).join(" ");

  const fcStart = allPts.findIndex(p => p.isFc);
  let bandPath = "";
  if (fcStart >= 0) {
    const fc = allPts.slice(fcStart), bi = fcStart;
    const up = fc.map((p, i) => `${xp(bi + i)},${yp(p.upper || p.pred || 0)}`);
    const lo = fc.map((p, i) => `${xp(bi + i)},${yp(p.lower || 0)}`).reverse();
    bandPath = `M${up.join("L")}L${lo.join("L")}Z`;
  }

  let stockPts = "", soX: number | null = null;
  if (forecast.length > 0 && stockLevel > 0) {
    let cur = stockLevel;
    const pts: string[] = [`${xp(fcStart)},${yp(Math.min(cur, maxV))}`];
    for (let i = 0; i < forecast.length; i++) {
      cur -= parseFloat(forecast[i].qty_predicted);
      const sv = Math.max(0, cur);
      const xi = fcStart + i + (i < forecast.length - 1 ? 1 : 0);
      pts.push(`${xp(xi)},${yp(Math.min(sv, maxV))}`);
      if (cur <= 0 && soX === null) soX = xp(fcStart + i);
    }
    stockPts = pts.join(" ");
  }

  const yTicks = [0, .25, .5, .75, 1].map(p => ({ v: Math.round(maxV * p), y: yp(maxV * p) }));
  const lEvery = Math.max(1, Math.floor(n / (mob ? 5 : 10)));
  const sepX = fcStart >= 0 ? xp(fcStart) : null;

  return (
    <div style={{ padding: mob ? "14px 12px" : "18px 22px", borderBottom: `1px solid ${C.border}`, background: "#FAFAFA" }}>

      {/* ── RESUMEN ── */}
      <div style={{
        marginBottom: 14, padding: mob ? "12px" : "12px 16px", borderRadius: 8,
        background: daysOut !== null && daysOut <= 7 ? C.redBg : C.surface,
        border: `1px solid ${daysOut !== null && daysOut <= 7 ? C.redBd : C.border}`,
        fontSize: 13, lineHeight: 1.7,
      }}>
        {daysOut === null && (
          <><b style={{ color: C.green }}>✓ Sin riesgo.</b> Tienes <b>{fmt(stockLevel)}</b> unidades en bodega. Se venden en promedio <b>{fmtDec(avgDemand)}</b> al día. Con eso te alcanza para más de {coverageLabel}, así que no necesitas hacer nada por ahora.</>
        )}
        {daysOut !== null && daysOut === 0 && (
          <><b style={{ color: C.red }}>⚠ ¡Se agotó!</b> Este producto ya no tiene stock. Se vendían <b>{fmtDec(avgDemand)}</b> unidades por día. <b>Necesitas pedir al menos {reorderQty} unidades</b> para cubrir {coverageLabel}{avgCost > 0 && <> (costo estimado: <b>{fmtMoney(reorderCost)}</b>)</>}.</>
        )}
        {daysOut !== null && daysOut > 0 && daysOut <= 3 && (
          <><b style={{ color: C.red }}>⚠ ¡Urgente!</b> Quedan solo <b>{fmt(stockLevel)}</b> unidades y se venden <b>{fmtDec(avgDemand)}</b> al día. <b>En {daysOut} día{daysOut > 1 ? "s" : ""} se acaba</b> si no repones. Te recomendamos pedir <b>{reorderQty}</b> unidades para cubrir {coverageLabel}{avgCost > 0 && <> ({fmtMoney(reorderCost)} aprox.)</>}.</>
        )}
        {daysOut !== null && daysOut > 3 && daysOut <= 7 && (
          <><b style={{ color: C.amber }}>⏰ Ojo:</b> Tienes <b>{fmt(stockLevel)}</b> unidades. Se venden <b>{fmtDec(avgDemand)}</b> al día, así que te alcanzan para unos <b>{daysOut} días</b>. Conviene hacer un pedido esta semana. Sugerimos pedir <b>{reorderQty}</b> unidades para {coverageLabel}{avgCost > 0 && <> ({fmtMoney(reorderCost)} aprox.)</>}.</>
        )}
        {daysOut !== null && daysOut > 7 && (
          <><b style={{ color: C.accent }}>👁 Bajo vigilancia:</b> Tienes <b>{fmt(stockLevel)}</b> unidades y se venden <b>{fmtDec(avgDemand)}</b> al día. Te alcanza para unos <b>{daysOut} días</b>. No es urgente, pero tenlo en cuenta para tu próximo pedido.</>
        )}
      </div>

      {/* ── TARJETAS DE RESUMEN ── */}
      <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(3, 1fr)", gap: 8, marginBottom: 14 }}>
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px" }}>
          <div style={{ fontSize: 10, color: C.mute, fontWeight: 600 }}>EN BODEGA</div>
          <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2 }}>{fmt(stockLevel)} <span style={{ fontSize: 12, fontWeight: 500, color: C.mute }}>unidades</span></div>
          {avgCost > 0 && <div style={{ fontSize: 11, color: C.mute }}>Valor: {fmtMoney(stockLevel * avgCost)}</div>}
        </div>
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px" }}>
          <div style={{ fontSize: 10, color: C.mute, fontWeight: 600 }}>VENDISTE (ÚLTIMO MES)</div>
          <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2 }}>{fmt(totalSold)} <span style={{ fontSize: 12, fontWeight: 500, color: C.mute }}>unidades</span></div>
          {totalRevenue > 0 && <div style={{ fontSize: 11, color: C.mute }}>Ingreso: {fmtMoney(totalRevenue)}</div>}
        </div>
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px", gridColumn: mob ? "1 / -1" : "auto" }}>
          <div style={{ fontSize: 10, color: C.mute, fontWeight: 600 }}>CUÁNTO PEDIR</div>
          <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2, color: reorderQty > 0 ? C.amber : C.green }}>
            {reorderQty > 0 ? `${fmt(reorderQty)} unidades` : "No necesitas"}
          </div>
          {reorderQty > 0 && avgCost > 0 && <div style={{ fontSize: 11, color: C.mute }}>Costo aprox: {fmtMoney(reorderCost)} · Para 2 semanas</div>}
          {reorderQty === 0 && <div style={{ fontSize: 11, color: C.mute }}>Tienes stock suficiente</div>}
        </div>
      </div>

      {/* ── GRÁFICO ── */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: mob ? "10px 6px" : "14px 12px", marginBottom: 8 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, marginBottom: 8, paddingLeft: mob ? 4 : 8 }}>
          📈 Tus ventas y lo que el sistema predice
        </div>
        <div style={{ overflowX: "auto" }}>
          <svg width={W} height={H} style={{ display: "block" }}>
            {yTicks.map(t => (
              <g key={t.v}>
                <line x1={pL} x2={W - pR} y1={t.y} y2={t.y} stroke="#E4E4E7" strokeWidth={.5} />
                <text x={pL - 6} y={t.y + 3} fontSize={9} fill={C.mute} textAnchor="end">{t.v}</text>
              </g>
            ))}
            {sepX !== null && (
              <g>
                <line x1={sepX} x2={sepX} y1={pT - 6} y2={pT + plotH} stroke={C.border} strokeWidth={1} strokeDasharray="4,3" />
                <text x={sepX - 10} y={pT - 10} fontSize={10} fill={C.accent} textAnchor="end" fontWeight="700">Lo que vendiste</text>
                <text x={sepX + 10} y={pT - 10} fontSize={10} fill={C.amber} textAnchor="start" fontWeight="700">Lo que vas a vender</text>
              </g>
            )}
            {bandPath && <path d={bandPath} fill={C.amber} opacity={.08} />}
            {stockPts && <polyline points={stockPts} fill="none" stroke={C.red} strokeWidth={2} strokeDasharray="6,4" opacity={.5} />}
            {soX !== null && (
              <g>
                <line x1={soX} x2={soX} y1={pT} y2={pT + plotH} stroke={C.red} strokeWidth={1.5} strokeDasharray="3,3" opacity={.3} />
                <rect x={soX - 40} y={pT - 2} width={80} height={16} rx={4} fill={C.red} opacity={.9} />
                <text x={soX} y={pT + 10} fontSize={9} fill="#fff" textAnchor="middle" fontWeight="700">¡SE ACABA!</text>
                <circle cx={soX} cy={yp(0)} r={5} fill={C.red} />
                <circle cx={soX} cy={yp(0)} r={9} fill="none" stroke={C.red} strokeWidth={1.5} opacity={.3} />
              </g>
            )}
            {actLine && <polyline points={actLine} fill="none" stroke={C.accent} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />}
            {allPts.map((p, i) => p.actual !== null ? <circle key={`a${i}`} cx={xp(i)} cy={yp(p.actual)} r={2} fill={C.accent} /> : null)}
            {predLine && <polyline points={predLine} fill="none" stroke={C.amber} strokeWidth={2.5} strokeLinejoin="round" strokeDasharray="6,4" />}
            {allPts.map((p, i) => p.pred !== null ? <circle key={`p${i}`} cx={xp(i)} cy={yp(p.pred)} r={2.5} fill={C.amber} /> : null)}
            {allPts.map((p, i) => i % lEvery === 0 ? <text key={`x${i}`} x={xp(i)} y={H - 6} fontSize={9} fill={C.mute} textAnchor="middle">{p.label}</text> : null)}
          </svg>
        </div>

        <div style={{ display: "flex", gap: mob ? 10 : 16, marginTop: 6, fontSize: 11, color: C.mid, flexWrap: "wrap", paddingLeft: mob ? 4 : 8 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 14, height: 3, background: C.accent, borderRadius: 2, display: "inline-block" }} /> Lo que vendiste
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 14, height: 0, borderTop: `3px dashed ${C.amber}`, display: "inline-block" }} /> Lo que vas a vender
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 14, height: 0, borderTop: `3px dashed ${C.red}`, display: "inline-block" }} /> Tu stock bajando
          </span>
          {bandPath && (
            <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 14, height: 8, background: C.amber + "20", border: `1px solid ${C.amberBd}`, borderRadius: 2, display: "inline-block" }} /> Rango posible
            </span>
          )}
        </div>
      </div>

      {/* ── INSIGHTS: POR QUÉ EL SISTEMA PREDICE ESTO ── */}
      <InsightsSection model={detail.model} history={history} avgDemand={avgDemand} mob={mob} />
    </div>
  );
}