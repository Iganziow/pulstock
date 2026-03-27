"use client";

import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";

// ─── Responsive hook ─────────────────────────────────────────────────────────

function useIsMobile(){const[m,setM]=useState(false);useEffect(()=>{const fn=()=>setM(window.innerWidth<768);fn();window.addEventListener("resize",fn);return()=>window.removeEventListener("resize",fn);},[]);return m;}

// ─── Types ────────────────────────────────────────────────────────────────────

type KPIs = {
  sales_today: { count: number; total: string; profit: string };
  low_stock: { count: number };
  stock_value: { total_value: string; total_items: number };
  pending_purchases: { count: number; total: string };
};

type ChartDay = { date: string; total: string; count: number; profit: string };

type RecentSale = {
  id: number; created_at: string | null; total: string;
  gross_profit: string; status: string;
  warehouse_name: string | null; created_by: string | null;
};

type LowStockItem = {
  product_id: number; product_name: string; sku: string | null;
  warehouse_name: string; on_hand: string; min_stock: string; deficit: string;
};

type DashboardData = {
  generated_at: string;
  store_id: number;
  kpis: KPIs;
  chart: ChartDay[];
  recent_sales: RecentSale[];
  low_stock_items: LowStockItem[];
  onboarding: { has_products: boolean; products_count: number };
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatCLP(v: string | number): string {
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "$0";
  return "$" + Math.round(n).toLocaleString("es-CL");
}

function formatNum(v: string | number): string {
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "0";
  return n.toLocaleString("es-CL");
}

function shortDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("es-CL", { day: "2-digit", month: "short" });
  } catch { return iso; }
}

function shortTime(iso: string | null): string {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });
  } catch { return "-"; }
}

function dayLabel(iso: string): string {
  try {
    const d = new Date(iso + "T12:00:00");
    const days = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
    return days[d.getDay()] + " " + d.getDate();
  } catch { return iso; }
}

// ─── Mini-components ──────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
      <svg width={28} height={28} viewBox="0 0 24 24" fill="none"
        stroke={C.mute} strokeWidth="2.5" strokeLinecap="round"
        style={{ animation: "spin 0.7s linear infinite" }}>
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
      </svg>
    </div>
  );
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

