"use client";
import Link from "next/link";
import { useEffect, useState, useMemo } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";


function useIsMobile() {
  const [m, setM] = useState(false);
  useEffect(() => {
    const fn = () => setM(window.innerWidth < 768);
    fn(); window.addEventListener("resize", fn);
    return () => window.removeEventListener("resize", fn);
  }, []);
  return m;
}

function Spinner() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ animation: "spin .7s linear infinite", display: "inline-block" }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" /></svg>;
}

const fmt = (v: number | string) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "—" : Math.round(n).toLocaleString("es-CL");
};
const fmtMoney = (v: number | string) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "—" : "$" + Math.round(n).toLocaleString("es-CL");
};

// ── ICONS
const ICONS: Record<string, React.ReactNode> = {
  sales:    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>,
  star:     <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>,
  trending: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>,
  alert:    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
  box:      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>,
  ghost:    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 10h.01M15 10h.01M12 2a8 8 0 0 0-8 8v12l3-3 2.5 2.5L12 19l2.5 2.5L17 19l3 3V10a8 8 0 0 0-8-8z"/></svg>,
  clipboard:<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg>,
  diff:     <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>,
  eye:      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  pie:      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>,
  shuffle:  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="4" y1="4" x2="9" y2="9"/></svg>,
  search:   <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>,
  arrow:    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>,
  print:    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>,
  brain:    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-1.04-4.79A3 3 0 0 1 4.5 11a3 3 0 0 1 1.5-2.6A2.5 2.5 0 0 1 9.5 2z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 1.04-4.79A3 3 0 0 0 19.5 11a3 3 0 0 0-1.5-2.6A2.5 2.5 0 0 0 14.5 2z"/></svg>,
};

type QuickStat = { label: string; value: string; trend?: string; trendUp?: boolean };

type ReportDef = {
  href: string;
  icon: string;
  label: string;
  desc: string;
  color: string;
  colorBg: string;
  colorBd: string;
  tag?: { text: string; icon: React.ReactNode };
  category: string;
  statsKey?: string; // key in quickStats
};

// Quick stats fetched from API to show on cards
type QuickStats = {
  sales_today?: number;
  stock_value?: number;
  abc_a_pct?: number;
  forecast_alerts?: number;
};

