"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

const C = {
  bg: "#0F172A", card: "#1E293B", border: "#334155",
  text: "#F1F5F9", mute: "#94A3B8", accent: "#6366F1",
  green: "#22C55E", red: "#EF4444", yellow: "#F59E0B", white: "#FFFFFF",
};

type Stats = {
  total_tenants: number; active_tenants: number; new_tenants_30d: number;
  total_users: number; total_stores: number;
  subscription_stats: Record<string, number>;
  revenue_30d: number; revenue_total: number; mrr: number;
  past_due: number; suspended: number;
  plan_distribution: { plan_name: string; plan_key: string; count: number }[];
};

type RevenueMonth = { month: string; total: number; count: number };

const fCLP = (n: number) => "$" + n.toLocaleString("es-CL");

function KPI({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: "16px 20px", flex: "1 1 200px" }}>
      <div style={{ fontSize: 11, color: C.mute, textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 800, color: color || C.white }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function StatusBadge({ status, count }: { status: string; count: number }) {
  const colors: Record<string, string> = { active: C.green, trialing: C.accent, past_due: C.yellow, suspended: C.red, cancelled: C.mute };
  const labels: Record<string, string> = { active: "Activas", trialing: "Trial", past_due: "Pago pendiente", suspended: "Suspendidas", cancelled: "Canceladas" };
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0" }}>
      <div style={{ width: 8, height: 8, borderRadius: "50%", background: colors[status] || C.mute }} />
      <span style={{ fontSize: 13, color: C.text, flex: 1 }}>{labels[status] || status}</span>
      <span style={{ fontSize: 14, fontWeight: 700, color: C.white }}>{count}</span>
    </div>
  );
}

export default function SuperadminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [revenue, setRevenue] = useState<RevenueMonth[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      apiFetch("/superadmin/stats/"),
      apiFetch("/superadmin/revenue-chart/"),
    ]).then(([s, r]) => {
      setStats(s);
      setRevenue(r || []);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: 60, color: C.mute }}>
      <div style={{ width: 20, height: 20, border: `2px solid ${C.border}`, borderTopColor: C.accent, borderRadius: "50%", animation: "spin .7s linear infinite" }} />
      Cargando métricas...
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  );

  if (!stats) return <div style={{ color: C.mute, padding: 40 }}>Error cargando datos.</div>;

  const maxRev = Math.max(...revenue.map((r) => r.total), 1);

  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Dashboard</h1>
      <p style={{ color: C.mute, fontSize: 13, marginBottom: 24 }}>Resumen general de la plataforma Pulstock</p>

      {/* KPIs */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 24 }}>
        <KPI label="MRR" value={fCLP(stats.mrr)} sub="Ingreso mensual recurrente" color={C.green} />
        <KPI label="Ingresos 30d" value={fCLP(stats.revenue_30d)} />
        <KPI label="Tenants activos" value={String(stats.active_tenants)} sub={`${stats.new_tenants_30d} nuevos este mes`} />
        <KPI label="Usuarios" value={String(stats.total_users)} sub={`${stats.total_stores} locales`} />
      </div>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
        {/* Suscripciones */}
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 20, flex: "1 1 280px" }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Estado de suscripciones</div>
          {Object.entries(stats.subscription_stats).map(([s, c]) => (
            <StatusBadge key={s} status={s} count={c} />
          ))}
          {stats.past_due > 0 && (
            <div style={{ marginTop: 8, padding: "8px 12px", borderRadius: 8, background: C.yellow + "15", border: `1px solid ${C.yellow}33`, fontSize: 12, color: C.yellow }}>
              {stats.past_due} con pago pendiente · {stats.suspended} suspendidas
            </div>
          )}
        </div>

        {/* Plan distribution */}
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 20, flex: "1 1 280px" }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Distribución por plan</div>
          {stats.plan_distribution.map((p) => {
            const total = stats.plan_distribution.reduce((a, b) => a + b.count, 0);
            const pct = total > 0 ? (p.count / total) * 100 : 0;
            return (
              <div key={p.plan_key} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                  <span>{p.plan_name}</span>
                  <span style={{ fontWeight: 700 }}>{p.count} <span style={{ color: C.mute, fontWeight: 400 }}>({pct.toFixed(0)}%)</span></span>
                </div>
                <div style={{ height: 6, borderRadius: 3, background: C.border }}>
                  <div style={{ height: "100%", borderRadius: 3, background: C.accent, width: `${pct}%`, transition: "width .3s" }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Revenue Chart */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16 }}>Ingresos mensuales</div>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 160 }}>
          {revenue.map((r) => {
            const h = (r.total / maxRev) * 140;
            return (
              <div key={r.month} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                <div style={{ fontSize: 10, color: C.mute }}>{fCLP(r.total)}</div>
                <div style={{ width: "100%", maxWidth: 40, height: Math.max(4, h), borderRadius: "4px 4px 0 0", background: C.accent, transition: "height .3s" }} />
                <div style={{ fontSize: 10, color: C.mute }}>{r.month.slice(5)}</div>
              </div>
            );
          })}
        </div>
        <div style={{ fontSize: 11, color: C.mute, marginTop: 8, textAlign: "right" }}>
          Total acumulado: {fCLP(stats.revenue_total)}
        </div>
      </div>
    </div>
  );
}
