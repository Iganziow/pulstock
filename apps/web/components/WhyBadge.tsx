/**
 * WhyBadge — Componente de Explicabilidad para Forecast
 *
 * Uso:
 *   <WhyBadge
 *     stockLevel={15}
 *     avgDemand={3.2}
 *     daysToStockout={5}
 *     reorderQty={30}
 *     trendPct={15}          // opcional: % cambio vs período anterior
 *     leadTimeDays={4}       // opcional: días que tarda el proveedor
 *     seasonality="high"     // opcional: "high" | "normal" | "low"
 *     algorithm="holt_winters" // opcional
 *     confidence={85}         // opcional: % confianza del modelo
 *   />
 *
 * Genera automáticamente una explicación en lenguaje plano como:
 * "Tus ventas subieron 15% este mes. Con 15 unidades en stock y ventas
 *  de 3.2/día, se agota en 5 días. Tu proveedor tarda 4 días en entregar,
 *  así que hay que pedir ya."
 */

import { useState } from "react";
import { C } from "@/lib/theme";


type WhyBadgeProps = {
  stockLevel: number;
  avgDemand: number;
  daysToStockout: number | null;
  reorderQty: number;
  trendPct?: number | null;      // % change vs previous period
  leadTimeDays?: number | null;  // supplier lead time
  seasonality?: "high" | "normal" | "low" | null;
  algorithm?: string | null;
  confidence?: number | null;    // model confidence %
  compact?: boolean;             // show only icon, expand on click
};

function buildExplanation(p: WhyBadgeProps): string[] {
  const lines: string[] = [];

  // 1. Trend context
  if (p.trendPct !== null && p.trendPct !== undefined && p.trendPct !== 0) {
    if (p.trendPct > 0) {
      lines.push(`📈 Tus ventas de este producto subieron un ${Math.round(p.trendPct)}% comparado con el período anterior.`);
    } else {
      lines.push(`📉 Las ventas bajaron un ${Math.abs(Math.round(p.trendPct))}% vs el período anterior.`);
    }
  }

  // 2. Current situation
  if (p.stockLevel <= 0) {
    lines.push(`🚫 Ya no tienes stock de este producto. Cada día sin stock es venta perdida.`);
  } else if (p.daysToStockout !== null && p.daysToStockout <= 3) {
    lines.push(`⚠️ Quedan ${Math.round(p.stockLevel)} unidades y se venden ~${p.avgDemand.toFixed(1)} al día. Se agota en ${p.daysToStockout} día${p.daysToStockout > 1 ? "s" : ""}.`);
  } else if (p.daysToStockout !== null && p.daysToStockout <= 7) {
    lines.push(`⏰ Con ${Math.round(p.stockLevel)} unidades y ventas de ${p.avgDemand.toFixed(1)}/día, el stock alcanza para unos ${p.daysToStockout} días.`);
  } else {
    lines.push(`📦 Tienes ${Math.round(p.stockLevel)} unidades. Se venden ~${p.avgDemand.toFixed(1)} al día.`);
  }

  // 3. Lead time urgency
  if (p.leadTimeDays && p.leadTimeDays > 0 && p.daysToStockout !== null) {
    if (p.daysToStockout <= p.leadTimeDays) {
      lines.push(`🚚 Tu proveedor tarda ${p.leadTimeDays} días en entregar, pero solo te quedan ${p.daysToStockout} días de stock. Hay que pedir hoy.`);
    } else if (p.daysToStockout <= p.leadTimeDays + 3) {
      lines.push(`🚚 El proveedor tarda ${p.leadTimeDays} días. Conviene pedir ahora para que llegue a tiempo.`);
    }
  }

  // 4. Seasonality
  if (p.seasonality === "high") {
    lines.push(`🔥 Estamos en temporada alta para este producto — la demanda es mayor de lo normal.`);
  } else if (p.seasonality === "low") {
    lines.push(`❄️ Temporada baja — la demanda está más tranquila de lo habitual.`);
  }

  // 5. Reorder recommendation
  if (p.reorderQty > 0) {
    lines.push(`🛒 Te sugerimos pedir ${Math.round(p.reorderQty)} unidades para cubrir ~2 semanas de venta.`);
  }

  // 6. Model confidence
  if (p.confidence !== null && p.confidence !== undefined) {
    if (p.confidence >= 80) {
      lines.push(`🎯 El sistema tiene alta confianza (${Math.round(p.confidence)}%) en esta predicción basándose en tu historial de ventas.`);
    } else if (p.confidence >= 60) {
      lines.push(`📊 Confianza moderada (${Math.round(p.confidence)}%). La predicción mejora con más datos de venta.`);
    } else {
      lines.push(`📊 Confianza baja (${Math.round(p.confidence)}%) — el producto tiene pocas ventas registradas. La sugerencia es aproximada.`);
    }
  }

  return lines;
}

