"use client";

import { C } from "@/lib/theme";
import { Btn } from "@/components/ui";
import { formatCLP } from "@/lib/format";
import type { BulkPreviewItem } from "./types";

interface BulkPreviewModalProps {
  bulkDir: "increase" | "decrease";
  bulkType: "pct" | "amt";
  bulkValue: string;
  bulkPreview: BulkPreviewItem[];
  onCancel: () => void;
  onConfirm: () => void;
}

export function BulkPreviewModal({ bulkDir, bulkType, bulkValue, bulkPreview, onCancel, onConfirm }: BulkPreviewModalProps) {
  const thStyle: React.CSSProperties = {
    padding: "10px 12px", fontSize: 11, fontWeight: 700, color: C.mute,
    textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left",
    borderBottom: `2px solid ${C.border}`, whiteSpace: "nowrap",
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={onCancel}>
      <div style={{ background: C.surface, borderRadius: C.rMd, width: 600, maxWidth: "95vw", maxHeight: "80vh", overflow: "auto", boxShadow: C.shLg, padding: 24 }} onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 8px", fontSize: 16, fontWeight: 700 }}>Preview — Ajuste masivo</h3>
        <p style={{ margin: "0 0 4px", fontSize: 13, color: C.mid }}>
          {bulkDir === "increase" ? "Subir" : "Bajar"} {bulkType === "pct" ? `${bulkValue}%` : `$${formatCLP(bulkValue)}`} a {bulkPreview.length} producto(s)
        </p>
        {bulkPreview.some(p => (p.newMargin ?? 0) < 0) && (
          <p style={{ margin: "4px 0 8px", fontSize: 12, color: C.red, fontWeight: 600 }}>
            Algunos productos quedaran con margen negativo
          </p>
        )}
        <div style={{ maxHeight: 320, overflow: "auto", border: `1px solid ${C.border}`, borderRadius: C.r }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px" }}>Producto</th>
                <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Actual</th>
                <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Nuevo</th>
                <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Margen</th>
              </tr>
            </thead>
            <tbody>
              {bulkPreview.map(p => (
                <tr key={p.id} style={{ background: (p.newMargin ?? 0) < 0 ? C.redBg : undefined }}>
                  <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}` }}>{p.name}</td>
                  <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono }}>${formatCLP(p.oldPrice)}</td>
                  <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono, fontWeight: 700 }}>${formatCLP(p.newPrice)}</td>
                  <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono, color: p.newMargin !== null ? (p.newMargin < 0 ? C.red : p.newMargin < 15 ? C.amber : C.green) : C.mute }}>
                    {p.newMargin !== null ? `${p.newMargin.toFixed(1)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <Btn variant="secondary" onClick={onCancel}>Cancelar</Btn>
          <Btn variant="primary" onClick={onConfirm}>Confirmar y aplicar</Btn>
        </div>
      </div>
    </div>
  );
}
