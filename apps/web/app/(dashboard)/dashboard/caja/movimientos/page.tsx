"use client";

/**
 * /dashboard/caja/movimientos
 * ===========================
 * Listado cross-session de movimientos de caja con filtros y breakdown por
 * categoría (Daniel 01/05/26).
 *
 * Diferenciador vs Fudo: Pulstock muestra el desglose "en qué se va la plata"
 * por categoría predefinida, no solo texto libre.
 */

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { useBreakpoint } from "@/hooks/useIsMobile";
import { AddMovementModal } from "@/components/caja/CajaModals";

type Movement = {
  id: number;
  session_id: number;
  register_id: number;
  register_name: string;
  type: "IN" | "OUT";
  category: string;
  category_label: string;
  amount: string;
  description: string;
  created_by: string;
  created_at: string;
};

type CategoryStat = {
  type: "IN" | "OUT";
  category: string;
  category_label: string;
  total: string;
  count: number;
};

type ListResp = {
  results: Movement[];
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  totals_by_type: { in: string; out: string; net: string; count: number };
  totals_by_category: CategoryStat[];
};

type CategoryOption = { code: string; label: string };

const fmtCLP = (n: number | string) => {
  const v = typeof n === "string" ? Number(n) : n;
  if (!Number.isFinite(v)) return "0";
  return Math.round(v).toLocaleString("es-CL");
};

