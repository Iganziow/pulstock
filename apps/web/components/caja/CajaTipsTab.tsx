"use client";

/**
 * CajaTipsTab — visor histórico de propinas embebido en /dashboard/caja.
 *
 * Mario lo pidió: "agrega un tercer apartado que sea para vizualizar las
 * propinas historico, que muestre por dia, por mes por año etc".
 *
 * Reusa el endpoint /sales/tips-summary/ (el mismo que /dashboard/propinas).
 * Diferencia: presets de rango más rápidos (Hoy / 7D / 30D / Mes / Año)
 * y vista compacta para reconciliar durante el cierre de caja.
 */

import React, { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { fmt } from "./CajaShared";

type Range = "today" | "7D" | "30D" | "MONTH" | "YEAR" | "CUSTOM";

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

function fmtCLP(n: number | string): string {
  const v = typeof n === "string" ? parseFloat(n) : n;
  if (!Number.isFinite(v)) return "$0";
  return "$" + Math.round(v).toLocaleString("es-CL");
}

function rangeToDates(range: Range): { from: string; to: string } {
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const dFrom = new Date(now);
  switch (range) {
    case "today":
      return { from: today, to: today };
    case "7D":
      dFrom.setDate(now.getDate() - 6); // últimos 7 días incluyendo hoy
      return { from: dFrom.toISOString().slice(0, 10), to: today };
    case "30D":
      dFrom.setDate(now.getDate() - 29);
      return { from: dFrom.toISOString().slice(0, 10), to: today };
    case "MONTH":
      dFrom.setDate(1);
      return { from: dFrom.toISOString().slice(0, 10), to: today };
    case "YEAR":
      dFrom.setMonth(0, 1);
      return { from: dFrom.toISOString().slice(0, 10), to: today };
    default:
      return { from: today, to: today };
  }
}

function fmtDate(s: string): string {
  // "2026-04-27" → "27 abr"
  const months = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];
  const [y, m, d] = s.split("-");
  if (!d) return s;
  return `${parseInt(d, 10)} ${months[parseInt(m, 10) - 1] || ""} ${y}`;
}

