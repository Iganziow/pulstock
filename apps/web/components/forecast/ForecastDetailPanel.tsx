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

  // Helper para formatear fechas tipo "2025-04-28" → "28 abr".
  // Mucho más legible que "04-28" (formato del backend).
  const MONTH_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const DOW_ES = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
  function fmtShortDate(iso: string): string {
    const parts = iso.split("-"); // YYYY-MM-DD
    if (parts.length !== 3) return iso.slice(5);
    const month = parseInt(parts[1], 10);
    const day = parseInt(parts[2], 10);
    if (!Number.isFinite(month) || !Number.isFinite(day)) return iso.slice(5);
    return `${day} ${MONTH_ES[month - 1] || ""}`.trim();
  }
  function fmtFullDate(iso: string): string {
    const parts = iso.split("-");
    if (parts.length !== 3) return iso;
    const dt = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    if (Number.isNaN(dt.getTime())) return iso;
    return `${DOW_ES[dt.getDay()]} ${dt.getDate()} ${MONTH_ES[dt.getMonth()]}`;
  }

  // Chart
  const allPts = [
    ...history.map(h => ({ iso: h.date, label: fmtShortDate(h.date), actual: num(h.qty_sold), pred: null as number | null, upper: null as number | null, lower: null as number | null, isFc: false })),
    ...forecast.map(f => ({ iso: f.date, label: fmtShortDate(f.date), actual: null as number | null, pred: num(f.qty_predicted), upper: num(f.upper_bound), lower: num(f.lower_bound), isFc: true })),
  ];
  if (allPts.length === 0) return null;

  // Math.max con array vacío retorna -Infinity. Como filtramos a 0+ con num()
  // y agregamos 1 al final, el resultado siempre es >= 1. Aún así, defendemos
  // contra el caso donde TODOS los valores son 0 (producto sin ventas ni
  // predicción) — el gráfico se ve plano pero no roto.
  const rawMax = Math.max(
    ...allPts.map(d => Math.max(d.actual || 0, d.upper || d.pred || 0, 0)),
    1,
  );
  // "Nice" Y-axis: pasos redondos en [1, 2, 5] × 10^n para que los números
  // del eje sean fáciles de leer (5, 10, 15, 20 — no 4, 7, 11, 14). Antes
  // dividíamos maxV en cuartos exactos y redondeábamos cada tick → escala
  // confusa para el dueño de la cafetería.
  function niceStep(v: number): number {
    const target = v / 4; // apuntamos a ~4 divisiones
    if (target <= 0) return 1;
    const exp = Math.floor(Math.log10(target));
    const base = Math.pow(10, exp);
    const m = target / base;
    const nice = m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10;
    return Math.max(1, nice * base);
  }
  const step = niceStep(rawMax * 1.15);
  const maxV = Math.ceil((rawMax * 1.15) / step) * step;
  const tickCount = Math.max(2, Math.round(maxV / step));
  const W = mob ? 340 : 680, H = mob ? 170 : 210;
  // Más padding arriba (pT) para que las etiquetas "Pasado/Futuro" no
  // queden pegadas al borde. Más pL para que números grandes (1.500, etc.)
  // no se corten.
  const pL = 44, pR = 14, pT = 36, pB = 28;
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

  // Ticks Y como pasos enteros del "step" calculado (0, step, 2*step, …, maxV).
  // Eso garantiza números limpios (5, 10, 15, 20) en vez de 4, 7, 11, 14.
  const yTicks = Array.from({ length: tickCount + 1 }, (_, i) => {
    const v = i * step;
    return { v: Math.round(v), y: yp(v) };
  });
  const lEvery = Math.max(1, Math.floor(n / (mob ? 5 : 10)));
  const sepX = fcStart >= 0 ? xp(fcStart) : null;
  // Etiquetas "Pasado/Futuro": solo se dibujan si la sección tiene al menos
  // ~40px de ancho (suficiente para que el texto entre sin cortarse). Antes
  // usábamos textAnchor="end" con sepX-10 → cuando no había historia (o muy
  // poca), "Pasado" quedaba con la P recortada por el límite del SVG.
  const pastWidth = sepX !== null ? sepX - pL : 0;
  const futureWidth = sepX !== null ? (W - pR) - sepX : 0;
  const showPasado = sepX !== null && pastWidth >= 40;
  const showFuturo = sepX !== null && futureWidth >= 40;

  // ─── Flags para legenda condicional ─────────────────────────────────────
  // Ocultamos items de la leyenda cuyas líneas no se dibujan — antes
  // mostrábamos "Ya vendido" aunque no hubiera ventas (totalSold = 0),
  // generando confusión: el cliente buscaba la línea azul y no la veía.
  const hasActuals = !!actLine && history.some(h => num(h.qty_sold) > 0);
  const hasStockLine = !!stockPts;
  const hasBand = !!bandPath;
  const hasPrediction = !!predLine;

  // ─── Promedio diario predicho (línea de referencia horizontal) ──────────
  // Es la métrica más útil para la lectura rápida — "vendés ~2 al día" es
  // más accionable que mirar día por día. Solo la dibujamos si hay
  // predicciones y el promedio es > 0.
  const avgRefY = (avgDemand > 0 && avgDemand <= maxV) ? yp(avgDemand) : null;

  // ─── Marker "Hoy" ──────────────────────────────────────────────────────
  // Buscamos el punto de hoy en el array. Si está dentro del rango,
  // pintamos una línea vertical sutil + label "Hoy" para anclar visualmente
  // dónde está el presente. Funciona aunque "hoy" caiga en la frontera
  // pasado/futuro (típico — la frontera ES hoy).
  const todayISO = (() => {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${dd}`;
  })();
  const todayIdx = allPts.findIndex(p => p.iso === todayISO);
  const todayX = todayIdx >= 0 ? xp(todayIdx) : null;

  // ─── Día de mayor venta predicha (visual peak) ──────────────────────────
  // Marcamos el punto más alto del forecast con un pequeño label encima.
  // Útil cuando hay un "viernes pico" o un evento — Mario lo ve a la primera.
  const fcPts = allPts.filter(p => p.isFc && p.pred !== null && Number.isFinite(p.pred as number));
  const peakPt = fcPts.length > 0
    ? fcPts.reduce((a, b) => ((b.pred as number) > (a.pred as number) ? b : a))
    : null;
  const peakIdx = peakPt ? allPts.indexOf(peakPt) : -1;
  // Solo destacamos el peak si es claramente más alto que el promedio
  // (mínimo 30% sobre el average) — si todos los días son parecidos, el
  // "pico" es ruido y mejor no destacar nada.
  const showPeak = peakPt !== null && avgDemand > 0
    && (peakPt.pred as number) >= avgDemand * 1.3;

  // ─── Total previsto en el período del forecast ──────────────────────────
  // Útil para repuesto: "vas a vender ~50 unidades en 30 días".
  const totalPredicted = forecast.reduce((s, f) => s + num(f.qty_predicted), 0);

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
        <div style={{
          display: "flex", alignItems: "flex-start", justifyContent: "space-between",
          flexWrap: "wrap", gap: 8, paddingLeft: mob ? 4 : 8, paddingRight: mob ? 4 : 8,
          marginBottom: 8,
        }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, marginBottom: 2 }}>
              📈 Cuánto vas a vender
            </div>
            <div style={{ fontSize: 11, color: C.mute }}>
              {/* Caption dinámica: solo mencionamos las líneas que realmente
                  se dibujan, así no quedamos prometiendo una "línea azul"
                  que no existe cuando el producto no tiene historia. */}
              {hasActuals && hasPrediction ? (
                <>La línea <b style={{ color: C.accent }}>continua azul</b> es lo que ya vendiste. La <b style={{ color: C.amber }}>cortada naranja</b> es la predicción.</>
              ) : hasActuals ? (
                <>Línea <b style={{ color: C.accent }}>azul</b>: tus ventas reales.</>
              ) : hasPrediction ? (
                <>Línea <b style={{ color: C.amber }}>cortada naranja</b>: lo que vas a vender los próximos días.</>
              ) : null}
            </div>
          </div>
          {/* Tarjeta resumen al lado derecho del título — mensaje accionable
              de un vistazo. En móvil cae debajo automáticamente. */}
          {avgDemand > 0 && (
            <div style={{
              background: C.amberBg, border: `1px solid ${C.amberBd}`,
              borderRadius: 6, padding: "6px 12px", textAlign: "right",
              fontSize: 11, color: C.mid, lineHeight: 1.3,
            }}>
              <div style={{ fontWeight: 700, color: C.amber, fontSize: 11 }}>Promedio</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>
                {fmtDec(avgDemand)} <span style={{ fontSize: 10, fontWeight: 600, color: C.mute }}>uds/día</span>
              </div>
              {totalPredicted > 0 && (
                <div style={{ fontSize: 10, color: C.mute }}>
                  ≈ {fmt(totalPredicted)} en {forecast.length} días
                </div>
              )}
            </div>
          )}
        </div>
        <div style={{ overflowX: "auto" }}>
          <svg width={W} height={H} style={{ display: "block" }}>
            {/* Y-axis grid + ticks. Etiqueta "uds/día" arriba del eje para
                que el cliente entienda qué significan los números. */}
            <text x={pL - 6} y={pT - 6} fontSize={9} fill={C.mute} textAnchor="end" fontWeight={600}>uds/día</text>
            {yTicks.map(t => (
              <g key={t.v}>
                <line x1={pL} x2={W - pR} y1={t.y} y2={t.y} stroke={C.border} strokeWidth={.5} />
                <text x={pL - 6} y={t.y + 3} fontSize={9} fill={C.mute} textAnchor="end">{t.v}</text>
              </g>
            ))}

            {/* Línea de promedio horizontal — referencia visual potente.
                Va atrás de las líneas de datos pero adelante del grid. */}
            {avgRefY !== null && (
              <g>
                <line
                  x1={pL} x2={W - pR} y1={avgRefY} y2={avgRefY}
                  stroke={C.accent} strokeWidth={1} strokeDasharray="2,3" opacity={0.45}
                />
                <text
                  x={W - pR - 4} y={avgRefY - 3}
                  fontSize={9} fill={C.accent} textAnchor="end" fontWeight={700}
                >
                  promedio {fmtDec(avgDemand)}/día
                </text>
              </g>
            )}

            {sepX !== null && (
              <g>
                <line x1={sepX} x2={sepX} y1={pT - 6} y2={pT + plotH} stroke={C.border} strokeWidth={1} strokeDasharray="4,3" />
                {showPasado && (
                  <text x={pL + pastWidth / 2} y={pT - 12} fontSize={11} fill={C.accent} textAnchor="middle" fontWeight="700">Pasado</text>
                )}
                {showFuturo && (
                  <text x={sepX + futureWidth / 2} y={pT - 12} fontSize={11} fill={C.amber} textAnchor="middle" fontWeight="700">Futuro</text>
                )}
              </g>
            )}

            {/* Marker "Hoy" — vertical sutil con etiqueta. Solo se dibuja si
                hoy cae dentro del rango del gráfico. */}
            {todayX !== null && (
              <g>
                <line
                  x1={todayX} x2={todayX} y1={pT} y2={pT + plotH}
                  stroke={C.green} strokeWidth={1.5} strokeDasharray="3,2" opacity={0.7}
                />
                <rect
                  x={todayX - 16} y={pT + plotH + 2}
                  width={32} height={13} rx={3} fill={C.green}
                />
                <text
                  x={todayX} y={pT + plotH + 11}
                  fontSize={9} fill="#fff" textAnchor="middle" fontWeight={700}
                >Hoy</text>
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

            {/* Marker "pico" — destacamos el día con mayor venta predicha
                cuando es claramente más alto que el promedio (>30%). */}
            {showPeak && peakPt && peakIdx >= 0 && (
              <g>
                <circle cx={xp(peakIdx)} cy={yp(peakPt.pred as number)} r={5} fill={C.amber} />
                <circle cx={xp(peakIdx)} cy={yp(peakPt.pred as number)} r={9} fill="none" stroke={C.amber} strokeWidth={1.5} opacity={0.5} />
                <text
                  x={xp(peakIdx)}
                  y={yp(peakPt.pred as number) - 14}
                  fontSize={10} fill={C.amber} textAnchor="middle" fontWeight={800}
                >★ {fmtDec(peakPt.pred as number)}</text>
                <text
                  x={xp(peakIdx)}
                  y={yp(peakPt.pred as number) - 4}
                  fontSize={8} fill={C.mid} textAnchor="middle" fontWeight={600}
                >{fmtFullDate(peakPt.iso).split(" ")[0]}</text>
              </g>
            )}

            {allPts.map((p, i) => i % lEvery === 0 ? <text key={`x${i}`} x={xp(i)} y={H - 6} fontSize={9} fill={C.mute} textAnchor="middle">{p.label}</text> : null)}
          </svg>
        </div>

        {/* Leyenda condicional — solo mostramos los items cuyas líneas
            realmente aparecen en el gráfico. Antes mostrábamos "Ya vendido"
            aunque no hubiera ventas → el cliente buscaba la línea azul y
            no la veía, generando dudas. */}
        <div style={{ display: "flex", gap: mob ? 10 : 16, marginTop: 6, fontSize: 11, color: C.mid, flexWrap: "wrap", paddingLeft: mob ? 4 : 8 }}>
          {hasActuals && (
            <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 14, height: 3, background: C.accent, borderRadius: 2, display: "inline-block" }} /> Ya vendido
            </span>
          )}
          {hasPrediction && (
            <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 14, height: 0, borderTop: `3px dashed ${C.amber}`, display: "inline-block" }} /> Predicción
            </span>
          )}
          {avgRefY !== null && (
            <span style={{ display: "flex", alignItems: "center", gap: 5, color: C.accent }}>
              <span style={{ width: 14, height: 0, borderTop: `2px dashed ${C.accent}`, opacity: 0.6, display: "inline-block" }} /> Promedio diario
            </span>
          )}
          {hasStockLine && (
            <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 14, height: 0, borderTop: `3px dashed ${C.red}`, display: "inline-block" }} /> Stock disponible
            </span>
          )}
          {hasBand && (
            <span style={{ display: "flex", alignItems: "center", gap: 5, color: C.mute }} title="Rango con margen de error de la predicción">
              <span style={{ width: 14, height: 8, background: C.amber + "20", border: `1px solid ${C.amberBd}`, borderRadius: 2, display: "inline-block" }} /> Margen de error
            </span>
          )}
          {todayX !== null && (
            <span style={{ display: "flex", alignItems: "center", gap: 5, color: C.green }}>
              <span style={{ width: 14, height: 0, borderTop: `2px dashed ${C.green}`, display: "inline-block" }} /> Hoy
            </span>
          )}
        </div>
      </div>

      {/* INSIGHTS */}
      <InsightsSection model={detail.model} history={history} avgDemand={avgDemand} mob={mob} />
    </div>
  );
}