// Fecha compacta: "02/05 · 17:11" (sin año, 24h, separador ·)
// Útil para columnas/celdas estrechas. El año se omite porque el rango
// de fechas ya está visible en los filtros.
const fmtDate = (iso: string) => {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${dd}/${mm} · ${hh}:${mi}`;
};

// Usamos zona local del navegador (no UTC) para que "hoy" coincida con
// el día calendario del usuario en Chile.
function todayIso() {
  const d = new Date();
  const yy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

function daysAgoIso(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  const yy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

// Clave de día (yyyy-mm-dd) en zona local — para agrupar movimientos.
function dayKeyLocal(iso: string): string {
  const d = new Date(iso);
  const yy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

// "Hoy", "Ayer" o "Lun 28 abr" (compacto y útil para encabezados de día).
const DAY_NAMES = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
const MONTH_NAMES_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(); yesterday.setDate(today.getDate() - 1);
  const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  if (sameDay(d, today)) return "Hoy";
  if (sameDay(d, yesterday)) return "Ayer";
  return `${DAY_NAMES[d.getDay()]} ${d.getDate()} ${MONTH_NAMES_SHORT[d.getMonth()]}`;
}

export default function MovimientosCajaPage() {
  const { isMobile, isTablet } = useBreakpoint();
  const card = isMobile || isTablet; // layout de tarjetas en móvil + tablet
  const [data, setData] = useState<ListResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Filtros — por defecto sólo HOY (los chicos de la cafetería suelen
  // mirar movimientos del día; antes el default eran 30 días y se mezclaba todo).
  const [from, setFrom] = useState(todayIso());
  const [to, setTo] = useState(todayIso());
  const [type, setType] = useState<"" | "IN" | "OUT">("");
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  // Borrar
  const [delTarget, setDelTarget] = useState<Movement | null>(null);
  const [delBusy, setDelBusy] = useState(false);
  const [delErr, setDelErr] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Crear movimiento (Daniel 01/05/26)
  const [activeSession, setActiveSession] = useState<{ id: number } | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [addBusy, setAddBusy] = useState(false);
  const [addType, setAddType] = useState<"IN" | "OUT">("OUT");
  const [addAmt, setAddAmt] = useState("");
  const [addDesc, setAddDesc] = useState("");
  const [addCategory, setAddCategory] = useState("");

  // Fetch sesión activa para saber si se puede crear movimiento
  useEffect(() => {
    let alive = true;
    apiFetch("/caja/sessions/current/")
      .then((s: any) => { if (alive) setActiveSession(s ? { id: s.id } : null); })
      .catch(() => { if (alive) setActiveSession(null); });
    return () => { alive = false; };
  }, [refreshKey]);

  async function handleAddMovement() {
    if (!activeSession) return;
    setAddBusy(true);
    try {
      await apiFetch(`/caja/sessions/${activeSession.id}/movements/`, {
        method: "POST",
        body: JSON.stringify({
          type: addType,
          amount: Number(addAmt),
          description: addDesc,
          category: addCategory || undefined,
        }),
      });
      setShowAdd(false);
      setAddAmt(""); setAddDesc(""); setAddCategory("");
      setRefreshKey(k => k + 1); // refrescar la lista
    } catch (e: any) {
      alert(e?.message ?? "Error al crear movimiento");
    } finally {
      setAddBusy(false);
    }
  }

  async function handleDelete() {
    if (!delTarget) return;
    setDelBusy(true);
    setDelErr(null);
    try {
      await apiFetch(`/caja/movements/${delTarget.id}/`, { method: "DELETE" });
      setDelTarget(null);
      setRefreshKey(k => k + 1);
    } catch (e: any) {
      setDelErr(e?.message ?? "Error al borrar");
    } finally {
      setDelBusy(false);
    }
  }

  // Categorías para el dropdown
  const [allCats, setAllCats] = useState<{ income: CategoryOption[]; expense: CategoryOption[] }>({ income: [], expense: [] });

  useEffect(() => {
    apiFetch("/caja/movements/categories/")
      .then((d: any) => setAllCats(d || { income: [], expense: [] }))
      .catch(() => {});
  }, []);

  const allCategoryOptions = useMemo(() => {
    if (type === "IN") return allCats.income;
    if (type === "OUT") return allCats.expense;
    return [...allCats.income, ...allCats.expense];
  }, [type, allCats]);

  // Cargar listado
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(null);
    const params = new URLSearchParams();
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    if (type) params.set("type", type);
    if (category) params.set("category", category);
    if (q) params.set("q", q);
    params.set("page", String(page));
    params.set("page_size", "50");

    apiFetch(`/caja/movements/?${params.toString()}`)
      .then((d: any) => { if (alive) setData(d); })
      .catch((e: any) => { if (alive) setErr(e?.message ?? "Error"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [from, to, type, category, q, page, refreshKey]);

  // Si cambia type, resetear categoría si ya no aplica
  useEffect(() => {
    if (!category) return;
    const valid = new Set(allCategoryOptions.map(c => c.code));
    if (!valid.has(category)) setCategory("");
  }, [type, allCategoryOptions, category]);

  const totals = data?.totals_by_type;
  const expensesByCategory = (data?.totals_by_category || []).filter(c => c.type === "OUT");
  const incomesByCategory = (data?.totals_by_category || []).filter(c => c.type === "IN");

  // Agrupación por día (los movimientos vienen ordenados desc por created_at).
  // Cada grupo trae su subtotal de ingresos/egresos para que se vea "por día".
  const groupedByDay = useMemo(() => {
    if (!data?.results?.length) return [] as { day: string; label: string; items: Movement[]; totalIn: number; totalOut: number }[];
    const groups: { day: string; label: string; items: Movement[]; totalIn: number; totalOut: number }[] = [];
    for (const m of data.results) {
      const day = dayKeyLocal(m.created_at);
      let g = groups[groups.length - 1];
      if (!g || g.day !== day) {
        g = { day, label: dayLabel(m.created_at), items: [], totalIn: 0, totalOut: 0 };
        groups.push(g);
      }
      g.items.push(m);
      const amt = Number(m.amount);
      if (m.type === "IN") g.totalIn += amt; else g.totalOut += amt;
    }
    return groups;
  }, [data]);

  // Atajos de rango — Hoy / Ayer / Últimos 7 días / Últimos 30 días.
  // Aplican from y to en un solo click; resetean la página.
  function applyQuickRange(kind: "today" | "yesterday" | "7d" | "30d") {
    const today = todayIso();
    if (kind === "today") { setFrom(today); setTo(today); }
    else if (kind === "yesterday") { const y = daysAgoIso(1); setFrom(y); setTo(y); }
    else if (kind === "7d") { setFrom(daysAgoIso(6)); setTo(today); }
    else if (kind === "30d") { setFrom(daysAgoIso(29)); setTo(today); }
    setPage(1);
  }
  // Para resaltar el chip activo, comparamos contra los rangos canónicos.
  const activeQuick = useMemo(() => {
    const today = todayIso();
    if (from === today && to === today) return "today";
    if (from === daysAgoIso(1) && to === daysAgoIso(1)) return "yesterday";
    if (from === daysAgoIso(6) && to === today) return "7d";
    if (from === daysAgoIso(29) && to === today) return "30d";
    return null;
  }, [from, to]);

  return (
    <div style={{ background: C.bg, minHeight: "100vh", padding: isMobile ? "16px 12px" : "24px 28px" }}>
      <div style={{ maxWidth: 1280, margin: "0 auto" }}>
        {/* Botón volver atrás */}
        <Link
          href="/dashboard/caja"
          style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            fontSize: 13, color: C.mid, textDecoration: "none",
            marginBottom: 14, fontWeight: 500,
          }}
        >
          ← Volver a Caja
        </Link>

        {/* Header
            - Móvil  : título arriba, botones full-width en grilla 1fr 1fr
            - Tablet : título arriba, botones en fila auto-width pero touch-friendly
            - Desktop: título a la izquierda, botones a la derecha en línea base */}
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: card ? "flex-start" : "baseline",
          marginBottom: 24,
          flexDirection: card ? "column" : "row",
          gap: card ? 14 : 0,
        }}>
          <div>
            <h1 style={{ fontSize: isMobile ? 19 : 22, fontWeight: 800, color: C.text, margin: 0 }}>Movimientos de caja</h1>
            <div style={{ fontSize: isMobile ? 12 : 13, color: C.mute, marginTop: 4 }}>
              Ingresos y egresos manuales (no ventas) — útil para auditar gastos por categoría
            </div>
          </div>
          <div style={{
            // móvil: grilla 1fr 1fr (los dos botones ocupan el ancho a partes iguales)
            // tablet: fila normal con botones auto-width pero altura touch
            // desktop: fila inline a la derecha
            display: isMobile ? "grid" : "flex",
            gridTemplateColumns: isMobile ? "1fr 1fr" : undefined,
            gap: 10,
            alignSelf: card ? "stretch" : "auto",
            flexWrap: "wrap",
            width: isMobile ? "100%" : "auto",
          }}>
            <button
              type="button"
              onClick={() => setShowAdd(true)}
              title={activeSession ? "Crear ingreso/egreso" : "Necesitás abrir una caja primero"}
              style={{
                // padding tablet/móvil: más vertical para touch; desktop: compacto
                padding: card ? "11px 18px" : "7px 14px",
                borderRadius: 8,
                background: C.accent, color: "#fff", border: "none",
                fontSize: card ? 14 : 13, fontWeight: 700, cursor: "pointer",
                display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
                opacity: activeSession ? 1 : 0.85,
                // móvil: full ancho de la celda; tablet/desktop: contenido natural
                width: isMobile ? "100%" : "auto",
                minHeight: card ? 44 : "auto",
                boxShadow: card ? "0 1px 2px rgba(79,70,229,0.18)" : "none",
                whiteSpace: "nowrap",
              }}
            >
              <span style={{ fontSize: 18, lineHeight: 1, fontWeight: 800 }}>+</span> Movimiento
            </button>
            <Link
              href="/dashboard/caja/categorias"
              style={{
                fontSize: 13, color: C.accent, textDecoration: "none", fontWeight: 600,
                padding: card ? "11px 18px" : "7px 12px",
                border: `1px solid ${C.border}`, borderRadius: 8,
                background: C.surface,
                display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
                width: isMobile ? "100%" : "auto",
                minHeight: card ? 44 : "auto",
                whiteSpace: "nowrap",
              }}
            >
              <span aria-hidden>⚙️</span>{isMobile ? "Categorías" : "Personalizar categorías"}
            </Link>
          </div>
        </div>

        {/* KPI cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12, marginBottom: 20 }}>
          <KpiCard label={from === to ? "Ingresos del día" : "Ingresos"} value={`$${fmtCLP(totals?.in || 0)}`} color={C.green} />
          <KpiCard label={from === to ? "Egresos del día" : "Egresos"} value={`$${fmtCLP(totals?.out || 0)}`} color={C.red} />
          <KpiCard label="Balance" value={`$${fmtCLP(totals?.net || 0)}`} color={Number(totals?.net || 0) >= 0 ? C.green : C.red} subtitle="ingresos − egresos" />
          <KpiCard label="Total movimientos" value={String(totals?.count || 0)} color={C.accent} />
        </div>

        {/* Filtros */}
        <div style={{ background: C.surface, padding: 14, borderRadius: C.rMd, border: `1px solid ${C.border}`, marginBottom: 16 }}>
          {/* Atajos rápidos de rango — los chicos eligen un día con un click */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
            {([
              { k: "today", label: "Hoy" },
              { k: "yesterday", label: "Ayer" },
              { k: "7d", label: "Últimos 7 días" },
              { k: "30d", label: "Últimos 30 días" },
            ] as const).map(opt => {
              const active = activeQuick === opt.k;
              return (
                <button
                  key={opt.k}
                  type="button"
                  onClick={() => applyQuickRange(opt.k)}
                  style={{
                    padding: card ? "8px 14px" : "5px 12px",
                    borderRadius: 99,
                    border: `1px solid ${active ? C.accent : C.border}`,
                    background: active ? C.accent : C.surface,
                    color: active ? "#fff" : C.mid,
                    fontSize: 12,
                    fontWeight: active ? 700 : 600,
                    cursor: "pointer",
                    minHeight: card ? 36 : "auto",
                    whiteSpace: "nowrap",
                  }}
                >{opt.label}</button>
              );
            })}
          </div>
          <div style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr 1fr" : (isTablet ? "1fr 1fr 1fr" : "1fr 1fr 1fr 1fr 1.5fr"),
            gap: 10,
            alignItems: "end",
          }}>
            <FilterField label="Desde">
              <input type="date" value={from} onChange={e => { setFrom(e.target.value); setPage(1); }} style={inputStyle} />
            </FilterField>
            <FilterField label="Hasta">
              <input type="date" value={to} onChange={e => { setTo(e.target.value); setPage(1); }} style={inputStyle} />
            </FilterField>
            <FilterField label="Tipo">
              <select value={type} onChange={e => { setType(e.target.value as any); setPage(1); }} style={inputStyle}>
                <option value="">Todos</option>
                <option value="IN">Ingresos</option>
                <option value="OUT">Egresos</option>
              </select>
            </FilterField>
            <FilterField label="Categoría">
              <select value={category} onChange={e => { setCategory(e.target.value); setPage(1); }} style={inputStyle}>
                <option value="">Todas</option>
                {allCategoryOptions.map(c => (
                  <option key={c.code} value={c.code}>{c.label}</option>
                ))}
              </select>
            </FilterField>
            <FilterField label="Buscar descripción">
              <input type="text" value={q} onChange={e => { setQ(e.target.value); setPage(1); }} placeholder="Ej: gas, banco..." style={inputStyle} />
            </FilterField>
          </div>
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: isMobile || isTablet ? "1fr" : "1fr 320px",
          gap: 16,
          alignItems: "flex-start",
        }}>
          {/* Tabla (desktop) / Tarjetas (móvil + tablet) */}
          <div style={{ background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`, overflow: "hidden" }}>
            <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.07em" }}>
              {data ? `${data.count} movimientos` : "..."}
            </div>

            {/* DESKTOP: tabla */}
            {!card && (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: C.bg }}>
                      <Th>Fecha</Th>
                      <Th>Tipo</Th>
                      <Th>Categoría</Th>
                      <Th>Descripción</Th>
                      <Th align="right">Monto</Th>
                      <Th>Caja</Th>
                      <Th>Usuario</Th>
                      <Th align="center">Acciones</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr><td colSpan={8} style={{ padding: 32, textAlign: "center" }}><Spinner size={16} /></td></tr>
                    )}
                    {err && !loading && (
                      <tr><td colSpan={8} style={{ padding: 16, color: C.red, textAlign: "center" }}>{err}</td></tr>
                    )}
                    {!loading && !err && data?.results.length === 0 && (
                      <tr><td colSpan={8} style={{ padding: 32, color: C.mute, textAlign: "center" }}>Sin movimientos en este rango</td></tr>
                    )}
                    {!loading && groupedByDay.map(g => (
                      <React.Fragment key={g.day}>
                        {/* Encabezado de día con subtotales */}
                        <tr style={{ background: C.bg, borderTop: `2px solid ${C.border}` }}>
                          <td colSpan={8} style={{ padding: "8px 12px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}>
                              <span style={{ fontWeight: 800, color: C.text, fontSize: 13 }}>{g.label}</span>
                              <span style={{ color: C.mute }}>·</span>
                              <span style={{ color: C.mute }}>{g.items.length} movimiento{g.items.length === 1 ? "" : "s"}</span>
                              <span style={{ marginLeft: "auto", display: "flex", gap: 14, fontVariantNumeric: "tabular-nums" }}>
                                {g.totalIn > 0 && <span style={{ color: C.green, fontWeight: 700 }}>+${fmtCLP(g.totalIn)}</span>}
                                {g.totalOut > 0 && <span style={{ color: C.red, fontWeight: 700 }}>−${fmtCLP(g.totalOut)}</span>}
                              </span>
                            </div>
                          </td>
                        </tr>
                        {g.items.map(m => (
                          <tr key={m.id} style={{ borderTop: `1px solid ${C.border}` }}>
                            <Td>{fmtDate(m.created_at)}</Td>
                            <Td>
                              <span style={{
                                display: "inline-block",
                                padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 700,
                                background: m.type === "IN" ? C.greenBg : C.redBg,
                                color: m.type === "IN" ? C.green : C.red,
                                border: `1px solid ${m.type === "IN" ? C.greenBd : C.redBd}`,
                              }}>
                                {m.type === "IN" ? "↑ Ingreso" : "↓ Egreso"}
                              </span>
                            </Td>
                            <Td>
                              <span style={{ fontSize: 12, color: m.category ? C.text : C.mute, fontStyle: m.category ? "normal" : "italic" }}>
                                {m.category_label}
                              </span>
                            </Td>
                            <Td>{m.description}</Td>
                            <Td align="right">
                              <span style={{ fontWeight: 700, color: m.type === "IN" ? C.green : C.red, fontVariantNumeric: "tabular-nums" }}>
                                {m.type === "IN" ? "+" : "-"}${fmtCLP(m.amount)}
                              </span>
                            </Td>
                            <Td><span style={{ fontSize: 12, color: C.mid }}>{m.register_name}</span></Td>
                            <Td><span style={{ fontSize: 12, color: C.mute }}>{m.created_by}</span></Td>
                            <Td align="center">
                              <button
                                onClick={() => setDelTarget(m)}
                                title="Borrar movimiento"
                                aria-label="Borrar"
                                style={{
                                  background: "none", border: `1px solid ${C.border}`, borderRadius: 4,
                                  padding: "3px 7px", cursor: "pointer", color: C.red, fontSize: 12,
                                }}
                              >🗑️</button>
                            </Td>
                          </tr>
                        ))}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* MÓVIL + TABLET: tarjetas */}
            {card && (
              <div style={{ display: "flex", flexDirection: "column" }}>
                {loading && (
                  <div style={{ padding: 32, textAlign: "center" }}><Spinner size={16} /></div>
                )}
                {err && !loading && (
                  <div style={{ padding: 16, color: C.red, textAlign: "center", fontSize: 13 }}>{err}</div>
                )}
                {!loading && !err && data?.results.length === 0 && (
                  <div style={{ padding: 32, color: C.mute, textAlign: "center", fontSize: 13 }}>Sin movimientos en este rango</div>
                )}
                {!loading && groupedByDay.map(g => (
                  <React.Fragment key={g.day}>
                    {/* Encabezado de día */}
                    <div style={{
                      padding: "9px 14px",
                      background: C.bg,
                      borderTop: `1px solid ${C.border}`,
                      borderBottom: `1px solid ${C.border}`,
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      flexWrap: "wrap",
                    }}>
                      <span style={{ fontWeight: 800, fontSize: 13, color: C.text }}>{g.label}</span>
                      <span style={{ color: C.mute, fontSize: 12 }}>· {g.items.length} mov{g.items.length === 1 ? "" : "s"}</span>
                      <span style={{ marginLeft: "auto", display: "flex", gap: 10, fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
                        {g.totalIn > 0 && <span style={{ color: C.green, fontWeight: 700 }}>+${fmtCLP(g.totalIn)}</span>}
                        {g.totalOut > 0 && <span style={{ color: C.red, fontWeight: 700 }}>−${fmtCLP(g.totalOut)}</span>}
                      </span>
                    </div>
                    {g.items.map((m, i) => {
                  const isIn = m.type === "IN";
                  // Sólo mostramos categoría si es una real (no "Sin categoría")
                  const hasRealCategory = !!m.category;
                  return (
                    <div
                      key={m.id}
                      style={{
                        padding: isMobile ? "12px 14px" : "14px 16px",
                        borderTop: i === 0 ? "none" : `1px solid ${C.border}`,
                        borderLeft: `4px solid ${isIn ? C.green : C.red}`,
                        display: "flex",
                        flexDirection: "column",
                        gap: 8,
                      }}
                    >
                      {/* Fila 1: tipo + monto (lo más importante) */}
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                        <span style={{
                          display: "inline-block",
                          padding: "3px 10px", borderRadius: 4, fontSize: 11, fontWeight: 700,
                          background: isIn ? C.greenBg : C.redBg,
                          color: isIn ? C.green : C.red,
                          border: `1px solid ${isIn ? C.greenBd : C.redBd}`,
                          flexShrink: 0,
                        }}>
                          {isIn ? "↑ Ingreso" : "↓ Egreso"}
                        </span>
                        <span style={{
                          fontSize: 18, fontWeight: 800,
                          color: isIn ? C.green : C.red,
                          fontVariantNumeric: "tabular-nums",
                        }}>
                          {isIn ? "+" : "-"}${fmtCLP(m.amount)}
                        </span>
                      </div>

                      {/* Fila 2: descripción (FULL, sin truncar) + categoría inline si la hay */}
                      <div style={{ fontSize: 14, fontWeight: 600, color: C.text, lineHeight: 1.35, wordBreak: "break-word" }}>
                        {m.description || <span style={{ color: C.mute, fontStyle: "italic", fontWeight: 500 }}>(sin descripción)</span>}
                        {hasRealCategory && (
                          <span style={{
                            display: "inline-block", marginLeft: 8,
                            fontSize: 11, fontWeight: 600, color: C.mid,
                            background: C.bg, padding: "1px 7px", borderRadius: 99,
                            border: `1px solid ${C.border}`,
                            verticalAlign: "middle",
                          }}>
                            {m.category_label}
                          </span>
                        )}
                      </div>

                      {/* Fila 3: meta (caja · usuario · fecha) + BOTÓN BORRAR siempre visible */}
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginTop: 2 }}>
                        <div style={{ fontSize: 11, color: C.mute, lineHeight: 1.4, minWidth: 0 }}>
                          <div>{m.register_name} · <span style={{ color: C.mid }}>{m.created_by}</span></div>
                          <div>{fmtDate(m.created_at)}</div>
                        </div>
                        <button
                          onClick={() => setDelTarget(m)}
                          title="Borrar movimiento"
                          aria-label="Borrar movimiento"
                          style={{
                            background: C.redBg,
                            border: `1px solid ${C.redBd}`,
                            borderRadius: 8,
                            padding: "9px 14px",
                            cursor: "pointer",
                            color: C.red,
                            fontSize: 13,
                            fontWeight: 700,
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                            flexShrink: 0,
                            minHeight: 40,
                          }}
                        >🗑️ Borrar</button>
                      </div>
                    </div>
                  );
                })}
                  </React.Fragment>
                ))}
              </div>
            )}

            {/* Paginación */}
            {data && data.total_pages > 1 && (
              <div style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: `1px solid ${C.border}` }}>
                <span style={{ fontSize: 12, color: C.mute }}>Página {data.page} de {data.total_pages}</span>
                <div style={{ display: "flex", gap: 6 }}>
                  <PagerBtn disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>← Anterior</PagerBtn>
                  <PagerBtn disabled={page >= (data.total_pages || 1)} onClick={() => setPage(p => p + 1)}>Siguiente →</PagerBtn>
                </div>
              </div>
            )}
          </div>

          {/* Sidebar: breakdown por categoría */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <CategoryBreakdownCard
              title="Egresos por categoría"
              color={C.red}
              items={expensesByCategory}
              emptyMessage="Sin egresos en este periodo"
            />
            <CategoryBreakdownCard
              title="Ingresos por categoría"
              color={C.green}
              items={incomesByCategory}
              emptyMessage="Sin ingresos en este periodo"
            />
          </div>
        </div>
      </div>

      {/* Modal de confirmación al borrar */}
      {delTarget && (
        <DeleteConfirmModal
          movement={delTarget}
          busy={delBusy}
          err={delErr}
          onCancel={() => { setDelTarget(null); setDelErr(null); }}
          onConfirm={handleDelete}
        />
      )}

      {/* Modal de crear movimiento (Daniel 01/05/26) */}
      {showAdd && (
        <AddMovementModal
          hasOpenSession={!!activeSession}
          moveType={addType}
          setMoveType={setAddType}
          moveAmt={addAmt}
          setMoveAmt={setAddAmt}
          moveDesc={addDesc}
          setMoveDesc={setAddDesc}
          moveCategory={addCategory}
          setMoveCategory={setAddCategory}
          busy={addBusy}
          onClose={() => setShowAdd(false)}
          onSubmit={handleAddMovement}
        />
      )}
    </div>
  );
}

function DeleteConfirmModal({
  movement, busy, err, onCancel, onConfirm,
}: {
  movement: Movement; busy: boolean; err: string | null;
  onCancel: () => void; onConfirm: () => void;
}) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ background: C.surface, borderRadius: 14, padding: 28, width: "100%", maxWidth: 440, boxShadow: "0 20px 52px rgba(0,0,0,0.18)", maxHeight: "calc(100vh - 32px)", overflowY: "auto" }}>
        <div style={{ fontSize: 36, marginBottom: 12, textAlign: "center" }}>⚠️</div>
        <div style={{ fontSize: 16, fontWeight: 800, color: C.text, marginBottom: 12, textAlign: "center" }}>
          ¿Borrar este movimiento?
        </div>
        <div style={{ background: C.bg, padding: 12, borderRadius: 8, marginBottom: 14 }}>
          <div style={{ fontSize: 12, color: C.mute, marginBottom: 4 }}>
            {movement.type === "IN" ? "↑ Ingreso" : "↓ Egreso"} · {movement.category_label}
          </div>
          <div style={{ fontSize: 18, fontWeight: 800, color: movement.type === "IN" ? C.green : C.red, fontVariantNumeric: "tabular-nums" }}>
            {movement.type === "IN" ? "+" : "-"}${fmtCLP(movement.amount)}
          </div>
          <div style={{ fontSize: 13, color: C.text, marginTop: 4 }}>{movement.description}</div>
          <div style={{ fontSize: 11, color: C.mute, marginTop: 6 }}>
            {movement.register_name} · {fmtDate(movement.created_at)}
          </div>
        </div>
        <div style={{ fontSize: 12, color: C.mute, lineHeight: 1.5, marginBottom: 16, textAlign: "center" }}>
          Esta acción es <b>irreversible</b>. Si el arqueo asociado ya está cerrado, solo el dueño puede eliminar.
        </div>
        {err && (
          <div style={{ padding: "8px 12px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 6, color: C.red, fontSize: 12, marginBottom: 14 }}>
            {err}
          </div>
        )}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onCancel} disabled={busy} style={{
            padding: "9px 18px", border: `1px solid ${C.border}`, borderRadius: 6,
            background: C.surface, color: C.mid, cursor: "pointer", fontSize: 13,
          }}>Cancelar</button>
          <button onClick={onConfirm} disabled={busy} style={{
            padding: "9px 18px", border: "none", borderRadius: 6,
            background: C.red, color: "#fff", cursor: busy ? "not-allowed" : "pointer",
            opacity: busy ? 0.6 : 1, fontSize: 13, fontWeight: 600,
          }}>{busy ? "Borrando..." : "Sí, borrar"}</button>
        </div>
      </div>
    </div>
  );
}

