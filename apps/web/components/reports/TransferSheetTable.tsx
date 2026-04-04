"use client";

import React from "react";
import { useIsMobile } from "@/hooks/useIsMobile";

export type Row = {
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

export type Header = {
  store_code?: string | null;
  store_name?: string | null;
  store_address?: string | null;
  category_name?: string | null;
  generated_at?: string | null;
  user_name?: string | null;
};

// ─── Utils ───────────────────────────────────────────────────────────────────
function toNum(s: string | null | undefined) {
  const x = Number(String(s ?? "0").replace(",", "."));
  return Number.isFinite(x) ? x : 0;
}

function asIntStr(v: string | null | undefined) {
  const n = Math.trunc(toNum(v));
  return String(Number.isFinite(n) ? n : 0);
}

function asDec3Str(v: string | null | undefined) {
  const n = toNum(v);
  return Number.isFinite(n) ? n.toFixed(3) : "0.000";
}

function formatCLDate(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("es-CL", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function statusOf(r: Row) {
  const sug = toNum(r.suggested);
  if (sug <= 0) return { label: "OK", cls: "bg-emerald-50 text-emerald-800 border-emerald-200" };
  if (sug < 5) return { label: "BAJO", cls: "bg-amber-50 text-amber-900 border-amber-200" };
  return { label: "CRITICO", cls: "bg-red-50 text-red-800 border-red-200" };
}

// ─── Component ───────────────────────────────────────────────────────────────
interface TransferSheetTableProps {
  header: Header;
  rows: Row[];
  loading: boolean;
  mounted: boolean;
  familyLabel: string;
  onSetQtyToOrder: (productId: number, value: string) => void;
}

export function TransferSheetTable({ header, rows, loading, mounted, familyLabel, onSetQtyToOrder }: TransferSheetTableProps) {
  const mob = useIsMobile();

  return (
    <div className="bg-white border rounded-2xl print:border-0 print:rounded-none" style={{ padding: mob ? "12px" : "16px" }}>
      <div className="grid gap-3">
        <div style={{ display: "flex", flexDirection: mob ? "column" : "row", alignItems: mob ? "flex-start" : "flex-start", justifyContent: "space-between", gap: 12 }}>
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 rounded-xl border bg-gray-50 flex items-center justify-center font-black">SI</div>
            <div>
              <div className="font-black text-lg">Reporte para Sugerido de Transferencia</div>
              <div className="text-sm text-gray-600">
                Local:{" "}
                <span className="font-extrabold">{header.store_code ?? "—"} {header.store_name ?? ""}</span>{" "}
                — {header.store_address ?? "—"}
              </div>
            </div>
          </div>
          <div className="text-sm">
            <div><span className="text-gray-500">Fecha/Hora:</span>{" "}<span className="font-extrabold" suppressHydrationWarning>{mounted ? formatCLDate(header.generated_at) : "—"}</span></div>
            <div><span className="text-gray-500">Usuario:</span>{" "}<span className="font-extrabold">{header.user_name ?? "—"}</span></div>
            <div><span className="text-gray-500">Familia:</span>{" "}<span className="font-extrabold">{familyLabel}</span></div>
          </div>
        </div>

        <div className="border rounded-xl print:border-0" style={{ overflowX: "auto" }}>
          <table className="min-w-[1100px] w-full text-sm">
            <thead className="bg-gray-50 print:bg-white">
              <tr className="border-b">
                <th className="text-left p-2 font-extrabold">Codigo Interno</th>
                <th className="text-left p-2 font-extrabold">Codigo Barras</th>
                <th className="text-left p-2 font-extrabold">Descripcion Producto</th>
                <th className="text-right p-2 font-extrabold">Stock Teorico</th>
                <th className="text-right p-2 font-extrabold">Stock Transito</th>
                <th className="text-right p-2 font-extrabold">Stock Fisico</th>
                <th className="text-right p-2 font-extrabold">Prom. Vta. dia</th>
                <th className="text-right p-2 font-extrabold">Sugerido</th>
                <th className="text-right p-2 font-extrabold">Cantidad a Pedir</th>
                <th className="text-left p-2 font-extrabold print:hidden">Estado</th>
              </tr>
            </thead>
            <tbody>
              {loading ? <tr><td className="p-4 text-gray-600" colSpan={10}>Cargando...</td></tr> : null}
              {!loading && rows.map((r, idx) => {
                const st = statusOf(r);
                const sug = toNum(r.suggested);
                return (
                  <tr key={r.product_id} className={`border-b print:bg-white ${sug > 0 ? "bg-amber-50/60" : idx % 2 ? "bg-white" : "bg-gray-50/40"}`}>
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
                        onChange={e => onSetQtyToOrder(r.product_id, e.target.value)}
                        className="w-28 text-right border rounded-lg px-2 py-1 bg-white tabular-nums"
                        inputMode="numeric"
                      />
                    </td>
                    <td className="p-2 print:hidden">
                      <span className={`inline-flex px-2 py-1 rounded-lg border text-xs font-extrabold ${st.cls}`}>{st.label}</span>
                    </td>
                  </tr>
                );
              })}
              {!loading && rows.length === 0 ? <tr><td className="p-4 text-gray-600" colSpan={10}>Sin resultados</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