const SECTIONS: {
  key: string; icon: string; label: string;
  color: string; colorBg: string; colorBd: string;
  desc: string; reports: ReportDef[];
}[] = [
  {
    key: "ventas", icon: "💰", label: "Ventas y rentabilidad",
    color: C.green, colorBg: C.greenBg, colorBd: C.greenBd,
    desc: "Analiza cuánto vendiste, qué te deja ganancia y dónde se pierden ingresos",
    reports: [
      {
        href: "/dashboard/reports/sales-summary", icon: "sales", label: "Resumen de ventas",
        desc: "Total vendido, margen bruto, ticket promedio y desglose por día.",
        color: C.green, colorBg: C.greenBg, colorBd: C.greenBd,
        tag: { text: "Diario", icon: null }, category: "ventas", statsKey: "sales_today",
      },
      {
        href: "/dashboard/reports/abc-analysis", icon: "pie", label: "Análisis ABC",
        desc: "Clasificación Pareto, ranking de productos y rentabilidad por categoría.",
        color: C.accent, colorBg: C.accentBg, colorBd: C.accentBd,
        tag: { text: "IA", icon: <span style={{ display: "inline-flex" }}>{ICONS.brain}</span> }, category: "ventas", statsKey: "abc_a_pct",
      },
      {
        href: "/dashboard/reports/losses", icon: "alert", label: "Mermas y pérdidas",
        desc: "Pérdidas por vencimiento, daño, robo o consumo interno.",
        color: C.red, colorBg: C.redBg, colorBd: C.redBd, category: "ventas",
      },
    ],
  },
  {
    key: "inventario", icon: "📦", label: "Inventario y stock",
    color: "#7C3AED", colorBg: "#F5F3FF", colorBd: "#DDD6FE",
    desc: "Conoce el valor de tu stock, detecta productos sin movimiento y haz conteos físicos",
    reports: [
      {
        href: "/dashboard/reports/stock-valued", icon: "box", label: "Stock valorizado",
        desc: "Cuánto capital tienes en inventario, desglosado por bodega.",
        color: "#7C3AED", colorBg: "#F5F3FF", colorBd: "#DDD6FE", category: "inventario", statsKey: "stock_value",
      },
      {
        href: "/dashboard/reports/inventory-health", icon: "trending", label: "Salud del inventario",
        desc: "Score general, stock sin rotación, descuadres y sobre-stock.",
        color: C.green, colorBg: C.greenBg, colorBd: C.greenBd, category: "inventario",
      },
      {
        href: "/dashboard/reports/toma-fisica", icon: "clipboard", label: "Toma física",
        desc: "Conteo físico y comparación contra sistema en un solo flujo.",
        color: "#7C3AED", colorBg: "#F5F3FF", colorBd: "#DDD6FE",
        tag: { text: "Imprimible", icon: <span style={{ display: "inline-flex" }}>{ICONS.print}</span> }, category: "inventario",
      },
    ],
  },
  {
    key: "analisis", icon: "🔍", label: "Análisis inteligente",
    color: C.accent, colorBg: C.accentBg, colorBd: C.accentBd,
    desc: "Audita movimientos y anticipa la demanda con modelos predictivos",
    reports: [
      {
        href: "/dashboard/reports/audit-trail", icon: "eye", label: "Auditoría de movimientos",
        desc: "Bitácora completa: quién movió qué, cuándo y cuánto.",
        color: "#18181B", colorBg: "#F4F4F5", colorBd: "#D4D4D8", category: "analisis",
      },
      {
        href: "/dashboard/forecast", icon: "brain", label: "Pronóstico de demanda",
        desc: "Modelos predictivos, alertas de quiebre y sugerencias de compra.",
        color: C.accent, colorBg: C.accentBg, colorBd: C.accentBd,
        tag: { text: "IA", icon: <span style={{ display: "inline-flex" }}>{ICONS.brain}</span> }, category: "analisis", statsKey: "forecast_alerts",
      },
    ],
  },
  {
    key: "operativo", icon: "🔧", label: "Operativo",
    color: C.mid, colorBg: "#F4F4F5", colorBd: "#D4D4D8",
    desc: "Documentos y herramientas para la operación diaria",
    reports: [
      {
        href: "/dashboard/reports/transfer-suggestion-sheet", icon: "shuffle", label: "Planilla de transferencia",
        desc: "Formato para reponer desde bodega central al punto de venta.",
        color: C.mid, colorBg: "#F4F4F5", colorBd: "#D4D4D8",
        tag: { text: "Imprimible", icon: <span style={{ display: "inline-flex" }}>{ICONS.print}</span> }, category: "operativo",
      },
    ],
  },
];

const ALL_REPORTS: ReportDef[] = SECTIONS.flatMap(s => s.reports);

function StatPill({ value, color }: { value: string; color: string }) {
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "3px 8px", borderRadius: 99, background: color + "18",
      fontSize: 11, fontWeight: 700, color, fontFamily: C.mono,
      letterSpacing: "-.01em",
    }}>
      {value}
    </div>
  );
}

function ReportCard({ r, stat, mob }: { r: ReportDef; stat?: string; mob: boolean }) {
  return (
    <Link href={r.href} className="rcard" style={{
      background: C.surface, border: `1.5px solid ${C.border}`,
      borderRadius: 10, padding: mob ? "14px" : "16px",
      textDecoration: "none", color: C.text,
      display: "flex", flexDirection: "column", gap: 10,
      boxShadow: C.sh, position: "relative", overflow: "hidden",
    }}>
      {/* color accent bar */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 3,
        background: r.color, borderRadius: "10px 10px 0 0", opacity: 0.7,
      }} />

      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <div style={{
          width: 38, height: 38, borderRadius: 10, background: r.colorBg,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, color: r.color,
          border: `1px solid ${r.colorBd}`,
        }}>
          {ICONS[r.icon] || ICONS.box}
        </div>

        {/* tag badge */}
        {r.tag && (
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            fontSize: 10, fontWeight: 700, padding: "3px 7px", borderRadius: 99,
            background: r.colorBg, color: r.color, border: `1px solid ${r.colorBd}`,
            textTransform: "uppercase", letterSpacing: ".04em", flexShrink: 0,
          }}>
            {r.tag.icon}
            {r.tag.text}
          </div>
        )}
      </div>

      <div>
        <div style={{ fontWeight: 700, fontSize: 13.5, color: C.text, marginBottom: 4, lineHeight: 1.3 }}>{r.label}</div>
        <div style={{ fontSize: 12, color: C.mute, lineHeight: 1.55 }}>{r.desc}</div>
      </div>

      {/* quick stat if available */}
      {stat && (
        <div style={{ marginTop: "auto", paddingTop: 6, borderTop: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <StatPill value={stat} color={r.color} />
          <span style={{ color: "#D4D4D8" }}>{ICONS.arrow}</span>
        </div>
      )}
      {!stat && (
        <div style={{ marginTop: "auto", display: "flex", justifyContent: "flex-end" }}>
          <span style={{ color: "#D4D4D8" }}>{ICONS.arrow}</span>
        </div>
      )}
    </Link>
  );
}

