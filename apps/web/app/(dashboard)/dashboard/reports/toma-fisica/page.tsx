"use client";
import Link from "next/link";
import { useEffect, useState, useMemo } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";

function useIsMobile() { const [m, setM] = useState(false); useEffect(() => { const c = () => setM(window.innerWidth < 768); c(); window.addEventListener("resize", c); return () => window.removeEventListener("resize", c); }, []); return m; }
function Spinner() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ animation: "spin .7s linear infinite" }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" /></svg>; }
const fmt = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "0" : Math.round(n).toLocaleString("es-CL"); };
const fmtMoney = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL"); };
const fmtDiff = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; if (isNaN(n) || n === 0) return "0"; return (n > 0 ? "+" : "") + Math.round(n).toLocaleString("es-CL"); };

type CountRow = { product_id: number; product_name: string; sku: string; barcode: string; category: string; warehouse_name: string; warehouse_id?: number; unit: string; stock_system: string; avg_cost: string; stock_value: string };
type Cat = { id: number; name: string };
type Header = { store_name: string | null; store_address: string; warehouses: { id: number; name: string }[]; generated_at: string; generated_by: string | null };
type DiffRow = { product_id: number; product_name: string; sku: string; category: string; warehouse_name: string; unit: string; stock_system: string; stock_physical: string; difference_qty: string; unit_cost: string; difference_value: string; status: string };
type Totals = { counted: number; matches: number; shortages: number; surpluses: number; shortage_qty: string; shortage_value: string; surplus_qty: string; surplus_value: string; net_value: string };
type Step = "count" | "result";

