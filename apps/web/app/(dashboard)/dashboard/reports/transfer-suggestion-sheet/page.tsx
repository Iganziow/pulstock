"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { TransferSheetFilters } from "@/components/reports/TransferSheetFilters";
import { TransferSheetTable, type Row, type Header } from "@/components/reports/TransferSheetTable";

// ─── Utils ───────────────────────────────────────────────────────────────────
function toNum(s: string | null | undefined) {
  const x = Number(String(s ?? "0").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
}

function clampInt(v: string, fallback: number) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : fallback;
}

function asIntStr(v: string | null | undefined) {
  const n = Math.trunc(toNum(v));
  return String(Number.isFinite(n) ? n : 0);
}

function asDec3Str(v: string | null | undefined) {
  const n = toNum(v);
  return Number.isFinite(n) ? n.toFixed(3) : "0.000";
}

function sanitizeQty(v: string) {
  const cleaned = v.replace(/[^\d-]/g, "").trim();
  if (cleaned === "") return "0";
  const n = parseInt(cleaned, 10);
  if (!Number.isFinite(n) || n < 0) return "0";
  return String(n);
}

function downloadTextFile(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function csvEscape(v: any) {
  const s = String(v ?? "");
  if (s.includes(",") || s.includes('"') || s.includes("\n")) return `"${s.replaceAll('"', '""')}"`;
  return s;
}

type Resp = { header: Header; meta?: any; results: Row[] };

// ─── Page ────────────────────────────────────────────────────────────────────
export default function TransferSuggestionSheetPage() {
  const mob = useIsMobile();
  const [mounted, setMounted] = useState(false);
  const [warehouseId, setWarehouseId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [q, setQ] = useState("");
  const [targetQty, setTargetQty] = useState("10");
  const [salesDays, setSalesDays] = useState("30");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [header, setHeader] = useState<Header>({});
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => { setMounted(true); }, []);

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
    setLoading(true); setError(null);
    try {
      const data = (await apiFetch(`/reports/transfer-suggestion-sheet/?${qs}`)) as Resp;
      setHeader(data?.header ?? {});
      setRows(Array.isArray(data?.results) ? data.results : []);
    } catch (e: any) { setError(e?.message ?? "Error cargando reporte"); setRows([]); setHeader({}); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, [qs]); // eslint-disable-line react-hooks/exhaustive-deps

  const kpis = useMemo(() => {
    const total = rows.length;
    const withSug = rows.filter(r => toNum(r.suggested) > 0).length;
    const totalSug = rows.reduce((acc, r) => acc + Math.trunc(toNum(r.suggested)), 0);
    const totalOrder = rows.reduce((acc, r) => acc + Math.trunc(toNum(r.qty_to_order ?? r.suggested)), 0);
    return { total, withSug, totalSug, totalOrder };
  }, [rows]);

  function setQtyToOrder(productId: number, value: string) {
    const next = sanitizeQty(value);
    setRows(prev => prev.map(r => r.product_id === productId ? { ...r, qty_to_order: next } : r));
  }

  function copySuggestedToOrder() {
    setRows(prev => prev.map(r => ({ ...r, qty_to_order: sanitizeQty(asIntStr(r.suggested)) })));
  }

  function exportCSV() {
    const cols = ["CodigoInterno", "CodigoBarras", "Descripcion", "StockTeorico", "StockTransito", "StockFisico", "PromVtaDia", "Sugerido", "CantidadAPedir"];
    const lines = [
      cols.join(","),
      ...rows.map(r => [
        csvEscape(r.internal_code ?? r.product_id), csvEscape(r.barcode ?? r.sku ?? ""), csvEscape(r.product_name),
        csvEscape(asIntStr(r.stock_theoretical)), csvEscape(asIntStr(r.stock_in_transit)), csvEscape(asIntStr(r.stock_physical)),
        csvEscape(asDec3Str(r.avg_sales_day)), csvEscape(asIntStr(r.suggested)), csvEscape(asIntStr(r.qty_to_order ?? r.suggested)),
      ].join(","))
    ];
    downloadTextFile(`sugerido_transferencia_${new Date().toISOString().slice(0, 10)}.csv`, lines.join("\n"));
  }

  const familyLabel = header.category_name ?? (categoryId ? `ID ${categoryId}` : "Todas");

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "16px 12px" : "24px" }} className="grid gap-4">
      {/* Back link */}
      <Link href="/dashboard/reports" className="print:hidden" style={{ fontSize: 12, color: C.mute, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4, padding: mob ? "4px 0" : 0 }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg> Reportes
      </Link>

      <TransferSheetFilters
        warehouseId={warehouseId} setWarehouseId={setWarehouseId}
        categoryId={categoryId} setCategoryId={setCategoryId}
        q={q} setQ={setQ}
        targetQty={targetQty} setTargetQty={setTargetQty}
        salesDays={salesDays} setSalesDays={setSalesDays}
        kpis={kpis} loading={loading} error={error}
        onLoad={load} onCopySuggested={copySuggestedToOrder} onExportCSV={exportCSV} onPrint={() => window.print()}
        rowsCount={rows.length} qs={qs}
        onClear={() => { setWarehouseId(""); setCategoryId(""); setQ(""); setTargetQty("10"); setSalesDays("30"); }}
      />

      <TransferSheetTable header={header} rows={rows} loading={loading} mounted={mounted} familyLabel={familyLabel} onSetQtyToOrder={setQtyToOrder} />

      {/* Footer KPIs */}
      <div className="flex flex-wrap gap-2 text-xs text-gray-600">
        <div className="px-3 py-2 rounded-xl border bg-gray-50">Target qty: <span className="font-extrabold">{clampInt(targetQty, 10)}</span></div>
        <div className="px-3 py-2 rounded-xl border bg-gray-50">Ventas dias: <span className="font-extrabold">{clampInt(salesDays, 30)}</span></div>
        <div className="px-3 py-2 rounded-xl border bg-gray-50">Warehouse: <span className="font-extrabold">{warehouseId || "Todas"}</span></div>
        <div className="px-3 py-2 rounded-xl border bg-gray-50">Filtro: <span className="font-extrabold">{q.trim() ? q.trim() : "—"}</span></div>
      </div>

      <style jsx global>{`
        @media print {
          body { background: white !important; }
          a, button { display: none !important; }
          input { border: 1px solid #ddd !important; }
        }
      `}</style>
    </div>
  );
}
