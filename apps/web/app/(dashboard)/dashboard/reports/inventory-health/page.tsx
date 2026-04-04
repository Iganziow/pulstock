"use client";
import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";

const fmtMoney = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL"); };
const fmt = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "0" : Math.round(n).toLocaleString("es-CL"); };

/* ── Types ── */
type ZeroStockRow = { product_name: string; sku: string; warehouse_name: string; on_hand: number; last_sale_date: string | null };
type DeadStockRow = { product_name: string; sku: string; warehouse_name: string; on_hand: number; days_without_sale: number | null; stock_value: string | number };
type DiscrepancyRow = { product_name: string; sku: string; warehouse_name: string; on_hand: number; expected: number; difference: number };
type BelowMinRow = { product_name: string; sku: string; warehouse_name: string; on_hand: number; min_stock: number };
type OverstockRow = { product_name: string; sku: string; warehouse_name: string; on_hand: number; avg_daily_sales: number; days_of_stock: number };

type HealthData = {
  score: number;
  summary: { total_products: number; healthy: number; at_risk: number; critical: number };
  zero_stock: ZeroStockRow[];
  dead_stock: DeadStockRow[];
  dead_stock_days: number;
  dead_total_value: string;
  discrepancies: DiscrepancyRow[];
  below_minimum: BelowMinRow[];
  overstock: OverstockRow[];
};

type SectionKey = "zero_stock" | "dead_stock" | "discrepancies" | "below_minimum" | "overstock";

/* ── Score helpers ── */
const scoreColor = (s: number) => s >= 80 ? C.green : s >= 60 ? C.amber : C.red;
const scoreBg = (s: number) => s >= 80 ? C.greenBg : s >= 60 ? C.amberBg : s >= 0 ? C.redBg : C.bg;
const scoreBd = (s: number) => s >= 80 ? C.greenBd : s >= 60 ? C.amberBd : C.redBd;
const scoreLabel = (s: number) => s >= 80 ? "Excelente" : s >= 60 ? "Aceptable" : "Necesita atención";

/* ── Section config ── */
const SECTIONS: { key: SectionKey; title: string; icon: string; color: string; borderColor: string }[] = [
  { key: "zero_stock", title: "Stock agotado con demanda", icon: "⚠️", color: C.red, borderColor: C.red },
  { key: "dead_stock", title: "Productos sin rotación", icon: "🧊", color: C.amber, borderColor: C.amber },
  { key: "discrepancies", title: "Descuadres", icon: "🔍", color: C.violet, borderColor: C.violet },
  { key: "below_minimum", title: "Bajo stock mínimo", icon: "📦", color: C.sky, borderColor: C.sky },
  { key: "overstock", title: "Sobre-stock (>90 días)", icon: "📦", color: C.teal, borderColor: C.teal },
];

const DEAD_DAYS_OPTIONS = [7, 14, 30, 60, 90];

/* ── Chevron ── */
function Chevron({ open }: { open: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ transition: "transform .2s", transform: open ? "rotate(180deg)" : "rotate(0deg)" }}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

/* ── KPI Card ── */
function KpiCard({ value, label, color }: { value: number | string; label: string; color: string }) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "16px 18px", flex: "1 1 0", minWidth: 130 }}>
      <div style={{ fontSize: 26, fontWeight: 800, color, letterSpacing: "-.03em" }}>{typeof value === "number" ? fmt(value) : value}</div>
      <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>{label}</div>
    </div>
  );
}

/* ── Table styles ── */
const TH: React.CSSProperties = { padding: "8px 12px", fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".07em", textAlign: "left", whiteSpace: "nowrap" };
const TD: React.CSSProperties = { padding: "9px 12px", fontSize: 13, borderTop: `1px solid ${C.border}`, whiteSpace: "nowrap" };
const TDR: React.CSSProperties = { ...TD, textAlign: "right" };

