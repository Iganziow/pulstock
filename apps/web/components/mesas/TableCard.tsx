"use client";

import { C } from "@/lib/theme";
import { Table } from "./types";
import { fmt, timeAgo } from "./helpers";

interface TableCardProps {
  table: Table;
  selected: boolean;
  onClick: () => void;
}

export function TableCard({ table, selected, onClick }: TableCardProps) {
  const occupied = table.status === "OPEN";
  const borderColor = selected ? C.accent : occupied ? C.amber : C.border;
  const bgColor = selected ? C.accentBg : occupied ? "#FFFDF5" : C.surface;
  return (
    <div className="mesa-card" onClick={onClick} style={{
      border: `2px solid ${borderColor}`, borderRadius: C.rMd, background: bgColor,
      padding: "12px 14px", position: "relative",
      boxShadow: selected ? `0 0 0 3px ${C.accentBd}` : C.sh,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontWeight: 700, fontSize: 14, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {table.name}
        </span>
        <span style={{
          width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
          background: occupied ? C.amber : C.green,
          boxShadow: occupied ? `0 0 0 3px ${C.amberBd}` : `0 0 0 3px ${C.greenBd}`,
        }} />
      </div>
      {occupied && table.active_order ? (
        <>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>
            ${fmt(table.active_order.subtotal)}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 2 }}>
            <span style={{ fontSize: 11, color: C.amber, fontWeight: 600 }}>
              {table.active_order.items_count} item{table.active_order.items_count !== 1 ? "s" : ""}
            </span>
            <span style={{ fontSize: 11, color: C.mute }}>
              {timeAgo(table.active_order.opened_at)}
            </span>
          </div>
        </>
      ) : (
        <div style={{ fontSize: 11, color: C.mute }}>
          {table.capacity} pers. · Libre
        </div>
      )}
    </div>
  );
}
