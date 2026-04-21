"use client";

import { C } from "@/lib/theme";
import { Btn } from "@/components/ui";
import { formatCLP } from "@/lib/format";
import { calcMargin } from "./helpers";
import type { PriceRow } from "./types";

const thStyle: React.CSSProperties = {
  padding: "10px 12px", fontSize: 11, fontWeight: 700, color: C.mute,
  textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left",
  borderBottom: `2px solid ${C.border}`, whiteSpace: "nowrap",
};

interface SaveConfirmModalProps {
  edits: Record<number, string>;
  rows: PriceRow[];
  onCancel: () => void;
  onConfirm: () => void;
}

export function SaveConfirmModal({ edits, rows, onCancel, onConfirm }: SaveConfirmModalProps) {
  const changedCount = Object.keys(edits).length;

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={onCancel}>
      <div style={{ background: C.surface, borderRadius: C.rMd, width: 520, maxWidth: "95vw", maxHeight: "80vh", overflow: "auto", boxShadow: C.shLg, padding: 24 }} onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 12px", fontSize: 16, fontWeight: 700 }}>Confirmar cambios de precio</h3>
        <p style={{ margin: "0 0 12px", fontSize: 13, color: C.mid }}>Se actualizaran {changedCount} producto(s):</p>
        <div style={{ maxHeight: 300, overflow: "auto", border: `1px solid ${C.border}`, borderRadius: C.r }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px" }}>Producto</th>
                <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Precio actual</th>
                <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Nuevo precio</th>
                <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Margen</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(edits).map(([pid, newP]) => {
                const row = rows.find(r => r.id === Number(pid));
                if (!row) return null;
                const nm = calcMargin(row.cost, newP);
                return (
                  <tr key={pid}>
                    <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}` }}>{row.name}</td>
                    <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono }}>${formatCLP(row.price)}</td>
                    <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono, fontWeight: 700 }}>${formatCLP(newP)}</td>
                    <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono, color: nm !== null ? (nm < 0 ? C.red : nm < 15 ? C.amber : C.green) : C.mute }}>
                      {nm !== null ? `${nm.toFixed(1)}%` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <Btn variant="secondary" onClick={onCancel}>Cancelar</Btn>
          <Btn variant="success" onClick={onConfirm}>Confirmar y guardar</Btn>
        </div>
      </div>
    </div>
  );
}
