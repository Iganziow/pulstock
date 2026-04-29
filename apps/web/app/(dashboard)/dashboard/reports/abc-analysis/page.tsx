"use client";
import Link from "next/link";
import { useEffect, useState, useMemo } from "react";
import { apiFetch } from "@/lib/api";
import ExportButtons, { buildExportConfig } from "@/components/ExportButtons";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";
import { humanizeError } from "@/lib/errors";
const fmt = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "0" : Math.round(n).toLocaleString("es-CL"); };
const fmtMoney = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL"); };
const fmtPct = (v: number) => isNaN(v) ? "0.0" : v.toFixed(1);
const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (d: number) => { const t = new Date(); t.setDate(t.getDate() - d); return t.toISOString().slice(0, 10); };
const toNum = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? 0 : n; };

const ABC_CONFIG: Record<string, { color: string; bg: string; bd: string; icon: string; label: string; advice: string }> = {
  A: { color: "#16A34A", bg: "#ECFDF5", bd: "#A7F3D0", icon: "⭐", label: "Estrella", advice: "Estos productos son tu fuente principal de ingreso. Nunca te quedes sin stock, negocia mejores precios con proveedores, y dales la mejor ubicación en tu local." },
  B: { color: "#D97706", bg: "#FFFBEB", bd: "#FDE68A", icon: "📦", label: "Importante", advice: "Son productos estables que complementan tus ventas. Mantén stock controlado y revísalos mensualmente para detectar si suben a A o bajan a C." },
  C: { color: "#A1A1AA", bg: "#F4F4F5", bd: "#D4D4D8", icon: "📋", label: "Cola", advice: "Aportan poco al ingreso total. Evalúa si vale la pena mantenerlos: considera liquidar, reducir stock mínimo, o negociar consignación con el proveedor." },
};

const MEDALS = ["🥇", "🥈", "🥉"];

type Row = { rank: number; product_id: number; product_name: string; sku: string; category: string; abc_class: string; revenue: string; cost: string; profit: string; margin_pct: string; qty: string; sale_count: number; contribution_pct: string; cumulative_pct: string; current_stock: string; stock_value: string; is_virtual_stock?: boolean };
type ClassSummary = Record<string, { count: number; pct_products: string; revenue: string; profit: string; pct_revenue: string; stock_value: string }>;
type ViewTab = "pareto" | "topn" | "category";