export function CajaTipsTab() {
  const [range, setRange] = useState<Range>("today");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [data, setData]   = useState<TipsSummary | null>(null);
  const [loading, setLoad] = useState(false);
  const [err, setErr]     = useState<string | null>(null);

  const dates = useMemo(() => {
    if (range === "CUSTOM") {
      const today = new Date().toISOString().slice(0, 10);
      return {
        from: customFrom || today,
        to: customTo || today,
      };
    }
    return rangeToDates(range);
  }, [range, customFrom, customTo]);

  useEffect(() => {
    let cancelled = false;
    setLoad(true); setErr(null);
    apiFetch(`/sales/tips-summary/?date_from=${dates.from}&date_to=${dates.to}`)
      .then((d: any) => { if (!cancelled) setData(d as TipsSummary); })
      .catch(e => { if (!cancelled) setErr(e?.message || "Error cargando propinas"); })
      .finally(() => { if (!cancelled) setLoad(false); });
    return () => { cancelled = true; };
  }, [dates.from, dates.to]);

  const total = data ? Number(data.total_tips) : 0;
  const count = data?.count_with_tip ?? 0;
  const avg   = data ? Number(data.avg_tip) : 0;

  // Propinas agrupadas por mes — para vista "por mes" cuando rango es
  // YEAR. Útil para ver tendencias mensuales del año.
  const byMonth = useMemo(() => {
    if (!data?.by_day) return [];
    const map = new Map<string, { total: number; count: number; label: string }>();
    for (const d of data.by_day) {
      const ym = d.date.slice(0, 7);
      const months = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];
      const label = `${months[parseInt(ym.slice(5, 7), 10) - 1]} ${ym.slice(0, 4)}`;
      const cur = map.get(ym) || { total: 0, count: 0, label };
      cur.total += parseFloat(d.total) || 0;
      cur.count += d.count;
      map.set(ym, cur);
    }
    return Array.from(map.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([_, v]) => v);
  }, [data]);

  const showByMonth = range === "YEAR" && byMonth.length > 0;
  const maxDayTotal = useMemo(() => Math.max(...(data?.by_day || []).map(d => parseFloat(d.total) || 0), 1), [data]);
  const maxMonthTotal = useMemo(() => Math.max(...byMonth.map(m => m.total), 1), [byMonth]);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* Range presets */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        {(["today", "7D", "30D", "MONTH", "YEAR", "CUSTOM"] as const).map(r => {
          const labels: Record<Range, string> = {
            today: "Hoy", "7D": "7 días", "30D": "30 días",
            MONTH: "Mes actual", YEAR: "Año", CUSTOM: "Personalizado",
          };
          const active = range === r;
          return (
            <button
              key={r}
              type="button"
              onClick={() => setRange(r)}
              style={{
                padding: "6px 12px", borderRadius: 99,
                border: `1px solid ${active ? C.accent : C.border}`,
                background: active ? C.accent : C.surface,
                color: active ? "#fff" : C.mid,
                fontSize: 12, fontWeight: 700, cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              {labels[r]}
            </button>
          );
        })}
        {range === "CUSTOM" && (
          <div style={{ display: "flex", gap: 6, alignItems: "center", marginLeft: 4 }}>
            <input type="date" value={customFrom} onChange={e => setCustomFrom(e.target.value)}
              style={{ padding: "5px 8px", border: `1px solid ${C.border}`, borderRadius: 6, fontSize: 12, fontFamily: "inherit" }} />
            <span style={{ color: C.mute, fontSize: 11 }}>→</span>
            <input type="date" value={customTo} onChange={e => setCustomTo(e.target.value)}
              style={{ padding: "5px 8px", border: `1px solid ${C.border}`, borderRadius: 6, fontSize: 12, fontFamily: "inherit" }} />
          </div>
        )}
      </div>

      {loading && <div style={{ display: "flex", justifyContent: "center", padding: 30 }}><Spinner /></div>}
      {err && (
        <div style={{ padding: "10px 14px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: C.r, color: C.red, fontSize: 13 }}>{err}</div>
      )}

      {!loading && data && (
        <>
          {/* KPIs */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
            <KPI label="Total propinas" value={fmtCLP(total)} accent={C.amber} big />
            <KPI label={count === 1 ? "Venta con propina" : "Ventas con propina"} value={String(count)} accent={C.text} />
            <KPI label="Promedio por venta" value={fmtCLP(avg)} accent={C.text} />
          </div>

          {total === 0 ? (
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: 30, textAlign: "center", color: C.mute, fontSize: 13 }}>
              No hubo propinas en este rango.
            </div>
          ) : (
            <>
              {/* Por método de pago */}
              {data.by_payment_method && data.by_payment_method.length > 0 && (
                <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
                  <SectionHeader>Por método de pago</SectionHeader>
                  {data.by_payment_method.map((m, i, arr) => {
                    const pct = total > 0 ? (parseFloat(m.total) / total) * 100 : 0;
                    const icon = m.method === "cash" ? "💵"
                      : m.method === "debit" ? "💳"
                      : m.method === "card" ? "💳"
                      : m.method === "transfer" ? "🏦" : "💰";
                    const accent = m.method === "cash" ? C.green
                      : m.method === "debit" ? C.accent
                      : m.method === "card" ? "#f59e0b"
                      : C.mid;
                    return (
                      <div key={m.method} style={{
                        padding: "10px 14px",
                        borderBottom: i < arr.length - 1 ? `1px solid ${C.border}` : "none",
                        display: "flex", alignItems: "center", gap: 12,
                      }}>
                        <div style={{ fontSize: 20, flexShrink: 0 }}>{icon}</div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{m.label}</div>
                          <div style={{ fontSize: 11, color: C.mute }}>{m.count} {m.count === 1 ? "venta" : "ventas"}</div>
                          <div style={{ marginTop: 4, height: 4, background: C.bg, borderRadius: 2, overflow: "hidden" }}>
                            <div style={{ width: `${pct}%`, height: "100%", background: accent }} />
                          </div>
                        </div>
                        <div style={{ textAlign: "right", flexShrink: 0 }}>
                          <div style={{ fontSize: 14, fontWeight: 800, color: C.text, fontVariantNumeric: "tabular-nums" }}>{fmtCLP(m.total)}</div>
                          <div style={{ fontSize: 11, color: C.mute }}>{pct.toFixed(0)}%</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Por cajero */}
              {data.by_cashier.length > 0 && (
                <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
                  <SectionHeader>Por cajero / mesero</SectionHeader>
                  {data.by_cashier.map((c, i) => {
                    const pct = total > 0 ? (parseFloat(c.total) / total) * 100 : 0;
                    return (
                      <div key={c.user_id ?? i} style={{
                        padding: "10px 14px",
                        borderBottom: i < data.by_cashier.length - 1 ? `1px solid ${C.border}` : "none",
                        display: "flex", alignItems: "center", gap: 12,
                      }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{c.name}</div>
                          <div style={{ fontSize: 11, color: C.mute }}>{c.count} {c.count === 1 ? "venta" : "ventas"}</div>
                          <div style={{ marginTop: 4, height: 4, background: C.bg, borderRadius: 2, overflow: "hidden" }}>
                            <div style={{ width: `${pct}%`, height: "100%", background: C.accent }} />
                          </div>
                        </div>
                        <div style={{ textAlign: "right", flexShrink: 0 }}>
                          <div style={{ fontSize: 14, fontWeight: 800, color: C.text, fontVariantNumeric: "tabular-nums" }}>{fmtCLP(c.total)}</div>
                          <div style={{ fontSize: 11, color: C.mute }}>{pct.toFixed(0)}%</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Por mes (solo en rango YEAR) */}
              {showByMonth && (
                <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
                  <SectionHeader>Por mes</SectionHeader>
                  {byMonth.map((m, i) => {
                    const pct = (m.total / maxMonthTotal) * 100;
                    return (
                      <div key={m.label} style={{
                        padding: "10px 14px",
                        borderBottom: i < byMonth.length - 1 ? `1px solid ${C.border}` : "none",
                        display: "flex", alignItems: "center", gap: 12,
                      }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: C.text, textTransform: "capitalize" }}>{m.label}</div>
                          <div style={{ fontSize: 11, color: C.mute }}>{m.count} {m.count === 1 ? "venta" : "ventas"}</div>
                          <div style={{ marginTop: 4, height: 4, background: C.bg, borderRadius: 2, overflow: "hidden" }}>
                            <div style={{ width: `${pct}%`, height: "100%", background: C.amber }} />
                          </div>
                        </div>
                        <div style={{ fontSize: 14, fontWeight: 800, color: C.text, fontVariantNumeric: "tabular-nums" }}>
                          {fmtCLP(m.total)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Por día (no se muestra cuando estamos en YEAR si ya
                  mostramos por mes — sería ruido, demasiados puntos) */}
              {data.by_day.length > 0 && !showByMonth && (
                <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
                  <SectionHeader>Por día</SectionHeader>
                  {/* Mini chart si hay > 1 día */}
                  {data.by_day.length > 1 && (
                    <div style={{ padding: "12px 14px", borderBottom: `1px solid ${C.border}` }}>
                      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 60 }}>
                        {data.by_day.map(d => {
                          const v = parseFloat(d.total) || 0;
                          const h = Math.max(2, Math.round((v / maxDayTotal) * 100));
                          return (
                            <div
                              key={d.date}
                              title={`${fmtDate(d.date)}: ${fmtCLP(v)}`}
                              style={{
                                flex: 1, height: `${h}%`,
                                background: v === maxDayTotal ? C.green : C.accent,
                                borderRadius: "2px 2px 0 0",
                                opacity: v > 0 ? 1 : 0.15,
                              }}
                            />
                          );
                        })}
                      </div>
                    </div>
                  )}
                  <div style={{ maxHeight: 320, overflowY: "auto" }}>
                    {[...data.by_day].reverse().map((d, i, arr) => {
                      const v = parseFloat(d.total) || 0;
                      return (
                        <div key={d.date} style={{
                          padding: "8px 14px",
                          borderBottom: i < arr.length - 1 ? `1px solid ${C.border}` : "none",
                          display: "flex", justifyContent: "space-between", alignItems: "center",
                        }}>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 600, color: C.text, textTransform: "capitalize" }}>{fmtDate(d.date)}</div>
                            <div style={{ fontSize: 11, color: C.mute }}>{d.count} {d.count === 1 ? "venta" : "ventas"}</div>
                          </div>
                          <div style={{ fontSize: 14, fontWeight: 800, color: C.text, fontVariantNumeric: "tabular-nums" }}>{fmtCLP(v)}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          )}

          {/* Disclaimer */}
          <div style={{ padding: "10px 14px", background: C.amberBg, border: `1px solid ${C.amberBd}`, borderRadius: 8, fontSize: 12, color: C.mid, lineHeight: 1.5 }}>
            ℹ️ Las propinas no se contabilizan como ingreso del local. Esta vista es solo para que sepas cuánto se recaudó por canal y puedas repartirlo al equipo.
          </div>
        </>
      )}
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      padding: "10px 14px",
      borderBottom: `1px solid ${C.border}`,
      background: C.bg,
      fontSize: 11, fontWeight: 700, color: C.mid,
      textTransform: "uppercase", letterSpacing: "0.05em",
    }}>{children}</div>
  );
}

function KPI({ label, value, accent, big }: { label: string; value: string; accent?: string; big?: boolean }) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "12px 14px" }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ marginTop: 4, fontSize: big ? 22 : 16, fontWeight: 900, color: accent || C.text, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}
