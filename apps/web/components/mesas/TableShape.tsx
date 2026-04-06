"use client";
import { C } from "@/lib/theme";
import type { Table } from "./types";
import { timeAgo, fmt } from "./helpers";

interface TableShapeProps {
  table: Table;
  selected?: boolean;
  onClick?: () => void;
  size?: number; // scale multiplier
}

const STATUS_STYLES = {
  FREE:     { bg: "#ECFDF5", border: "#16A34A", dot: "#16A34A" },
  OPEN:     { bg: "#FFFBEB", border: "#D97706", dot: "#D97706" },
  SELECTED: { bg: "#EEF2FF", border: "#4F46E5", dot: "#4F46E5" },
} as const;

export function TableShape({ table, selected, onClick, size = 1 }: TableShapeProps) {
  const s = selected ? STATUS_STYLES.SELECTED : STATUS_STYLES[table.status] || STATUS_STYLES.FREE;
  const isOccupied = table.status === "OPEN" && table.active_order;
  const w = table.width * size;
  const h = (table.shape === "rect" ? table.height * 0.65 : table.height) * size;

  return (
    <div
      onClick={onClick}
      style={{
        width: `${w}%`,
        height: `${h}%`,
        borderRadius: table.shape === "round" ? "50%" : 8,
        background: s.bg,
        border: `2px solid ${s.border}`,
        boxShadow: selected ? `0 0 0 3px ${s.border}40, 0 4px 12px rgba(0,0,0,.1)` : "0 2px 6px rgba(0,0,0,.06)",
        cursor: onClick ? "pointer" : "default",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        transition: "box-shadow .15s, border-color .15s",
        transform: table.rotation ? `rotate(${table.rotation}deg)` : undefined,
        overflow: "visible",
        userSelect: "none",
      }}
    >
      {/* Table name */}
      <div style={{
        fontSize: Math.max(9, 11 * size),
        fontWeight: 700,
        color: s.border,
        lineHeight: 1.1,
        textAlign: "center",
        transform: table.rotation ? `rotate(-${table.rotation}deg)` : undefined,
      }}>
        {table.name}
      </div>

      {/* Capacity */}
      <div style={{
        fontSize: Math.max(7, 9 * size),
        color: C.mute,
        marginTop: 1,
        transform: table.rotation ? `rotate(-${table.rotation}deg)` : undefined,
      }}>
        {table.capacity}p
      </div>

      {/* Occupied badge */}
      {isOccupied && table.active_order && (
        <div style={{
          position: "absolute",
          top: -6,
          right: -6,
          background: s.border,
          color: "#fff",
          fontSize: 8,
          fontWeight: 700,
          padding: "2px 5px",
          borderRadius: 6,
          lineHeight: 1,
          whiteSpace: "nowrap",
          boxShadow: "0 1px 4px rgba(0,0,0,.15)",
          animation: "pulse 2s ease-in-out infinite",
        }}>
          {timeAgo(table.active_order.opened_at)} · {table.active_order.items_count}
        </div>
      )}

      {/* Status dot */}
      <div style={{
        position: "absolute",
        bottom: -3,
        left: "50%",
        transform: "translateX(-50%)",
        width: 6,
        height: 6,
        borderRadius: "50%",
        background: s.dot,
        boxShadow: `0 0 4px ${s.dot}60`,
      }} />
    </div>
  );
}