/* ── Page ── */
export default function InventoryHealthPage() {
  const mob = useIsMobile();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<HealthData | null>(null);
  const [deadDays, setDeadDays] = useState(60);
  const [deadLoading, setDeadLoading] = useState(false);
  const [expanded, setExpanded] = useState<Record<SectionKey, boolean>>({
    zero_stock: false, dead_stock: false, discrepancies: false, below_minimum: false, overstock: false,
  });

  const loadAll = useCallback(async (days: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/reports/inventory-health/?dead_stock_days=${days}`);
      setData(res);
      const exp: Record<string, boolean> = {};
      for (const s of SECTIONS) exp[s.key] = (res[s.key]?.length ?? 0) > 0;
      setExpanded(exp as Record<SectionKey, boolean>);
    } catch (e: any) {
      setError(e?.message || "Error al cargar el reporte");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(deadDays); }, []);

  const handleDeadDaysChange = async (days: number) => {
    setDeadDays(days);
    setDeadLoading(true);
    try {
      const res = await apiFetch(`/reports/inventory-health/?dead_stock_days=${days}`);
      setData(prev => prev ? { ...prev, dead_stock: res.dead_stock, dead_stock_days: res.dead_stock_days, dead_total_value: res.dead_total_value } : res);
    } catch {}
    finally { setDeadLoading(false); }
  };

  const toggle = (key: SectionKey) => setExpanded(prev => ({ ...prev, [key]: !prev[key] }));
  const sectionCount = (key: SectionKey): number => data ? (data[key]?.length ?? 0) : 0;

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "14px 10px" : "24px 28px", display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Header */}
      <div>
        <Link href="/dashboard/reports" style={{ fontSize: 12, color: C.mute, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4, marginBottom: 8 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg> Reportes
        </Link>
        <h1 style={{ margin: 0, fontSize: mob ? 19 : 23, fontWeight: 800, letterSpacing: "-.04em" }}>Salud del inventario</h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: C.mute }}>Diagnóstico general del estado de tu inventario</p>
      </div>

      {loading && <div style={{ padding: 40, textAlign: "center", color: C.mute }}><Spinner /> Cargando…</div>}

      {error && !loading && (
        <div style={{ background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: C.r, padding: "14px 18px", fontSize: 13, color: C.red }}>{error}</div>
      )}

      {data && !loading && (<>
        {/* Score */}
        <div style={{ background: scoreBg(data.score), border: `1px solid ${scoreBd(data.score)}`, borderRadius: C.rMd, padding: mob ? "20px 16px" : "24px 28px", display: "flex", alignItems: "center", gap: mob ? 16 : 24, flexWrap: "wrap" }}>
          <div style={{
            width: mob ? 72 : 88, height: mob ? 72 : 88, borderRadius: "50%",
            background: C.surface, border: `3px solid ${scoreColor(data.score)}`,
            display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column",
            boxShadow: C.sh, flexShrink: 0,
          }}>
            <div style={{ fontSize: mob ? 28 : 36, fontWeight: 800, color: scoreColor(data.score), lineHeight: 1, letterSpacing: "-.03em" }}>{data.score}</div>
            <div style={{ fontSize: 9, color: C.mute, fontWeight: 600, marginTop: 2 }}>/100</div>
          </div>
          <div>
            <div style={{ fontSize: mob ? 16 : 19, fontWeight: 800, color: scoreColor(data.score) }}>{scoreLabel(data.score)}</div>
            <div style={{ fontSize: 13, color: C.mid, marginTop: 2 }}>Puntuación basada en disponibilidad, rotación y niveles de stock</div>
          </div>
        </div>

        {/* Summary cards */}
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(4, 1fr)", gap: 10 }}>
          <KpiCard value={data.summary.total_products} label="Total productos" color={C.text} />
          <KpiCard value={data.summary.healthy} label="Saludables" color={C.green} />
          <KpiCard value={data.summary.at_risk} label="En riesgo" color={C.amber} />
          <KpiCard value={data.summary.critical} label="Críticos" color={C.red} />
        </div>

        {/* Collapsible sections */}
        {SECTIONS.map(sec => {
          const count = sectionCount(sec.key);
          const isOpen = expanded[sec.key];
          const isDeadStock = sec.key === "dead_stock";

          return (
            <div key={sec.key} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden", boxShadow: C.sh }}>
              {/* Section header */}
              <button
                onClick={() => toggle(sec.key)}
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 10,
                  padding: mob ? "12px 14px" : "14px 18px", cursor: "pointer",
                  background: "transparent", border: "none", borderLeft: `4px solid ${sec.borderColor}`,
                  fontFamily: C.font, color: C.text, textAlign: "left",
                }}
              >
                <span style={{ fontSize: 18 }}>{sec.icon}</span>
                <div style={{ flex: 1 }}>
                  <span style={{ fontWeight: 700, fontSize: 14 }}>{sec.title}</span>
                  {/* Dead stock: show total value in header */}
                  {isDeadStock && count > 0 && data.dead_total_value && (
                    <span style={{ fontSize: 12, color: C.amber, fontWeight: 600, marginLeft: 8 }}>
                      — {fmtMoney(data.dead_total_value)} inmovilizado
                    </span>
                  )}
                </div>
                <span style={{
                  fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 99,
                  background: count > 0 ? sec.borderColor + "33" : C.greenBg,
                  color: count > 0 ? sec.color : C.green,
                }}>
                  {count}
                </span>
                <Chevron open={isOpen} />
              </button>

              {/* Section body */}
              {isOpen && (
                <>
                  {/* Dead stock: days selector + advice */}
                  {isDeadStock && (
                    <div style={{ padding: "10px 18px", borderTop: `1px solid ${C.border}`, background: C.bg, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 12, color: C.mid }}>Sin ventas en los últimos</span>
                      <div style={{ display: "flex", gap: 0, border: `1px solid ${C.border}`, borderRadius: 6, overflow: "hidden" }}>
                        {DEAD_DAYS_OPTIONS.map(d => (
                          <button key={d} onClick={() => handleDeadDaysChange(d)} style={{
                            padding: "4px 10px", fontSize: 11, fontWeight: deadDays === d ? 700 : 500,
                            background: deadDays === d ? C.amber : C.surface, color: deadDays === d ? "#fff" : C.mid,
                            border: "none", cursor: "pointer", fontFamily: C.font,
                          }}>{d}d</button>
                        ))}
                      </div>
                      {deadLoading && <Spinner />}
                      {count > 0 && (
                        <span style={{ fontSize: 11, color: C.mute, marginLeft: "auto" }}>
                          💡 Considera liquidar estos productos para liberar capital
                        </span>
                      )}
                    </div>
                  )}

                  {count === 0 ? (
                    <div style={{ padding: "20px 18px", textAlign: "center", fontSize: 13, color: C.mute, borderTop: `1px solid ${C.border}` }}>
                      Sin problemas detectados
                    </div>
                  ) : (
                    <div style={{ overflowX: "auto", borderTop: isDeadStock ? "none" : `1px solid ${C.border}` }}>
                      {sec.key === "zero_stock" && <ZeroStockTable rows={data.zero_stock} mob={mob} />}
                      {sec.key === "dead_stock" && <DeadStockTable rows={data.dead_stock} mob={mob} />}
                      {sec.key === "discrepancies" && <DiscrepancyTable rows={data.discrepancies} mob={mob} />}
                      {sec.key === "below_minimum" && <BelowMinTable rows={data.below_minimum} mob={mob} />}
                      {sec.key === "overstock" && <OverstockTable rows={data.overstock} mob={mob} />}
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}
      </>)}

      <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}} .ihr:hover{background:${C.accentBg}!important}`}</style>
    </div>
  );
}