export default function ReportsHome() {
  const mob = useIsMobile();
  const [search, setSearch] = useState("");
  const [quickStats, setQuickStats] = useState<QuickStats>({});
  const [statsLoading, setStatsLoading] = useState(true);

  useEffect(() => {
    // Load quick preview stats
    const today = new Date().toISOString().slice(0, 10);
    const d30ago = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10);

    Promise.allSettled([
      apiFetch(`/reports/sales-summary/?date_from=${today}&date_to=${today}`),
      apiFetch(`/reports/stock-valued/`),
      apiFetch(`/reports/abc-analysis/?date_from=${d30ago}&date_to=${today}&criterion=revenue`),
      apiFetch(`/forecast/dashboard/`),
    ]).then(([salesR, stockR, abcR, forecastR]) => {
      const stats: QuickStats = {};

      if (salesR.status === "fulfilled" && salesR.value) {
        stats.sales_today = salesR.value.summary?.total_revenue ?? salesR.value.total_revenue;
      }
      if (stockR.status === "fulfilled" && stockR.value) {
        stats.stock_value = stockR.value.summary?.total_value ?? stockR.value.total_value;
      }
      if (abcR.status === "fulfilled" && abcR.value) {
        const summary = abcR.value.class_summary;
        if (summary?.A?.pct_products) {
          stats.abc_a_pct = parseFloat(summary.A.pct_products);
        }
      }
      if (forecastR.status === "fulfilled" && forecastR.value) {
        stats.forecast_alerts = forecastR.value.stockout_alerts ?? forecastR.value.alerts_count;
      }

      setQuickStats(stats);
    }).finally(() => setStatsLoading(false));
  }, []);

  const getQuickStat = (key?: string): string | undefined => {
    if (!key || statsLoading) return undefined;
    switch (key) {
      case "sales_today":
        return quickStats.sales_today != null ? fmtMoney(quickStats.sales_today) + " hoy" : undefined;
      case "stock_value":
        return quickStats.stock_value != null ? fmtMoney(quickStats.stock_value) : undefined;
      case "abc_a_pct":
        return quickStats.abc_a_pct != null ? `${quickStats.abc_a_pct.toFixed(0)}% son clase A` : undefined;
      case "forecast_alerts":
        return quickStats.forecast_alerts != null ? `${quickStats.forecast_alerts} alertas` : undefined;
      default: return undefined;
    }
  };

  const searchResults = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return null;
    return ALL_REPORTS.filter(r =>
      r.label.toLowerCase().includes(q) ||
      r.desc.toLowerCase().includes(q)
    );
  }, [search]);

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "14px 10px" : "24px 28px" }}>
      <style>{`
        @keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }
        .rcard { transition: border-color .15s, box-shadow .15s, transform .12s; }
        .rcard:hover { border-color: ${C.accentBd} !important; box-shadow: 0 6px 20px rgba(79,70,229,.10) !important; transform: translateY(-2px); }
        .rcard:active { transform: scale(0.99); }
        .srch:focus { border-color: ${C.accent} !important; box-shadow: 0 0 0 3px rgba(79,70,229,.08) !important; outline: none; }
        @keyframes fadeUp { from { opacity:0; transform:translateY(8px) } to { opacity:1; transform:none } }
        .sec-anim { animation: fadeUp .25s ease both; }
      `}</style>

      {/* Header */}
      <div style={{ marginBottom: 22 }}>
        <h1 style={{ margin: 0, fontSize: mob ? 20 : 24, fontWeight: 800, letterSpacing: "-.04em" }}>
          Reportes
        </h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: C.mute }}>
          {ALL_REPORTS.length} informes para tomar mejores decisiones sobre tu negocio
        </p>
      </div>

      {/* Búsqueda */}
      <div style={{ position: "relative", maxWidth: 380, marginBottom: 28 }}>
        <span style={{ position: "absolute", left: 11, top: "50%", transform: "translateY(-50%)", color: C.mute, pointerEvents: "none", display: "flex" }}>
          {ICONS.search}
        </span>
        <input
          className="srch"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Buscar reporte…"
          style={{
            width: "100%", padding: "10px 34px 10px 34px",
            border: `1.5px solid ${C.border}`, borderRadius: 9,
            fontSize: 13, fontFamily: C.font, background: C.surface, color: C.text,
            transition: "border-color .15s, box-shadow .15s", boxSizing: "border-box",
          }}
        />
        {search && (
          <button onClick={() => setSearch("")} style={{
            position: "absolute", right: 9, top: "50%", transform: "translateY(-50%)",
            background: "none", border: "none", cursor: "pointer", color: C.mute,
            fontSize: 20, lineHeight: 1, padding: "0 2px",
          }}>×</button>
        )}
      </div>

      {/* Search: empty state */}
      {searchResults !== null && searchResults.length === 0 && (
        <div style={{ textAlign: "center", padding: "56px 20px", color: C.mute }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🔍</div>
          <div style={{ fontSize: 15, fontWeight: 700, color: C.mid, marginBottom: 4 }}>
            Sin resultados para &ldquo;{search}&rdquo;
          </div>
          <button onClick={() => setSearch("")} style={{
            marginTop: 12, padding: "8px 18px", fontSize: 13, fontWeight: 600,
            background: C.accentBg, border: `1px solid ${C.accentBd}`,
            borderRadius: 8, cursor: "pointer", color: C.accent, fontFamily: C.font,
          }}>Limpiar búsqueda</button>
        </div>
      )}

      {/* Search results */}
      {searchResults !== null && searchResults.length > 0 && (
        <div>
          <div style={{ fontSize: 12, color: C.mute, marginBottom: 12 }}>
            {searchResults.length} resultado{searchResults.length !== 1 ? "s" : ""} para &ldquo;{search}&rdquo;
          </div>
          <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "repeat(auto-fill, minmax(260px, 1fr))", gap: 10 }}>
            {searchResults.map(r => (
              <ReportCard key={r.href} r={r} stat={getQuickStat(r.statsKey)} mob={mob} />
            ))}
          </div>
        </div>
      )}

      {/* Sections */}
      {searchResults === null && (
        <div style={{ display: "flex", flexDirection: "column", gap: 36 }}>
          {SECTIONS.map((section, si) => (
            <section key={section.key} className="sec-anim" style={{ animationDelay: `${si * 0.07}s` }}>
              {/* Section header */}
              <div style={{
                display: "flex", alignItems: "center", gap: 12,
                marginBottom: 14, paddingBottom: 12,
                borderBottom: `2px solid ${section.colorBd}`,
              }}>
                <div style={{
                  width: 42, height: 42, borderRadius: 10,
                  background: section.colorBg, border: `1px solid ${section.colorBd}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 20, flexShrink: 0,
                }}>
                  {section.icon}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 15, fontWeight: 800, color: section.color, letterSpacing: "-.02em" }}>
                      {section.label}
                    </span>
                    <span style={{
                      fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 99,
                      background: section.colorBg, color: section.color,
                      border: `1px solid ${section.colorBd}`,
                    }}>
                      {section.reports.length} reporte{section.reports.length !== 1 ? "s" : ""}
                    </span>
                  </div>
                  {!mob && (
                    <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>
                      {section.desc}
                    </div>
                  )}
                </div>
              </div>

              {/* Cards grid */}
              <div style={{
                display: "grid",
                gridTemplateColumns: mob ? "1fr" : "repeat(auto-fill, minmax(260px, 1fr))",
                gap: 10,
              }}>
                {section.reports.map(r => (
                  <ReportCard key={r.href} r={r} stat={getQuickStat(r.statsKey)} mob={mob} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}