function KPICard({ title, value, subtitle, icon, bgColor, borderColor, href, animClass }: {
  title: string; value: string; subtitle?: string;
  icon: string; color: string; bgColor: string; borderColor: string;
  href?: string; animClass?: string;
}) {
  const content = (
    <div className={animClass} style={{
      background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`,
      padding: "20px 22px", boxShadow: C.sh, display: "flex", gap: 16, alignItems: "flex-start",
      transition: C.ease, cursor: href ? "pointer" : "default",
    }}
    onMouseEnter={e => { if (href) { (e.currentTarget as HTMLElement).style.boxShadow = C.shMd; (e.currentTarget as HTMLElement).style.borderColor = borderColor; } }}
    onMouseLeave={e => { if (href) { (e.currentTarget as HTMLElement).style.boxShadow = C.sh; (e.currentTarget as HTMLElement).style.borderColor = C.border; } }}
    >
      <div style={{
        width: 44, height: 44, borderRadius: C.rMd,
        background: bgColor, border: `1px solid ${borderColor}`,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 20, flexShrink: 0,
      }}>
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 500, color: C.mute, letterSpacing: "0.03em", textTransform: "uppercase", marginBottom: 4 }}>
          {title}
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: C.text, fontFamily: C.mono, lineHeight: 1.1 }}>
          {value}
        </div>
        {subtitle && (
          <div style={{ fontSize: 12, color: C.mid, marginTop: 4, fontWeight: 500 }}>
            {subtitle}
          </div>
        )}
      </div>
    </div>
  );

  if (href) return <Link href={href} style={{ textDecoration: "none", color: "inherit" }}>{content}</Link>;
  return content;
}

// ─── Simple Bar Chart (pure CSS, no deps) ─────────────────────────────────────

function BarChart({ data }: { data: ChartDay[] }) {
  const values = data.map(d => Number(d.total));
  const maxVal = Math.max(...values, 1);

  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 8, height: 160, padding: "0 4px" }}>
      {data.map((d, i) => {
        const val = Number(d.total);
        const pct = Math.max((val / maxVal) * 100, 2);
        const isToday = i === data.length - 1;
        return (
          <div key={d.date} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: C.mid, fontFamily: C.mono }}>
              {val > 0 ? formatCLP(val) : ""}
            </div>
            <div
              style={{
                width: "100%", maxWidth: 56,
                height: `${pct}%`, minHeight: 4,
                background: isToday ? C.accent : "#C7D2FE",
                borderRadius: "6px 6px 2px 2px",
                transition: "height 0.4s ease",
              }}
              title={`${dayLabel(d.date)}: ${formatCLP(val)} (${d.count} ventas)`}
            />
            <div style={{
              fontSize: 11, fontWeight: isToday ? 700 : 500,
              color: isToday ? C.accent : C.mute,
            }}>
              {dayLabel(d.date)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Status Badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; color: string; border: string; label: string }> = {
    COMPLETED: { bg: C.greenBg, color: C.green, border: C.greenBd, label: "Completada" },
    VOID:      { bg: C.redBg,   color: C.red,   border: C.redBd,   label: "Anulada" },
    DRAFT:     { bg: C.amberBg, color: C.amber,  border: C.amberBd, label: "Borrador" },
    POSTED:    { bg: C.accentBg, color: C.accent, border: C.accentBd, label: "Publicada" },
  };
  const s = map[status] || { bg: "#F4F4F5", color: C.mid, border: C.border, label: status };
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 99,
      fontSize: 11, fontWeight: 600, background: s.bg, color: s.color,
      border: `1px solid ${s.border}`,
    }}>
      {s.label}
    </span>
  );
}

// ─── Onboarding (empty state) ─────────────────────────────────────────────────

function OnboardingCard() {
  const steps = [
    { icon: "📦", title: "Crea tu primer producto", desc: "Agrega los productos que vendes", href: "/dashboard/catalog" },
    { icon: "🏪", title: "Agrega stock", desc: "Registra inventario en tu bodega", href: "/dashboard/inventory/stock" },
    { icon: "💰", title: "Haz tu primera venta", desc: "Usa el punto de venta", href: "/dashboard/pos" },
  ];

  return (
    <div className="fade-in" style={{
      background: C.surface, borderRadius: C.rLg, border: `1px solid ${C.accentBd}`,
      padding: 32, boxShadow: C.shMd, maxWidth: 640, margin: "40px auto",
    }}>
      <div style={{ textAlign: "center", marginBottom: 28 }}>
        <div style={{ fontSize: 32, marginBottom: 8 }}>🚀</div>
        <h2 style={{ fontSize: 22, fontWeight: 700, color: C.text, margin: 0 }}>
          ¡Bienvenido a tu sistema de inventario!
        </h2>
        <p style={{ fontSize: 14, color: C.mid, marginTop: 8 }}>
          Configura tu negocio en 3 pasos simples
        </p>
      </div>

      <div style={{ display: "grid", gap: 12 }}>
        {steps.map((step, i) => (
          <Link key={i} href={step.href} style={{ textDecoration: "none", color: "inherit" }}>
            <div className="xb" style={{
              display: "flex", alignItems: "center", gap: 16,
              padding: "16px 20px", borderRadius: C.rMd,
              border: `1px solid ${C.border}`, background: C.bg,
              transition: C.ease,
            }}>
              <div style={{
                width: 42, height: 42, borderRadius: "50%",
                background: C.accentBg, border: `1px solid ${C.accentBd}`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 18, flexShrink: 0,
              }}>
                {step.icon}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>{step.title}</div>
                <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>{step.desc}</div>
              </div>
              <div style={{ color: C.mute, fontSize: 18 }}>→</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

const PAGE_CSS = `
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.fade-in{animation:fadeIn 0.3s ease both}
.fade-in-d1{animation:fadeIn 0.3s ease 0.05s both}
.fade-in-d2{animation:fadeIn 0.3s ease 0.1s both}
.fade-in-d3{animation:fadeIn 0.3s ease 0.15s both}
.fade-in-d4{animation:fadeIn 0.3s ease 0.2s both}
`;

export default function DashboardPage() {
  useGlobalStyles(PAGE_CSS);
  const mob = useIsMobile();

  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await apiFetch("/dashboard/summary/");
      setData(res);
    } catch (e: any) {
      setError(e?.message || "Error al cargar dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh cada 2 minutos
  useEffect(() => {
    const id = setInterval(load, 120_000);
    return () => clearInterval(id);
  }, [load]);

  if (loading && !data) return <div style={{ background: C.bg, minHeight: "100vh", padding: 24 }}><Spinner /></div>;

  if (error && !data) {
    return (
      <div style={{ background: C.bg, minHeight: "100vh", padding: 24 }}>
        <div style={{
          background: C.redBg, border: `1px solid ${C.redBd}`,
          borderRadius: C.rMd, padding: 20, color: C.red, fontSize: 14,
          maxWidth: 500, margin: "60px auto", textAlign: "center",
        }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Error al cargar el dashboard</div>
          <div style={{ color: C.mid }}>{error}</div>
          <button onClick={load} className="xb" style={{
            marginTop: 16, padding: "8px 20px", borderRadius: C.r,
            border: `1px solid ${C.redBd}`, background: C.surface,
            color: C.red, fontWeight: 600, fontSize: 13,
          }}>
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  // Si no tiene productos, mostrar onboarding
  if (!data.onboarding.has_products) {
    return (
      <div style={{ background: C.bg, minHeight: "100vh", padding: 24, fontFamily: C.font }}>
        <OnboardingCard />
      </div>
    );
  }

  const k = data.kpis;

  return (
    <div style={{ background: C.bg, minHeight: "100vh", fontFamily: C.font }}>
      {/* Header */}
      <div style={{
        padding: mob ? "16px 12px 12px" : "20px 24px 16px", display: "flex", alignItems: "center",
        justifyContent: "space-between", flexWrap: "wrap", gap: 8,
      }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: C.text, margin: 0 }}>Dashboard</h1>
          <p style={{ fontSize: 13, color: C.mute, margin: "4px 0 0" }}>
            Resumen de tu negocio hoy
          </p>
        </div>
        <button onClick={load} className="xb" disabled={loading} style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "8px 14px", borderRadius: C.r,
          border: `1px solid ${C.borderMd}`, background: C.surface,
          color: C.mid, fontWeight: 600, fontSize: 12,
        }}>
          {loading ? (
            <svg width={14} height={14} viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
              style={{ animation: "spin 0.7s linear infinite" }}>
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
          ) : "↻"} Actualizar
        </button>
      </div>

      <div style={{ padding: mob ? "0 12px 24px" : "0 24px 32px" }}>

        {/* KPI Cards */}
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(auto-fit, minmax(220px, 1fr))", gap: mob ? 10 : 16, marginBottom: 24 }}>
          <KPICard
            title="Ventas Hoy"
            value={formatCLP(k.sales_today.total)}
            subtitle={`${k.sales_today.count} venta${k.sales_today.count !== 1 ? "s" : ""} · Utilidad ${formatCLP(k.sales_today.profit)}`}
            icon="💰" color={C.green} bgColor={C.greenBg} borderColor={C.greenBd}
            href="/dashboard/sales" animClass="fade-in"
          />
          <KPICard
            title="Stock Bajo Mínimo"
            value={String(k.low_stock.count)}
            subtitle={k.low_stock.count > 0 ? "Productos necesitan reposición" : "Todo en orden ✓"}
            icon={k.low_stock.count > 0 ? "⚠️" : "✅"}
            color={k.low_stock.count > 0 ? C.amber : C.green}
            bgColor={k.low_stock.count > 0 ? C.amberBg : C.greenBg}
            borderColor={k.low_stock.count > 0 ? C.amberBd : C.greenBd}
            href="/dashboard/inventory/stock" animClass="fade-in-d1"
          />
          <KPICard
            title="Stock Valorizado"
            value={formatCLP(k.stock_value.total_value)}
            subtitle={`${formatNum(k.stock_value.total_items)} ítems en bodega`}
            icon="📊" color={C.accent} bgColor={C.accentBg} borderColor={C.accentBd}
            href="/dashboard/reports" animClass="fade-in-d2"
          />
          <KPICard
            title="Compras Pendientes"
            value={String(k.pending_purchases.count)}
            subtitle={k.pending_purchases.count > 0 ? `Total ${formatCLP(k.pending_purchases.total)}` : "Sin borradores"}
            icon="📋" color={C.violet} bgColor={C.violetBg} borderColor={C.violetBd}
            href="/dashboard/purchases" animClass="fade-in-d3"
          />
        </div>

        {/* 2-column layout: Chart + Low Stock */}
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 1fr", gap: 16, marginBottom: 24 }}>

          {/* Chart */}
          <div className="fade-in-d2" style={{
            background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`,
            padding: 22, boxShadow: C.sh,
          }}>
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              marginBottom: 18,
            }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, color: C.text, margin: 0 }}>
                Ventas últimos 7 días
              </h3>
              <Link href="/dashboard/sales" style={{
                fontSize: 12, fontWeight: 600, color: C.accent,
                textDecoration: "none",
              }}>
                Ver todas →
              </Link>
            </div>
            <BarChart data={data.chart} />
          </div>

          {/* Low Stock */}
          <div className="fade-in-d3" style={{
            background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`,
            padding: 22, boxShadow: C.sh,
          }}>
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              marginBottom: 18,
            }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, color: C.text, margin: 0 }}>
                ⚠️ Stock bajo mínimo
              </h3>
              <Link href="/dashboard/inventory/stock" style={{
                fontSize: 12, fontWeight: 600, color: C.accent,
                textDecoration: "none",
              }}>
                Ver stock →
              </Link>
            </div>

            {data.low_stock_items.length === 0 ? (
              <div style={{
                display: "flex", flexDirection: "column", alignItems: "center",
                justifyContent: "center", padding: "30px 0", color: C.mute,
              }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>✅</div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>Todos los productos tienen stock suficiente</div>
              </div>
            ) : (
              <div style={{ display: "grid", gap: 8 }}>
                {data.low_stock_items.map((item) => (
                  <div key={item.product_id} style={{
                    display: "flex", alignItems: "center", gap: 12,
                    padding: "10px 12px", borderRadius: C.r,
                    background: C.bg, border: `1px solid ${C.border}`,
                  }}>
                    <div style={{
                      width: 8, height: 8, borderRadius: "50%",
                      background: Number(item.on_hand) <= 0 ? C.red : C.amber,
                      flexShrink: 0,
                    }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 13, fontWeight: 600, color: C.text,
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                      }}>
                        {item.product_name}
                      </div>
                      <div style={{ fontSize: 11, color: C.mute }}>
                        {item.warehouse_name}
                        {item.sku ? ` · ${item.sku}` : ""}
                      </div>
                    </div>
                    <div style={{ textAlign: "right", flexShrink: 0 }}>
                      <div style={{
                        fontSize: 14, fontWeight: 700, fontFamily: C.mono,
                        color: Number(item.on_hand) <= 0 ? C.red : C.amber,
                      }}>
                        {formatNum(item.on_hand)}
                      </div>
                      <div style={{ fontSize: 10, color: C.mute }}>
                        mín: {formatNum(item.min_stock)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Recent Sales Table */}
        <div className="fade-in-d4" style={{
          background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`,
          boxShadow: C.sh, overflow: "hidden",
        }}>
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "18px 22px 14px",
          }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, color: C.text, margin: 0 }}>
              Últimas ventas
            </h3>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <Link href="/dashboard/pos" className="xb" style={{
                display: "inline-flex", alignItems: "center", gap: 4,
                padding: "6px 14px", borderRadius: C.r,
                background: C.accent, color: "#fff",
                fontWeight: 600, fontSize: 12, textDecoration: "none",
                border: `1px solid ${C.accent}`,
              }}>
                + Nueva Venta
              </Link>
              <Link href="/dashboard/sales" style={{
                fontSize: 12, fontWeight: 600, color: C.accent,
                textDecoration: "none", display: "flex", alignItems: "center",
              }}>
                Ver todas →
              </Link>
            </div>
          </div>

          {data.recent_sales.length === 0 ? (
            <div style={{
              padding: "32px 22px", textAlign: "center", color: C.mute,
            }}>
              <div style={{ fontSize: 28, marginBottom: 8 }}>🧾</div>
              <div style={{ fontSize: 13, fontWeight: 500 }}>No hay ventas registradas aún</div>
              <Link href="/dashboard/pos" style={{
                display: "inline-block", marginTop: 12,
                padding: "8px 20px", borderRadius: C.r,
                background: C.accent, color: "#fff",
                fontWeight: 600, fontSize: 13, textDecoration: "none",
              }}>
                Ir al POS
              </Link>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{
                width: "100%", borderCollapse: "collapse",
                fontSize: 13, color: C.text,
              }}>
                <thead>
                  <tr style={{ borderTop: `1px solid ${C.border}`, borderBottom: `1px solid ${C.border}` }}>
                    {(mob ? ["#", "Fecha", "Total", "Estado"] : ["#", "Fecha", "Hora", "Total", "Utilidad", "Estado", "Cajero", "Bodega"]).map(h => (
                      <th key={h} style={{
                        padding: "10px 14px", textAlign: "left",
                        fontWeight: 600, fontSize: 11, color: C.mute,
                        textTransform: "uppercase", letterSpacing: "0.04em",
                        background: C.bg,
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.recent_sales.map((s) => (
                    <tr key={s.id} className="prow"
                      onClick={() => { window.location.href = `/dashboard/sales/${s.id}`; }}
                      style={{ borderBottom: `1px solid ${C.border}` }}
                    >
                      <td style={{ padding: "10px 14px", fontWeight: 600, fontFamily: C.mono, fontSize: 12 }}>
                        #{s.id}
                      </td>
                      <td style={{ padding: "10px 14px" }}>
                        {s.created_at ? shortDate(s.created_at) : "-"}
                      </td>
                      {!mob && <td style={{ padding: "10px 14px", fontFamily: C.mono, fontSize: 12, color: C.mid }}>
                        {shortTime(s.created_at)}
                      </td>}
                      <td style={{ padding: "10px 14px", fontWeight: 600, fontFamily: C.mono }}>
                        {formatCLP(s.total)}
                      </td>
                      {!mob && <td style={{
                        padding: "10px 14px", fontFamily: C.mono, fontSize: 12,
                        color: Number(s.gross_profit) >= 0 ? C.green : C.red,
                      }}>
                        {formatCLP(s.gross_profit)}
                      </td>}
                      <td style={{ padding: "10px 14px" }}>
                        <StatusBadge status={s.status} />
                      </td>
                      {!mob && <td style={{ padding: "10px 14px", color: C.mid }}>
                        {s.created_by || "-"}
                      </td>}
                      {!mob && <td style={{ padding: "10px 14px", color: C.mute, fontSize: 12 }}>
                        {s.warehouse_name || "-"}
                      </td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Quick Actions */}
        <div className="fade-in-d4" style={{
          display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(auto-fit, minmax(200px, 1fr))",
          gap: mob ? 8 : 12, marginTop: 24,
        }}>
          {[
            { label: "Punto de Venta", icon: "🛒", href: "/dashboard/pos", desc: "Registrar venta" },
            { label: "Nueva Compra", icon: "📥", href: "/dashboard/purchases/new", desc: "Ingresar factura" },
            { label: "Ver Catálogo", icon: "📦", href: "/dashboard/catalog", desc: "Productos y categorías" },
            { label: "Ver Reportes", icon: "📊", href: "/dashboard/reports", desc: "Stock, Kardex, Sugeridos" },
          ].map(a => (
            <Link key={a.href} href={a.href} style={{ textDecoration: "none", color: "inherit" }}>
              <div className="xb" style={{
                display: "flex", alignItems: "center", gap: 14,
                padding: "14px 18px", borderRadius: C.rMd,
                background: C.surface, border: `1px solid ${C.border}`,
                boxShadow: C.sh, transition: C.ease,
              }}>
                <span style={{ fontSize: 20 }}>{a.icon}</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{a.label}</div>
                  <div style={{ fontSize: 11, color: C.mute }}>{a.desc}</div>
                </div>
              </div>
            </Link>
          ))}
        </div>

      </div>
    </div>
  );
}