export default function ABCAnalysisPage() {
  const mob = useIsMobile();
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<Row[]>([]);
  const [classSummary, setClassSummary] = useState<ClassSummary>({});
  const [meta, setMeta] = useState<any>(null);
  const [dateFrom, setDateFrom] = useState(daysAgo(90));
  const [dateTo, setDateTo] = useState(today());
  const [criterion, setCriterion] = useState("revenue");
  const [filter, setFilter] = useState<"all" | "A" | "B" | "C">("all");
  const [err, setErr] = useState("");
  const [view, setView] = useState<ViewTab>("pareto");
  const [topLimit, setTopLimit] = useState(20);
  const [topSort, setTopSort] = useState("revenue");

  const load = async () => {
    setLoading(true);
    try {
      setErr("");
      const data = await apiFetch(`/reports/abc-analysis/?date_from=${dateFrom}&date_to=${dateTo}&criterion=${criterion}`);
      setRows(data?.results || []);
      setClassSummary(data?.class_summary || {});
      setMeta(data?.meta || null);
    } catch (e: any) { setErr(humanizeError(e, "Error al cargar el reporte")); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  // ── Computed data ──
  const totals = useMemo(() => {
    const rev = rows.reduce((s, r) => s + toNum(r.revenue), 0);
    const cost = rows.reduce((s, r) => s + toNum(r.cost), 0);
    const profit = rows.reduce((s, r) => s + toNum(r.profit), 0);
    return { revenue: rev, cost, profit, margin: rev > 0 ? (profit / rev) * 100 : 0 };
  }, [rows]);

  const filtered = filter === "all" ? rows : rows.filter(r => r.abc_class === filter);

  const topSorted = useMemo(() => {
    const sorted = [...rows].sort((a, b) => toNum(b[topSort as keyof Row] as string) - toNum(a[topSort as keyof Row] as string));
    return sorted.slice(0, topLimit);
  }, [rows, topSort, topLimit]);

  const byCategory = useMemo(() => {
    const map: Record<string, { category: string; revenue: number; cost: number; profit: number; qty: number; count: number }> = {};
    rows.forEach(r => {
      const cat = r.category || "Sin categoría";
      if (!map[cat]) map[cat] = { category: cat, revenue: 0, cost: 0, profit: 0, qty: 0, count: 0 };
      map[cat].revenue += toNum(r.revenue);
      map[cat].cost += toNum(r.cost);
      map[cat].profit += toNum(r.profit);
      map[cat].qty += toNum(r.qty);
      map[cat].count += 1;
    });
    return Object.values(map).sort((a, b) => b.revenue - a.revenue);
  }, [rows]);

  const iS: React.CSSProperties = { padding: "7px 10px", border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 13, fontFamily: C.font, background: C.surface, outline: "none" };

  // Pareto chart
  const chartW = mob ? 340 : 680, chartH = mob ? 120 : 150;
  const pL = 36, pR = 10, pT = 14, pB = 18;
  const plotW = chartW - pL - pR, plotH = chartH - pT - pB;
  const n = rows.length;

  const criterionLabel = criterion === "revenue" ? "ingreso" : criterion === "profit" ? "ganancia" : "cantidad vendida";

  const VIEW_TABS: { key: ViewTab; label: string; icon: string }[] = [
    { key: "pareto", label: "Pareto ABC", icon: "📊" },
    { key: "topn", label: "Top Productos", icon: "🏆" },
    { key: "category", label: "Por categoría", icon: "📁" },
  ];

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "14px 10px" : "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <Link href="/dashboard/reports" style={{ fontSize: 12, color: C.mute, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4, marginBottom: 8 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg> Reportes
        </Link>
        <h1 style={{ margin: 0, fontSize: mob ? 19 : 23, fontWeight: 800, letterSpacing: "-.04em" }}>📊 Análisis ABC de Inventario</h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: C.mute }}>
          Clasifica tus productos, ve cuáles son los más rentables, y analiza por categoría — todo en un solo lugar
        </p>
      </div>

      {/* ── Filters & Actions ── */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={iS} />
          <span style={{ fontSize: 12, color: C.mute }}>a</span>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={iS} />
          <select value={criterion} onChange={e => setCriterion(e.target.value)} style={{ ...iS, cursor: "pointer" }}>
            <option value="revenue">Por ingreso</option>
            <option value="profit">Por ganancia</option>
            <option value="qty">Por cantidad vendida</option>
          </select>
          <button onClick={load} style={{ ...iS, background: C.accent, color: "#fff", border: "none", cursor: "pointer", fontWeight: 600, padding: "7px 14px" }}>
            Analizar
          </button>
        </div>
        {!loading && rows.length > 0 && (
          <ExportButtons {...buildExportConfig("abc-analysis", rows)} compact={!mob} />
        )}
      </div>

      {err && <div style={{ padding: "10px 16px", borderRadius: 8, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 13, fontWeight: 500 }}>{err}</div>}
      {loading && <div style={{ padding: 40, textAlign: "center", color: C.mute }}><Spinner /> Analizando tus productos…</div>}

      {/* ── KPI CARDS ── */}
      {!loading && rows.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(4, 1fr)", gap: 10 }}>
          {[
            { label: "Ingreso total", value: fmtMoney(totals.revenue), color: C.accent },
            { label: "Costo total", value: fmtMoney(totals.cost), color: C.mid },
            { label: "Ganancia bruta", value: fmtMoney(totals.profit), color: C.green },
            { label: "Margen global", value: fmtPct(totals.margin) + "%", color: totals.margin >= 30 ? C.green : totals.margin >= 15 ? C.amber : C.red },
          ].map(kpi => (
            <div key={kpi.label} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "12px 14px", boxShadow: C.sh }}>
              <div style={{ fontSize: 10, fontWeight: 600, color: C.mute, textTransform: "uppercase", letterSpacing: ".04em" }}>{kpi.label}</div>
              <div style={{ fontSize: mob ? 17 : 20, fontWeight: 800, color: kpi.color, marginTop: 2, fontFamily: C.mono }}>{kpi.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── VIEW TABS ── */}
      {!loading && rows.length > 0 && (
        <div style={{ display: "flex", gap: 0, borderBottom: `2px solid ${C.border}` }}>
          {VIEW_TABS.map(t => (
            <button key={t.key} onClick={() => setView(t.key)} style={{
              padding: mob ? "8px 10px" : "10px 18px", fontSize: 13, fontWeight: view === t.key ? 700 : 500,
              color: view === t.key ? C.accent : C.mute, background: view === t.key ? C.accentBg : "none",
              border: "none", cursor: "pointer", borderBottom: view === t.key ? `2px solid ${C.accent}` : "2px solid transparent",
              marginBottom: -2, fontFamily: C.font, borderRadius: "6px 6px 0 0", transition: "all .15s",
            }}>{t.icon} {t.label}</button>
          ))}
        </div>
      )}

      {/* ══════════ TAB: PARETO ══════════ */}
      {view === "pareto" && !loading && rows.length > 0 && (<>
        {/* Explanation box */}
        <div style={{ background: C.accentBg, border: `1px solid ${C.accent}30`, borderRadius: C.r, padding: mob ? "12px" : "14px 18px", fontSize: 13, lineHeight: 1.6 }}>
          <b>¿Qué es el análisis ABC?</b> Ordena tus productos de mayor a menor según {criterionLabel} y los clasifica en 3 grupos:
          los <b style={{ color: ABC_CONFIG.A.color }}>⭐ Estrella (A)</b> son pocos pero generan la mayor parte de tus ventas,
          los <b style={{ color: ABC_CONFIG.B.color }}>📦 Importantes (B)</b> complementan,
          y los <b style={{ color: ABC_CONFIG.C.color }}>📋 Cola (C)</b> aportan poco.
        </div>

        {/* Class summary cards */}
        {classSummary.A && (
          <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "repeat(3, 1fr)", gap: 12 }}>
            {(["A", "B", "C"] as const).map(cls => {
              const cfg = ABC_CONFIG[cls];
              const data = classSummary[cls];
              if (!data) return null;
              return (
                <div key={cls} style={{ background: cfg.bg, border: `1px solid ${cfg.bd}`, borderRadius: C.r, padding: "16px", boxShadow: C.sh }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <span style={{ fontSize: 22 }}>{cfg.icon}</span>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 800, color: cfg.color }}>Clase {cls} — {cfg.label}</div>
                      <div style={{ fontSize: 11, color: C.mid }}>{data.count} productos ({data.pct_products}% del catálogo)</div>
                    </div>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
                    <div>
                      <div style={{ fontSize: 10, color: C.mute, fontWeight: 600 }}>INGRESO</div>
                      <div style={{ fontSize: 16, fontWeight: 800 }}>{fmtMoney(data.revenue)}</div>
                      <div style={{ fontSize: 10, color: C.mute }}>{data.pct_revenue}% del total</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: C.mute, fontWeight: 600 }}>EN STOCK</div>
                      <div style={{ fontSize: 16, fontWeight: 800 }}>{fmtMoney(data.stock_value)}</div>
                      <div style={{ fontSize: 10, color: C.mute }}>invertido</div>
                    </div>
                  </div>
                  <div style={{ fontSize: 11, color: C.mid, lineHeight: 1.5, borderTop: `1px solid ${cfg.bd}`, paddingTop: 8 }}>
                    💡 {cfg.advice}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Pareto curve */}
        {rows.length > 5 && (
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: mob ? "10px 6px" : "14px 12px", boxShadow: C.sh }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, marginBottom: 8, paddingLeft: 8 }}>
              📈 Curva de Pareto — {criterionLabel} acumulado
            </div>
            <div style={{ overflowX: "auto" }}>
              <svg width={chartW} height={chartH} style={{ display: "block" }}>
                {[0, 25, 50, 75, 100].map(v => {
                  const y = pT + plotH * (1 - v / 100);
                  return (<g key={v}><line x1={pL} x2={chartW - pR} y1={y} y2={y} stroke="#E4E4E7" strokeWidth={.5} /><text x={pL - 4} y={y + 3} fontSize={9} fill={C.mute} textAnchor="end">{v}%</text></g>);
                })}
                <line x1={pL} x2={chartW - pR} y1={pT + plotH * .2} y2={pT + plotH * .2} stroke={C.green} strokeWidth={1} strokeDasharray="4,3" opacity={.5} />
                <line x1={pL} x2={chartW - pR} y1={pT + plotH * .05} y2={pT + plotH * .05} stroke={C.amber} strokeWidth={1} strokeDasharray="4,3" opacity={.5} />
                {rows.map((r, i) => {
                  const barX = pL + (i / n) * plotW;
                  const barW = Math.max(1, plotW / n - 0.5);
                  const maxContrib = Math.max(...rows.map(x => parseFloat(x.contribution_pct)), 1);
                  const barH = (parseFloat(r.contribution_pct) / maxContrib) * plotH;
                  const cumY = pT + plotH * (1 - parseFloat(r.cumulative_pct) / 100);
                  const cfg = ABC_CONFIG[r.abc_class];
                  return (<g key={i}>
                    <rect x={barX} y={pT + plotH - barH} width={barW} height={barH} fill={cfg.color} opacity={.25} rx={1} />
                    {i > 0 && <line x1={pL + ((i - 1) / n) * plotW + Math.max(1, plotW / n - .5) / 2} y1={pT + plotH * (1 - parseFloat(rows[i - 1].cumulative_pct) / 100)} x2={barX + barW / 2} y2={cumY} stroke={C.accent} strokeWidth={2} />}
                    <circle cx={barX + barW / 2} cy={cumY} r={1.5} fill={C.accent} />
                  </g>);
                })}
                <text x={chartW - pR - 2} y={pT + plotH * .2 - 4} fontSize={9} fill={C.green} textAnchor="end" fontWeight="600">80% — Clase A</text>
                <text x={chartW - pR - 2} y={pT + plotH * .05 - 4} fontSize={9} fill={C.amber} textAnchor="end" fontWeight="600">95% — Clase B</text>
              </svg>
            </div>
            <div style={{ fontSize: 10, color: C.mute, paddingLeft: 8, marginTop: 4 }}>Cada barra = 1 producto · La línea azul = % acumulado</div>
          </div>
        )}

        {/* Filter tabs A/B/C */}
        <div style={{ display: "flex", gap: 0, borderBottom: `2px solid ${C.border}` }}>
          {([
            { key: "all" as const, label: `Todos (${rows.length})` },
            { key: "A" as const, label: `⭐ A (${classSummary.A?.count || 0})` },
            { key: "B" as const, label: `📦 B (${classSummary.B?.count || 0})` },
            { key: "C" as const, label: `📋 C (${classSummary.C?.count || 0})` },
          ]).map(t => (
            <button key={t.key} onClick={() => setFilter(t.key)} style={{
              padding: mob ? "8px 10px" : "8px 16px", fontSize: 12, fontWeight: filter === t.key ? 700 : 500,
              color: filter === t.key ? C.accent : C.mute, background: "none", border: "none", cursor: "pointer",
              borderBottom: filter === t.key ? `2px solid ${C.accent}` : "2px solid transparent", marginBottom: -2, fontFamily: C.font,
            }}>{t.label}</button>
          ))}
        </div>

        {/* Product table (Pareto) */}
        {filtered.length > 0 && (
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", boxShadow: C.sh }}>
            {!mob && (
              <div style={{ display: "grid", gridTemplateColumns: "40px 1fr 50px 80px 80px 65px 70px 70px", columnGap: 6, padding: "8px 16px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".06em" }}>
                <div>#</div><div>Producto</div><div style={{ textAlign: "center" }}>Clase</div><div style={{ textAlign: "right" }}>Ingreso</div><div style={{ textAlign: "right" }}>Ganancia</div><div style={{ textAlign: "right" }}>Margen</div><div style={{ textAlign: "right" }}>Stock</div><div style={{ textAlign: "right" }}>% acum.</div>
              </div>
            )}
            {filtered.map((r, i) => {
              const cfg = ABC_CONFIG[r.abc_class] || ABC_CONFIG.C;
              const maxRev = parseFloat(rows[0]?.revenue || "1") || 1;
              const barPct = (parseFloat(r.revenue) / maxRev) * 100;
              if (mob) return (
                <div key={r.product_id} style={{ padding: "10px 12px", borderBottom: i < filtered.length - 1 ? `1px solid ${C.border}` : "none", borderLeft: `3px solid ${cfg.color}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                    <div style={{ flex: 1 }}><span style={{ fontSize: 12, marginRight: 4 }}>{cfg.icon}</span><span style={{ fontWeight: 600, fontSize: 13 }}>{r.product_name}</span></div>
                    <span style={{ fontSize: 11, fontWeight: 700, color: cfg.color, background: cfg.bg, padding: "1px 6px", borderRadius: 4, border: `1px solid ${cfg.bd}` }}>{r.abc_class}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.mid, marginTop: 4 }}>
                    <span>Ingreso: <b style={{ color: C.text }}>{fmtMoney(r.revenue)}</b></span>
                    <span>Margen: <b>{r.margin_pct}%</b></span>
                  </div>
                  <div style={{ height: 3, borderRadius: 2, background: "#E4E4E7", marginTop: 6, overflow: "hidden" }}><div style={{ height: "100%", width: `${barPct}%`, background: cfg.color, borderRadius: 2, opacity: .5 }} /></div>
                  <div style={{ fontSize: 10, color: C.mute, marginTop: 3 }}>
                    {r.contribution_pct}% del total · Acumulado: {r.cumulative_pct}% · Stock: {fmt(r.current_stock)}
                    {r.is_virtual_stock && <span title="Stock calculado a partir de los ingredientes de la receta. El producto se 'arma' al vender." style={{ marginLeft: 4, fontSize: 9, padding: "1px 4px", background: "#EEF2FF", color: "#4F46E5", borderRadius: 3, fontWeight: 600 }}>vía receta</span>}
                  </div>
                </div>
              );
              return (
                <div key={r.product_id} className="abc-row" style={{ display: "grid", gridTemplateColumns: "40px 1fr 50px 80px 80px 65px 70px 70px", columnGap: 6, padding: "8px 16px", borderBottom: i < filtered.length - 1 ? `1px solid ${C.border}` : "none", alignItems: "center", borderLeft: `3px solid ${cfg.color}`, transition: "background .1s" }}>
                  <div style={{ fontSize: 12, color: C.mute, textAlign: "center" }}>{r.rank}</div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 12 }}>{r.product_name}</div>
                    <div style={{ fontSize: 10, color: C.mute }}>{r.category}{r.sku && ` · ${r.sku}`}</div>
                    <div style={{ height: 3, borderRadius: 2, background: "#E4E4E7", marginTop: 3, overflow: "hidden", maxWidth: 180 }}><div style={{ height: "100%", width: `${barPct}%`, background: cfg.color, borderRadius: 2, opacity: .4 }} /></div>
                  </div>
                  <div style={{ textAlign: "center" }}><span style={{ fontSize: 11, fontWeight: 700, color: cfg.color, background: cfg.bg, padding: "2px 8px", borderRadius: 4, border: `1px solid ${cfg.bd}` }}>{r.abc_class}</span></div>
                  <div style={{ textAlign: "right", fontWeight: 600, fontSize: 12 }}>{fmtMoney(r.revenue)}</div>
                  <div style={{ textAlign: "right", fontSize: 12, color: parseFloat(r.profit) > 0 ? C.green : C.red }}>{fmtMoney(r.profit)}</div>
                  <div style={{ textAlign: "right", fontSize: 12, color: C.mid }}>{r.margin_pct}%</div>
                  <div style={{ textAlign: "right", fontSize: 12 }}>
                    {fmt(r.current_stock)}
                    {r.is_virtual_stock && <span title="Stock calculado a partir de los ingredientes de la receta. El producto se 'arma' al vender." style={{ display: "inline-block", marginLeft: 4, fontSize: 9, padding: "1px 4px", background: "#EEF2FF", color: "#4F46E5", borderRadius: 3, fontWeight: 600 }}>vía receta</span>}
                  </div>
                  <div style={{ textAlign: "right", fontSize: 11, color: C.mute }}>{r.cumulative_pct}%</div>
                </div>
              );
            })}
          </div>
        )}
      </>)}

      {/* ══════════ TAB: TOP N ══════════ */}
      {view === "topn" && !loading && rows.length > 0 && (<>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <select value={topSort} onChange={e => setTopSort(e.target.value)} style={{ ...iS, cursor: "pointer" }}>
            <option value="revenue">Ordenar por ingreso</option>
            <option value="profit">Ordenar por ganancia</option>
            <option value="qty">Ordenar por cantidad</option>
          </select>
          <div style={{ display: "flex", gap: 0, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
            {[10, 20, 50].map(lim => (
              <button key={lim} onClick={() => setTopLimit(lim)} style={{
                padding: "7px 12px", fontSize: 12, fontWeight: topLimit === lim ? 700 : 500,
                background: topLimit === lim ? C.accent : C.surface, color: topLimit === lim ? "#fff" : C.mid,
                border: "none", cursor: "pointer", fontFamily: C.font,
              }}>Top {lim}</button>
            ))}
          </div>
        </div>

        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", boxShadow: C.sh }}>
          {!mob && (
            <div style={{ display: "grid", gridTemplateColumns: "44px 1fr 90px 90px 80px 65px", columnGap: 6, padding: "8px 16px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".06em" }}>
              <div>#</div><div>Producto</div><div style={{ textAlign: "right" }}>Ingreso</div><div style={{ textAlign: "right" }}>Ganancia</div><div style={{ textAlign: "right" }}>Cantidad</div><div style={{ textAlign: "right" }}>Margen</div>
            </div>
          )}
          {topSorted.map((r, i) => {
            const cfg = ABC_CONFIG[r.abc_class] || ABC_CONFIG.C;
            const maxVal = toNum(topSorted[0]?.[topSort as keyof Row] as string) || 1;
            const barPct = (toNum(r[topSort as keyof Row] as string) / maxVal) * 100;

            if (mob) return (
              <div key={r.product_id} style={{ padding: "10px 12px", borderBottom: i < topSorted.length - 1 ? `1px solid ${C.border}` : "none", borderLeft: `3px solid ${cfg.color}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 18, width: 28, textAlign: "center" }}>{i < 3 ? MEDALS[i] : <span style={{ fontSize: 13, color: C.mute, fontWeight: 700 }}>#{i + 1}</span>}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{r.product_name}</div>
                    <div style={{ fontSize: 11, color: C.mute }}>{r.category}</div>
                  </div>
                  <span style={{ fontSize: 11, fontWeight: 700, color: cfg.color, background: cfg.bg, padding: "1px 6px", borderRadius: 4, border: `1px solid ${cfg.bd}` }}>{r.abc_class}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.mid, marginTop: 6 }}>
                  <span>Ingreso: <b style={{ color: C.text }}>{fmtMoney(r.revenue)}</b></span>
                  <span>Ganancia: <b style={{ color: C.green }}>{fmtMoney(r.profit)}</b></span>
                </div>
                <div style={{ height: 4, borderRadius: 2, background: "#E4E4E7", marginTop: 6, overflow: "hidden" }}><div style={{ height: "100%", width: `${barPct}%`, background: C.accent, borderRadius: 2 }} /></div>
              </div>
            );

            return (
              <div key={r.product_id} className="abc-row" style={{ display: "grid", gridTemplateColumns: "44px 1fr 90px 90px 80px 65px", columnGap: 6, padding: "8px 16px", borderBottom: i < topSorted.length - 1 ? `1px solid ${C.border}` : "none", alignItems: "center", borderLeft: `3px solid ${cfg.color}`, transition: "background .1s" }}>
                <div style={{ textAlign: "center" }}>
                  {i < 3 ? <span style={{ fontSize: 18 }}>{MEDALS[i]}</span> : <span style={{ fontSize: 13, color: C.mute, fontWeight: 700 }}>#{i + 1}</span>}
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12 }}>{r.product_name}</div>
                  <div style={{ fontSize: 10, color: C.mute }}>{r.category}{r.sku && ` · ${r.sku}`}</div>
                  <div style={{ height: 3, borderRadius: 2, background: "#E4E4E7", marginTop: 3, overflow: "hidden", maxWidth: 200 }}><div style={{ height: "100%", width: `${barPct}%`, background: C.accent, borderRadius: 2, opacity: .6 }} /></div>
                </div>
                <div style={{ textAlign: "right", fontWeight: 700, fontSize: 13 }}>{fmtMoney(r.revenue)}</div>
                <div style={{ textAlign: "right", fontSize: 12, color: parseFloat(r.profit) > 0 ? C.green : C.red }}>{fmtMoney(r.profit)}</div>
                <div style={{ textAlign: "right", fontSize: 12 }}>{fmt(r.qty)}</div>
                <div style={{ textAlign: "right", fontSize: 12, color: parseFloat(r.margin_pct) >= 30 ? C.green : parseFloat(r.margin_pct) >= 15 ? C.amber : C.red }}>{r.margin_pct}%</div>
              </div>
            );
          })}
        </div>
      </>)}

      {/* ══════════ TAB: POR CATEGORÍA ══════════ */}
      {view === "category" && !loading && rows.length > 0 && (<>
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", boxShadow: C.sh }}>
          {!mob && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 60px 100px 100px 100px 65px", columnGap: 6, padding: "8px 16px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".06em" }}>
              <div>Categoría</div><div style={{ textAlign: "center" }}>Prods.</div><div style={{ textAlign: "right" }}>Ingreso</div><div style={{ textAlign: "right" }}>Costo</div><div style={{ textAlign: "right" }}>Ganancia</div><div style={{ textAlign: "right" }}>Margen</div>
            </div>
          )}
          {byCategory.map((cat, i) => {
            const margin = cat.revenue > 0 ? (cat.profit / cat.revenue) * 100 : 0;
            const maxRev = byCategory[0]?.revenue || 1;
            const barPct = (cat.revenue / maxRev) * 100;
            const marginColor = margin >= 30 ? C.green : margin >= 15 ? C.amber : C.red;

            if (mob) return (
              <div key={cat.category} style={{ padding: "12px", borderBottom: i < byCategory.length - 1 ? `1px solid ${C.border}` : "none" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 13 }}>{cat.category}</div>
                    <div style={{ fontSize: 11, color: C.mute }}>{cat.count} productos · {fmt(cat.qty)} unidades</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 700, fontSize: 14 }}>{fmtMoney(cat.revenue)}</div>
                    <div style={{ fontSize: 11, color: marginColor, fontWeight: 600 }}>{fmtPct(margin)}% margen</div>
                  </div>
                </div>
                <div style={{ height: 4, borderRadius: 2, background: "#E4E4E7", marginTop: 8, overflow: "hidden" }}><div style={{ height: "100%", width: `${barPct}%`, background: C.accent, borderRadius: 2, opacity: .5 }} /></div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: C.mid, marginTop: 4 }}>
                  <span>Costo: {fmtMoney(cat.cost)}</span>
                  <span>Ganancia: <b style={{ color: C.green }}>{fmtMoney(cat.profit)}</b></span>
                </div>
              </div>
            );

            return (
              <div key={cat.category} className="abc-row" style={{ display: "grid", gridTemplateColumns: "1fr 60px 100px 100px 100px 65px", columnGap: 6, padding: "10px 16px", borderBottom: i < byCategory.length - 1 ? `1px solid ${C.border}` : "none", alignItems: "center", transition: "background .1s" }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{cat.category}</div>
                  <div style={{ height: 3, borderRadius: 2, background: "#E4E4E7", marginTop: 4, overflow: "hidden", maxWidth: 200 }}><div style={{ height: "100%", width: `${barPct}%`, background: C.accent, borderRadius: 2, opacity: .4 }} /></div>
                </div>
                <div style={{ textAlign: "center", fontSize: 12, color: C.mid }}>{cat.count}</div>
                <div style={{ textAlign: "right", fontWeight: 700, fontSize: 13 }}>{fmtMoney(cat.revenue)}</div>
                <div style={{ textAlign: "right", fontSize: 12, color: C.mid }}>{fmtMoney(cat.cost)}</div>
                <div style={{ textAlign: "right", fontSize: 12, color: C.green, fontWeight: 600 }}>{fmtMoney(cat.profit)}</div>
                <div style={{ textAlign: "right", fontSize: 12, fontWeight: 600, color: marginColor }}>{fmtPct(margin)}%</div>
              </div>
            );
          })}

          {/* Total row */}
          <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "1fr 60px 100px 100px 100px 65px", columnGap: 6, padding: "10px 16px", background: C.bg, borderTop: `2px solid ${C.border}`, fontWeight: 700, fontSize: 13 }}>
            {mob ? (<>
              <div>TOTAL</div>
              <div style={{ textAlign: "right" }}>{fmtMoney(totals.revenue)}</div>
            </>) : (<>
              <div>TOTAL</div>
              <div style={{ textAlign: "center" }}>{rows.length}</div>
              <div style={{ textAlign: "right" }}>{fmtMoney(totals.revenue)}</div>
              <div style={{ textAlign: "right", color: C.mid }}>{fmtMoney(totals.cost)}</div>
              <div style={{ textAlign: "right", color: C.green }}>{fmtMoney(totals.profit)}</div>
              <div style={{ textAlign: "right", color: totals.margin >= 30 ? C.green : totals.margin >= 15 ? C.amber : C.red }}>{fmtPct(totals.margin)}%</div>
            </>)}
          </div>
        </div>
      </>)}

      {/* ── EMPTY STATE ── */}
      {!loading && rows.length === 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "48px 20px", textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>📊</div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>Sin datos de ventas</div>
          <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>Necesitas ventas registradas para generar el análisis ABC.</div>
        </div>
      )}

      <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}} .abc-row:hover{background:${C.accentBg}!important}`}</style>
    </div>
  );
}
