"use client";
import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";

const C = {
  bg: "#0F172A", card: "#1E293B", border: "#334155",
  text: "#F1F5F9", mute: "#94A3B8", accent: "#6366F1",
  green: "#22C55E", red: "#EF4444", yellow: "#F59E0B",
  violet: "#8B5CF6", cyan: "#06B6D4", white: "#FFFFFF",
};

const ALGO_LABELS: Record<string, string> = {
  ensemble: "Ensemble", holt_winters: "Holt-Winters", moving_avg: "Media Móvil",
  simple_avg: "Media Simple", category_prior: "Prior Categoría",
  croston: "Croston", croston_sba: "Croston SBA",
};
const CONF_LABELS: Record<string, string> = {
  very_high: "Muy alta", high: "Alta", medium: "Media", low: "Baja", very_low: "Muy baja",
};
const CONF_COLORS: Record<string, string> = {
  very_high: C.green, high: "#4ADE80", medium: C.yellow, low: "#FB923C", very_low: C.red,
};
const PATTERN_LABELS: Record<string, string> = {
  smooth: "Suave", intermittent: "Intermitente", lumpy: "Irregular", insufficient: "Insuficiente",
};

type ForecastData = {
  total_active_models: number;
  global_avg_mape: number;
  by_tenant: { tenant_name: string; tenant_id: number; model_count: number; avg_mape: number }[];
  by_algorithm: { algorithm: string; count: number }[];
  by_confidence: { confidence: string; count: number }[];
  by_pattern: { demand_pattern: string; count: number }[];
  model_health: { improved: number; worsened: number; unchanged: number };
  accuracy_trend: { date: string; avg_error: number; predictions: number }[];
  recent_7d: { avg_pct_error: number; total_predictions: number };
};

function KpiCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{
      background: C.card, border: `1px solid ${C.border}`, borderRadius: 14, padding: "18px 22px",
      flex: "1 1 200px", minWidth: 180,
    }}>
      <div style={{ fontSize: 11, color: C.mute, textTransform: "uppercase", fontWeight: 600, letterSpacing: ".05em" }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 800, color: color || C.white, marginTop: 4 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function BarChart({ data, labelKey, valueKey, colorFn, labelMap }: {
  data: { [k: string]: any }[];
  labelKey: string; valueKey: string;
  colorFn?: (key: string) => string;
  labelMap?: Record<string, string>;
}) {
  const max = Math.max(...data.map((d) => d[valueKey]), 1);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {data.map((d, i) => {
        const label = labelMap?.[d[labelKey]] || d[labelKey] || "—";
        const pct = (d[valueKey] / max) * 100;
        const color = colorFn?.(d[labelKey]) || C.accent;
        return (
          <div key={i}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
              <span style={{ color: C.text, fontWeight: 600 }}>{label}</span>
              <span style={{ color: C.mute }}>{d[valueKey]}</span>
            </div>
            <div style={{ height: 8, background: C.bg, borderRadius: 4, overflow: "hidden" }}>
              <div style={{
                height: "100%", width: `${pct}%`, borderRadius: 4,
                background: `linear-gradient(90deg, ${color}, ${color}CC)`,
                transition: "width .5s ease",
              }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MiniLineChart({ data }: { data: { date: string; avg_error: number; predictions: number }[] }) {
  if (data.length < 2) return <div style={{ color: C.mute, fontSize: 13, padding: 20 }}>Sin datos suficientes</div>;
  const maxErr = Math.max(...data.map((d) => d.avg_error), 1);
  const w = 100;
  const h = 40;
  const points = data.map((d, i) => ({
    x: (i / (data.length - 1)) * w,
    y: h - (d.avg_error / maxErr) * (h - 4),
  }));
  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const areaD = pathD + ` L ${w} ${h} L 0 ${h} Z`;

  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: 120 }} preserveAspectRatio="none">
        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.accent} stopOpacity="0.3" />
            <stop offset="100%" stopColor={C.accent} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaD} fill="url(#areaGrad)" />
        <path d={pathD} fill="none" stroke={C.accent} strokeWidth="0.6" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="0.8" fill={C.accent} />
        ))}
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.mute, marginTop: 4 }}>
        <span>{data[0].date.slice(5)}</span>
        <span>{data[data.length - 1].date.slice(5)}</span>
      </div>
    </div>
  );
}

