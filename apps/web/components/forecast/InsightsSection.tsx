"use client";

import { C } from "@/lib/theme";
import type { Detail } from "./types";

// Etiquetas cortas y simples para cada algoritmo. Antes eran descripciones
// técnicas tipo "Holt-Winters captura tendencia + estacionalidad". Mario y
// otros dueños de cafetería NO necesitan saber el nombre del algoritmo —
// sólo qué tipo de cálculo usamos en términos humanos.
const ALG_LABELS: Record<string, string> = {
  simple_avg: "Promedio de tus ventas pasadas",
  moving_avg: "Promedio dando más peso a los últimos días",
  holt_winters: "Mirando ventas pasadas + temporada (estacional)",
  category_prior: "Comparando con productos parecidos de la categoría",
  croston: "Especial para productos que vendes esporádicamente",
  croston_sba: "Especial para productos que vendes esporádicamente",
  ensemble: "Combinando varios métodos para mejor resultado",
};

const PATTERN_LABELS: Record<string, { label: string; desc: string; color: string }> = {
  smooth: { label: "Estable", desc: "se vende parejo todos los días", color: C.green },
  intermittent: { label: "A intervalos", desc: "se vende solo algunos días, no todos", color: C.amber },
  lumpy: { label: "Irregular", desc: "días buenos y malos muy distintos", color: C.red },
  insufficient: { label: "Pocos datos", desc: "todavía no hay suficientes ventas para clasificar", color: C.mute },
};

// Helpers seguros para arrays/objetos vacíos. Math.max/min con array vacío
// retorna -Infinity / Infinity → bugs sutiles. Estas versiones devuelven
// null y los callers chequean.
function safeMax(values: number[]): number | null {
  const finite = values.filter((v) => Number.isFinite(v));
  return finite.length === 0 ? null : Math.max(...finite);
}
function safeMin(values: number[]): number | null {
  const finite = values.filter((v) => Number.isFinite(v));
  return finite.length === 0 ? null : Math.min(...finite);
}