/* ── Table components ── */

function ZeroStockTable({ rows, mob }: { rows: ZeroStockRow[]; mob: boolean }) {
  if (mob) return <MobileList rows={rows} render={r => ({
    title: r.product_name,
    sub: `SKU: ${r.sku || "-"} · ${r.warehouse_name}`,
    right: r.last_sale_date || "Sin ventas",
    rightColor: C.red,
  })} />;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 500 }}>
      <thead><tr style={{ background: C.bg }}><th style={TH}>Producto</th><th style={TH}>SKU</th><th style={TH}>Bodega</th><th style={{ ...TH, textAlign: "right" }}>Stock</th><th style={TH}>Última venta</th></tr></thead>
      <tbody>{rows.map((r, i) => (
        <tr key={i} className="ihr"><td style={TD}>{r.product_name}</td><td style={{ ...TD, color: C.mute }}>{r.sku || "-"}</td><td style={{ ...TD, color: C.mid }}>{r.warehouse_name}</td><td style={TDR}>{fmt(r.on_hand)}</td><td style={{ ...TD, color: C.red }}>{r.last_sale_date || "Sin ventas"}</td></tr>
      ))}</tbody>
    </table>
  );
}

function DeadStockTable({ rows, mob }: { rows: DeadStockRow[]; mob: boolean }) {
  if (mob) return <MobileList rows={rows} render={r => ({
    title: r.product_name,
    sub: `SKU: ${r.sku || "-"} · ${r.warehouse_name} · Stock: ${fmt(r.on_hand)}`,
    right: r.days_without_sale !== null ? `${r.days_without_sale}d` : "Nunca",
    rightColor: (r.days_without_sale ?? 999) > 90 ? C.red : C.amber,
    extra: fmtMoney(r.stock_value),
  })} />;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 600 }}>
      <thead><tr style={{ background: C.bg }}><th style={TH}>Producto</th><th style={TH}>SKU</th><th style={TH}>Bodega</th><th style={{ ...TH, textAlign: "right" }}>Stock</th><th style={{ ...TH, textAlign: "right" }}>Días sin venta</th><th style={{ ...TH, textAlign: "right" }}>Valor inmovilizado</th></tr></thead>
      <tbody>{rows.map((r, i) => {
        const dws = r.days_without_sale ?? 9999;
        const daysColor = dws > 90 ? C.red : dws > 60 ? C.amber : C.mid;
        return (
          <tr key={i} className="ihr">
            <td style={TD}>{r.product_name}</td>
            <td style={{ ...TD, color: C.mute }}>{r.sku || "-"}</td>
            <td style={{ ...TD, color: C.mid }}>{r.warehouse_name}</td>
            <td style={TDR}>{fmt(r.on_hand)}</td>
            <td style={{ ...TDR, fontWeight: 600, color: daysColor }}>{dws === 9999 ? "Nunca" : `${dws}d`}</td>
            <td style={{ ...TDR, fontWeight: 700, color: C.amber }}>{fmtMoney(r.stock_value)}</td>
          </tr>
        );
      })}</tbody>
    </table>
  );
}

