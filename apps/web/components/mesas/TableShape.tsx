"use client";
import { C } from "@/lib/theme";
import type { Table } from "./types";
import { timeAgo } from "./helpers";

interface TableShapeProps {
  table: Table;
  selected?: boolean;
  onClick?: () => void;
}

const STATUS_STYLES = {
  FREE:     { bg: "#ECFDF5", border: "#16A34A", dot: "#16A34A" },
  OPEN:     { bg: "#FFFBEB", border: "#D97706", dot: "#D97706" },
  SELECTED: { bg: "#EEF2FF", border: "#4F46E5", dot: "#4F46E5" },
} as const;

export function TableShape({ table, selected, onClick }: TableShapeProps) {
  const s = selected ? STATUS_STYLES.SELECTED : STATUS_STYLES[table.status] || STATUS_STYLES.FREE;
  const isOccupied = table.status === "OPEN" && table.active_order;

  // Fixed pixel sizes based on shape
  const w = table.shape === "rect" ? 100 : 72;
  const h = table.shape === "rect" ? 56 : 72;

  return (
    <div
      onClick={onClick}
      style={{
        width: w,
        height: h,
        borderRadius: table.shape === "round" ? "50%" : 10,
        background: s.bg,
        border: `2.5px solid ${s.border}`,
        boxShadow: selected
          ? `0 0 0 3px ${s.border}40, 0 6px 16px rgba(0,0,0,.12)`
          : "0 2px 8px rgba(0,0,0,.08)",
        cursor: onClick ? "pointer" : "default",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        transition: "box-shadow .15s, border-color .15s, transform .15s",
        transform: `${table.rotation ? `rotate(${table.rotation}deg)` : ""} ${selected ? "scale(1.08)" : ""}`.trim() || undefined,
        userSelect: "none",
        overflow: "visible",
      }}
    >
      {/* Table name */}
      <div style={{
        fontSize: 12,
        fontWeight: 800,
        color: s.border,
        lineHeight: 1.1,
        textAlign: "center",
        transform: table.rotation ? `rotate(-${table.rotation}deg)` : undefined,
      }}>
        {table.name}
      </div>

      {/* Capacity */}
      <div style={{
        fontSize: 9,
        color: C.mute,
        marginTop: 2,
        fontWeight: 600,
        transform: table.rotation ? `rotate(-${table.rotation}deg)` : undefined,
      }}>
        {table.capacity} pers.
      </div>

      {/* Occupied badge */}
      {isOccupied && table.active_order && (
        <div style={{
          position: "absolute",
          top: -8,
          right: -8,
          background: s.border,
          color: "#fff",
          fontSize: 9,
          fontWeight: 700,
          padding: "2px 6px",
          borderRadius: 8,
          lineHeight: 1.2,
          whiteSpace: "nowrap",
          boxShadow: "0 2px 6px rgba(0,0,0,.2)",
        }}>
          {timeAgo(table.active_order.opened_at)} · {table.active_order.items_count}
        </div>
      )}
    </div>
  );
}
