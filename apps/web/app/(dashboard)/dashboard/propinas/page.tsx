"use client";

/**
 * Apartado de Propinas — vista DEDICADA, separada de Ventas/Reportes.
 *
 * ¿Por qué separado?
 *   Las propinas pertenecen al equipo (mesero/cajero) — NO al negocio.
 *   Mostrarlas mezcladas con ingresos confunde al dueño y le hace pensar
 *   que está ganando más de lo que realmente gana. En `apps/api/sales/models.py`
 *   `Sale.tip` se guarda separado y NO se incluye en `Sale.total` ni en
 *   `gross_profit` (ver comentario línea 64-65). Los reportes de ingresos
 *   suman `Sale.total`, así que ya están limpios. Esta página consume el
 *   endpoint dedicado `/sales/tips-summary/` que devuelve sólo propinas.
 *
 * Lo que muestra:
 *   - Total de propinas en el período + cantidad de ventas con propina
 *   - Promedio por venta
 *   - Breakdown por día (lista para repartir / liquidación de turno)
 *   - Breakdown por cajero (para repartir entre quienes las generaron)
 */

import { useEffect, useState, useMemo } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";

interface ByDay { date: string; total: string; count: number; }
interface ByCashier { user_id: number | null; name: string; total: string; count: number; }
interface ByPaymentMethod { method: string; label: string; total: string; count: number; }
interface TipsSummary {
  date_from: string;
  date_to: string;
  total_tips: string;
  count_with_tip: number;
  avg_tip: string;
  by_day: ByDay[];
  by_cashier: ByCashier[];
  by_payment_method?: ByPaymentMethod[];
}

type Range = "7D" | "30D" | "90D" | "CUSTOM";

function fmtCLP(n: number | string): string {
  const num = typeof n === "string" ? parseFloat(n) : n;
  if (!Number.isFinite(num)) return "$0";
  return "$" + Math.round(num).toLocaleString("es-CL");
}

function fmtDate(s: string): string {
  // s viene como YYYY-MM-DD, formato corto en español-CL
  const [y, m, d] = s.split("-");
  if (!y || !m || !d) return s;
  return `${d}/${m}/${y}`;
}

