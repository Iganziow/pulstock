"use client";

import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { Btn } from "@/components/ui/Button";
import { Table } from "./types";
import { fmt, timeAgo } from "./helpers";

interface CounterSectionProps {
  counterOrders: Table[];
  selectedTableId: number | undefined;
  counterLoading: boolean;
  onSelectTable: (t: Table) => void;
  onNewCounter: () => void;
}

export function CounterSection({ counterOrders, selectedTableId, counterLoading, onSelectTable, onNewCounter }: CounterSectionProps) {
  return (
    <div style={{ marginTop: 16, paddingTop: 14, borderTop: `1px solid ${C.border}` }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 14 }}>{"\uD83D\uDCE6"}</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Para llevar</span>
          {counterOrders.length > 0 && (
            <span style={{ padding: "1px 7px", borderRadius: 99, fontSize: 10, fontWeight: 700, background: C.amberBg, color: C.amber, border: `1px solid ${C.amberBd}` }}>
              {counterOrders.length}
            </span>
          )}
        </div>
        <Btn variant="primary" size="sm" disabled={counterLoading} onClick={onNewCounter}>
          {counterLoading ? <Spinner size={12} /> : <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>}
          Nuevo
        </Btn>
      </div>

      {counterOrders.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {counterOrders.map(t => {
            const isSel = selectedTableId === t.id;
            return (
              <div key={t.id} onClick={() => onSelectTable(t)} style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "10px 12px", borderRadius: C.r,
                background: isSel ? C.accentBg : C.surface,
                border: `1px solid ${isSel ? C.accent : C.border}`,
                cursor: "pointer",
              }}>
                <span style={{ fontSize: 14 }}>{"\uD83D\uDCE6"}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: C.text }}>
                    {t.active_order?.customer_name || t.name}
                  </div>
                  <div style={{ fontSize: 10, color: C.mute }}>
                    {t.active_order?.customer_name && <span style={{ color: C.mid }}>{t.name} &middot; </span>}
                    {t.active_order ? `${t.active_order.items_count} item${t.active_order.items_count !== 1 ? "s" : ""} \u00b7 ${timeAgo(t.active_order.opened_at)}` : ""}
                  </div>
                </div>
                {t.active_order && Number(t.active_order.subtotal) > 0 && (
                  <span style={{ fontWeight: 800, fontSize: 13, color: C.text }}>${fmt(t.active_order.subtotal)}</span>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{ padding: 12, textAlign: "center", color: C.mute, fontSize: 11, background: C.surface, borderRadius: C.r, border: `1px solid ${C.border}` }}>
          Sin pedidos para llevar activos.
        </div>
      )}
    </div>
  );
}
