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
  const coverageLabel = targetDays === 7 ? "1 semana" : targetDays === 10 ? "10 dias" : targetDays === 14 ? "2 semanas" : `${targetDays} dias`;

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
    <div style={{ padding: mob ? "14px 12px" : "18px 22px", borderBottom: `1px solid ${C.border}`, background: C.bg }}>

      {/* RESUMEN */}
      <div style={{
        marginBottom: 14, padding: mob ? "12px" : "12px 16px", borderRadius: 8,
        background: daysOut !== null && daysOut <= 7 ? C.redBg : C.surface,
        border: `1px solid ${daysOut !== null && daysOut <= 7 ? C.redBd : C.border}`,
        fontSize: 13, lineHeight: 1.7,
      }}>
        {daysOut === null && (
          <><b style={{ color: C.green }}>✓ Sin riesgo.</b> Tienes <b>{fmt(stockLevel)}</b> unidades en bodega. Se venden en promedio <b>{fmtDec(avgDemand)}</b> al dia. Con eso te alcanza para mas de {coverageLabel}, asi que no necesitas hacer nada por ahora.</>
        )}
        {daysOut !== null && daysOut === 0 && (
          <><b style={{ color: C.red }}>⚠ ¡Se agoto!</b> Este producto ya no tiene stock. Se vendian <b>{fmtDec(avgDemand)}</b> unidades por dia. <b>Necesitas pedir al menos {reorderQty} unidades</b> para cubrir {coverageLabel}{avgCost > 0 && <> (costo estimado: <b>{fmtMoney(reorderCost)}</b>)</>}.</>
        )}
        {daysOut !== null && daysOut > 0 && daysOut <= 3 && (
          <><b style={{ color: C.red }}>⚠ ¡Urgente!</b> Quedan solo <b>{fmt(stockLevel)}</b> unidades y se venden <b>{fmtDec(avgDemand)}</b> al dia. <b>En {daysOut} dia{daysOut > 1 ? "s" : ""} se acaba</b> si no repones. Te recomendamos pedir <b>{reorderQty}</b> unidades para cubrir {coverageLabel}{avgCost > 0 && <> ({fmtMoney(reorderCost)} aprox.)</>}.</>
        )}
        {daysOut !== null && daysOut > 3 && daysOut <= 7 && (
          <><b style={{ color: C.amber }}>⏰ Ojo:</b> Tienes <b>{fmt(stockLevel)}</b> unidades. Se venden <b>{fmtDec(avgDemand)}</b> al dia, asi que te alcanzan para unos <b>{daysOut} dias</b>. Conviene hacer un pedido esta semana. Sugerimos pedir <b>{reorderQty}</b> unidades para {coverageLabel}{avgCost > 0 && <> ({fmtMoney(reorderCost)} aprox.)</>}.</>
        )}
        {daysOut !== null && daysOut > 7 && (
          <><b style={{ color: C.accent }}>👁 Bajo vigilancia:</b> Tienes <b>{fmt(stockLevel)}</b> unidades y se venden <b>{fmtDec(avgDemand)}</b> al dia. Te alcanza para unos <b>{daysOut} dias</b>. No es urgente, pero tenlo en cuenta para tu proximo pedido.</>
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
          <div style={{ fontSize: 10, color: C.mute, fontWeight: 600 }}>VENDISTE (ULTIMO MES)</div>
          <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2 }}>{fmt(totalSold)} <span style={{ fontSize: 12, fontWeight: 500, color: C.mute }}>unidades</span></div>
          {totalRevenue > 0 && <div style={{ fontSize: 11, color: C.mute }}>Ingreso: {fmtMoney(totalRevenue)}</div>}
        </div>
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px", gridColumn: mob ? "1 / -1" : "auto" }}>
          <div style={{ fontSize: 10, color: C.mute, fontWeight: 600 }}>CUANTO PEDIR</div>
          <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2, color: reorderQty > 0 ? C.amber : C.green }}>
            {reorderQty > 0 ? `${fmt(reorderQty)} unidades` : "No necesitas"}
          </div>
          {reorderQty > 0 && avgCost > 0 && <div style={{ fontSize: 11, color: C.mute }}>Costo aprox: {fmtMoney(reorderCost)} · Para 2 semanas</div>}
          {reorderQty === 0 && <div style={{ fontSize: 11, color: C.mute }}>Tienes stock suficiente</div>}
        </div>
      </div>

      {/* GRAFICO */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: mob ? "10px 6px" : "14px 12px", marginBottom: 8 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, marginBottom: 8, paddingLeft: mob ? 4 : 8 }}>
          📈 Tus ventas y lo que el sistema predice
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

      {/* INSIGHTS */}
      <InsightsSection model={detail.model} history={history} avgDemand={avgDemand} mob={mob} />
    </div>
  );
}
