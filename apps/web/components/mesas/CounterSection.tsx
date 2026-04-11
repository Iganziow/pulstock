"use client";

import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
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
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      padding: "10px 14px", marginBottom: 8,
      background: C.surface, borderRadius: 10,
      border: `1px solid ${C.border}`,
      overflowX: "auto",
    }}>
      {/* Label + new button */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
        <span style={{ fontSize: 16 }}>🛍️</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: C.text, whiteSpace: "nowrap" }}>Para llevar</span>
      </div>

      {/* Divider */}
      <div style={{ width: 1, height: 28, background: C.border, flexShrink: 0 }} />

      {/* Order chips */}
      {counterOrders.length > 0 ? (
        counterOrders.map(t => {
          const isSel = selectedTableId === t.id;
          const name = t.active_order?.customer_name || t.name;
          const items = t.active_order?.items_count || 0;
          const total = t.active_order ? Number(t.active_order.subtotal) : 0;

          return (
            <button key={t.id} type="button" onClick={() => onSelectTable(t)} style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "6px 12px", borderRadius: 8, flexShrink: 0,
              background: isSel ? C.accentBg : "#FFFBEB",
              border: `1.5px solid ${isSel ? C.accent : C.amberBd}`,
              cursor: "pointer", fontFamily: C.font,
              transition: "all .12s",
            }}>
              <div style={{ textAlign: "left" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: isSel ? C.accent : C.text, whiteSpace: "nowrap" }}>
                  {name}
                </div>
                <div style={{ fontSize: 9, color: C.mute, whiteSpace: "nowrap" }}>
                  {items} item{items !== 1 ? "s" : ""} · {t.active_order ? timeAgo(t.active_order.opened_at) : ""}
                </div>
              </div>
              {total > 0 && (
                <span style={{ fontSize: 12, fontWeight: 800, color: isSel ? C.accent : C.amber, whiteSpace: "nowrap" }}>
                  ${fmt(t.active_order!.subtotal)}
                </span>
              )}
            </button>
          );
        })
      ) : (
        <span style={{ fontSize: 11, color: C.mute, whiteSpace: "nowrap" }}>Sin pedidos activos</span>
      )}

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* New order button */}
      <button type="button" onClick={onNewCounter} disabled={counterLoading} style={{
        display: "flex", alignItems: "center", gap: 5,
        padding: "7px 14px", borderRadius: 8, flexShrink: 0,
        background: C.accent, color: "#fff",
        border: "none", cursor: counterLoading ? "wait" : "pointer",
        fontSize: 12, fontWeight: 700, fontFamily: C.font,
        transition: "all .12s",
      }}>
        {counterLoading ? <Spinner size={12} /> : (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
        )}
        Nuevo
      </button>
    </div>
  );
}
