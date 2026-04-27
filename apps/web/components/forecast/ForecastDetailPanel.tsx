"use client";

import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { InsightsSection } from "./InsightsSection";
import { fmt, fmtDec, fmtMoney } from "./helpers";
import type { Detail } from "./types";

export function ForecastDetailPanel({ detail, loading, mob }: { detail: Detail | null; loading: boolean; mob: boolean }) {
  if (loading) return (
    <div style={{ padding: 24, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, color: C.mute, borderBottom: `1px solid ${C.border}` }}>
      <Spinner /> <span style={{ fontSize: 12 }}>Cargando detalle…</span>
    </div>
  );
  if (!detail) return null;

  // Helper para parseFloat seguro: si el backend manda string raro, NaN o
  // null, devolvemos 0 en vez de propagar NaN al cálculo (que ensucia el
  // gráfico, los KPIs y el mensaje de resumen).
  const num = (s: any, def = 0) => {
    const n = typeof s === "number" ? s : parseFloat(s ?? "");
    return Number.isFinite(n) ? n : def;
  };

  const history = detail.history || [];
  const forecast = detail.forecast || [];
  const stockLevel = num(detail.stock?.on_hand);
  const avgCost = num(detail.stock?.avg_cost);
  const daysOut = forecast.length > 0 && forecast[0].days_to_stockout !== null ? forecast[0].days_to_stockout : null;
  const avgDemand = forecast.length > 0 ? forecast.reduce((s, f) => s + num(f.qty_predicted), 0) / forecast.length : 0;

  const sug = detail.suggestion;
  const targetDays = sug?.target_days ?? 14;
  const reorderQty = sug ? Math.max(0, Math.ceil(num(sug.suggested_qty))) : Math.max(0, Math.ceil(avgDemand * targetDays - stockLevel));
  const reorderCost = sug ? num(sug.estimated_cost) : reorderQty * avgCost;
  const coverageLabel = targetDays === 7 ? "1 semana" : targetDays === 10 ? "10 días" : targetDays === 14 ? "2 semanas" : `${targetDays} días`;

  const totalSold = history.reduce((s, h) => s + num(h.qty_sold), 0);
  const totalRevenue = history.reduce((s, h) => s + num(h.revenue), 0);

  // Chart
  const allPts = [
    ...history.map(h => ({ label: h.date.slice(5), actual: num(h.qty_sold), pred: null as number | null, upper: null as number | null, lower: null as number | null, isFc: false })),
    ...forecast.map(f => ({ label: f.date.slice(5), actual: null as number | null, pred: num(f.qty_predicted), upper: num(f.upper_bound), lower: num(f.lower_bound), isFc: true })),
  ];
  if (allPts.length === 0) return null;

  // Math.max con array vacío retorna -Infinity. Como filtramos a 0+ con num()
  // y agregamos 1 al final, el resultado siempre es >= 1.2. Aún así, defendemos
  // contra el caso donde TODOS los valores son 0 (producto sin ventas ni
  // predicción) — el gráfico se ve plano pero no roto.
  const maxV = Math.max(
    ...allPts.map(d => Math.max(d.actual || 0, d.upper || d.pred || 0, 0)),
    1,
  ) * 1.2;
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
      cur -= num(forecast[i].qty_predicted);
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
    <div style={{ padding: mob ? "14px 12px" : "18px 22px", borderBottom: `1px solid ${C.border}`, background: C.bg }}>

      {/* RESUMEN */}
      <div style={{
        marginBottom: 14, padding: mob ? "12px" : "12px 16px", borderRadius: 8,
        background: daysOut !== null && daysOut <= 7 ? C.redBg : C.surface,
        border: `1px solid ${daysOut !== null && daysOut <= 7 ? C.redBd : C.border}`,
        fontSize: 13, lineHeight: 1.7,
      }}>
        {daysOut === null && (
          <><b style={{ color: C.green }}>✓ Tranqui, hay stock.</b> Tenés <b>{fmt(stockLevel)}</b> unidades. Vendés en promedio <b>{fmtDec(avgDemand)}</b> al día. Con eso te alcanza para más de {coverageLabel}.</>
        )}
        {daysOut !== null && daysOut === 0 && (
          <><b style={{ color: C.red }}>⚠ ¡Se agotó!</b> Ya no queda stock. Vendías <b>{fmtDec(avgDemand)}</b> por día. <b>Pedí al menos {reorderQty} unidades</b> para cubrir {coverageLabel}{avgCost > 0 && <> (costo: <b>{fmtMoney(reorderCost)}</b>)</>}.</>
        )}
        {daysOut !== null && daysOut > 0 && daysOut <= 3 && (
          <><b style={{ color: C.red }}>⚠ ¡Urgente!</b> Quedan <b>{fmt(stockLevel)}</b> unidades y vendés <b>{fmtDec(avgDemand)}</b> al día. <b>Se acaba en {daysOut} día{daysOut > 1 ? "s" : ""}</b> si no repones. Te sugerimos pedir <b>{reorderQty}</b> para cubrir {coverageLabel}{avgCost > 0 && <> ({fmtMoney(reorderCost)} aprox.)</>}.</>
        )}
        {daysOut !== null && daysOut > 3 && daysOut <= 7 && (
          <><b style={{ color: C.amber }}>⏰ Ojo:</b> Tenés <b>{fmt(stockLevel)}</b> unidades. Vendés <b>{fmtDec(avgDemand)}</b> al día, te alcanza para <b>{daysOut} días</b>. Conviene pedir esta semana: <b>{reorderQty}</b> unidades para {coverageLabel}{avgCost > 0 && <> ({fmtMoney(reorderCost)} aprox.)</>}.</>
        )}
        {daysOut !== null && daysOut > 7 && (
          <><b style={{ color: C.accent }}>👁 Bajo vigilancia:</b> Tenés <b>{fmt(stockLevel)}</b> unidades y vendés <b>{fmtDec(avgDemand)}</b> al día. Te alcanza para <b>{daysOut} días</b>. No es urgente, pero tenelo en cuenta para tu próximo pedido.</>
        )}
      </div>

      {/* TARJETAS DE RESUMEN */}
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
            {reorderQty > 0 ? `${fmt(reorderQty)} unidades` : "Nada por ahora"}
          </div>
          {reorderQty > 0 && avgCost > 0 && <div style={{ fontSize: 11, color: C.mute }}>Costo aprox: {fmtMoney(reorderCost)} · para {coverageLabel}</div>}
          {reorderQty === 0 && <div style={{ fontSize: 11, color: C.mute }}>Tenés stock suficiente</div>}
        </div>
      </div>

      {/* GRÁFICO */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: mob ? "10px 6px" : "14px 12px", marginBottom: 8 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, marginBottom: 4, paddingLeft: mob ? 4 : 8 }}>
          📈 Cuánto vendiste y cuánto vas a vender
        </div>
        <div style={{ fontSize: 11, color: C.mute, marginBottom: 8, paddingLeft: mob ? 4 : 8 }}>
          La línea continua azul es lo que ya vendiste. La línea cortada naranja es la predicción.
        </div>
        <div style={{ overflowX: "auto" }}>
          <svg width={W} height={H} style={{ display: "block" }}>
            {yTicks.map(t => (
              <g key={t.v}>
                <line x1={pL} x2={W - pR} y1={t.y} y2={t.y} stroke={C.border} strokeWidth={.5} />
                <text x={pL - 6} y={t.y + 3} fontSize={9} fill={C.mute} textAnchor="end">{t.v}</text>
              </g>
            ))}
            {sepX !== null && (
              <g>
                <line x1={sepX} x2={sepX} y1={pT - 6} y2={pT + plotH} stroke={C.border} strokeWidth={1} strokeDasharray="4,3" />
                <text x={sepX - 10} y={pT - 10} fontSize={10} fill={C.accent} textAnchor="end" fontWeight="700">Pasado</text>
                <text x={sepX + 10} y={pT - 10} fontSize={10} fill={C.amber} textAnchor="start" fontWeight="700">Futuro</text>
              </g>
            )}
            {bandPath && <path d={bandPath} fill={C.amber} opacity={.08} />}
            {stockPts && <polyline points={stockPts} fill="none" stroke={C.red} strokeWidth={2} strokeDasharray="6,4" opacity={.5} />}
            {soX !== null && (
              <g>
                <line x1={soX} x2={soX} y1={pT} y2={pT + plotH} stroke={C.red} strokeWidth={1.5} strokeDasharray="3,3" opacity={.3} />
                <rect x={soX - 40} y={pT - 2} width={80} height={16} rx={4} fill={C.red} opacity={.9} />
                <text x={soX} y={pT + 10} fontSize={9} fill="#fff" textAnchor="middle" fontWeight="700">SE ACABA</text>
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
            <span style={{ width: 14, height: 3, background: C.accent, borderRadius: 2, display: "inline-block" }} /> Ya vendido
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 14, height: 0, borderTop: `3px dashed ${C.amber}`, display: "inline-block" }} /> Predicción
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 14, height: 0, borderTop: `3px dashed ${C.red}`, display: "inline-block" }} /> Stock disponible
          </span>
          {bandPath && (
            <span style={{ display: "flex", alignItems: "center", gap: 5, color: C.mute }} title="Rango con margen de error de la predicción">
              <span style={{ width: 14, height: 8, background: C.amber + "20", border: `1px solid ${C.amberBd}`, borderRadius: 2, display: "inline-block" }} /> Margen de error
            </span>
          )}
        </div>
      </div>

      {/* INSIGHTS */}
      <InsightsSection model={detail.model} history={history} avgDemand={avgDemand} mob={mob} />
    </div>
  );
}
