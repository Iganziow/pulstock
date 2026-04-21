"use client";

import { C } from "@/lib/theme";
import type { Detail } from "./types";

const ALG_LABELS: Record<string, string> = {
  simple_avg: "Promedio simple de ventas historicas",
  moving_avg: "Media movil ponderada (mas peso a dias recientes)",
  holt_winters: "Modelo Holt-Winters (captura tendencia + estacionalidad)",
  category_prior: "Basado en productos similares de la categoria",
  croston: "Metodo Croston (especializado en demanda intermitente)",
  croston_sba: "Metodo Croston SBA (demanda intermitente, corregido)",
  ensemble: "Combinacion de multiples modelos (ensemble)",
};

const PATTERN_LABELS: Record<string, { label: string; desc: string; color: string }> = {
  smooth: { label: "Regular", desc: "Se vende de forma constante", color: C.green },
  intermittent: { label: "Intermitente", desc: "Ventas espaciadas con periodos sin movimiento", color: C.amber },
  lumpy: { label: "Irregular", desc: "Ventas infrecuentes y con cantidades muy variables", color: C.red },
  insufficient: { label: "Datos insuficientes", desc: "Muy pocos dias de historial para clasificar", color: C.mute },
};

export function InsightsSection({ model, history, avgDemand, mob }: {
  model: Detail["model"]; history: Detail["history"]; avgDemand: number; mob: boolean;
}) {
  if (!model) return null;
  const p = model.params || {};
  const m = model.metrics || {};

  const insights: { icon: string; text: string }[] = [];

  // 1. Algorithm
  const algLabel = ALG_LABELS[model.algorithm] || model.algorithm;
  insights.push({ icon: "🧠", text: `Metodo: ${algLabel}` });

  // 2. Demand pattern
  const dp = model.demand_pattern || p.demand_pattern;
  if (dp && PATTERN_LABELS[dp]) {
    const pl = PATTERN_LABELS[dp];
    insights.push({ icon: "📊", text: `Patron de demanda: ${pl.label} — ${pl.desc}` });
  }

  // 3. Accuracy
  const mape = m.mape;
  if (mape != null) {
    const acc = Math.round(100 - mape);
    const label = acc >= 85 ? "Excelente" : acc >= 70 ? "Buena" : acc >= 50 ? "Aceptable" : "Baja";
    insights.push({ icon: acc >= 70 ? "✅" : "⚠️", text: `Precision del modelo: ${acc}% (${label}) — error promedio ${Math.round(mape)}%` });
  }

  // 4. Trend
  const trend = p.trend;
  if (trend && trend.direction && trend.direction !== "flat") {
    const pct = trend.slope && avgDemand > 0 ? Math.abs(Math.round((trend.slope / avgDemand) * 30 * 100)) : null;
    const dir = trend.direction === "up" ? "subiendo" : "bajando";
    const txt = pct ? `Tendencia: la demanda viene ${dir} (~${pct}% mensual)` : `Tendencia: la demanda viene ${dir}`;
    insights.push({ icon: trend.direction === "up" ? "📈" : "📉", text: txt });
  }

  // 5. Monthly seasonality (payday effect)
  const ms = p.monthly_seasonality;
  if (ms && typeof ms === "object") {
    const values = Object.values(ms) as number[];
    const max = Math.max(...values);
    const min = Math.min(...values);
    if (max / Math.max(min, 0.01) > 1.15) {
      const peakKey = Object.keys(ms).find(k => ms[k] === max);
      const bucketLabels: Record<string, string> = { early: "inicio de mes (1-5)", mid_early: "primera quincena (6-12)", mid: "mediados (13-19)", mid_late: "antes del dia de pago (20-25)", late: "fin de mes (26-31)" };
      const peakLabel = peakKey ? bucketLabels[peakKey] || peakKey : "";
      const boost = Math.round((max - 1) * 100);
      insights.push({ icon: "💰", text: `Efecto dia de pago: vende ${boost}% mas a ${peakLabel}` });
    }
  }

  // 6. Day of week
  const dow = p.dow_factors;
  if (dow && typeof dow === "object") {
    const dayNames = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"];
    const entries = Object.entries(dow).map(([k, v]) => ({ day: parseInt(k), factor: v as number }));
    if (entries.length >= 5) {
      const best = entries.reduce((a, b) => b.factor > a.factor ? b : a);
      const worst = entries.reduce((a, b) => b.factor < a.factor ? b : a);
      if (best.factor / Math.max(worst.factor, 0.01) > 1.3) {
        insights.push({ icon: "📅", text: `Mejor dia: ${dayNames[best.day] || best.day} (${Math.round((best.factor - 1) * 100)}% sobre promedio) · Peor: ${dayNames[worst.day] || worst.day}` });
      }
    }
  }

  // 7. YoY growth
  const yoy = p.yoy_growth;
  if (yoy && Math.abs(yoy) > 0.05) {
    const pctY = Math.round(yoy * 100);
    insights.push({ icon: pctY > 0 ? "🚀" : "⬇️", text: `Crecimiento anual: ${pctY > 0 ? "+" : ""}${pctY}% respecto al ano pasado` });
  }

  // 8. Bias correction
  const bias = p.bias_correction;
  if (bias && Math.abs(bias) > 0.1) {
    insights.push({ icon: "🔧", text: `Auto-correccion aplicada: el modelo ajusto ${bias > 0 ? "hacia arriba" : "hacia abajo"} para compensar predicciones recientes` });
  }

  // 9. Price sensitivity
  const ps = p.price_sensitivity;
  if (ps && ps.is_sensitive) {
    insights.push({ icon: "💲", text: "Producto sensible al precio: cambios de precio afectan la demanda" });
  }

  // 10. Data quality
  if (model.data_points < 14) {
    insights.push({ icon: "⏳", text: `Solo ${model.data_points} dias de datos — la prediccion mejorara con mas historial` });
  }

  if (insights.length === 0) return null;

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: mob ? "10px 10px" : "14px 16px" }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, marginBottom: 8 }}>
        🔍 ¿Por que el sistema predice esto?
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {insights.map((ins, i) => (
          <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12, color: C.text, lineHeight: 1.5 }}>
            <span style={{ flexShrink: 0, fontSize: 13 }}>{ins.icon}</span>
            <span>{ins.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
