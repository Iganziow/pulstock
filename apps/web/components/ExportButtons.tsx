/**
 * ExportButtons — Componente reutilizable para exportar datos de reportes
 * 
 * Uso:
 *   <ExportButtons
 *     title="Ventas del Período"
 *     subtitle="01/01/2026 - 31/01/2026"
 *     columns={[
 *       { key: "product_name", label: "Producto", width: 30 },
 *       { key: "revenue", label: "Ingreso", width: 15, format: "money" },
 *       { key: "qty", label: "Cantidad", width: 12, format: "number" },
 *     ]}
 *     rows={data}
 *     summaryRows={[
 *       { label: "Total", revenue: "$1.500.000", qty: "320" }
 *     ]}
 *     fileName="ventas-enero-2026"
 *   />
 */

import { useState } from "react";
import { C } from "@/lib/theme";


type ColDef = {
  key: string;
  label: string;
  width?: number;       // column width in characters
  format?: "text" | "number" | "money" | "percent" | "date";
};

type ExportProps = {
  title: string;
  subtitle?: string;
  columns: ColDef[];
  rows: Record<string, any>[];
  summaryRows?: Record<string, any>[];
  fileName?: string;
  compact?: boolean;
};

/**
 * Formats a cell value for display in Excel
 */
function formatCell(value: any, format?: string): string | number {
  if (value === null || value === undefined || value === "") return "";
  if (format === "money") {
    const n = typeof value === "string" ? parseFloat(value) : value;
    return isNaN(n) ? value : n;
  }
  if (format === "number") {
    const n = typeof value === "string" ? parseFloat(value) : value;
    return isNaN(n) ? value : n;
  }
  if (format === "percent") {
    const n = typeof value === "string" ? parseFloat(value) : value;
    return isNaN(n) ? value : n / 100;  // Excel expects 0.19 for 19%
  }
  return String(value);
}

/**
 * Exports to XLSX using SheetJS (loaded dynamically)
 */
async function exportToExcel(props: ExportProps) {
  const { title, subtitle, columns, rows, summaryRows, fileName } = props;

  // Dynamic import of SheetJS
  const XLSX = await import("xlsx");

  // Build data array
  const data: any[][] = [];

  // Title rows
  data.push([title]);
  if (subtitle) data.push([subtitle]);
  data.push([]); // blank row

  // Header row
  data.push(columns.map(c => c.label));

  // Data rows
  for (const row of rows) {
    data.push(columns.map(c => formatCell(row[c.key], c.format)));
  }

  // Summary rows
  if (summaryRows && summaryRows.length > 0) {
    data.push([]); // blank separator
    for (const sr of summaryRows) {
      data.push(columns.map(c => {
        if (c.key === columns[0].key) return sr.label || "Total";
        return formatCell(sr[c.key], c.format);
      }));
    }
  }

  // Create workbook
  const ws = XLSX.utils.aoa_to_sheet(data);

  // Column widths
  ws["!cols"] = columns.map(c => ({ wch: c.width || 15 }));

  // Merge title cell across all columns
  ws["!merges"] = [
    { s: { r: 0, c: 0 }, e: { r: 0, c: columns.length - 1 } },
  ];
  if (subtitle) {
    ws["!merges"].push({ s: { r: 1, c: 0 }, e: { r: 1, c: columns.length - 1 } });
  }

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Reporte");

  // Download
  const name = (fileName || title.toLowerCase().replace(/\s+/g, "-")) + ".xlsx";
  XLSX.writeFile(wb, name);
}

/**
 * Exports to PDF using browser print dialog
 * Creates a clean printable view in a new window
 */
