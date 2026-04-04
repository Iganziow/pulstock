"use client";

import React from "react";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { fmt, fmtDate, type Session } from "./CajaShared";

interface CajaHistoryProps {
  history: Session[];
  histLoad: boolean;
  histPage: number;
  histTotal: number;
  onPageChange: (page: number) => void;
}

export function CajaHistory({ history, histLoad, histPage, histTotal, onPageChange }: CajaHistoryProps) {
  if (histLoad) return <div style={{ textAlign: "center", padding: 48 }}><Spinner /></div>;

  if (history.length === 0) return <div style={{ padding: 32, textAlign: "center", color: C.mute, fontSize: 14 }}>Sin arqueos cerrados.</div>;

  const totalPages = Math.ceil(histTotal / 20);

  return (
    <>
      <div style={{ display: "grid", gap: 10 }}>
        {history.map(s => {
          const diff = Number(s.difference ?? 0);
          return (
            <div key={s.id} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "14px 18px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14 }}>{s.register_name}</div>
                  <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>
                    {fmtDate(s.opened_at)} → {s.closed_at ? fmtDate(s.closed_at) : "—"}
                  </div>
                  <div style={{ fontSize: 12, color: C.mute }}>Cajero: {s.opened_by}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 11, color: C.mute }}>Diferencia</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: diff >= 0 ? C.green : C.red, fontVariantNumeric: "tabular-nums" }}>
                    {diff >= 0 ? "+" : ""}${fmt(Math.abs(diff))}
                  </div>
                </div>
              </div>
              <div style={{ marginTop: 10, display: "flex", gap: 24, fontSize: 12, color: C.mid }}>
                <span>Esperado: <b style={{ color: C.text }}>${fmt(s.expected_cash ?? 0)}</b></span>
                <span>Contado: <b style={{ color: C.text }}>${fmt(s.counted_cash ?? 0)}</b></span>
              </div>
            </div>
          );
        })}
      </div>

      {histTotal > 20 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 12 }}>
          <button
            disabled={histPage <= 1}
            onClick={() => onPageChange(histPage - 1)}
            style={{ padding: "6px 14px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: histPage <= 1 ? "default" : "pointer", opacity: histPage <= 1 ? 0.4 : 1, fontSize: 13 }}
          >← Anterior</button>
          <span style={{ fontSize: 13, color: C.mid, alignSelf: "center" }}>
            Pagina {histPage} de {totalPages}
          </span>
          <button
            disabled={histPage >= totalPages}
            onClick={() => onPageChange(histPage + 1)}
            style={{ padding: "6px 14px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: histPage >= totalPages ? "default" : "pointer", opacity: histPage >= totalPages ? 0.4 : 1, fontSize: 13 }}
          >Siguiente →</button>
        </div>
      )}
    </>
  );
}
