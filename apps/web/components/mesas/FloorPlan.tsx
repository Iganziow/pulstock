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
  const regularTables = tables.filter(t => !t.is_counter);

  return (
    <div style={{
      position: "relative",
      width: "100%",
      paddingBottom: "62.5%", // 16:10 aspect ratio
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: 12,
      overflow: "hidden",
      boxShadow: "inset 0 2px 8px rgba(0,0,0,.03)",
    }}>
      {/* Grid background */}
      <div style={{
        position: "absolute",
        inset: 0,
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
              left: `${avgX}%`,
              top: `${Math.max(1, minY - 6)}%`,
              transform: "translateX(-50%)",
              fontSize: 10,
              fontWeight: 700,
              color: C.mute,
              textTransform: "uppercase",
              letterSpacing: ".06em",
              pointerEvents: "none",
              opacity: 0.6,
            }}>
              {zone}
            </div>
          );
        });
      })()}

      {/* Tables */}
      {regularTables.map(table => (
        <div
          key={table.id}
          style={{
            position: "absolute",
            left: `${table.position_x}%`,
            top: `${table.position_y}%`,
            transform: "translate(-50%, -50%)",
            zIndex: selectedId === table.id ? 10 : 1,
          }}
        >
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
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: C.mute,
          fontSize: 14,
        }}>
          No hay mesas configuradas. Ve a Config para crear mesas.
        </div>
      )}
    </div>
  );
}
