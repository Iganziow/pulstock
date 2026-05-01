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

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";

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

const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleString("es-CL", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
};

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function daysAgoIso(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export default function MovimientosCajaPage() {
  const [data, setData] = useState<ListResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Filtros
  const [from, setFrom] = useState(daysAgoIso(30));
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

  return (
    <div style={{ background: C.bg, minHeight: "100vh", padding: "24px 28px" }}>
      <div style={{ maxWidth: 1280, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 800, color: C.text, margin: 0 }}>Movimientos de caja</h1>
            <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>
              Ingresos y egresos manuales (no ventas) — útil para auditar gastos por categoría
            </div>
          </div>
          <Link
            href="/dashboard/caja/categorias"
            style={{
              fontSize: 13, color: C.accent, textDecoration: "none", fontWeight: 600,
              padding: "7px 12px", border: `1px solid ${C.border}`, borderRadius: 6,
              background: C.surface, display: "inline-flex", alignItems: "center", gap: 4,
            }}
          >
            ⚙️ Personalizar categorías
          </Link>
        </div>

        {/* KPI cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12, marginBottom: 20 }}>
          <KpiCard label="Ingresos del periodo" value={`$${fmtCLP(totals?.in || 0)}`} color={C.green} />
          <KpiCard label="Egresos del periodo" value={`$${fmtCLP(totals?.out || 0)}`} color={C.red} />
          <KpiCard label="Balance" value={`$${fmtCLP(totals?.net || 0)}`} color={Number(totals?.net || 0) >= 0 ? C.green : C.red} subtitle="ingresos − egresos" />
          <KpiCard label="Total movimientos" value={String(totals?.count || 0)} color={C.accent} />
        </div>

        {/* Filtros */}
        <div style={{ background: C.surface, padding: 14, borderRadius: C.rMd, border: `1px solid ${C.border}`, marginBottom: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1.5fr", gap: 10, alignItems: "end" }}>
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

        <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 16, alignItems: "flex-start" }}>
          {/* Tabla */}
          <div style={{ background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`, overflow: "hidden" }}>
            <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.07em" }}>
              {data ? `${data.count} movimientos` : "..."}
            </div>
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
                  {!loading && data?.results.map(m => (
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
                </tbody>
              </table>
            </div>
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
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: C.surface, borderRadius: 14, padding: 28, width: 440, boxShadow: "0 20px 52px rgba(0,0,0,0.18)" }}>
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