export function InsightsSection({ model, history, avgDemand, mob }: {
  model: Detail["model"]; history: Detail["history"]; avgDemand: number; mob: boolean;
}) {
  if (!model) return null;
  const p = model.params || {};
  const m = model.metrics || {};

  const insights: { icon: string; text: string }[] = [];

  // 1. Algorithm — cómo se calculó la predicción
  const algLabel = ALG_LABELS[model.algorithm] || "Promedio de tus ventas";
  insights.push({ icon: "🧠", text: `Cómo lo calculamos: ${algLabel}` });

  // 2. Demand pattern — estilo de venta
  const dp = model.demand_pattern || p.demand_pattern;
  if (dp && PATTERN_LABELS[dp]) {
    const pl = PATTERN_LABELS[dp];
    insights.push({ icon: "📊", text: `Estilo de venta: ${pl.label} — ${pl.desc}` });
  }

  // (Antes había un insight de "Qué tan acertada es" basado en MAPE, pero
  //  cuando el modelo está aprendiendo el porcentaje es bajo y el cliente
  //  piensa que la app no funciona. Es una métrica interna de debugging,
  //  no algo que el dueño de la cafetería deba ver.)

  // 4. Trend — está vendiendo más o menos
  const trend = p.trend;
  if (trend && trend.direction && trend.direction !== "flat") {
    const slope = typeof trend.slope === "number" ? trend.slope : 0;
    const pct = avgDemand > 0 && Number.isFinite(slope)
      ? Math.abs(Math.round((slope / avgDemand) * 30 * 100))
      : null;
    const dir = trend.direction === "up" ? "subiendo" : "bajando";
    const txt = pct
      ? `Tendencia: las ventas vienen ${dir} (~${pct}% al mes)`
      : `Tendencia: las ventas vienen ${dir}`;
    insights.push({ icon: trend.direction === "up" ? "📈" : "📉", text: txt });
  }

  // 5. Monthly seasonality — efecto del día de pago
  const ms = p.monthly_seasonality;
  if (ms && typeof ms === "object") {
    const values = Object.values(ms) as number[];
    const max = safeMax(values);
    const min = safeMin(values);
    if (max !== null && min !== null && max / Math.max(min, 0.01) > 1.15) {
      const peakKey = Object.keys(ms).find((k) => ms[k] === max);
      const bucketLabels: Record<string, string> = {
        early: "a principio de mes",
        mid_early: "los primeros 15 días",
        mid: "a mediados de mes",
        mid_late: "antes de fin de mes",
        late: "a fin de mes",
      };
      const peakLabel = peakKey ? bucketLabels[peakKey] || peakKey : "";
      const boost = Math.round((max - 1) * 100);
      if (boost > 0 && peakLabel) {
        insights.push({ icon: "💰", text: `Vendés ${boost}% más ${peakLabel}` });
      }
    }
  }

  // 6. Day of week — mejor y peor día
  const dow = p.dow_factors;
  if (dow && typeof dow === "object") {
    const dayNames = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
    const entries = Object.entries(dow)
      .map(([k, v]) => ({ day: parseInt(k), factor: v as number }))
      .filter((e) => Number.isFinite(e.factor) && e.factor > 0);
    if (entries.length >= 5) {
      const best = entries.reduce((a, b) => (b.factor > a.factor ? b : a));
      const worst = entries.reduce((a, b) => (b.factor < a.factor ? b : a));
      if (best.factor / Math.max(worst.factor, 0.01) > 1.3) {
        const bestPct = Math.round((best.factor - 1) * 100);
        insights.push({
          icon: "📅",
          text: `Tu mejor día es el ${dayNames[best.day] || best.day} (${bestPct > 0 ? "+" : ""}${bestPct}% sobre el promedio). El más flojo: ${dayNames[worst.day] || worst.day}.`,
        });
      }
    }
  }

  // 7. Year-over-year growth — comparado con el año pasado
  const yoy = p.yoy_growth;
  if (typeof yoy === "number" && Number.isFinite(yoy) && Math.abs(yoy) > 0.05) {
    const pctY = Math.round(yoy * 100);
    insights.push({
      icon: pctY > 0 ? "🚀" : "⬇️",
      text: pctY > 0
        ? `Estás vendiendo +${pctY}% comparado al año pasado`
        : `Estás vendiendo ${pctY}% comparado al año pasado`,
    });
  }

  // 8. Bias correction — auto-ajuste interno (lo dejamos solo si es notorio)
  const bias = p.bias_correction;
  if (typeof bias === "number" && Math.abs(bias) > 0.1) {
    insights.push({
      icon: "🔧",
      text: `Ajustamos la predicción ${bias > 0 ? "hacia arriba" : "hacia abajo"} porque las últimas semanas vendiste ${bias > 0 ? "más" : "menos"} de lo esperado`,
    });
  }

  // 9. Price sensitivity
  const ps = p.price_sensitivity;
  if (ps && ps.is_sensitive) {
    insights.push({
      icon: "💲",
      text: "Los cambios de precio afectan mucho cuánto se vende — tenelo en cuenta si subís precio",
    });
  }

  // (Antes mostrábamos "Tenemos N días de tus ventas — la predicción se
  //  vuelve más certera con el tiempo". El cliente lo leía como "la app no
  //  tiene datos suficientes" y le generaba dudas. Es información interna,
  //  no algo que el dueño de la cafetería deba ver.)
  //
  // SÍ mostramos el mensaje cuando NO hay ventas registradas para ese
  // producto, porque ahí sí es útil saber que la predicción se basa en
  // productos parecidos (transparencia) y NO en datos propios todavía.
  const dpts = typeof model.data_points === "number" ? model.data_points : 0;
  if (dpts === 0) {
    insights.push({
      icon: "ℹ️",
      text: "Aún no hay ventas registradas de este producto. Mientras tanto, calculamos la predicción mirando productos parecidos.",
    });
  }

  if (insights.length === 0) return null;

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: mob ? "10px 10px" : "14px 16px" }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, marginBottom: 8 }}>
        🔍 ¿Por qué te sugerimos esto?
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
