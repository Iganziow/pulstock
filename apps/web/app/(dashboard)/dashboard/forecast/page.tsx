"use client";

import Link from "next/link";
import { useEffect, useState, useCallback, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner, SkeletonPage } from "@/components/ui";
import { ForecastStatusBadge, UrgencyBar } from "@/components/forecast/ForecastBadges";
import { ForecastDetailPanel } from "@/components/forecast/ForecastDetailPanel";
import { fmt, fmtDec, fmtMoney } from "@/components/forecast/helpers";
import type { KPIs, FP, Detail, PageMeta } from "@/components/forecast/types";
import { humanizeError } from "@/lib/errors";

// ─── Main page ───────────────────────────────────────────────────────────────

export default function ForecastPage() {
  const mob = useIsMobile();
  const [kpis, setKpis] = useState<KPIs | null>(null);
  const [products, setProducts] = useState<FP[]>([]);
  const [meta, setMeta] = useState<PageMeta>({ count: 0, page: 1, page_size: 50, total_pages: 0, categories: [] });
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
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
    } catch (e: any) { setErr(humanizeError(e, "Error al cargar predicciones")); }
    finally { setTableLoading(false); setLoading(false); }
  }, []);

  useEffect(() => { loadProducts(page, search, category, risk, sort); }, [page, category, risk, sort]);

  const onSearch = (val: string) => {
    setSearch(val);
    clearTimeout(searchTimer.current!);
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
            ¿Que productos necesito reponer?
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: C.mute }}>
            El sistema analiza tus ventas y te avisa antes de que se acabe el stock
          </p>
        </div>
        <Link href="/dashboard/forecast/suggestions" style={{
          padding: "10px 18px", background: C.surface, border: `1px solid ${C.border}`,
          borderRadius: 8, color: C.text, textDecoration: "none", fontWeight: 600,
          fontSize: 14, display: "inline-flex", alignItems: "center", gap: 8,
          boxShadow: C.sh, transition: "all .2s"
        }} className="btn-secondary">
          Ver pedidos sugeridos
        </Link>
      </div>

      {err && (
        <div style={{ padding: "10px 16px", marginBottom: 16, borderRadius: 8, background: "#FEF2F2", border: "1px solid #FECACA", color: "#DC2626", fontSize: 13 }}>
          {err}
        </div>
      )}

      {loading && <SkeletonPage cards={3} rows={6} />}

      {kpis && kpis.imminent_3d > 0 && (
        <div style={{ background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: C.r, padding: mob ? "12px 14px" : "14px 20px", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div style={{ width: 36, height: 36, borderRadius: "50%", background: C.red, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 18, flexShrink: 0 }}>!</div>
          <div style={{ flex: 1, minWidth: 180 }}>
            <div style={{ fontWeight: 700, fontSize: 14, color: C.red }}>
              {kpis.imminent_3d} producto{kpis.imminent_3d > 1 ? "s se van a agotar" : " se va a agotar"} en menos de 3 dias
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
            <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 6 }}>Necesitan reposicion</div>
            <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-.03em", color: hasUrgent ? C.red : C.green, fontVariantNumeric: "tabular-nums" }}>{kpis.at_risk_7d + kpis.imminent_3d}</div>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{hasUrgent ? `${kpis.imminent_3d} critico${kpis.imminent_3d !== 1 ? "s" : ""} · ${kpis.at_risk_7d} en riesgo` : "Todo bajo control"}</div>
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
              {kpis.avg_mape > 0 ? `Precision: ${kpis.avg_mape < 25 ? "alta" : kpis.avg_mape < 40 ? "buena" : "mejorando"} (${Math.round(100 - kpis.avg_mape)}%)` : "Acumulando datos…"}
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
          <div style={{ width: 36, height: 36, borderRadius: C.r, background: C.amber, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 16, flexShrink: 0, fontWeight: 800 }}>&#x1F4CB;</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 14 }}>Tienes {kpis.pending_suggestions} pedido{kpis.pending_suggestions > 1 ? "s" : ""} listo{kpis.pending_suggestions > 1 ? "s" : ""} para aprobar</div>
            <div style={{ fontSize: 12, color: C.mid, marginTop: 1 }}>Armados automaticamente segun lo que necesitas reponer</div>
          </div>
          <div style={{ fontWeight: 700, color: C.amber, fontSize: 20, flexShrink: 0 }}>→</div>
        </Link>
      )}

      {!loading && meta.count === 0 && !search && !category && !risk && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "48px 24px", textAlign: "center", boxShadow: C.sh }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>&#x1F4CA;</div>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>Todavia no hay predicciones</div>
          <div style={{ fontSize: 13, color: C.mute, maxWidth: 400, margin: "0 auto", lineHeight: 1.7 }}>
            El sistema necesita al menos 2 semanas de ventas registradas para empezar a predecir. Sigue vendiendo normalmente y las predicciones apareceran automaticamente.
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
              <option value="">Todas las categorias</option>
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
            <option value="stockout">Mas urgente primero</option>
            <option value="demand">Mas vendido primero</option>
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
              <div style={{ textAlign: "right" }}>Venta / dia</div>
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
                        Quedan <b style={{ color: C.text }}>{fmt(stock)}</b> · Se venden <b style={{ color: C.text }}>{fmtDec(p.avg_daily_demand)}</b> al dia
                      </div>
                    </div>
                    <ForecastStatusBadge days={dto} />
                  </div>
                  <UrgencyBar days={dto} style={{ marginTop: 8 }} />
                </div>
                {sel && <ForecastDetailPanel detail={detail} loading={detLoad} mob />}
              </div>
            );

            return (
              <div key={p.product_id}>
                <div onClick={() => setSelId(sel ? null : p.product_id)} className="prow" style={{ display: "grid", gridTemplateColumns: "1fr 80px 100px 90px 120px", columnGap: 8, padding: "11px 18px", cursor: "pointer", borderBottom: i < products.length - 1 ? `1px solid ${C.border}` : "none", borderLeft: bL, background: sel ? C.accentBg : "transparent", alignItems: "center", transition: "background .1s" }}>
                  <div>
                    <div style={{ display:"flex", alignItems:"center", gap:6, flexWrap:"wrap" }}>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{p.product_name}</span>
                      {p.is_recipe_ingredient && (
                        <span style={{ fontSize:10, fontWeight:700, padding:"2px 7px", borderRadius:99, background:"#FFFBEB", border:"1px solid #FDE68A", color:"#D97706", letterSpacing:"0.03em" }}>Ingrediente</span>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: C.mute, marginTop: 1 }}>
                      {p.sku && <span style={{ fontFamily: C.mono }}>{p.sku}</span>}
                      {p.category && <span style={{ marginLeft: p.sku ? 6 : 0 }}>{p.category}</span>}
                    </div>
                  </div>
                  <div style={{ textAlign: "right", fontWeight: 700, fontSize: 13, fontVariantNumeric: "tabular-nums" }}>{fmt(stock)}</div>
                  <div style={{ textAlign: "right", fontSize: 13, fontVariantNumeric: "tabular-nums", color: C.mid }}>{fmtDec(p.avg_daily_demand)}</div>
                  <div style={{ textAlign: "center" }}><ForecastStatusBadge days={dto} /></div>
                  <UrgencyBar days={dto} />
                </div>
                {sel && <ForecastDetailPanel detail={detail} loading={detLoad} mob={false} />}
              </div>
            );
          })}
        </div>
      )}

      {!loading && products.length === 0 && (search || category || risk) && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "32px 20px", textAlign: "center" }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>&#x1F50D;</div>
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
            let pg: number;
            if (meta.total_pages <= 7) pg = i + 1;
            else if (page <= 4) pg = i + 1;
            else if (page >= meta.total_pages - 3) pg = meta.total_pages - 6 + i;
            else pg = page - 3 + i;
            return (
              <button key={pg} onClick={() => setPage(pg)} style={{
                ...iS, width: 36, padding: "6px", textAlign: "center", cursor: "pointer",
                background: pg === page ? C.accent : C.surface, color: pg === page ? "#fff" : C.mid,
                fontWeight: pg === page ? 700 : 500, border: pg === page ? "none" : `1px solid ${C.border}`,
              }}>{pg}</button>
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
