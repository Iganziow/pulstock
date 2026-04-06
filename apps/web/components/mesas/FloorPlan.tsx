"use client";
import { C } from "@/lib/theme";
import type { Table } from "./types";
import { TableShape } from "./TableShape";

interface FloorPlanProps {
  tables: Table[];
  selectedId: number | null;
  onSelectTable: (table: Table) => void;
}

export function FloorPlan({ tables, selectedId, onSelectTable }: FloorPlanProps) {
  const rawTables = tables.filter(t => !t.is_counter);

  // Auto-distribute if all at origin (never positioned)
  const allAtOrigin = rawTables.length > 0 && rawTables.every(t => t.position_x <= 1 && t.position_y <= 1);
  const regularTables = allAtOrigin ? rawTables.map((t, i) => {
    const cols = Math.ceil(Math.sqrt(rawTables.length));
    const spacing = 70 / Math.max(cols, 1);
    return { ...t, position_x: 15 + (i % cols) * spacing, position_y: 20 + Math.floor(i / cols) * spacing };
  }) : rawTables;

  return (
    <div style={{
      position: "relative",
      width: "100%",
      minHeight: 480,
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: 14,
      overflow: "hidden",
      boxShadow: "inset 0 2px 8px rgba(0,0,0,.03)",
    }}>
      {/* Grid background */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: `
          linear-gradient(rgba(0,0,0,.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(0,0,0,.03) 1px, transparent 1px)
        `,
        backgroundSize: "5% 5%",
        pointerEvents: "none",
      }} />

      {/* Zone labels */}
      {(() => {
        const zones = [...new Set(regularTables.map(t => t.zone).filter(Boolean))];
        return zones.map(zone => {
          const zoneTables = regularTables.filter(t => t.zone === zone);
          if (zoneTables.length === 0) return null;
          const avgX = zoneTables.reduce((s, t) => s + t.position_x, 0) / zoneTables.length;
          const minY = Math.min(...zoneTables.map(t => t.position_y));
          return (
            <div key={zone} style={{
              position: "absolute",
              left: `${avgX}%`, top: `${Math.max(2, minY - 6)}%`,
              transform: "translateX(-50%)",
              fontSize: 11, fontWeight: 700, color: C.mute,
              textTransform: "uppercase", letterSpacing: ".06em",
              pointerEvents: "none", opacity: 0.5,
            }}>
              {zone}
            </div>
          );
        });
      })()}

      {/* Tables */}
      {regularTables.map(table => (
        <div key={table.id} style={{
          position: "absolute",
          left: `${table.position_x}%`, top: `${table.position_y}%`,
          transform: "translate(-50%, -50%)",
          zIndex: selectedId === table.id ? 10 : 1,
          transition: "transform .15s",
        }}>
          <TableShape
            table={table}
            selected={selectedId === table.id}
            onClick={() => onSelectTable(table)}
          />
        </div>
      ))}

      {/* Empty state */}
      {regularTables.length === 0 && (
        <div style={{
          position: "absolute", inset: 0,
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          color: C.mute, fontSize: 14, gap: 8,
        }}>
          <div style={{ fontSize: 32 }}>🪑</div>
          <div>No hay mesas configuradas. Ve a Config para crear mesas.</div>
        </div>
      )}
    </div>
  );
}