export default function ForecastMetricsPage() {
  const [data, setData] = useState<ForecastData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch("/superadmin/forecast/");
      setData(res);
    } catch (e: any) {
      setError(e.message || "Error al cargar métricas");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh", color: C.mute }}>
      Cargando métricas de forecast...
    </div>
  );

  if (error) return (
    <div style={{ padding: 40, textAlign: "center" }}>
      <div style={{ color: C.red, fontSize: 15, marginBottom: 12 }}>{error}</div>
      <button onClick={load} style={{ padding: "8px 20px", borderRadius: 8, background: C.accent, color: C.white, border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600 }}>Reintentar</button>
    </div>
  );

  if (!data) return null;

  const healthTotal = data.model_health.improved + data.model_health.worsened + data.model_health.unchanged;
  const healthPcts = {
    improved: healthTotal ? ((data.model_health.improved / healthTotal) * 100).toFixed(0) : "0",
    worsened: healthTotal ? ((data.model_health.worsened / healthTotal) * 100).toFixed(0) : "0",
    unchanged: healthTotal ? ((data.model_health.unchanged / healthTotal) * 100).toFixed(0) : "0",
  };

  const mapeColor = data.global_avg_mape <= 15 ? C.green : data.global_avg_mape <= 30 ? C.yellow : C.red;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Forecast IA — Métricas</h1>
          <p style={{ color: C.mute, fontSize: 13 }}>Supervisión de modelos de predicción de demanda</p>
        </div>
        <button onClick={load} style={{
          padding: "8px 16px", borderRadius: 8, background: C.card, border: `1px solid ${C.border}`,
          color: C.mute, fontSize: 12, fontWeight: 600, cursor: "pointer",
        }}>Actualizar</button>
      </div>

      {/* KPIs */}
      <div style={{ display: "flex", gap: 14, marginBottom: 24, flexWrap: "wrap" }}>
        <KpiCard label="Modelos activos" value={String(data.total_active_models)} sub="En toda la plataforma" />
        <KpiCard label="MAPE promedio" value={`${data.global_avg_mape}%`} sub="Error porcentual medio" color={mapeColor} />
        <KpiCard label="Predicciones 7d" value={data.recent_7d.total_predictions.toLocaleString()} sub={`Error prom: ${data.recent_7d.avg_pct_error}%`} color={C.cyan} />
        <KpiCard
          label="Salud de modelos"
          value={`${healthPcts.improved}% mejor`}
          sub={`${data.model_health.improved} mejoraron · ${data.model_health.worsened} empeoraron`}
          color={data.model_health.improved >= data.model_health.worsened ? C.green : C.red}
        />
      </div>

      {/* Charts row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
        {/* Accuracy trend */}
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 14, padding: 22 }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Tendencia de error (30 días)</div>
          <MiniLineChart data={data.accuracy_trend} />
          <div style={{ fontSize: 11, color: C.mute, marginTop: 8, textAlign: "center" }}>
            Error porcentual absoluto promedio diario
          </div>
        </div>

        {/* Model health donut-like */}
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 14, padding: 22 }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 16 }}>Evolución de modelos</div>
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <div style={{ flex: 1 }}>
              {[
                { label: "Mejoraron", val: data.model_health.improved, color: C.green },
                { label: "Sin cambio", val: data.model_health.unchanged, color: C.mute },
                { label: "Empeoraron", val: data.model_health.worsened, color: C.red },
              ].map((item) => {
                const pct = healthTotal ? (item.val / healthTotal) * 100 : 0;
                return (
                  <div key={item.label} style={{ marginBottom: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                      <span style={{ color: item.color, fontWeight: 600 }}>{item.label}</span>
                      <span style={{ color: C.mute }}>{item.val} ({pct.toFixed(0)}%)</span>
                    </div>
                    <div style={{ height: 6, background: C.bg, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${pct}%`, background: item.color, borderRadius: 3, transition: "width .5s" }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Distribution row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 24 }}>
        {/* By algorithm */}
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 14, padding: 22 }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>Por algoritmo</div>
          <BarChart
            data={data.by_algorithm}
            labelKey="algorithm" valueKey="count"
            labelMap={ALGO_LABELS}
            colorFn={() => C.accent}
          />
        </div>

        {/* By confidence */}
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 14, padding: 22 }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>Por confianza</div>
          <BarChart
            data={data.by_confidence}
            labelKey="confidence" valueKey="count"
            labelMap={CONF_LABELS}
            colorFn={(k) => CONF_COLORS[k] || C.mute}
          />
        </div>

        {/* By demand pattern */}
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 14, padding: 22 }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>Patrón de demanda</div>
          <BarChart
            data={data.by_pattern}
            labelKey="demand_pattern" valueKey="count"
            labelMap={PATTERN_LABELS}
            colorFn={() => C.violet}
          />
        </div>
      </div>

      {/* By tenant table */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 14, overflow: "hidden" }}>
        <div style={{ padding: "16px 22px", borderBottom: `1px solid ${C.border}`, fontSize: 14, fontWeight: 700 }}>
          Modelos por negocio
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: C.bg, borderBottom: `1px solid ${C.border}` }}>
              {["Negocio", "Modelos", "MAPE prom.", "Estado"].map((h) => (
                <th key={h} style={{
                  padding: "10px 16px", textAlign: "left", color: C.mute,
                  fontWeight: 600, fontSize: 11, textTransform: "uppercase",
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.by_tenant.length === 0 ? (
              <tr><td colSpan={4} style={{ padding: 30, textAlign: "center", color: C.mute }}>Sin modelos activos</td></tr>
            ) : data.by_tenant.map((t) => {
              const mColor = t.avg_mape <= 15 ? C.green : t.avg_mape <= 30 ? C.yellow : C.red;
              const mLabel = t.avg_mape <= 15 ? "Excelente" : t.avg_mape <= 30 ? "Aceptable" : "Revisar";
              return (
                <tr key={t.tenant_id} style={{ borderBottom: `1px solid ${C.border}22` }}>
                  <td style={{ padding: "12px 16px", fontWeight: 600 }}>{t.tenant_name}</td>
                  <td style={{ padding: "12px 16px" }}>{t.model_count}</td>
                  <td style={{ padding: "12px 16px", fontWeight: 700, color: mColor }}>{t.avg_mape}%</td>
                  <td style={{ padding: "12px 16px" }}>
                    <span style={{
                      padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700,
                      background: mColor + "20", color: mColor,
                    }}>{mLabel}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
