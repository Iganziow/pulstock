"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";




const fmt = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "0" : Math.round(n).toLocaleString("es-CL"); };
const fmtMoney = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL"); };
const fmtPct = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "0%" : n.toFixed(1) + "%"; };

const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (d: number) => { const t = new Date(); t.setDate(t.getDate() - d); return t.toISOString().slice(0, 10); };

type KPIs = { total_revenue: string; total_cost: string; gross_profit: string; margin_pct: string; sale_count: number; items_sold: string; avg_ticket: string };
type Daily = { date: string; revenue: string; cost: string; count: number };
type ByCat = { category: string; revenue: string; cost: string; qty: string; profit: string };

export default function SalesSummaryPage() {
  const mob = useIsMobile();
  const [loading, setLoading] = useState(true);
  const [kpis, setKpis] = useState<KPIs | null>(null);
  const [daily, setDaily] = useState<Daily[]>([]);
  const [byCat, setByCat] = useState<ByCat[]>([]);
  const [dateFrom, setDateFrom] = useState(daysAgo(30));
  const [dateTo, setDateTo] = useState(today());
  const [err, setErr] = useState("");

  const load = async (df: string, dt: string) => {
    setLoading(true);
    try {
      setErr("");
      const data = await apiFetch(`/reports/sales-summary/?date_from=${df}&date_to=${dt}`);
      setKpis(data?.kpis || null);
      setDaily(data?.daily || []);
      setByCat(data?.by_category || []);
    } catch (e: any) { setErr(e?.message || "Error al cargar el reporte"); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(dateFrom, dateTo); }, []);

  const iS: React.CSSProperties = { padding: "7px 10px", border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 13, fontFamily: C.font, background: C.surface, outline: "none" };

  // Quick date presets
  const presets = [
    { label: "Hoy", fn: () => { setDateFrom(today()); setDateTo(today()); load(today(), today()); } },
    { label: "7 días", fn: () => { const d = daysAgo(7); setDateFrom(d); setDateTo(today()); load(d, today()); } },
    { label: "30 días", fn: () => { const d = daysAgo(30); setDateFrom(d); setDateTo(today()); load(d, today()); } },
    { label: "90 días", fn: () => { const d = daysAgo(90); setDateFrom(d); setDateTo(today()); load(d, today()); } },
  ];

  // Mini bar chart
  const maxRev = Math.max(...daily.map(d => parseFloat(d.revenue) || 0), 1);
  const chartH = 100, barW = Math.max(4, Math.min(18, (mob ? 320 : 600) / Math.max(daily.length, 1) - 2));

  // Category totals for pie-like bars
  const catTotalRev = byCat.reduce((s, c) => s + parseFloat(c.revenue || "0"), 0) || 1;

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "14px 10px" : "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>

      <div>
        <Link href="/dashboard/reports" style={{ fontSize: 12, color: C.mute, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4, marginBottom: 8 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg> Reportes
        </Link>
        <h1 style={{ margin: 0, fontSize: mob ? 19 : 23, fontWeight: 800, letterSpacing: "-.04em" }}>💰 Ventas del período</h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: C.mute }}>Resumen de todo lo que vendiste en el rango seleccionado</p>
      </div>

      {err && <div style={{margin:"0 0 16px",padding:"10px 16px",borderRadius:8,background:C.redBg,border:`1px solid ${C.redBd}`,color:C.red,fontSize:13,fontWeight:500}}>{err}</div>}

      {/* Date filters */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={iS} />
        <span style={{ fontSize: 12, color: C.mute }}>a</span>
        <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={iS} />
        <button onClick={() => load(dateFrom, dateTo)} style={{ ...iS, background: C.accent, color: "#fff", border: "none", cursor: "pointer", fontWeight: 600, padding: "7px 14px" }}>Consultar</button>
        <div style={{ display: "flex", gap: 4, marginLeft: mob ? 0 : "auto" }}>
          {presets.map(p => (
            <button key={p.label} onClick={p.fn} style={{ ...iS, fontSize: 11, padding: "5px 10px", cursor: "pointer", color: C.mid }}>{p.label}</button>
          ))}
        </div>
      </div>

      {loading && <div style={{ padding: 40, textAlign: "center", color: C.mute }}><Spinner /> Cargando…</div>}

      {/* KPI Cards */}
      {kpis && !loading && (
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(4, 1fr)", gap: 10 }}>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "14px 16px", boxShadow: C.sh }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Total vendido</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: C.green, marginTop: 4 }}>{fmtMoney(kpis.total_revenue)}</div>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{kpis.sale_count} venta{kpis.sale_count !== 1 ? "s" : ""}</div>
          </div>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "14px 16px", boxShadow: C.sh }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Ganancia bruta</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: C.accent, marginTop: 4 }}>{fmtMoney(kpis.gross_profit)}</div>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>Margen: {fmtPct(kpis.margin_pct)}</div>
          </div>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "14px 16px", boxShadow: C.sh }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Ticket promedio</div>
            <div style={{ fontSize: 24, fontWeight: 800, marginTop: 4 }}>{fmtMoney(kpis.avg_ticket)}</div>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>por venta</div>
          </div>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "14px 16px", boxShadow: C.sh, gridColumn: mob ? "1 / -1" : "auto" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Unidades vendidas</div>
            <div style={{ fontSize: 24, fontWeight: 800, marginTop: 4 }}>{fmt(kpis.items_sold)}</div>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>productos despachados</div>
          </div>
        </div>
      )}

      {/* Daily Chart */}
      {daily.length > 0 && !loading && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: mob ? "12px" : "16px", boxShadow: C.sh }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.mid, marginBottom: 10 }}>📈 Venta por día</div>
          <div style={{ overflowX: "auto" }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 2, minWidth: daily.length * (barW + 2), height: chartH }}>
              {daily.map((d, i) => {
                const rev = parseFloat(d.revenue) || 0;
                const h = Math.max(2, (rev / maxRev) * chartH);
                const dayLabel = d.date.slice(5);
                return (
                  <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: "0 0 auto" }} title={`${dayLabel}: ${fmtMoney(rev)} (${d.count} ventas)`}>
                    <div style={{ width: barW, height: h, background: C.green, borderRadius: "3px 3px 0 0", minHeight: 2 }} />
                    {(daily.length <= 31 && i % Math.max(1, Math.floor(daily.length / 10)) === 0) && (
                      <div style={{ fontSize: 8, color: C.mute, marginTop: 2, whiteSpace: "nowrap" }}>{dayLabel}</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* By Category */}
      {byCat.length > 0 && !loading && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: mob ? "12px" : "16px", boxShadow: C.sh }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.mid, marginBottom: 10 }}>📦 Venta por categoría</div>
          {byCat.map((c, i) => {
            const rev = parseFloat(c.revenue || "0");
            const pct = (rev / catTotalRev) * 100;
            const profit = parseFloat(c.profit || "0");
            return (
              <div key={i} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 3 }}>
                  <span style={{ fontWeight: 600 }}>{c.category}</span>
                  <span style={{ fontWeight: 700 }}>{fmtMoney(rev)}</span>
                </div>
                <div style={{ height: 6, borderRadius: 3, background: "#E4E4E7", overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${pct}%`, background: C.accent, borderRadius: 3, transition: "width .3s" }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.mute, marginTop: 2 }}>
                  <span>{fmt(c.qty)} unidades</span>
                  <span>Ganancia: {fmtMoney(profit)} ({pct.toFixed(0)}% del total)</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Empty */}
      {!loading && (!kpis || parseFloat(kpis.total_revenue) === 0) && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "48px 20px", textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>📋</div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>Sin ventas en este período</div>
          <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>Prueba con un rango de fechas diferente.</div>
        </div>
      )}

      <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}