function exportToPDF(props: ExportProps) {
  const { title, subtitle, columns, rows, summaryRows, fileName } = props;

  const fmtValue = (v: any, format?: string) => {
    if (v === null || v === undefined || v === "") return "";
    if (format === "money") {
      const n = typeof v === "string" ? parseFloat(v) : v;
      return isNaN(n) ? v : "$" + Math.round(n).toLocaleString("es-CL");
    }
    if (format === "number") {
      const n = typeof v === "string" ? parseFloat(v) : v;
      return isNaN(n) ? v : Math.round(n).toLocaleString("es-CL");
    }
    if (format === "percent") {
      const n = typeof v === "string" ? parseFloat(v) : v;
      return isNaN(n) ? v : n.toFixed(1) + "%";
    }
    return String(v);
  };

  const headerRow = columns.map(c =>
    `<th style="padding:6px 10px;text-align:${c.format === "money" || c.format === "number" || c.format === "percent" ? "right" : "left"};font-size:11px;font-weight:700;border-bottom:2px solid #333;white-space:nowrap">${c.label}</th>`
  ).join("");

  const dataRows = rows.map((row, i) =>
    `<tr style="background:${i % 2 === 0 ? "#fff" : "#f9f9f9"}">${
      columns.map(c =>
        `<td style="padding:5px 10px;font-size:11px;text-align:${c.format === "money" || c.format === "number" || c.format === "percent" ? "right" : "left"};border-bottom:1px solid #eee;white-space:nowrap">${fmtValue(row[c.key], c.format)}</td>`
      ).join("")
    }</tr>`
  ).join("");

  let summaryHTML = "";
  if (summaryRows && summaryRows.length > 0) {
    summaryHTML = summaryRows.map(sr =>
      `<tr style="font-weight:700;border-top:2px solid #333">${
        columns.map((c, i) =>
          `<td style="padding:6px 10px;font-size:11px;text-align:${i === 0 ? "left" : c.format === "money" || c.format === "number" || c.format === "percent" ? "right" : "left"};white-space:nowrap">${i === 0 ? (sr.label || "Total") : fmtValue(sr[c.key], c.format)}</td>`
        ).join("")
      }</tr>`
    ).join("");
  }

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${title}</title>
  <style>
    @page { margin: 15mm; size: landscape; }
    body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #333; margin: 0; padding: 20px; }
    h1 { font-size: 18px; margin: 0 0 4px; }
    .sub { font-size: 12px; color: #666; margin: 0 0 16px; }
    table { border-collapse: collapse; width: 100%; }
    .footer { margin-top: 20px; font-size: 10px; color: #999; display: flex; justify-content: space-between; }
  </style>
</head>
<body>
  <h1>${title}</h1>
  ${subtitle ? `<p class="sub">${subtitle}</p>` : ""}
  <table>
    <thead><tr>${headerRow}</tr></thead>
    <tbody>${dataRows}${summaryHTML}</tbody>
  </table>
  <div class="footer">
    <span>Generado: ${new Date().toLocaleString("es-CL")}</span>
    <span>${rows.length} registros</span>
  </div>
  <script>window.onload=function(){window.print()}</script>
</body>
</html>`;

  const w = window.open("", "_blank");
  if (w) { w.document.write(html); w.document.close(); }
}

/**
 * ExportButtons Component
 */
export default function ExportButtons(props: ExportProps) {
  const [exporting, setExporting] = useState(false);
  const compact = props.compact !== false;

  const handleExcel = async () => {
    setExporting(true);
    try { await exportToExcel(props); }
    catch (e) { console.error("Export error:", e); alert("Error al exportar. Intenta de nuevo."); }
    finally { setExporting(false); }
  };

  const handlePDF = () => { exportToPDF(props); };

  const btnStyle = (bg: string): React.CSSProperties => ({
    padding: compact ? "6px 12px" : "8px 16px",
    fontSize: 12, fontWeight: 600, cursor: "pointer",
    background: "transparent", border: `1px solid ${C.border}`,
    borderRadius: 6, color: bg, fontFamily: C.font,
    display: "inline-flex", alignItems: "center", gap: 5,
    transition: "all .15s",
  });

  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      <button onClick={handleExcel} disabled={exporting || props.rows.length === 0} style={{ ...btnStyle(C.green), opacity: exporting || props.rows.length === 0 ? .5 : 1 }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        {exporting ? "Exportando…" : "Excel"}
      </button>
      <button onClick={handlePDF} disabled={props.rows.length === 0} style={{ ...btnStyle(C.accent), opacity: props.rows.length === 0 ? .5 : 1 }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
        PDF
      </button>
    </div>
  );
}

/**
 * Helper: builds export config from common report patterns
 */
export function buildExportConfig(type: string, data: any, meta?: any): ExportProps {
  const configs: Record<string, () => ExportProps> = {
    "sales-summary": () => ({
      title: "Reporte de Ventas",
      subtitle: meta?.date_from && meta?.date_to ? `${meta.date_from} a ${meta.date_to}` : undefined,
      columns: [
        { key: "category", label: "Categoría", width: 25 },
        { key: "revenue", label: "Ingreso", width: 15, format: "money" },
        { key: "cost", label: "Costo", width: 15, format: "money" },
        { key: "profit", label: "Ganancia", width: 15, format: "money" },
        { key: "qty", label: "Cantidad", width: 12, format: "number" },
      ],
      rows: data,
      fileName: "ventas-periodo",
    }),
    "top-products": () => ({
      title: "Productos Más Vendidos",
      subtitle: meta?.date_from && meta?.date_to ? `${meta.date_from} a ${meta.date_to}` : undefined,
      columns: [
        { key: "product_name", label: "Producto", width: 30 },
        { key: "category", label: "Categoría", width: 20 },
        { key: "revenue", label: "Ingreso", width: 15, format: "money" },
        { key: "qty", label: "Cantidad", width: 12, format: "number" },
        { key: "profit", label: "Ganancia", width: 15, format: "money" },
        { key: "margin_pct", label: "Margen %", width: 10, format: "percent" },
      ],
      rows: data,
      fileName: "top-productos",
    }),
    "profitability": () => ({
      title: "Rentabilidad",
      subtitle: meta?.group_by === "category" ? "Por Categoría" : "Por Producto",
      columns: [
        { key: meta?.group_by === "category" ? "category" : "product_name", label: meta?.group_by === "category" ? "Categoría" : "Producto", width: 30 },
        { key: "revenue", label: "Ingreso", width: 15, format: "money" },
        { key: "cost", label: "Costo", width: 15, format: "money" },
        { key: "profit", label: "Ganancia", width: 15, format: "money" },
        { key: "margin_pct", label: "Margen %", width: 10, format: "percent" },
        { key: "qty", label: "Cantidad", width: 12, format: "number" },
      ],
      rows: data,
      fileName: "rentabilidad",
    }),
    "losses": () => ({
      title: "Mermas y Pérdidas",
      columns: [
        { key: "product_name", label: "Producto", width: 30 },
        { key: "reason", label: "Motivo", width: 18 },
        { key: "qty", label: "Cantidad", width: 12, format: "number" },
        { key: "value_lost", label: "Valor Perdido", width: 15, format: "money" },
        { key: "warehouse_name", label: "Bodega", width: 18 },
        { key: "created_at", label: "Fecha", width: 18, format: "date" },
      ],
      rows: data,
      fileName: "mermas-perdidas",
    }),
    "stock-valued": () => ({
      title: "Stock Valorizado",
      columns: [
        { key: "name", label: "Producto", width: 30 },
        { key: "sku", label: "SKU", width: 15 },
        { key: "warehouse_name", label: "Bodega", width: 18 },
        { key: "on_hand", label: "En Stock", width: 12, format: "number" },
        { key: "avg_cost", label: "Costo Prom.", width: 15, format: "money" },
        { key: "stock_value", label: "Valor", width: 15, format: "money" },
      ],
      rows: data,
      fileName: "stock-valorizado",
    }),
    "dead-stock": () => ({
      title: "Productos Sin Rotación",
      columns: [
        { key: "product_name", label: "Producto", width: 30 },
        { key: "category", label: "Categoría", width: 20 },
        { key: "on_hand", label: "En Stock", width: 12, format: "number" },
        { key: "stock_value", label: "Valor Parado", width: 15, format: "money" },
        { key: "days_since_last_sale", label: "Días sin venta", width: 14, format: "number" },
      ],
      rows: data,
      fileName: "sin-rotacion",
    }),
    "abc-analysis": () => ({
      title: "Análisis ABC de Inventario",
      columns: [
        { key: "rank", label: "#", width: 5, format: "number" },
        { key: "product_name", label: "Producto", width: 30 },
        { key: "abc_class", label: "Clase", width: 8 },
        { key: "category", label: "Categoría", width: 20 },
        { key: "revenue", label: "Ingreso", width: 15, format: "money" },
        { key: "profit", label: "Ganancia", width: 15, format: "money" },
        { key: "margin_pct", label: "Margen %", width: 10, format: "percent" },
        { key: "contribution_pct", label: "% Contribución", width: 13, format: "percent" },
        { key: "cumulative_pct", label: "% Acumulado", width: 12, format: "percent" },
        { key: "current_stock", label: "Stock", width: 10, format: "number" },
      ],
      rows: data,
      fileName: "analisis-abc",
    }),
    "audit-trail": () => ({
      title: "Auditoría de Movimientos",
      columns: [
        { key: "created_at", label: "Fecha", width: 18, format: "date" },
        { key: "product_name", label: "Producto", width: 25 },
        { key: "move_type", label: "Tipo", width: 8 },
        { key: "ref_type", label: "Operación", width: 14 },
        { key: "qty", label: "Cantidad", width: 12, format: "number" },
        { key: "value_delta", label: "Impacto $", width: 15, format: "money" },
        { key: "warehouse_name", label: "Bodega", width: 18 },
        { key: "user", label: "Usuario", width: 15 },
        { key: "note", label: "Nota", width: 25 },
      ],
      rows: data,
      fileName: "auditoria-movimientos",
    }),
    "inventory-count": () => ({
      title: "Hoja de Conteo de Inventario",
      columns: [
        { key: "product_name", label: "Producto", width: 30 },
        { key: "sku", label: "SKU", width: 15 },
        { key: "category", label: "Categoría", width: 18 },
        { key: "unit", label: "Unidad", width: 8 },
        { key: "stock_system", label: "Stock Sistema", width: 14, format: "number" },
        { key: "stock_physical", label: "Conteo Real", width: 14 },
        { key: "difference", label: "Diferencia", width: 12 },
        { key: "note", label: "Observación", width: 25 },
      ],
      rows: data,
      fileName: "hoja-conteo",
    }),
    "inventory-diff": () => ({
      title: "Diferencias Físico vs Sistema",
      columns: [
        { key: "product_name", label: "Producto", width: 30 },
        { key: "category", label: "Categoría", width: 18 },
        { key: "stock_system", label: "Sistema", width: 12, format: "number" },
        { key: "stock_physical", label: "Real", width: 12, format: "number" },
        { key: "difference_qty", label: "Diferencia", width: 12, format: "number" },
        { key: "difference_value", label: "Impacto $", width: 15, format: "money" },
        { key: "status", label: "Estado", width: 12 },
      ],
      rows: data,
      fileName: "diferencias-inventario",
    }),
  };

  return configs[type]?.() || {
    title: "Reporte",
    columns: Object.keys(data[0] || {}).map(k => ({ key: k, label: k, width: 15 })),
    rows: data,
  };
}