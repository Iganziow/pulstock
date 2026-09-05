"use client";

import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { InsightsSection } from "./InsightsSection";
import { fmt, fmtDec, fmtMoney, fmtQty, fmtQtyDaily, formatQty, type UnitInfo } from "./helpers";
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
  // Info de unidad para que el formatter sepa si convertir ml→L, g→kg, etc.
  const unitInfo: UnitInfo = {
    unit_code: detail.product?.unit_code,
    unit_family: detail.product?.unit_family,
  };
  const stockLevel = num(detail.stock?.on_hand);
  const avgCost = num(detail.stock?.avg_cost);
  const daysOut = forecast.length > 0 && forecast[0].days_to_stockout !== null ? forecast[0].days_to_stockout : null;
  const avgDemand = forecast.length > 0 ? forecast.reduce((s, f) => s + num(f.qty_predicted), 0) / forecast.length : 0;

  // Gate "datos insuficientes" — Mario lo pidió: "deja que recopile
  // unos días de información y entrega una predicción más acertada".
  // Con menos de 7 días de ventas reales el modelo no puede producir
  // una predicción confiable: muestra ventas "en patrón aleatorio" o
  // se cae en category_prior con muy poca seguridad. En lugar de
  // mostrar números engañosos, mostramos un banner claro indicando
  // cuántos días faltan para tener una predicción útil.
  const dataPoints = detail.model?.data_points ?? 0;
  const MIN_DAYS_FOR_FORECAST = 7;
  const isInsufficientData = dataPoints < MIN_DAYS_FOR_FORECAST;

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
  const pL = 44, pR = 14, pT = 22, pB = 30;
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

  // Ticks Y como pasos enteros del "step" calculado (0, step, 2*step, …, maxV).
  const yTicks = Array.from({ length: tickCount + 1 }, (_, i) => {
    const v = i * step;
    return { v: Math.round(v), y: yp(v) };
  });
  // Pocas etiquetas en X, grandes: 6 en escritorio, 4 en móvil.
  const lEvery = Math.max(1, Math.round(n / (mob ? 4 : 6)));
  const sepX = fcStart >= 0 ? xp(fcStart) : null;

  // ─── Flags para leyenda condicional ────────────────────────────────────
  const hasActuals = !!actLine && history.some(h => num(h.qty_sold) > 0);
  const hasBand = !!bandPath;
  const hasPrediction = !!predLine;

  // ─── Marker "Hoy" ──────────────────────────────────────────────────────
  const todayISO = (() => {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${dd}`;
  })();
  const todayIdx = allPts.findIndex(p => p.iso === todayISO);
  const todayX = todayIdx >= 0 ? xp(todayIdx) : null;

  // ─── Resumen por semana ────────────────────────────────────────────────
  // Rediseño del 05/09/26. El gráfico anterior dibujaba cinco líneas, una
  // banda y tres marcadores en 200px de alto, con etiquetas de 9px: decía
  // demasiado a la vez. La compra se decide por semana (medido: el error
  // semanal del núcleo es 7-31% contra 39-68% diario), así que el resumen en
  // palabras va por semana y el gráfico se queda con lo esencial.
  const last7 = history.slice(-7);
  const next7 = forecast.slice(0, 7);
  const soldLast7 = last7.reduce((acc, h) => acc + num(h.qty_sold), 0);
  const predNext7 = next7.reduce((acc, f) => acc + num(f.qty_predicted), 0);
  const weekDelta = (soldLast7 > 0 && last7.length === 7 && next7.length === 7)
    ? Math.round((predNext7 - soldLast7) / soldLast7 * 100)
    : null;

  // ─── Barra de stock (reemplaza la línea roja y el badge sobre el gráfico)
  const stockoutLabel = (() => {
    if (daysOut === null) return "Alcanza para más de un mes";
    if (daysOut === 0) return "Sin stock";
    const d = new Date();
    d.setDate(d.getDate() + daysOut);
    const fecha = `${DOW_ES[d.getDay()]} ${d.getDate()} ${MONTH_ES[d.getMonth()]}`;
    return `Alcanza hasta el ${fecha} (${daysOut} día${daysOut === 1 ? "" : "s"})`;
  })();
  const stockTone = daysOut === null ? C.green : daysOut <= 3 ? C.red : daysOut <= 7 ? C.amber : daysOut <= 14 ? C.accent : C.green;
  const stockFill = daysOut === null ? 1 : Math.max(0.03, Math.min(1, daysOut / 30));

  // ─── Total previsto en el período del forecast ──────────────────────────
  const totalPredicted = forecast.reduce((s, f) => s + num(f.qty_predicted), 0);

  return (
    <div style={{ padding: mob ? "14px 12px" : "18px 22px", borderBottom: `1px solid ${C.border}`, background: C.bg }}>

      {/* RESUMEN */}
      {isInsufficientData ? (
        <div style={{
          marginBottom: 14, padding: mob ? "14px" : "16px 20px", borderRadius: 8,
          background: C.amberBg, border: `1px solid ${C.amberBd}`,
          fontSize: 13, lineHeight: 1.6,
        }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 800, color: C.amber, marginBottom: 4 }}>
                Estamos recopilando datos
              </div>
              <div style={{ color: C.text }}>
                Tenemos <b>{dataPoints} día{dataPoints !== 1 ? "s" : ""}</b> de venta de este producto.
                {" "}Necesitamos al menos <b>{MIN_DAYS_FOR_FORECAST} días</b> para entregar una predicción confiable.
                {" "}Faltan <b>{Math.max(0, MIN_DAYS_FOR_FORECAST - dataPoints)} día{(MIN_DAYS_FOR_FORECAST - dataPoints) !== 1 ? "s" : ""}</b>.
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: C.mute }}>
                Mientras tanto, abajo verás tu stock actual y las ventas registradas.
                {" "}No mostramos predicción para no orientarte con datos poco fiables.
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div style={{
          marginBottom: 14, padding: mob ? "12px" : "12px 16px", borderRadius: 8,
          background: daysOut !== null && daysOut <= 7 ? C.redBg : C.surface,
          border: `1px solid ${daysOut !== null && daysOut <= 7 ? C.redBd : C.border}`,
          fontSize: 13, lineHeight: 1.7,
        }}>
          {daysOut === null && (
            <><b style={{ color: C.green }}>✓ Hay stock suficiente.</b> Tienes <b>{fmtQty(stockLevel, unitInfo)}</b>. Vendes en promedio <b>{fmtQtyDaily(avgDemand, unitInfo)}</b>. Con eso alcanza para más de {coverageLabel}.</>
          )}
          {daysOut !== null && daysOut === 0 && (
            <><b style={{ color: C.red }}>⚠ ¡Se agotó!</b> Ya no queda stock. Vendías <b>{fmtQtyDaily(avgDemand, unitInfo)}</b>. <b>Pide al menos {fmtQty(reorderQty, unitInfo)}</b> para cubrir {coverageLabel}{avgCost > 0 && <> (costo: <b>{fmtMoney(reorderCost)}</b>)</>}.</>
          )}
          {daysOut !== null && daysOut > 0 && daysOut <= 3 && (
            <><b style={{ color: C.red }}>⚠ ¡Urgente!</b> Quedan <b>{fmtQty(stockLevel, unitInfo)}</b> y vendes <b>{fmtQtyDaily(avgDemand, unitInfo)}</b>. <b>Se acaba en {daysOut} día{daysOut > 1 ? "s" : ""}</b> si no repones. Te sugerimos pedir <b>{fmtQty(reorderQty, unitInfo)}</b> para cubrir {coverageLabel}{avgCost > 0 && <> ({fmtMoney(reorderCost)} aprox.)</>}.</>
          )}
          {daysOut !== null && daysOut > 3 && daysOut <= 7 && (
            <><b style={{ color: C.amber }}>Atención:</b> Tienes <b>{fmtQty(stockLevel, unitInfo)}</b>. Vendes <b>{fmtQtyDaily(avgDemand, unitInfo)}</b>, alcanza para <b>{daysOut} días</b>. Conviene pedir esta semana: <b>{fmtQty(reorderQty, unitInfo)}</b> para {coverageLabel}{avgCost > 0 && <> ({fmtMoney(reorderCost)} aprox.)</>}.</>
          )}
          {daysOut !== null && daysOut > 7 && (
            <><b style={{ color: C.accent }}>Bajo vigilancia:</b> Tienes <b>{fmtQty(stockLevel, unitInfo)}</b> y vendes <b>{fmtQtyDaily(avgDemand, unitInfo)}</b>. Alcanza para <b>{daysOut} días</b>. No es urgente, pero tenlo en cuenta para tu próximo pedido.</>
          )}
        </div>
      )}

      {/* TARJETAS DE RESUMEN — usan formatQty para que productos en ml/g
          se muestren en L/kg automáticamente */}
      {(() => {
        const stockFmt = formatQty(stockLevel, unitInfo, { unitWord: "" });
        const soldFmt = formatQty(totalSold, unitInfo, { unitWord: "" });
        const reorderFmt = formatQty(reorderQty, unitInfo, { unitWord: "" });
        return (
          <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(3, 1fr)", gap: 8, marginBottom: 14 }}>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px" }}>
              <div style={{ fontSize: 10, color: C.mute, fontWeight: 600 }}>EN BODEGA</div>
              <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2 }} title={stockFmt.tooltip}>
                {stockFmt.text}
                <span style={{ fontSize: 12, fontWeight: 500, color: C.mute }}>{stockFmt.suffix || " unidades"}</span>
              </div>
              {avgCost > 0 && <div style={{ fontSize: 11, color: C.mute }}>Valor: {fmtMoney(stockLevel * avgCost)}</div>}
            </div>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px" }}>
              <div style={{ fontSize: 10, color: C.mute, fontWeight: 600 }}>VENDIDO (ÚLTIMO MES)</div>
              <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2 }} title={soldFmt.tooltip}>
                {soldFmt.text}
                <span style={{ fontSize: 12, fontWeight: 500, color: C.mute }}>{soldFmt.suffix || " unidades"}</span>
              </div>
              {totalRevenue > 0 && <div style={{ fontSize: 11, color: C.mute }}>Ingreso: {fmtMoney(totalRevenue)}</div>}
            </div>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px", gridColumn: mob ? "1 / -1" : "auto" }}>
              <div style={{ fontSize: 10, color: C.mute, fontWeight: 600 }}>CUÁNTO PEDIR</div>
              {isInsufficientData ? (
                <>
                  <div style={{ fontSize: 16, fontWeight: 800, marginTop: 2, color: C.mute }}>
                    — sin datos
                  </div>
                  <div style={{ fontSize: 11, color: C.mute }}>
                    Recopilando información de ventas
                  </div>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2, color: reorderQty > 0 ? C.amber : C.green }} title={reorderFmt.tooltip}>
                    {reorderQty > 0 ? `${reorderFmt.text}${reorderFmt.suffix || " unidades"}` : "Nada por ahora"}
                  </div>
                  {reorderQty > 0 && avgCost > 0 && <div style={{ fontSize: 11, color: C.mute }}>Costo aprox: {fmtMoney(reorderCost)} · para {coverageLabel}</div>}
                  {reorderQty === 0 && <div style={{ fontSize: 11, color: C.mute }}>Tienes stock suficiente</div>}
                </>
              )}
            </div>
          </div>
        );
      })()}

      {/* GRÁFICO */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: mob ? "12px 8px" : "16px 14px", marginBottom: 8 }}>
        <div style={{ paddingLeft: mob ? 4 : 8, paddingRight: mob ? 4 : 8, marginBottom: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Cuánto vendes y cuánto vas a vender</div>
          {(last7.length > 0 || next7.length > 0) && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: mob ? 10 : 20, marginTop: 8 }}>
              {last7.length > 0 && (
                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                  <span style={{ width: 12, height: 3, background: C.accent, borderRadius: 2, display: "inline-block" }} />
                  <span style={{ fontSize: 12, color: C.mute }}>Últimos {last7.length} días</span>
                  <b style={{ fontSize: 15, color: C.text }}>{fmtQty(soldLast7, unitInfo)}</b>
                </div>
              )}
              {next7.length > 0 && (
                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                  <span style={{ width: 12, height: 0, borderTop: `3px dashed ${C.amber}`, display: "inline-block" }} />
                  <span style={{ fontSize: 12, color: C.mute }}>Próximos {next7.length} días</span>
                  <b style={{ fontSize: 15, color: C.text }}>{fmtQty(predNext7, unitInfo)}</b>
                  {weekDelta !== null && (
                    <span style={{ fontSize: 12, fontWeight: 700, color: weekDelta > 0 ? C.amber : weekDelta < 0 ? C.accent : C.mute }}>
                      {weekDelta > 0 ? "+" : ""}{weekDelta}%
                    </span>
                  )}
                </div>
              )}
              {avgDemand > 0 && (
                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                  <span style={{ fontSize: 12, color: C.mute }}>Promedio</span>
                  <b style={{ fontSize: 15, color: C.text }}>{fmtQtyDaily(avgDemand, unitInfo)}</b>
                </div>
              )}
            </div>
          )}
        </div>

        <div style={{ overflowX: "auto" }}>
          <svg width={W} height={H} style={{ display: "block" }} role="img" aria-label="Ventas pasadas y predicción de los próximos días">
            {/* El futuro lleva un fondo apenas más cálido: se distingue sin
                necesitar las etiquetas "Pasado" y "Futuro". */}
            {sepX !== null && <rect x={sepX} y={pT} width={Math.max(0, W - pR - sepX)} height={plotH} fill={C.amber} opacity={0.05} />}

            {(() => {
              const code = (unitInfo.unit_code || "").trim().toUpperCase();
              const isMl = code === "ML" || code === "MILILITRO" || code === "MILILITROS";
              const isG = code === "G" || code === "GR" || code === "GRAMO" || code === "GRAMOS";
              const convertVolume = isMl && maxV >= 1000;
              const convertMass = isG && maxV >= 1000;
              const convert = convertVolume || convertMass;
              const axisLabel = convertVolume ? "L/día" : convertMass ? "kg/día" : (isMl ? "ml/día" : isG ? "g/día" : "por día");
              const fmtTick = (v: number): string => {
                if (!convert) return String(v);
                const conv = v / 1000;
                const d = conv >= 100 ? 0 : conv >= 10 ? 1 : 2;
                return conv.toLocaleString("es-CL", { maximumFractionDigits: d });
              };
              return (
                <>
                  <text x={pL - 6} y={pT - 8} fontSize={10} fill={C.mute} textAnchor="end" fontWeight={600}>{axisLabel}</text>
                  {yTicks.map(t => (
                    <g key={t.v}>
                      <line x1={pL} x2={W - pR} y1={t.y} y2={t.y} stroke={C.border} strokeWidth={.5} />
                      <text x={pL - 6} y={t.y + 3.5} fontSize={10} fill={C.mute} textAnchor="end">{fmtTick(t.v)}</text>
                    </g>
                  ))}
                </>
              );
            })()}

            {todayX !== null && (
              <g>
                <line x1={todayX} x2={todayX} y1={pT} y2={pT + plotH} stroke={C.green} strokeWidth={1.5} strokeDasharray="3,2" opacity={0.8} />
                <rect x={todayX - 16} y={pT + plotH + 3} width={32} height={14} rx={3} fill={C.green} />
                <text x={todayX} y={pT + plotH + 13} fontSize={10} fill="#fff" textAnchor="middle" fontWeight={700}>Hoy</text>
              </g>
            )}

            {bandPath && <path d={bandPath} fill={C.amber} opacity={.12} />}
            {actLine && <polyline points={actLine} fill="none" stroke={C.accent} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />}
            {allPts.map((p, i) => p.actual !== null ? <circle key={`a${i}`} cx={xp(i)} cy={yp(p.actual)} r={2} fill={C.accent} /> : null)}
            {predLine && <polyline points={predLine} fill="none" stroke={C.amber} strokeWidth={2.5} strokeLinejoin="round" strokeDasharray="6,4" />}
            {allPts.map((p, i) => p.pred !== null ? <circle key={`p${i}`} cx={xp(i)} cy={yp(p.pred)} r={2.5} fill={C.amber} /> : null)}

            {allPts.map((p, i) => (i % lEvery === 0 && (todayX === null || Math.abs(xp(i) - todayX) > 22)) ? <text key={`x${i}`} x={xp(i)} y={H - 8} fontSize={10} fill={C.mute} textAnchor="middle">{p.label}</text> : null)}
          </svg>
        </div>

        {/* Barra de stock: cuánto hay y hasta qué día alcanza. Antes esto
            era una línea roja punteada cruzando las de venta, más un badge
            "SE ACABA" encima de todo. */}
        {(stockLevel > 0 || daysOut !== null) && (
          <div style={{ marginTop: 12, paddingLeft: mob ? 4 : 8, paddingRight: mob ? 4 : 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 6, fontSize: 12, color: C.mid, marginBottom: 5 }}>
              <span>En bodega: <b style={{ color: C.text }}>{fmtQty(stockLevel, unitInfo)}</b></span>
              <span style={{ color: stockTone, fontWeight: 700 }}>{stockoutLabel}</span>
            </div>
            <div style={{ height: 8, borderRadius: 99, background: C.bg, border: `1px solid ${C.border}`, overflow: "hidden" }} aria-hidden>
              <div style={{ width: `${Math.round(stockFill * 100)}%`, height: "100%", background: stockTone, borderRadius: 99, transition: "width .3s" }} />
            </div>
          </div>
        )}

        <div style={{ display: "flex", gap: mob ? 10 : 16, marginTop: 10, fontSize: 11, color: C.mid, flexWrap: "wrap", paddingLeft: mob ? 4 : 8 }}>
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
          {hasBand && (
            <span style={{ display: "flex", alignItems: "center", gap: 5, color: C.mute }} title="Rango en el que suele caer la venta real">
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