export default function WhyBadge(props: WhyBadgeProps) {
  const [open, setOpen] = useState(false);
  const lines = buildExplanation(props);
  const compact = props.compact !== false;

  if (lines.length === 0) return null;

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        style={{
          background: open ? C.accentBg : "transparent",
          border: `1px solid ${open ? C.accentBd : C.border}`,
          borderRadius: 6, padding: compact ? "3px 8px" : "4px 10px",
          fontSize: 11, fontWeight: 600, color: C.accent,
          cursor: "pointer", fontFamily: C.font,
          display: "inline-flex", alignItems: "center", gap: 4,
          transition: "all .15s",
        }}
        title="¿Por qué sugerimos esto?"
      >
        💡 {!compact && "¿Por qué?"}
      </button>

      {open && (
        <>
          {/* Backdrop */}
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 999 }} />

          {/* Tooltip */}
          <div style={{
            position: "absolute", top: "calc(100% + 6px)", right: 0,
            width: 320, maxWidth: "90vw", zIndex: 1000,
            background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,.12)",
            padding: "14px 16px",
          }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 8 }}>
              💡 ¿Por qué sugerimos esto?
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {lines.map((line, i) => (
                <div key={i} style={{ fontSize: 12, color: C.mid, lineHeight: 1.5 }}>
                  {line}
                </div>
              ))}
            </div>
            {props.algorithm && (
              <div style={{ fontSize: 10, color: C.mute, marginTop: 8, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>
                Modelo: {props.algorithm === "holt_winters" ? "Estacional (Holt-Winters)" : props.algorithm === "weighted_ma" ? "Promedio ponderado" : props.algorithm}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * WhyBadgeFromData — versión que recibe datos crudos del API
 * y calcula trend automáticamente desde el historial
 */
export function WhyBadgeFromDetail(props: {
  detail: {
    stock: { on_hand: string };
    model: { algorithm: string; metrics: any; params?: any } | null;
    history: { date: string; qty_sold: string }[];
    forecast: { qty_predicted: string; days_to_stockout: number | null; confidence?: string }[];
  };
  compact?: boolean;
}) {
  const { detail, compact } = props;
  const stockLevel = parseFloat(detail.stock.on_hand);
  const forecast = detail.forecast || [];
  const history = detail.history || [];

  const avgDemand = forecast.length > 0
    ? forecast.reduce((s, f) => s + parseFloat(f.qty_predicted), 0) / forecast.length
    : 0;
  const daysToStockout = forecast.length > 0 ? forecast[0].days_to_stockout : null;
  const reorderQty = Math.max(0, Math.ceil(avgDemand * 14 - stockLevel));

  // Calculate trend: compare last 14d vs previous 14d
  let trendPct: number | null = null;
  if (history.length >= 14) {
    const recent = history.slice(-14);
    const previous = history.slice(-28, -14);
    if (previous.length >= 7) {
      const recentAvg = recent.reduce((s, h) => s + parseFloat(h.qty_sold), 0) / recent.length;
      const prevAvg = previous.reduce((s, h) => s + parseFloat(h.qty_sold), 0) / previous.length;
      if (prevAvg > 0) {
        trendPct = ((recentAvg - prevAvg) / prevAvg) * 100;
      }
    }
  }

  const confidence = forecast.length > 0 && forecast[0].confidence
    ? parseFloat(forecast[0].confidence)
    : detail.model?.metrics?.mape
      ? Math.max(0, 100 - detail.model.metrics.mape)
      : null;

  const leadTime = detail.model?.params?.lead_time_days || null;

  return (
    <WhyBadge
      stockLevel={stockLevel}
      avgDemand={avgDemand}
      daysToStockout={daysToStockout}
      reorderQty={reorderQty}
      trendPct={trendPct}
      leadTimeDays={leadTime}
      algorithm={detail.model?.algorithm}
      confidence={confidence}
      compact={compact}
    />
  );
}