"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";

function useIsMobile(){const[m,setM]=useState(false);useEffect(()=>{const fn=()=>setM(window.innerWidth<768);fn();window.addEventListener("resize",fn);return()=>window.removeEventListener("resize",fn);},[]);return m;}

type Header = {
  store_code?: string | null;
  store_name?: string | null;
  store_address?: string | null;
  category_name?: string | null;
  generated_at?: string | null; // ISO desde backend
  user_name?: string | null;
};

type Row = {
  product_id: number;
  internal_code?: string | null;
  barcode?: string | null;
  sku?: string | null;
  product_name: string;

  stock_theoretical: string;
  stock_in_transit: string;
  stock_physical: string;
  avg_sales_day: string;

  suggested: string;
  qty_to_order?: string;
};

type Resp = {
  header: Header;
  meta?: any;
  results: Row[];
};

// ---------- utils ----------
function toNum(s: string | null | undefined) {
  const x = Number(String(s ?? "0").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
}

function clampInt(v: string, fallback: number) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : fallback;
}

// ✅ para evitar 133.000 en pantalla (mostrar ENTERO)
function asIntStr(v: string | null | undefined) {
  const n = Math.trunc(toNum(v));
  return String(Number.isFinite(n) ? n : 0);
}

// ✅ decimales 3 (avg)
function asDec3Str(v: string | null | undefined) {
  const n = toNum(v);
  return Number.isFinite(n) ? n.toFixed(3) : "0.000";
}

