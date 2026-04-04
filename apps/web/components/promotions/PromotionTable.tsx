"use client";

import { C } from "@/lib/theme";
import { Btn, Spinner } from "@/components/ui";
import { StatusBadge } from "./StatusBadge";
import { discountLabel, formatDate } from "./helpers";
import type { Promotion } from "./types";

interface PromotionTableProps {
  promotions: Promotion[];
  loading: boolean;
  onEdit: (promo: Promotion) => void;
  onClone: (promo: Promotion) => void;
  onDelete: (id: number) => void;
}

const thStyle: React.CSSProperties = {
  padding: "10px 14px", fontSize: 11, fontWeight: 600,
  color: C.mute, textTransform: "uppercase", letterSpacing: "0.04em",
  textAlign: "left", borderBottom: `1px solid ${C.border}`,
  background: C.bg, whiteSpace: "nowrap",
};

const tdStyle: React.CSSProperties = {
  padding: "12px 14px", fontSize: 13, color: C.text,
  borderBottom: `1px solid ${C.border}`, whiteSpace: "nowrap",
};

export function PromotionTable({ promotions, loading, onEdit, onClone, onDelete }: PromotionTableProps) {
  return (
    <div style={{
      background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`,
      boxShadow: C.sh, overflow: "auto",
    }}>
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
          <Spinner size={22} />
        </div>
      ) : promotions.length === 0 ? (
        <div style={{ padding: 48, textAlign: "center", color: C.mute, fontSize: 14 }}>
          No hay ofertas creadas aun
        </div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={thStyle}>Nombre</th>
              <th style={thStyle}>Tipo</th>
              <th style={thStyle}>Fecha inicio</th>
              <th style={thStyle}>Fecha fin</th>
              <th style={thStyle}>Estado</th>
              <th style={thStyle}>N° productos</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {promotions.map((p) => (
              <tr key={p.id} style={{ transition: C.ease }}>
                <td style={{ ...tdStyle, fontWeight: 600 }}>{p.name}</td>
                <td style={tdStyle}>{discountLabel(p.discount_type, p.discount_value)}</td>
                <td style={tdStyle}>{formatDate(p.start_date)}</td>
                <td style={tdStyle}>{formatDate(p.end_date)}</td>
                <td style={tdStyle}><StatusBadge status={p.status} /></td>
                <td style={tdStyle}>{p.product_count}</td>
                <td style={{ ...tdStyle, textAlign: "right" }}>
                  <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                    <Btn size="sm" variant="ghost" onClick={() => onClone(p)}>Duplicar</Btn>
                    <Btn size="sm" variant="ghost" onClick={() => onEdit(p)}>Editar</Btn>
                    <Btn size="sm" variant="danger" onClick={() => onDelete(p.id)}>Desactivar</Btn>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