function isoDate(d: Date): string {
  const y = d.getFullYear(); const m = String(d.getMonth() + 1).padStart(2, "0"); const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

export default function PropinasPage() {
  const mob = useIsMobile();
  const [data, setData] = useState<TipsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [range, setRange] = useState<Range>("30D");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  // Para el modo CUSTOM mantenemos las fechas en estado independiente.
  // Cuando se cambia de range a uno predefinido las recalculamos.
  const params = useMemo(() => {
    const now = new Date();
    let dFrom = new Date(now), dTo = new Date(now);
    if (range === "7D") dFrom.setDate(now.getDate() - 7);
    else if (range === "30D") dFrom.setDate(now.getDate() - 30);
    else if (range === "90D") dFrom.setDate(now.getDate() - 90);
    else if (range === "CUSTOM") {
      if (from) dFrom = new Date(from);
      if (to) dTo = new Date(to);
    }
    return { date_from: isoDate(dFrom), date_to: isoDate(dTo) };
  }, [range, from, to]);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    setErr(null);
    const qs = new URLSearchParams(params).toString();
    apiFetch(`/sales/tips-summary/?${qs}`)
      .then((d: TipsSummary) => { if (!cancel) setData(d); })
      .catch((e: any) => {
        if (!cancel) setErr(e?.message || "Error al cargar propinas");
      })
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [params]);

  // Mejor día para resaltar el "récord" del período. Si no hay datos, null.
  const bestDay = useMemo(() => {
    if (!data || !data.by_day.length) return null;
    return data.by_day.reduce((best, d) => parseFloat(d.total) > parseFloat(best.total) ? d : best, data.by_day[0]);
  }, [data]);

  // Mejor cajero por monto total
  const topCashier = useMemo(() => {
    if (!data || !data.by_cashier.length) return null;
    return data.by_cashier[0]; // ya viene ordenado desc por backend
  }, [data]);

  const totalTips = data ? parseFloat(data.total_tips) : 0;

  return (
    <div style={{ background: C.bg, minHeight: "100vh", padding: mob ? "16px 12px" : "24px 28px", fontFamily: "'DM Sans', system-ui, sans-serif" }}>

      {/* Header */}
      <div style={{ marginBottom: 18 }}>
        <h1 style={{ fontSize: mob ? 22 : 26, fontWeight: 800, color: C.text, margin: 0 }}>💵 Propinas</h1>
        <div style={{ fontSize: 13, color: C.mute, marginTop: 4, lineHeight: 1.5 }}>
          Total recibido por el equipo en el período. <b>Las propinas no se mezclan con las ganancias del local</b> — pertenecen a quienes atienden.
        </div>
      </div>

      {/* Range selector */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
        {(["7D", "30D", "90D", "CUSTOM"] as Range[]).map(r => (
          <button key={r} type="button" onClick={() => setRange(r)} style={{
            padding: "6px 14px", borderRadius: C.r, fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
            background: range === r ? C.accent : C.surface,
            color: range === r ? "#fff" : C.mid,
            border: range === r ? "none" : `1px solid ${C.border}`,
          }}>
            {r === "7D" ? "Últimos 7 días" : r === "30D" ? "Últimos 30 días" : r === "90D" ? "Últimos 90 días" : "Personalizado"}
          </button>
        ))}
        {range === "CUSTOM" && (
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="date" value={from} onChange={e => setFrom(e.target.value)}
              style={{ padding: "6px 8px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 12, fontFamily: "inherit", outline: "none" }} />
            <span style={{ fontSize: 11, color: C.mute }}>→</span>
            <input type="date" value={to} onChange={e => setTo(e.target.value)}
              style={{ padding: "6px 8px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 12, fontFamily: "inherit", outline: "none" }} />
          </div>
        )}
      </div>

      {/* Error */}
      {err && (
        <div style={{ padding: "10px 14px", marginBottom: 14, borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 13 }}>
          {err}
        </div>
      )}

      {/* Loading */}
      {loading && !data && (
        <div style={{ display: "flex", justifyContent: "center", padding: 64 }}><Spinner size={28} /></div>
      )}

      {/* Empty state */}
      {!loading && data && totalTips === 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "40px 20px", textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 10 }}>💸</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>Sin propinas en el período</div>
          <div style={{ fontSize: 13, color: C.mute, maxWidth: 460, margin: "0 auto", lineHeight: 1.5 }}>
            Cuando un cliente deja propina al pagar, aparece acá. La propina se ingresa al cobrar la mesa o venta y va al equipo, no al local.
          </div>
        </div>
      )}

      {/* Data */}
      {!loading && data && totalTips > 0 && (<>
        {/* KPIs */}
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(3, 1fr)", gap: 10, marginBottom: 16 }}>
          <KPI label="TOTAL DEL PERÍODO" value={fmtCLP(totalTips)} hint="Para repartir entre el equipo" big />
          <KPI label="VENTAS CON PROPINA" value={String(data.count_with_tip)} hint={`del ${fmtDate(data.date_from)} al ${fmtDate(data.date_to)}`} />
          <KPI label="PROMEDIO POR VENTA" value={fmtCLP(parseFloat(data.avg_tip))} hint="Solo cuenta las que dejaron propina" />
        </div>

        {/* Highlights */}
        {(bestDay || topCashier) && (
          <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 1fr", gap: 10, marginBottom: 16 }}>
            {bestDay && (
              <div style={{ background: C.accentBg, border: `1px solid ${C.accentBd}`, borderRadius: 8, padding: "12px 14px" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: C.accent, textTransform: "uppercase", letterSpacing: "0.05em" }}>📅 Mejor día</div>
                <div style={{ fontSize: 15, fontWeight: 800, color: C.text, marginTop: 4 }}>
                  {fmtDate(bestDay.date)} — {fmtCLP(parseFloat(bestDay.total))}
                </div>
                <div style={{ fontSize: 12, color: C.mid, marginTop: 2 }}>{bestDay.count} {bestDay.count === 1 ? "venta" : "ventas"} con propina ese día</div>
              </div>
            )}
            {topCashier && (
              <div style={{ background: C.greenBg, border: `1px solid ${C.greenBd}`, borderRadius: 8, padding: "12px 14px" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: C.green, textTransform: "uppercase", letterSpacing: "0.05em" }}>👤 Top del equipo</div>
                <div style={{ fontSize: 15, fontWeight: 800, color: C.text, marginTop: 4 }}>
                  {topCashier.name} — {fmtCLP(parseFloat(topCashier.total))}
                </div>
                <div style={{ fontSize: 12, color: C.mid, marginTop: 2 }}>Generó {topCashier.count} {topCashier.count === 1 ? "venta" : "ventas"} con propina</div>
              </div>
            )}
          </div>
        )}

        {/* Por método de pago — Mario lo pidió: ver cuánto entra de propina
            por canal. Útil para reconciliar con el banco (débito/crédito) vs
            efectivo en mano. Iconos para distinción visual rápida. */}
        {data.by_payment_method && data.by_payment_method.length > 0 && (
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, marginBottom: 16, overflow: "hidden" }}>
            <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.05em", background: C.bg }}>
              Por método de pago
            </div>
            {data.by_payment_method.map((m, i) => {
              const pct = totalTips > 0 ? (parseFloat(m.total) / totalTips) * 100 : 0;
              const icon = m.method === "cash" ? "💵"
                : m.method === "debit" ? "💳"
                : m.method === "card" ? "💳"
                : m.method === "transfer" ? "🏦"
                : "💰";
              const accent = m.method === "cash" ? C.green
                : m.method === "debit" ? C.accent
                : m.method === "card" ? "#f59e0b"
                : C.mid;
              return (
                <div key={m.method} style={{
                  padding: "12px 14px",
                  borderBottom: i < (data.by_payment_method!.length - 1) ? `1px solid ${C.border}` : "none",
                  display: "flex", alignItems: "center", gap: 12,
                }}>
                  <div style={{ fontSize: 22, flexShrink: 0 }}>{icon}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{m.label}</div>
                    <div style={{ fontSize: 11, color: C.mute, marginTop: 1 }}>{m.count} {m.count === 1 ? "venta" : "ventas"}</div>
                    <div style={{ marginTop: 6, height: 4, background: C.bg, borderRadius: 2, overflow: "hidden" }}>
                      <div style={{ width: `${pct}%`, height: "100%", background: accent, borderRadius: 2 }} />
                    </div>
                  </div>
                  <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <div style={{ fontSize: 15, fontWeight: 800, color: C.text }}>{fmtCLP(parseFloat(m.total))}</div>
                    <div style={{ fontSize: 11, color: C.mute }}>{pct.toFixed(0)}% del total</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Por cajero */}
        {data.by_cashier.length > 0 && (
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, marginBottom: 16, overflow: "hidden" }}>
            <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.05em", background: C.bg }}>
              Por cajero / mesero
            </div>
            {data.by_cashier.map((c, i) => {
              const pct = totalTips > 0 ? (parseFloat(c.total) / totalTips) * 100 : 0;
              return (
                <div key={c.user_id ?? i} style={{
                  padding: "12px 14px",
                  borderBottom: i < data.by_cashier.length - 1 ? `1px solid ${C.border}` : "none",
                  display: "flex", alignItems: "center", gap: 12,
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{c.name}</div>
                    <div style={{ fontSize: 11, color: C.mute, marginTop: 1 }}>{c.count} {c.count === 1 ? "venta" : "ventas"} con propina</div>
                    {/* Barra proporcional */}
                    <div style={{ marginTop: 6, height: 4, background: C.bg, borderRadius: 2, overflow: "hidden" }}>
                      <div style={{ width: `${pct}%`, height: "100%", background: C.accent, borderRadius: 2 }} />
                    </div>
                  </div>
                  <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <div style={{ fontSize: 15, fontWeight: 800, color: C.text }}>{fmtCLP(parseFloat(c.total))}</div>
                    <div style={{ fontSize: 11, color: C.mute }}>{pct.toFixed(0)}% del total</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Por día — con mini-gráfico de barras arriba.
            Mario lo pidió: visibilidad de las propinas por día para
            poder ver el patrón de un vistazo (qué días recaudan más).
            La lista detalle de abajo sigue siendo la fuente de verdad
            para el monto exacto; el gráfico es solo orientativo. */}
        {data.by_day.length > 0 && (() => {
          const maxTotal = Math.max(...data.by_day.map(d => parseFloat(d.total) || 0), 1);
          const avg = data.by_day.reduce((s, d) => s + (parseFloat(d.total) || 0), 0) / data.by_day.length;
          // Para muchos días limitamos las barras visibles a los últimos 30
          // — más allá el gráfico se vuelve ilegible. La lista debajo
          // sigue mostrando todo el rango.
          const chartDays = data.by_day.length > 30 ? data.by_day.slice(-30) : data.by_day;
          return (
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
              <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.05em", background: C.bg, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span>Por día</span>
                <span style={{ fontSize: 10, fontWeight: 600, color: C.mute, textTransform: "none", letterSpacing: 0 }}>
                  Promedio: <b style={{ color: C.text }}>{fmtCLP(avg)}</b> · Mejor día: <b style={{ color: C.green }}>{fmtCLP(maxTotal)}</b>
                </span>
              </div>

              {/* Mini-gráfico de barras */}
              <div style={{ padding: "14px 14px 8px", background: C.surface }}>
                <div style={{
                  display: "flex", alignItems: "flex-end", gap: 3,
                  height: 80, width: "100%",
                }}>
                  {chartDays.map(d => {
                    const v = parseFloat(d.total) || 0;
                    const h = Math.max(2, Math.round((v / maxTotal) * 100));
                    const isMax = v === maxTotal && v > 0;
                    return (
                      <div
                        key={d.date}
                        title={`${fmtDate(d.date)}: ${fmtCLP(v)} (${d.count} venta${d.count === 1 ? "" : "s"})`}
                        style={{
                          flex: 1, minWidth: 0,
                          height: `${h}%`,
                          background: isMax ? C.green : C.accent,
                          borderRadius: "3px 3px 0 0",
                          opacity: v > 0 ? 1 : 0.15,
                          transition: "opacity .15s",
                          cursor: "default",
                        }}
                      />
                    );
                  })}
                </div>
                {data.by_day.length > 30 && (
                  <div style={{ fontSize: 10, color: C.mute, marginTop: 6, textAlign: "right" }}>
                    Mostrando últimos 30 días en el gráfico (lista completa abajo)
                  </div>
                )}
              </div>

              {/* Lista detalle */}
              <div style={{ maxHeight: 360, overflowY: "auto", borderTop: `1px solid ${C.border}` }}>
                {[...data.by_day].reverse().map((d, i, arr) => {
                  const v = parseFloat(d.total) || 0;
                  const isMax = v === maxTotal && v > 0;
                  return (
                    <div key={d.date} style={{
                      padding: "10px 14px",
                      borderBottom: i < arr.length - 1 ? `1px solid ${C.border}` : "none",
                      display: "flex", alignItems: "center", gap: 12, justifyContent: "space-between",
                      background: isMax ? C.greenBg : "transparent",
                    }}>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>
                          {fmtDate(d.date)}
                          {isMax && <span style={{ marginLeft: 6, fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 99, background: C.green, color: "#fff", textTransform: "uppercase", letterSpacing: "0.05em" }}>Mejor día</span>}
                        </div>
                        <div style={{ fontSize: 11, color: C.mute }}>{d.count} {d.count === 1 ? "venta" : "ventas"} · prom. {fmtCLP(v / Math.max(d.count, 1))} c/u</div>
                      </div>
                      <div style={{ fontSize: 14, fontWeight: 800, color: isMax ? C.green : C.text }}>{fmtCLP(v)}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })()}

        {/* Recordatorio */}
        <div style={{ marginTop: 16, padding: "10px 14px", background: C.amberBg, border: `1px solid ${C.amberBd}`, borderRadius: 8, fontSize: 12, color: C.mid, lineHeight: 1.5 }}>
          ℹ️ Las propinas <b>no aparecen en Reportes ni en Caja como ingreso del local</b>. Son del equipo. Esta sección es solo para que sepas cuánto se recaudó y puedas repartirlo.
        </div>
      </>)}
    </div>
  );
}

function KPI({ label, value, hint, big }: { label: string; value: string; hint?: string; big?: boolean }) {
  return (
    <div style={{
      background: big ? C.accentBg : C.surface,
      border: `1px solid ${big ? C.accentBd : C.border}`,
      borderRadius: 8, padding: "12px 14px",
      gridColumn: big ? undefined : undefined,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: big ? C.accent : C.mute, textTransform: "uppercase", letterSpacing: "0.06em" }}>
        {label}
      </div>
      <div style={{ fontSize: big ? 26 : 20, fontWeight: 800, color: C.text, marginTop: 4 }}>{value}</div>
      {hint && <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{hint}</div>}
    </div>
  );
}