export default function TomaFisicaPage() {
  const mob = useIsMobile();

  // ── Count step state ──
  const [loading, setLoading] = useState(true);
  const [countRows, setCountRows] = useState<CountRow[]>([]);
  const [header, setHeader] = useState<Header | null>(null);
  const [categories, setCategories] = useState<Cat[]>([]);
  const [countTotals, setCountTotals] = useState<{ product_count: number; total_value: string; category_count: number } | null>(null);
  const [categoryId, setCategoryId] = useState("");
  const [search, setSearch] = useState("");
  const [showZero, setShowZero] = useState(false);
  const [physicals, setPhysicals] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");

  // ── Result step state ──
  const [step, setStep] = useState<Step>("count");
  const [comparing, setComparing] = useState(false);
  const [diffRows, setDiffRows] = useState<DiffRow[]>([]);
  const [diffTotals, setDiffTotals] = useState<Totals | null>(null);
  const [filter, setFilter] = useState<"all" | "shortage" | "surplus" | "match">("all");

  const load = async () => {
    setLoading(true);
    try {
      setErr("");
      const params = new URLSearchParams({ sort: "category" });
      if (categoryId) params.set("category_id", categoryId);
      if (search) params.set("q", search);
      if (showZero) params.set("show_zero", "true");
      const data = await apiFetch(`/reports/inventory-count-sheet/?${params}`);
      setCountRows(data?.results || []);
      setHeader(data?.header || null);
      setCategories(data?.categories || []);
      setCountTotals(data?.totals || null);
    } catch (e: any) { setErr(e?.message || "Error al cargar productos"); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const handleApplyFilters = () => {
    setPhysicals({});
    load();
  };

  const filledCount = Object.values(physicals).filter(v => v !== "").length;

  // Group by category
  const grouped = useMemo(() => {
    const map: Record<string, CountRow[]> = {};
    countRows.forEach(r => {
      const cat = r.category || "Sin categoría";
      if (!map[cat]) map[cat] = [];
      map[cat].push(r);
    });
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
  }, [countRows]);

  const handleCompare = async () => {
    const counts = Object.entries(physicals)
      .filter(([_, v]) => v !== "")
      .map(([key, v]) => {
        const [pid, wid] = key.split("-").map(Number);
        return { product_id: pid, warehouse_id: wid, physical: parseFloat(v) };
      })
      .filter(c => !isNaN(c.physical));
    if (counts.length === 0) return;

    setComparing(true);
    try {
      setErr("");
      const data = await apiFetch("/reports/inventory-diff/", { method: "POST", body: JSON.stringify({ counts }) });
      setDiffRows(data?.results || []);
      setDiffTotals(data?.totals || null);
      setStep("result");
      setFilter("all");
    } catch (e: any) { setErr(e?.message || "Error al comparar"); }
    finally { setComparing(false); }
  };

  const filtered = filter === "all" ? diffRows : diffRows.filter(r => r.status === filter);
  const statusColor = (s: string) => s === "shortage" ? C.red : s === "surplus" ? C.green : C.mute;
  const statusIcon = (s: string) => s === "shortage" ? "🔴" : s === "surplus" ? "🟢" : "✅";

  const iS: React.CSSProperties = { padding: "7px 10px", border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 13, fontFamily: C.font, background: C.surface, outline: "none" };

  // Steps indicator
  const STEPS = [
    { key: "count" as const, label: "Contar", icon: "📋" },
    { key: "result" as const, label: "Resultados", icon: "🔍" },
  ];

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "14px 10px" : "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header */}
      <div>
        <Link href="/dashboard/reports" style={{ fontSize: 12, color: C.mute, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4, marginBottom: 8 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg> Reportes
        </Link>
        <h1 style={{ margin: 0, fontSize: mob ? 19 : 23, fontWeight: 800, letterSpacing: "-.04em" }}>📋 Toma física de inventario</h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: C.mute }}>
          Cuenta tus productos, compara con el sistema y detecta diferencias
        </p>
      </div>

      {/* Step indicator */}
      <div className="no-print" style={{ display: "flex", gap: 0, alignItems: "center" }}>
        {STEPS.map((s, i) => (
          <div key={s.key} style={{ display: "flex", alignItems: "center" }}>
            {i > 0 && <div style={{ width: 32, height: 2, background: step === "result" ? C.accent : C.border }} />}
            <div style={{
              display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 99,
              background: step === s.key ? C.accentBg : "transparent", border: `1.5px solid ${step === s.key ? C.accent : C.border}`,
              fontSize: 12, fontWeight: step === s.key ? 700 : 500, color: step === s.key ? C.accent : C.mute,
            }}>
              {s.icon} {s.label}
            </div>
          </div>
        ))}
      </div>

      {err && <div style={{ padding: "10px 16px", borderRadius: 8, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 13, fontWeight: 500 }}>{err}</div>}

      {/* ═══════════════════ STEP 1: COUNT ═══════════════════ */}
      {step === "count" && (<>
        {/* Filters */}
        <div className="no-print" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <input placeholder="Buscar producto…" value={search} onChange={e => setSearch(e.target.value)} style={{ ...iS, minWidth: 160 }} />
          <select value={categoryId} onChange={e => setCategoryId(e.target.value)} style={{ ...iS, cursor: "pointer" }}>
            <option value="">Todas las categorías</option>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: C.mid, cursor: "pointer" }}>
            <input type="checkbox" checked={showZero} onChange={e => setShowZero(e.target.checked)} /> Incluir sin stock
          </label>
          <button onClick={handleApplyFilters} style={{ ...iS, background: C.accent, color: "#fff", border: "none", cursor: "pointer", fontWeight: 600 }}>
            Filtrar
          </button>
          <button onClick={() => window.print()} style={{ ...iS, cursor: "pointer", color: C.mid, marginLeft: "auto" }}>
            🖨 Imprimir hoja
          </button>
        </div>

        {loading && <div style={{ padding: 40, textAlign: "center", color: C.mute }}><Spinner /> Cargando productos…</div>}

        {!loading && countRows.length > 0 && (<>
          {/* KPIs */}
          <div className="no-print" style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(4, 1fr)", gap: 10 }}>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "12px 14px", boxShadow: C.sh }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Productos</div>
              <div style={{ fontSize: 22, fontWeight: 800, marginTop: 2 }}>{countTotals?.product_count || countRows.length}</div>
            </div>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "12px 14px", boxShadow: C.sh }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Categorías</div>
              <div style={{ fontSize: 22, fontWeight: 800, marginTop: 2 }}>{countTotals?.category_count || grouped.length}</div>
            </div>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "12px 14px", boxShadow: C.sh }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Valor teórico</div>
              <div style={{ fontSize: 22, fontWeight: 800, marginTop: 2, color: C.accent }}>{fmtMoney(countTotals?.total_value || 0)}</div>
            </div>
            <div style={{ background: C.amberBg, border: `1px solid ${C.amberBd}`, borderRadius: C.r, padding: "12px 14px" }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.amber, textTransform: "uppercase" }}>Contados</div>
              <div style={{ fontSize: 22, fontWeight: 800, marginTop: 2, color: C.amber }}>{filledCount} / {countRows.length}</div>
            </div>
          </div>

          {/* Compare button */}
          <div className="no-print" style={{ display: "flex", justifyContent: "flex-end" }}>
            <button onClick={handleCompare} disabled={filledCount === 0 || comparing}
              style={{ ...iS, background: filledCount > 0 ? C.accent : "#ccc", color: "#fff", border: "none", cursor: filledCount > 0 ? "pointer" : "default", fontWeight: 700, padding: "10px 24px", fontSize: 14, opacity: comparing ? .6 : 1 }}>
              {comparing ? <><Spinner /> Comparando…</> : `🔍 Comparar con el sistema (${filledCount})`}
            </button>
          </div>

          {/* Products grouped by category */}
          {grouped.map(([cat, items]) => (
            <div key={cat} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", boxShadow: C.sh }}>
              {/* Category header */}
              <div style={{ padding: "8px 16px", background: C.bg, borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: C.mid }}>{cat}</span>
                <span style={{ fontSize: 11, color: C.mute }}>{items.length} productos</span>
              </div>
              {/* Table header */}
              {!mob && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 80px 70px 80px 70px", columnGap: 6, padding: "6px 16px", borderBottom: `1px solid ${C.border}`, fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".06em" }}>
                  <div>Producto</div><div style={{ textAlign: "right" }}>Código</div><div style={{ textAlign: "right" }}>Sistema</div><div style={{ textAlign: "center" }}>Conteo real</div><div style={{ textAlign: "center" }}>Dif.</div>
                </div>
              )}
              {items.map((r, i) => {
                const key = `${r.product_id}-${(r as any).warehouse_id || 0}`;
                const physVal = physicals[key];
                const hasFilled = physVal !== undefined && physVal !== "";
                const sysNum = parseFloat(r.stock_system) || 0;
                const physNum = hasFilled ? parseFloat(physVal) : NaN;
                const diff = hasFilled && !isNaN(physNum) ? physNum - sysNum : NaN;

                return (
                  <div key={key} style={{ display: "grid", gridTemplateColumns: mob ? "1fr 50px 60px 50px" : "1fr 80px 70px 80px 70px", columnGap: 6, padding: mob ? "8px 10px" : "7px 16px", borderBottom: i < items.length - 1 ? `1px solid ${C.border}` : "none", alignItems: "center" }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 12 }}>{r.product_name}</div>
                      {!mob && <div style={{ fontSize: 10, color: C.mute }}>{r.unit}{r.barcode && ` · ${r.barcode}`}</div>}
                    </div>
                    {!mob && <div style={{ textAlign: "right", fontSize: 11, color: C.mute, fontFamily: C.mono }}>{r.sku || "-"}</div>}
                    <div style={{ textAlign: "right", fontWeight: 700, fontSize: 13, fontVariantNumeric: "tabular-nums" }}>{fmt(r.stock_system)}</div>
                    <div style={{ textAlign: "center" }}>
                      <input type="number" min="0" step="1" value={physicals[key] ?? ""} onChange={e => setPhysicals(prev => ({ ...prev, [key]: e.target.value }))} placeholder="—"
                        style={{ width: "100%", maxWidth: 65, padding: "4px 5px", border: `1.5px solid ${hasFilled ? C.amber : C.border}`, borderRadius: 6, fontSize: 13, fontWeight: 700, textAlign: "center", fontFamily: C.font, outline: "none", background: hasFilled ? C.amberBg : "#fff" }} />
                    </div>
                    <div style={{ textAlign: "center", fontSize: 12, fontWeight: 700, fontVariantNumeric: "tabular-nums", color: isNaN(diff) ? "transparent" : diff === 0 ? C.green : diff < 0 ? C.red : C.amber }}>
                      {isNaN(diff) ? "—" : diff === 0 ? "✓" : fmtDiff(diff)}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}

          {/* Print footer */}
          <div className="print-only" style={{ display: "none", marginTop: 32, borderTop: `1px solid #000`, paddingTop: 12, fontSize: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span>Firma: ________________________</span>
              <span>Fecha: ________________________</span>
            </div>
          </div>
        </>)}

        {!loading && countRows.length === 0 && (
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "48px 20px", textAlign: "center" }}>
            <div style={{ fontSize: 40, marginBottom: 8 }}>📋</div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>Sin productos</div>
            <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>No se encontraron productos con los filtros seleccionados.</div>
          </div>
        )}
      </>)}

      {/* ═══════════════════ STEP 2: RESULTS ═══════════════════ */}
      {step === "result" && diffTotals && (<>
        <button className="no-print" onClick={() => setStep("count")} style={{ ...iS, cursor: "pointer", color: C.accent, fontWeight: 600, alignSelf: "flex-start" }}>
          ← Volver al conteo
        </button>

        {/* Summary cards */}
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(4, 1fr)", gap: 10 }}>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "12px 14px", boxShadow: C.sh }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Contados</div>
            <div style={{ fontSize: 24, fontWeight: 800, marginTop: 4 }}>{diffTotals.counted}</div>
            <div style={{ fontSize: 11, color: C.mute }}>✅ {diffTotals.matches} coinciden</div>
          </div>
          <div style={{ background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: C.r, padding: "12px 14px" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.red, textTransform: "uppercase" }}>Faltantes</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: C.red, marginTop: 4 }}>{diffTotals.shortages}</div>
            <div style={{ fontSize: 11, color: C.mid }}>{fmt(diffTotals.shortage_qty)} uds · {fmtMoney(diffTotals.shortage_value)}</div>
          </div>
          <div style={{ background: C.greenBg, border: `1px solid ${C.greenBd}`, borderRadius: C.r, padding: "12px 14px" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.green, textTransform: "uppercase" }}>Sobrantes</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: C.green, marginTop: 4 }}>{diffTotals.surpluses}</div>
            <div style={{ fontSize: 11, color: C.mid }}>{fmt(diffTotals.surplus_qty)} uds · {fmtMoney(diffTotals.surplus_value)}</div>
          </div>
          <div style={{ background: C.surface, border: `1px solid ${parseFloat(diffTotals.net_value) < 0 ? C.redBd : C.border}`, borderRadius: C.r, padding: "12px 14px", boxShadow: C.sh, gridColumn: mob ? "1 / -1" : "auto" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Impacto neto</div>
            <div style={{ fontSize: 24, fontWeight: 800, marginTop: 4, color: parseFloat(diffTotals.net_value) < 0 ? C.red : C.green }}>{fmtMoney(diffTotals.net_value)}</div>
            <div style={{ fontSize: 11, color: C.mute }}>diferencia en valor de inventario</div>
          </div>
        </div>

        {/* Filter tabs */}
        <div style={{ display: "flex", gap: 0, borderBottom: `2px solid ${C.border}` }}>
          {([
            { key: "all" as const, label: `Todos (${diffRows.length})` },
            { key: "shortage" as const, label: `Faltantes (${diffTotals.shortages})` },
            { key: "surplus" as const, label: `Sobrantes (${diffTotals.surpluses})` },
            { key: "match" as const, label: `Coinciden (${diffTotals.matches})` },
          ]).map(t => (
            <button key={t.key} onClick={() => setFilter(t.key)} style={{
              padding: mob ? "8px 10px" : "8px 16px", fontSize: 12, fontWeight: filter === t.key ? 700 : 500,
              color: filter === t.key ? C.accent : C.mute, background: "none", border: "none", cursor: "pointer",
              borderBottom: filter === t.key ? `2px solid ${C.accent}` : "2px solid transparent", marginBottom: -2, fontFamily: C.font,
            }}>{t.label}</button>
          ))}
        </div>

        {/* Results table */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", boxShadow: C.sh }}>
          {!mob && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 70px 70px 80px 90px 60px", columnGap: 8, padding: "8px 16px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".06em" }}>
              <div>Producto</div><div style={{ textAlign: "right" }}>Sistema</div><div style={{ textAlign: "right" }}>Real</div><div style={{ textAlign: "right" }}>Diferencia</div><div style={{ textAlign: "right" }}>Valor dif.</div><div style={{ textAlign: "center" }}>Estado</div>
            </div>
          )}
          {filtered.map((r, i) => {
            const diff = parseFloat(r.difference_qty);
            const sc = statusColor(r.status);

            if (mob) return (
              <div key={`${r.product_id}-${i}`} style={{ padding: "10px 12px", borderBottom: i < filtered.length - 1 ? `1px solid ${C.border}` : "none", borderLeft: `3px solid ${sc}`, background: r.status === "shortage" ? C.redBg + "60" : r.status === "surplus" ? C.greenBg + "60" : "transparent" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{r.product_name}</span>
                  <span style={{ fontSize: 12 }}>{statusIcon(r.status)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.mid, marginTop: 4 }}>
                  <span>Sistema: <b>{fmt(r.stock_system)}</b> · Real: <b>{fmt(r.stock_physical)}</b></span>
                  <span style={{ fontWeight: 700, color: sc }}>{fmtDiff(diff)}</span>
                </div>
                <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>Impacto: <b style={{ color: sc }}>{fmtMoney(r.difference_value)}</b></div>
              </div>
            );

            return (
              <div key={`${r.product_id}-${i}`} className="tf-row" style={{ display: "grid", gridTemplateColumns: "1fr 70px 70px 80px 90px 60px", columnGap: 8, padding: "8px 16px", borderBottom: i < filtered.length - 1 ? `1px solid ${C.border}` : "none", alignItems: "center", borderLeft: `3px solid ${sc}`, background: r.status === "shortage" ? C.redBg + "30" : r.status === "surplus" ? C.greenBg + "30" : "transparent", transition: "background .1s" }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12 }}>{r.product_name}</div>
                  <div style={{ fontSize: 10, color: C.mute }}>{r.category}{r.sku && ` · ${r.sku}`}</div>
                </div>
                <div style={{ textAlign: "right", fontSize: 13, fontVariantNumeric: "tabular-nums" }}>{fmt(r.stock_system)}</div>
                <div style={{ textAlign: "right", fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{fmt(r.stock_physical)}</div>
                <div style={{ textAlign: "right", fontSize: 13, fontWeight: 700, color: sc, fontVariantNumeric: "tabular-nums" }}>{fmtDiff(diff)}</div>
                <div style={{ textAlign: "right", fontSize: 12, fontWeight: 600, color: sc }}>{fmtMoney(r.difference_value)}</div>
                <div style={{ textAlign: "center", fontSize: 13 }}>{statusIcon(r.status)}</div>
              </div>
            );
          })}
        </div>

        {/* Print results button */}
        <div className="no-print" style={{ display: "flex", justifyContent: "flex-end" }}>
          <button onClick={() => window.print()} style={{ ...iS, cursor: "pointer", color: C.mid }}>🖨 Imprimir resultados</button>
        </div>
      </>)}

      <style>{`
        @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
        .tf-row:hover{background:${C.accentBg}!important}
        @media print { .no-print { display: none !important; } .print-only { display: block !important; } }
      `}</style>
    </div>
  );
}
