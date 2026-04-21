"use client";

import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { formatCLP } from "@/lib/format";
import { calcMargin } from "./helpers";
import type { PriceRow } from "./types";

interface PriceTableProps {
  rows: PriceRow[];
  loading: boolean;
  edits: Record<number, string>;
  selected: Set<number>;
  allSelected: boolean;
  toggleAll: () => void;
  toggleOne: (id: number) => void;
  setNewPrice: (id: number, val: string) => void;
  total: number;
  pageSize: number;
  page: number;
  setPage: React.Dispatch<React.SetStateAction<number>>;
}

const thStyle: React.CSSProperties = {
  padding: "10px 12px",
  fontSize: 11,
  fontWeight: 700,
  color: C.mute,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  textAlign: "left",
  borderBottom: `2px solid ${C.border}`,
  whiteSpace: "nowrap",
};

const tdStyle: React.CSSProperties = {
  padding: "10px 12px",
  fontSize: 13,
  borderBottom: `1px solid ${C.border}`,
  verticalAlign: "middle",
};

export function PriceTable({
  rows, loading, edits, selected, allSelected,
  toggleAll, toggleOne, setNewPrice,
  total, pageSize, page, setPage,
}: PriceTableProps) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "auto", boxShadow: C.sh }}>
      {loading ? (
        <div style={{ padding: 40, display: "flex", justifyContent: "center", alignItems: "center", gap: 8, color: C.mute, fontSize: 13 }}>
          <Spinner size={16} /> Cargando...
        </div>
      ) : rows.length === 0 ? (
        <div style={{ padding: 40, textAlign: "center", color: C.mute, fontSize: 13 }}>
          No se encontraron productos
        </div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...thStyle, width: 40, textAlign: "center" }}>
                <input type="checkbox" checked={allSelected} onChange={toggleAll} style={{ cursor: "pointer" }} />
              </th>
              <th style={thStyle}>SKU</th>
              <th style={thStyle}>Nombre</th>
              <th style={thStyle}>Categoria</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Costo</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Precio Actual</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Margen %</th>
              <th style={{ ...thStyle, textAlign: "right", minWidth: 130 }}>Nuevo Precio</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Nuevo Margen</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const hasEdit = row.id in edits;
              const newPrice = edits[row.id] ?? "";
              const newMargin = hasEdit ? calcMargin(row.cost, newPrice) : null;
              const currentMargin = Number(row.margin_pct);

              return (
                <tr key={row.id} style={{ background: hasEdit ? C.amberBg : undefined, transition: C.ease }}>
                  <td style={{ ...tdStyle, textAlign: "center" }}>
                    <input type="checkbox" checked={selected.has(row.id)} onChange={() => toggleOne(row.id)} style={{ cursor: "pointer" }} />
                  </td>
                  <td style={{ ...tdStyle, fontFamily: C.mono, fontSize: 12, color: C.mid }}>
                    {row.sku || "—"}
                  </td>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{row.name}</td>
                  <td style={{ ...tdStyle, color: C.mid, fontSize: 12 }}>{row.category_name || "—"}</td>
                  <td style={{ ...tdStyle, textAlign: "right", fontFamily: C.mono }}>${formatCLP(row.cost)}</td>
                  <td style={{ ...tdStyle, textAlign: "right", fontFamily: C.mono, fontWeight: 600 }}>${formatCLP(row.price)}</td>
                  <td style={{ ...tdStyle, textAlign: "right", fontFamily: C.mono, color: Number.isFinite(currentMargin) ? (currentMargin < 0 ? C.red : currentMargin < 15 ? C.amber : C.green) : C.mute }}>
                    {Number.isFinite(currentMargin) ? `${currentMargin.toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right" }}>
                    <input
                      type="text"
                      inputMode="numeric"
                      placeholder={formatCLP(row.price)}
                      value={newPrice}
                      onChange={(e) => setNewPrice(row.id, e.target.value)}
                      style={{
                        width: 110, height: 30, padding: "0 8px",
                        border: `1px solid ${hasEdit ? C.amberBd : C.border}`,
                        borderRadius: C.r, fontSize: 13, fontFamily: C.mono,
                        textAlign: "right", background: hasEdit ? C.surface : C.bg,
                      }}
                    />
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right", fontFamily: C.mono, fontWeight: hasEdit ? 700 : 400, color: newMargin !== null ? (newMargin < 0 ? C.red : newMargin < 15 ? C.amber : C.green) : C.mute }}>
                    {newMargin !== null ? `${newMargin.toFixed(1)}%` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {/* Pagination */}
      {total > pageSize && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 12, paddingBottom: 8 }}>
          <button
            disabled={page <= 1}
            onClick={() => setPage(p => p - 1)}
            style={{ padding: "6px 14px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: page <= 1 ? "default" : "pointer", opacity: page <= 1 ? 0.4 : 1, fontSize: 13 }}
          >← Anterior</button>
          <span style={{ fontSize: 13, color: C.mid, alignSelf: "center" }}>
            Pagina {page} de {Math.ceil(total / pageSize)}
          </span>
          <button
            disabled={page >= Math.ceil(total / pageSize)}
            onClick={() => setPage(p => p + 1)}
            style={{ padding: "6px 14px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: page >= Math.ceil(total / pageSize) ? "default" : "pointer", opacity: page >= Math.ceil(total / pageSize) ? 0.4 : 1, fontSize: 13 }}
          >Siguiente →</button>
        </div>
      )}
    </div>
  );
}