function DiscrepancyTable({ rows, mob }: { rows: DiscrepancyRow[]; mob: boolean }) {
  if (mob) return <MobileList rows={rows} render={r => ({
    title: r.product_name,
    sub: `SKU: ${r.sku || "-"} · ${r.warehouse_name}`,
    right: (r.difference > 0 ? "+" : "") + fmt(r.difference),
    rightColor: r.difference < 0 ? C.red : C.amber,
  })} />;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 600 }}>
      <thead><tr style={{ background: C.bg }}><th style={TH}>Producto</th><th style={TH}>SKU</th><th style={TH}>Bodega</th><th style={{ ...TH, textAlign: "right" }}>Stock sistema</th><th style={{ ...TH, textAlign: "right" }}>Esperado</th><th style={{ ...TH, textAlign: "right" }}>Diferencia</th></tr></thead>
      <tbody>{rows.map((r, i) => (
        <tr key={i} className="ihr"><td style={TD}>{r.product_name}</td><td style={{ ...TD, color: C.mute }}>{r.sku || "-"}</td><td style={{ ...TD, color: C.mid }}>{r.warehouse_name}</td><td style={TDR}>{fmt(r.on_hand)}</td><td style={TDR}>{fmt(r.expected)}</td><td style={{ ...TDR, fontWeight: 700, color: r.difference < 0 ? C.red : C.amber }}>{(r.difference > 0 ? "+" : "") + fmt(r.difference)}</td></tr>
      ))}</tbody>
    </table>
  );
}