// ✅ formatea fecha SOLO si viene ISO válido (no usa Date.now() como fallback en SSR)
function formatCLDate(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("es-CL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function downloadTextFile(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function csvEscape(v: any) {
  const s = String(v ?? "");
  if (s.includes(",") || s.includes('"') || s.includes("\n")) {
    return `"${s.replaceAll('"', '""')}"`;
  }
  return s;
}

// ✅ Cantidad a Pedir: ENTERO (sin decimales)
function sanitizeQty(v: string) {
  const cleaned = v.replace(/[^\d-]/g, "").trim();
  if (cleaned === "") return "0";
  const n = parseInt(cleaned, 10);
  if (!Number.isFinite(n) || n < 0) return "0";
  return String(n);
}

export default function TransferSuggestionSheetPage() {
  const mob = useIsMobile();
  const [mounted, setMounted] = useState(false);

  // filtros
  const [warehouseId, setWarehouseId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [q, setQ] = useState("");
  const [targetQty, setTargetQty] = useState("10");
  const [salesDays, setSalesDays] = useState("30");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ✅ SIN DEMO: header/rows vacíos (no metas fechas aquí)
  const [header, setHeader] = useState<Header>({});
  const [rows, setRows] = useState<Row[]>([]);

  // marca mount (cliente)
  useEffect(() => {
    setMounted(true);
  }, []);

  const qs = useMemo(() => {
    const p = new URLSearchParams();
    if (warehouseId) p.set("warehouse_id", warehouseId);
    if (categoryId) p.set("category_id", categoryId);
    if (q.trim()) p.set("q", q.trim());
    p.set("target_qty", String(clampInt(targetQty, 10)));
    p.set("sales_days", String(clampInt(salesDays, 30)));
    return p.toString();
  }, [warehouseId, categoryId, q, targetQty, salesDays]);

  async function load() {
    setLoading(true);
    setError(null);

    try {
      const data = (await apiFetch(`/reports/transfer-suggestion-sheet/?${qs}`)) as Resp;

      const nextHeader = data?.header ?? {};
      setHeader(nextHeader);
      setRows(Array.isArray(data?.results) ? data.results : []);
    } catch (e: any) {
      setError(e?.message ?? "Error cargando reporte");
      setRows([]);
      setHeader({});
    } finally {
      setLoading(false);
    }
  }

  // carga automática por filtros (OK)
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qs]);

  const kpis = useMemo(() => {
    const total = rows.length;
    const withSug = rows.filter((r) => toNum(r.suggested) > 0).length;
    const totalSug = rows.reduce((acc, r) => acc + Math.trunc(toNum(r.suggested)), 0);
    const totalOrder = rows.reduce((acc, r) => acc + Math.trunc(toNum(r.qty_to_order ?? r.suggested)), 0);
    return { total, withSug, totalSug, totalOrder };
  }, [rows]);

  function setQtyToOrder(productId: number, value: string) {
    const next = sanitizeQty(value);
    setRows((prev) => prev.map((r) => (r.product_id === productId ? { ...r, qty_to_order: next } : r)));
  }

  function copySuggestedToOrder() {
    setRows((prev) => prev.map((r) => ({ ...r, qty_to_order: sanitizeQty(asIntStr(r.suggested)) })));
  }

  function exportCSV() {
    const cols = [
      "CodigoInterno",
      "CodigoBarras",
      "Descripcion",
      "StockTeorico",
      "StockTransito",
      "StockFisico",
      "PromVtaDia",
      "Sugerido",
      "CantidadAPedir",
    ];

    const lines = [
      cols.join(","),
      ...rows.map((r) =>
        [
          csvEscape(r.internal_code ?? r.product_id),
          csvEscape(r.barcode ?? r.sku ?? ""),
          csvEscape(r.product_name),
          csvEscape(asIntStr(r.stock_theoretical)),
          csvEscape(asIntStr(r.stock_in_transit)),
          csvEscape(asIntStr(r.stock_physical)),
          csvEscape(asDec3Str(r.avg_sales_day)),
          csvEscape(asIntStr(r.suggested)),
          csvEscape(asIntStr(r.qty_to_order ?? r.suggested)),
        ].join(",")
      ),
    ];

    downloadTextFile(`sugerido_transferencia_${new Date().toISOString().slice(0, 10)}.csv`, lines.join("\n"));
  }

  function printReport() {
    window.print();
  }

  function statusOf(r: Row) {
    const sug = toNum(r.suggested);
    if (sug <= 0) return { label: "OK", cls: "bg-emerald-50 text-emerald-800 border-emerald-200" };
    if (sug < 5) return { label: "BAJO", cls: "bg-amber-50 text-amber-900 border-amber-200" };
    return { label: "CRÍTICO", cls: "bg-red-50 text-red-800 border-red-200" };
  }

  const familyLabel = header.category_name ?? (categoryId ? `ID ${categoryId}` : "Todas");

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "16px 12px" : "24px" }} className="grid gap-4">
      {/* Back link (no-print) */}
      <Link href="/dashboard/reports" className="print:hidden" style={{ fontSize: 12, color: C.mute, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4, padding: mob ? "4px 0" : 0 }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg> Reportes
      </Link>
      {/* Top actions (no-print) */}
      <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
        <div>
          <h1 style={{ fontSize: mob ? 20 : 24 }} className="font-black">Reporte para Sugerido de Transferencia</h1>
          <p className="text-sm text-gray-600">Formato tipo planilla (cliente), listo para imprimir/exportar.</p>

          <div className="mt-2 text-xs text-gray-500">
            Endpoint: <span className="font-mono">/reports/transfer-suggestion-sheet/?{qs}</span>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={load}
            disabled={loading}
            className="px-4 py-2 rounded-xl border font-extrabold bg-white hover:bg-gray-50 disabled:opacity-60"
          >
            {loading ? "Cargando..." : "Refrescar"}
          </button>

          <button
            onClick={copySuggestedToOrder}
            disabled={rows.length === 0}
            className="px-4 py-2 rounded-xl border font-extrabold bg-white hover:bg-gray-50 disabled:opacity-60"
          >
            Copiar sugerido → pedir
          </button>

          <button
            onClick={exportCSV}
            disabled={rows.length === 0}
            className="px-4 py-2 rounded-xl border font-extrabold bg-white hover:bg-gray-50 disabled:opacity-60"
          >
            Export CSV
          </button>

          <button
            onClick={printReport}
            className="px-4 py-2 rounded-xl border font-extrabold bg-black text-white hover:opacity-90"
          >
            Imprimir
          </button>
        </div>
      </div>

      {/* Filters (no-print) */}
      <div className="border rounded-2xl bg-white print:hidden" style={{ padding: mob ? "12px" : "16px" }}>
        <div className="grid gap-3">
          <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 1fr 2fr 1fr", gap: 12 }}>
            <div className="grid gap-1">
              <label className="text-xs font-bold text-gray-600">Warehouse ID</label>
              <input
                className="border rounded-xl px-3 py-2"
                value={warehouseId}
                onChange={(e) => setWarehouseId(e.target.value)}
                placeholder="Ej: 2"
              />
            </div>

            <div className="grid gap-1">
              <label className="text-xs font-bold text-gray-600">Familia/Categoría (id)</label>
              <input
                className="border rounded-xl px-3 py-2"
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
                placeholder="Ej: 10"
              />
            </div>

            <div className="grid gap-1">
              <label className="text-xs font-bold text-gray-600">Buscar (código / barras / nombre)</label>
              <input
                className="border rounded-xl px-3 py-2"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Ej: 7802 / jugo / ambrosoli"
              />
            </div>

            <div className="grid gap-1">
              <label className="text-xs font-bold text-gray-600">Target qty</label>
              <input
                className="border rounded-xl px-3 py-2"
                value={targetQty}
                onChange={(e) => setTargetQty(e.target.value)}
                inputMode="numeric"
                placeholder="Ej: 10"
              />
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 4fr", gap: 12, alignItems: "end" }}>
            <div className="grid gap-1">
              <label className="text-xs font-bold text-gray-600">Ventas (días)</label>
              <input
                className="border rounded-xl px-3 py-2"
                value={salesDays}
                onChange={(e) => setSalesDays(e.target.value)}
                inputMode="numeric"
                placeholder="Ej: 30"
              />
            </div>

            <div className="flex flex-wrap gap-2">
              <div className="rounded-xl border px-3 py-2 bg-gray-50 text-sm">
                <span className="font-extrabold">Items:</span> {kpis.total}
              </div>
              <div className="rounded-xl border px-3 py-2 bg-gray-50 text-sm">
                <span className="font-extrabold">Con sugerido &gt; 0:</span> {kpis.withSug}
              </div>
              <div className="rounded-xl border px-3 py-2 bg-gray-50 text-sm">
                <span className="font-extrabold">Total sugerido:</span> {kpis.totalSug.toLocaleString("es-CL")}
              </div>
              <div className="rounded-xl border px-3 py-2 bg-gray-50 text-sm">
                <span className="font-extrabold">Total a pedir:</span> {kpis.totalOrder.toLocaleString("es-CL")}
              </div>

              <button
                type="button"
                className="ml-auto px-4 py-2 rounded-xl border font-extrabold bg-white hover:bg-gray-50"
                onClick={() => {
                  setWarehouseId("");
                  setCategoryId("");
                  setQ("");
                  setTargetQty("10");
                  setSalesDays("30");
                }}
              >
                Limpiar
              </button>
            </div>
          </div>

          {error ? <div className="p-3 rounded-xl border border-red-200 bg-red-50 text-red-800">{error}</div> : null}
        </div>
      </div>

      {/* Report sheet */}
      <div className="bg-white border rounded-2xl print:border-0 print:rounded-none" style={{ padding: mob ? "12px" : "16px" }}>
        <div className="grid gap-3">
          <div style={{ display: "flex", flexDirection: mob ? "column" : "row", alignItems: mob ? "flex-start" : "flex-start", justifyContent: "space-between", gap: 12 }}>
            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-xl border bg-gray-50 flex items-center justify-center font-black">SI</div>
              <div>
                <div className="font-black text-lg">Reporte para Sugerido de Transferencia</div>
                <div className="text-sm text-gray-600">
                  Local:{" "}
                  <span className="font-extrabold">
                    {header.store_code ?? "—"} {header.store_name ?? ""}
                  </span>{" "}
                  — {header.store_address ?? "—"}
                </div>
              </div>
            </div>

            <div className="text-sm">
              <div>
                <span className="text-gray-500">Fecha/Hora:</span>{" "}
                <span
                  className="font-extrabold"
                  suppressHydrationWarning
                >
                  {/* ✅ evita mismatch: en SSR muestra —, en cliente formatea */}
                  {mounted ? formatCLDate(header.generated_at) : "—"}
                </span>
              </div>
              <div>
                <span className="text-gray-500">Usuario:</span>{" "}
                <span className="font-extrabold">{header.user_name ?? "—"}</span>
              </div>
              <div>
                <span className="text-gray-500">Familia:</span>{" "}
                <span className="font-extrabold">{familyLabel}</span>
              </div>
            </div>
          </div>

          <div className="border rounded-xl print:border-0" style={{ overflowX: "auto" }}>
            <table className="min-w-[1100px] w-full text-sm">
              <thead className="bg-gray-50 print:bg-white">
                <tr className="border-b">
                  <th className="text-left p-2 font-extrabold">Código Interno</th>
                  <th className="text-left p-2 font-extrabold">Código Barras</th>
                  <th className="text-left p-2 font-extrabold">Descripción Producto</th>
                  <th className="text-right p-2 font-extrabold">Stock Teórico</th>
                  <th className="text-right p-2 font-extrabold">Stock Tránsito</th>
                  <th className="text-right p-2 font-extrabold">Stock Físico</th>
                  <th className="text-right p-2 font-extrabold">Prom. Vta. día</th>
                  <th className="text-right p-2 font-extrabold">Sugerido</th>
                  <th className="text-right p-2 font-extrabold">Cantidad a Pedir</th>
                  <th className="text-left p-2 font-extrabold print:hidden">Estado</th>
                </tr>
              </thead>

              <tbody>
                {loading ? (
                  <tr>
                    <td className="p-4 text-gray-600" colSpan={10}>
                      Cargando...
                    </td>
                  </tr>
                ) : null}

                {!loading &&
                  rows.map((r, idx) => {
                    const st = statusOf(r);
                    const sug = toNum(r.suggested);

                    return (
                      <tr
                        key={r.product_id}
                        className={`border-b print:bg-white ${
                          sug > 0 ? "bg-amber-50/60" : idx % 2 ? "bg-white" : "bg-gray-50/40"
                        }`}
                      >
                        <td className="p-2 font-bold">{r.internal_code ?? r.product_id}</td>
                        <td className="p-2">{r.barcode ?? r.sku ?? "-"}</td>
                        <td className="p-2">{r.product_name}</td>

                        <td className="p-2 text-right tabular-nums">{asIntStr(r.stock_theoretical)}</td>
                        <td className="p-2 text-right tabular-nums">{asIntStr(r.stock_in_transit)}</td>
                        <td className="p-2 text-right tabular-nums">{asIntStr(r.stock_physical)}</td>
                        <td className="p-2 text-right tabular-nums">{asDec3Str(r.avg_sales_day)}</td>

                        <td className="p-2 text-right tabular-nums font-extrabold">{asIntStr(r.suggested)}</td>

                        <td className="p-2 text-right">
                          <input
                            value={asIntStr(r.qty_to_order ?? r.suggested)}
                            onChange={(e) => setQtyToOrder(r.product_id, e.target.value)}
                            className="w-28 text-right border rounded-lg px-2 py-1 bg-white tabular-nums"
                            inputMode="numeric"
                          />
                        </td>

                        <td className="p-2 print:hidden">
                          <span className={`inline-flex px-2 py-1 rounded-lg border text-xs font-extrabold ${st.cls}`}>
                            {st.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}

                {!loading && rows.length === 0 ? (
                  <tr>
                    <td className="p-4 text-gray-600" colSpan={10}>
                      Sin resultados
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap gap-2 text-xs text-gray-600">
            <div className="px-3 py-2 rounded-xl border bg-gray-50">
              Target qty: <span className="font-extrabold">{clampInt(targetQty, 10)}</span>
            </div>
            <div className="px-3 py-2 rounded-xl border bg-gray-50">
              Ventas días: <span className="font-extrabold">{clampInt(salesDays, 30)}</span>
            </div>
            <div className="px-3 py-2 rounded-xl border bg-gray-50">
              Warehouse: <span className="font-extrabold">{warehouseId || "Todas"}</span>
            </div>
            <div className="px-3 py-2 rounded-xl border bg-gray-50">
              Filtro: <span className="font-extrabold">{q.trim() ? q.trim() : "—"}</span>
            </div>
          </div>
        </div>
      </div>

      <style jsx global>{`
        @media print {
          body {
            background: white !important;
          }
          a,
          button {
            display: none !important;
          }
          input {
            border: 1px solid #ddd !important;
          }
        }
      `}</style>
    </div>
  );
}
