"use client";

import React from "react";
import { useIsMobile } from "@/hooks/useIsMobile";

function clampInt(v: string, fallback: number) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : fallback;
}

interface KPIs {
  total: number;
  withSug: number;
  totalSug: number;
  totalOrder: number;
}

interface TransferSheetFiltersProps {
  warehouseId: string; setWarehouseId: (v: string) => void;
  categoryId: string; setCategoryId: (v: string) => void;
  q: string; setQ: (v: string) => void;
  targetQty: string; setTargetQty: (v: string) => void;
  salesDays: string; setSalesDays: (v: string) => void;
  kpis: KPIs;
  loading: boolean;
  error: string | null;
  onLoad: () => void;
  onCopySuggested: () => void;
  onExportCSV: () => void;
  onPrint: () => void;
  rowsCount: number;
  qs: string;
  onClear: () => void;
}

export function TransferSheetFilters({
  warehouseId, setWarehouseId, categoryId, setCategoryId, q, setQ,
  targetQty, setTargetQty, salesDays, setSalesDays, kpis,
  loading, error, onLoad, onCopySuggested, onExportCSV, onPrint, rowsCount, qs, onClear,
}: TransferSheetFiltersProps) {
  const mob = useIsMobile();

  return (
    <>
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
          <button type="button" onClick={onLoad} disabled={loading} className="px-4 py-2 rounded-xl border font-extrabold bg-white hover:bg-gray-50 disabled:opacity-60">
            {loading ? "Cargando..." : "Refrescar"}
          </button>
          <button type="button" onClick={onCopySuggested} disabled={rowsCount === 0} className="px-4 py-2 rounded-xl border font-extrabold bg-white hover:bg-gray-50 disabled:opacity-60">
            Copiar sugerido → pedir
          </button>
          <button type="button" onClick={onExportCSV} disabled={rowsCount === 0} className="px-4 py-2 rounded-xl border font-extrabold bg-white hover:bg-gray-50 disabled:opacity-60">
            Export CSV
          </button>
          <button type="button" onClick={onPrint} className="px-4 py-2 rounded-xl border font-extrabold bg-black text-white hover:opacity-90">
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
              <input className="border rounded-xl px-3 py-2" value={warehouseId} onChange={e => setWarehouseId(e.target.value)} placeholder="Ej: 2" />
            </div>
            <div className="grid gap-1">
              <label className="text-xs font-bold text-gray-600">Familia/Categoria (id)</label>
              <input className="border rounded-xl px-3 py-2" value={categoryId} onChange={e => setCategoryId(e.target.value)} placeholder="Ej: 10" />
            </div>
            <div className="grid gap-1">
              <label className="text-xs font-bold text-gray-600">Buscar (codigo / barras / nombre)</label>
              <input className="border rounded-xl px-3 py-2" value={q} onChange={e => setQ(e.target.value)} placeholder="Ej: 7802 / jugo / ambrosoli" />
            </div>
            <div className="grid gap-1">
              <label className="text-xs font-bold text-gray-600">Target qty</label>
              <input className="border rounded-xl px-3 py-2" value={targetQty} onChange={e => setTargetQty(e.target.value)} inputMode="numeric" placeholder="Ej: 10" />
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 4fr", gap: 12, alignItems: "end" }}>
            <div className="grid gap-1">
              <label className="text-xs font-bold text-gray-600">Ventas (dias)</label>
              <input className="border rounded-xl px-3 py-2" value={salesDays} onChange={e => setSalesDays(e.target.value)} inputMode="numeric" placeholder="Ej: 30" />
            </div>
            <div className="flex flex-wrap gap-2">
              <div className="rounded-xl border px-3 py-2 bg-gray-50 text-sm"><span className="font-extrabold">Items:</span> {kpis.total}</div>
              <div className="rounded-xl border px-3 py-2 bg-gray-50 text-sm"><span className="font-extrabold">Con sugerido &gt; 0:</span> {kpis.withSug}</div>
              <div className="rounded-xl border px-3 py-2 bg-gray-50 text-sm"><span className="font-extrabold">Total sugerido:</span> {kpis.totalSug.toLocaleString("es-CL")}</div>
              <div className="rounded-xl border px-3 py-2 bg-gray-50 text-sm"><span className="font-extrabold">Total a pedir:</span> {kpis.totalOrder.toLocaleString("es-CL")}</div>
              <button type="button" className="ml-auto px-4 py-2 rounded-xl border font-extrabold bg-white hover:bg-gray-50" onClick={onClear}>Limpiar</button>
            </div>
          </div>

          {error ? <div className="p-3 rounded-xl border border-red-200 bg-red-50 text-red-800">{error}</div> : null}
        </div>
      </div>
    </>
  );
}