function BelowMinTable({ rows, mob }: { rows: BelowMinRow[]; mob: boolean }) {
  if (mob) return <MobileList rows={rows} render={r => ({
    title: r.product_name,
    sub: `SKU: ${r.sku || "-"} · ${r.warehouse_name}`,
    right: `${fmt(r.on_hand)} / ${fmt(r.min_stock)}`,
    rightColor: C.sky,
  })} />;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 500 }}>
      <thead><tr style={{ background: C.bg }}><th style={TH}>Producto</th><th style={TH}>SKU</th><th style={TH}>Bodega</th><th style={{ ...TH, textAlign: "right" }}>Stock</th><th style={{ ...TH, textAlign: "right" }}>Mínimo</th></tr></thead>
      <tbody>{rows.map((r, i) => (
        <tr key={i} className="ihr"><td style={TD}>{r.product_name}</td><td style={{ ...TD, color: C.mute }}>{r.sku || "-"}</td><td style={{ ...TD, color: C.mid }}>{r.warehouse_name}</td><td style={{ ...TDR, fontWeight: 700, color: r.on_hand === 0 ? C.red : C.sky }}>{fmt(r.on_hand)}</td><td style={TDR}>{fmt(r.min_stock)}</td></tr>
      ))}</tbody>
    </table>
  );
}

function OverstockTable({ rows, mob }: { rows: OverstockRow[]; mob: boolean }) {
  if (mob) return <MobileList rows={rows} render={r => ({
    title: r.product_name,
    sub: `SKU: ${r.sku || "-"} · ${r.warehouse_name} · Stock: ${fmt(r.on_hand)}`,
    right: `${fmt(r.days_of_stock)}d`,
    rightColor: C.teal,
    extra: `${fmt(r.avg_daily_sales)}/día`,
  })} />;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 600 }}>
      <thead><tr style={{ background: C.bg }}><th style={TH}>Producto</th><th style={TH}>SKU</th><th style={TH}>Bodega</th><th style={{ ...TH, textAlign: "right" }}>Stock</th><th style={{ ...TH, textAlign: "right" }}>Venta diaria</th><th style={{ ...TH, textAlign: "right" }}>Días de stock</th></tr></thead>
      <tbody>{rows.map((r, i) => (
        <tr key={i} className="ihr"><td style={TD}>{r.product_name}</td><td style={{ ...TD, color: C.mute }}>{r.sku || "-"}</td><td style={{ ...TD, color: C.mid }}>{r.warehouse_name}</td><td style={TDR}>{fmt(r.on_hand)}</td><td style={{ ...TDR, color: C.mid }}>{fmt(r.avg_daily_sales)}</td><td style={{ ...TDR, fontWeight: 700, color: C.teal }}>{fmt(r.days_of_stock)}</td></tr>
      ))}</tbody>
    </table>
  );
}

/* ── Generic mobile list ── */
function MobileList<T>({ rows, render }: { rows: T[]; render: (r: T) => { title: string; sub: string; right: string; rightColor: string; extra?: string } }) {
  return (
    <div>
      {rows.map((r, i) => {
        const d = render(r);
        return (
          <div key={i} style={{ padding: "10px 14px", borderTop: i > 0 ? `1px solid ${C.border}` : "none" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <div style={{ fontWeight: 600, fontSize: 13, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.title}</div>
              <span style={{ fontSize: 12, fontWeight: 700, color: d.rightColor, whiteSpace: "nowrap" }}>{d.right}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: C.mute, marginTop: 3 }}>
              <span>{d.sub}</span>
              {d.extra && <span style={{ fontWeight: 600, color: C.mid }}>{d.extra}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
