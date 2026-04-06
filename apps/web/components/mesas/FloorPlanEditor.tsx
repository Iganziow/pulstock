"use client";
import { useState, useRef, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Btn, Spinner } from "@/components/ui";
import type { Table, TableShape as TShape } from "./types";
import { TableShape } from "./TableShape";

interface FloorPlanEditorProps {
  tables: Table[];
  onRefresh: () => void;
}

export function FloorPlanEditor({ tables, onRefresh }: FloorPlanEditorProps) {
  const [positions, setPositions] = useState<Record<number, { x: number; y: number; rotation: number; shape: TShape }>>(() => {
    const map: Record<number, { x: number; y: number; rotation: number; shape: TShape }> = {};
    tables.filter(t => !t.is_counter).forEach(t => {
      map[t.id] = { x: t.position_x, y: t.position_y, rotation: t.rotation, shape: t.shape };
    });
    return map;
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [dragging, setDragging] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const regularTables = tables.filter(t => !t.is_counter);
  const dirty = regularTables.some(t => {
    const p = positions[t.id];
    return p && (p.x !== t.position_x || p.y !== t.position_y || p.rotation !== t.rotation || p.shape !== t.shape);
  });

  const getRelativePos = useCallback((clientX: number, clientY: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    const x = Math.max(3, Math.min(97, ((clientX - rect.left) / rect.width) * 100));
    const y = Math.max(3, Math.min(97, ((clientY - rect.top) / rect.height) * 100));
    // Snap to 2.5% grid
    return { x: Math.round(x / 2.5) * 2.5, y: Math.round(y / 2.5) * 2.5 };
  }, []);

  const handlePointerDown = (tableId: number, e: React.PointerEvent) => {
    e.preventDefault();
    setDragging(tableId);
    setSelectedId(tableId);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (dragging === null) return;
    const { x, y } = getRelativePos(e.clientX, e.clientY);
    setPositions(prev => ({ ...prev, [dragging]: { ...prev[dragging], x, y } }));
  };

  const handlePointerUp = () => {
    setDragging(null);
  };

  const saveLayout = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const payload = regularTables.map(t => ({
        id: t.id,
        position_x: positions[t.id]?.x ?? t.position_x,
        position_y: positions[t.id]?.y ?? t.position_y,
        rotation: positions[t.id]?.rotation ?? t.rotation,
        shape: positions[t.id]?.shape ?? t.shape,
      }));
      await apiFetch("/tables/tables/save-layout/", {
        method: "POST",
        body: JSON.stringify({ positions: payload }),
      });
      setSaved(true);
      onRefresh();
      setTimeout(() => setSaved(false), 2000);
    } catch { /* silent */ }
    finally { setSaving(false); }
  };

  const setShape = (id: number, shape: TShape) => {
    setPositions(prev => ({ ...prev, [id]: { ...prev[id], shape } }));
  };

  const setRotation = (id: number, deg: number) => {
    setPositions(prev => ({ ...prev, [id]: { ...prev[id], rotation: deg } }));
  };

  const autoDistribute = () => {
    const cols = Math.ceil(Math.sqrt(regularTables.length));
    const spacing = 85 / Math.max(cols, 1);
    const newPos: typeof positions = {};
    regularTables.forEach((t, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      newPos[t.id] = {
        x: 10 + col * spacing,
        y: 15 + row * spacing,
        rotation: positions[t.id]?.rotation ?? 0,
        shape: positions[t.id]?.shape ?? t.shape,
      };
    });
    setPositions(newPos);
  };

  const selected = selectedId ? regularTables.find(t => t.id === selectedId) : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Toolbar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        gap: 8, flexWrap: "wrap",
      }}>
        <div style={{ fontSize: 13, color: C.mute }}>
          Arrastra las mesas para posicionarlas. Click para seleccionar.
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn variant="ghost" size="sm" onClick={autoDistribute}>Auto-distribuir</Btn>
          <Btn variant="primary" size="sm" onClick={saveLayout} disabled={saving || !dirty}>
            {saving ? <><Spinner size={12} /> Guardando...</> : saved ? "Guardado" : "Guardar distribución"}
          </Btn>
        </div>
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        {/* Canvas */}
        <div
          ref={containerRef}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          style={{
            position: "relative",
            flex: 1,
            paddingBottom: "62.5%",
            background: C.surface,
            border: `2px dashed ${C.border}`,
            borderRadius: 12,
            overflow: "hidden",
            touchAction: "none",
          }}
        >
          {/* Grid */}
          <div style={{
            position: "absolute", inset: 0,
            backgroundImage: `
              linear-gradient(rgba(79,70,229,.04) 1px, transparent 1px),
              linear-gradient(90deg, rgba(79,70,229,.04) 1px, transparent 1px)
            `,
            backgroundSize: "5% 5%",
            pointerEvents: "none",
          }} />

          {/* Tables */}
          {regularTables.map(table => {
            const pos = positions[table.id] || { x: table.position_x, y: table.position_y, rotation: table.rotation, shape: table.shape };
            const modifiedTable = { ...table, position_x: pos.x, position_y: pos.y, rotation: pos.rotation, shape: pos.shape };
            return (
              <div
                key={table.id}
                onPointerDown={e => handlePointerDown(table.id, e)}
                style={{
                  position: "absolute",
                  left: `${pos.x}%`,
                  top: `${pos.y}%`,
                  transform: "translate(-50%, -50%)",
                  cursor: dragging === table.id ? "grabbing" : "grab",
                  zIndex: dragging === table.id || selectedId === table.id ? 10 : 1,
                  transition: dragging === table.id ? "none" : "left .1s, top .1s",
                }}
              >
                <TableShape
                  table={modifiedTable}
                  selected={selectedId === table.id}
                  onClick={() => setSelectedId(table.id)}
                />
              </div>
            );
          })}

          {regularTables.length === 0 && (
            <div style={{
              position: "absolute", inset: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              color: C.mute, fontSize: 14,
            }}>
              Crea mesas en la pestaña "Lista" primero
            </div>
          )}
        </div>

        {/* Properties panel */}
        {selected && (
          <div style={{
            width: 200, background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 12,
            flexShrink: 0, alignSelf: "flex-start",
          }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>{selected.name}</div>
            <div style={{ fontSize: 11, color: C.mute }}>{selected.capacity} personas · {selected.zone || "Sin zona"}</div>

            {/* Shape selector */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 6 }}>Forma</div>
              <div style={{ display: "flex", gap: 4 }}>
                {(["round", "square", "rect"] as const).map(sh => (
                  <button
                    key={sh}
                    type="button"
                    onClick={() => setShape(selected.id, sh)}
                    style={{
                      flex: 1, padding: "6px 0", borderRadius: 6, fontSize: 11, fontWeight: 600,
                      border: `1.5px solid ${(positions[selected.id]?.shape ?? selected.shape) === sh ? C.accent : C.border}`,
                      background: (positions[selected.id]?.shape ?? selected.shape) === sh ? C.accentBg : C.surface,
                      color: (positions[selected.id]?.shape ?? selected.shape) === sh ? C.accent : C.mid,
                      cursor: "pointer", fontFamily: C.font,
                    }}
                  >
                    {sh === "round" ? "●" : sh === "square" ? "■" : "▬"}
                  </button>
                ))}
              </div>
            </div>

            {/* Rotation */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 6 }}>
                Rotación: {positions[selected.id]?.rotation ?? selected.rotation}°
              </div>
              <input
                type="range"
                min={0} max={360} step={15}
                value={positions[selected.id]?.rotation ?? selected.rotation}
                onChange={e => setRotation(selected.id, Number(e.target.value))}
                style={{ width: "100%" }}
              />
            </div>

            {/* Position readout */}
            <div style={{ fontSize: 10, color: C.mute, fontFamily: C.mono }}>
              x: {(positions[selected.id]?.x ?? selected.position_x).toFixed(1)}%
              {" · "}
              y: {(positions[selected.id]?.y ?? selected.position_y).toFixed(1)}%
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