// ─── helpers UI ────────────────────────────────────────────────────────────

function KpiCard({ label, value, color, subtitle }: { label: string; value: string; color: string; subtitle?: string }) {
  return (
    <div style={{ background: C.surface, padding: 14, borderRadius: C.rMd, border: `1px solid ${C.border}` }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color, marginTop: 6, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      {subtitle && (
        <div style={{ fontSize: 10, color: C.mute, marginTop: 3, fontStyle: "italic" }}>{subtitle}</div>
      )}
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: C.mute, marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "8px 10px", border: `1px solid ${C.border}`,
  borderRadius: 6, fontSize: 13, background: C.surface, color: C.text,
};

function Th({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" | "center" }) {
  return <th style={{ padding: "8px 12px", textAlign: align, fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em" }}>{children}</th>;
}

function Td({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" | "center" }) {
  return <td style={{ padding: "8px 12px", textAlign: align }}>{children}</td>;
}

function PagerBtn({ disabled, onClick, children }: { disabled?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button disabled={disabled} onClick={onClick} style={{
      padding: "5px 10px", border: `1px solid ${C.border}`, borderRadius: 6,
      background: C.surface, color: disabled ? C.mute : C.mid, fontSize: 12,
      cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1,
    }}>{children}</button>
  );
}

function CategoryBreakdownCard({
  title, color, items, emptyMessage,
}: {
  title: string; color: string; items: CategoryStat[]; emptyMessage: string;
}) {
  const total = items.reduce((s, it) => s + Number(it.total), 0);
  return (
    <div style={{ background: C.surface, padding: 14, borderRadius: C.rMd, border: `1px solid ${C.border}` }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>{title}</div>
      {items.length === 0 ? (
        <div style={{ fontSize: 12, color: C.mute, fontStyle: "italic", padding: "12px 0" }}>{emptyMessage}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {items.map(it => {
            const pct = total > 0 ? (Number(it.total) / total) * 100 : 0;
            return (
              <div key={`${it.type}-${it.category}`}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                  <span style={{ fontSize: 12, color: C.text }}>{it.category_label}</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color, fontVariantNumeric: "tabular-nums" }}>${fmtCLP(it.total)}</span>
                </div>
                <div style={{ height: 6, background: C.bg, borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${pct}%`, background: color }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2 }}>
                  <span style={{ fontSize: 10, color: C.mute }}>{it.count} mov{it.count === 1 ? "" : "s"}</span>
                  <span style={{ fontSize: 10, color: C.mute }}>{pct.toFixed(0)}%</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
