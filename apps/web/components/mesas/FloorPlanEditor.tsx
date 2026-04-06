"use client";
import { useState, useRef, useCallback, useEffect } from "react";
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
  const [positions, setPositions] = useState<Record<number, { x: number; y: number; rotation: number; shape: TShape }>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [dragging, setDragging] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCapacity, setNewCapacity] = useState("4");
  const [newShape, setNewShape] = useState<TShape>("square");
  const [clickPos, setClickPos] = useState<{ x: number; y: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const regularTables = tables.filter(t => !t.is_counter);

  // Sync positions when tables change
  useEffect(() => {
    const map: Record<number, { x: number; y: number; rotation: number; shape: TShape }> = {};
    regularTables.forEach(t => {
      map[t.id] = positions[t.id] || { x: t.position_x, y: t.position_y, rotation: t.rotation, shape: t.shape };
    });
    setPositions(map);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tables]);

  const dirty = regularTables.some(t => {
    const p = positions[t.id];
    return p && (p.x !== t.position_x || p.y !== t.position_y || p.rotation !== t.rotation || p.shape !== t.shape);
  });

  const getRelativePos = useCallback((clientX: number, clientY: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return { x: 50, y: 50 };
    const x = Math.max(5, Math.min(95, ((clientX - rect.left) / rect.width) * 100));
    const y = Math.max(5, Math.min(95, ((clientY - rect.top) / rect.height) * 100));
    return { x: Math.round(x / 2.5) * 2.5, y: Math.round(y / 2.5) * 2.5 };
  }, []);

  const handlePointerDown = (tableId: number, e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(tableId);
    setSelectedId(tableId);
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (dragging === null) return;
    const { x, y } = getRelativePos(e.clientX, e.clientY);
    setPositions(prev => ({ ...prev, [dragging]: { ...prev[dragging], x, y } }));
  };

  const handlePointerUp = () => setDragging(null);

  // Click empty area → create new table
  const handleCanvasClick = (e: React.MouseEvent) => {
    if (dragging !== null) return;
    // Check if click was on a table (not empty area)
    if ((e.target as HTMLElement).closest("[data-table-id]")) return;

    const { x, y } = getRelativePos(e.clientX, e.clientY);
    setClickPos({ x, y });
    setCreating(true);
    setNewName(`Mesa ${regularTables.length + 1}`);
    setNewCapacity("4");
    setNewShape("square");
    setSelectedId(null);
  };

  const createTableAtPosition = async () => {
    if (!newName.trim() || !clickPos) return;
    setCreating(false);
    try {
      await apiFetch("/tables/tables/", {
        method: "POST",
        body: JSON.stringify({
          name: newName.trim(),
          capacity: Number(newCapacity) || 4,
          shape: newShape,
          position_x: clickPos.x,
          position_y: clickPos.y,
        }),
      });
      setClickPos(null);
      onRefresh();
    } catch { /* silent */ }
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
    const spacing = 80 / Math.max(cols, 1);
    const newPos: typeof positions = {};
    regularTables.forEach((t, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      newPos[t.id] = {
        x: 12 + col * spacing,
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
          Arrastra para mover · Click en espacio vacío para crear mesa
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn variant="ghost" size="sm" onClick={autoDistribute}>Auto-distribuir</Btn>
          <Btn variant="primary" size="sm" onClick={saveLayout} disabled={saving || !dirty}>
            {saving ? <><Spinner size={12} /> Guardando...</> : saved ? "✓ Guardado" : "Guardar distribución"}
          </Btn>
        </div>
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        {/* Canvas */}
        <div
          ref={containerRef}
          onClick={handleCanvasClick}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          style={{
            position: "relative",
            flex: 1,
            minHeight: 500,
            background: C.surface,
            border: `2px dashed ${C.border}`,
            borderRadius: 14,
            overflow: "hidden",
            touchAction: "none",
            cursor: "crosshair",
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
                data-table-id={table.id}
                onPointerDown={e => handlePointerDown(table.id, e)}
                style={{
                  position: "absolute",
                  left: `${pos.x}%`,
                  top: `${pos.y}%`,
                  transform: "translate(-50%, -50%)",
                  cursor: dragging === table.id ? "grabbing" : "grab",
                  zIndex: dragging === table.id || selectedId === table.id ? 10 : 1,
                  transition: dragging === table.id ? "none" : "left .15s, top .15s",
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

          {/* Click-to-create ghost */}
          {clickPos && creating && (
            <div style={{
              position: "absolute",
              left: `${clickPos.x}%`,
              top: `${clickPos.y}%`,
              transform: "translate(-50%, -50%)",
              width: 72, height: 72,
              borderRadius: newShape === "round" ? "50%" : 10,
              border: `2px dashed ${C.accent}`,
              background: `${C.accent}10`,
              pointerEvents: "none",
            }} />
          )}

          {/* Empty state */}
          {regularTables.length === 0 && !creating && (
            <div style={{
              position: "absolute", inset: 0,
              display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center",
              color: C.mute, fontSize: 14, gap: 8,
            }}>
              <div style={{ fontSize: 32 }}>🪑</div>
              <div style={{ fontWeight: 600 }}>Click en cualquier parte para crear una mesa</div>
              <div style={{ fontSize: 12 }}>O crea mesas desde la pestaña "Lista"</div>
            </div>
          )}
        </div>

        {/* Right panel: properties or create form */}
        <div style={{
          width: 220, flexShrink: 0, display: "flex", flexDirection: "column", gap: 12,
          alignSelf: "flex-start",
        }}>
          {/* Create form */}
          {creating && clickPos && (
            <div style={{
              background: C.surface, border: `2px solid ${C.accent}`,
              borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 10,
            }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.accent }}>Nueva mesa</div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 4 }}>Nombre</div>
                <input
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && createTableAtPosition()}
                  autoFocus
                  style={{
                    width: "100%", padding: "8px 10px", borderRadius: 8, fontSize: 13,
                    border: `1.5px solid ${C.border}`, fontFamily: C.font, outline: "none",
                  }}
                />
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 4 }}>Capacidad</div>
                <input
                  type="number" min={1} max={20}
                  value={newCapacity}
                  onChange={e => setNewCapacity(e.target.value)}
                  style={{
                    width: "100%", padding: "8px 10px", borderRadius: 8, fontSize: 13,
                    border: `1.5px solid ${C.border}`, fontFamily: C.font, outline: "none",
                  }}
                />
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 4 }}>Forma</div>
                <div style={{ display: "flex", gap: 4 }}>
                  {(["round", "square", "rect"] as const).map(sh => (
                    <button key={sh} type="button" onClick={() => setNewShape(sh)} style={{
                      flex: 1, padding: "8px 0", borderRadius: 8, fontSize: 18, cursor: "pointer",
                      border: `2px solid ${newShape === sh ? C.accent : C.border}`,
                      background: newShape === sh ? C.accentBg : C.surface,
                      fontFamily: C.font, transition: "all .1s",
                    }}>
                      {sh === "round" ? "⬤" : sh === "square" ? "⬛" : "▬"}
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <Btn variant="ghost" size="sm" onClick={() => { setCreating(false); setClickPos(null); }}>Cancelar</Btn>
                <Btn variant="primary" size="sm" onClick={createTableAtPosition} disabled={!newName.trim()}>Crear</Btn>
              </div>
            </div>
          )}

          {/* Properties panel */}
          {selected && !creating && (
            <div style={{
              background: C.surface, border: `1px solid ${C.border}`,
              borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 12,
            }}>
              <div style={{ fontSize: 14, fontWeight: 800 }}>{selected.name}</div>
              <div style={{ fontSize: 11, color: C.mute }}>{selected.capacity} personas · {selected.zone || "Sin zona"}</div>

              {/* Shape selector */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 6 }}>Forma</div>
                <div style={{ display: "flex", gap: 4 }}>
                  {(["round", "square", "rect"] as const).map(sh => (
                    <button key={sh} type="button" onClick={() => setShape(selected.id, sh)} style={{
                      flex: 1, padding: "7px 0", borderRadius: 8, fontSize: 16, fontWeight: 600,
                      border: `2px solid ${(positions[selected.id]?.shape ?? selected.shape) === sh ? C.accent : C.border}`,
                      background: (positions[selected.id]?.shape ?? selected.shape) === sh ? C.accentBg : C.surface,
                      cursor: "pointer", fontFamily: C.font,
                    }}>
                      {sh === "round" ? "⬤" : sh === "square" ? "⬛" : "▬"}
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
                  type="range" min={0} max={360} step={15}
                  value={positions[selected.id]?.rotation ?? selected.rotation}
                  onChange={e => setRotation(selected.id, Number(e.target.value))}
                  style={{ width: "100%" }}
                />
              </div>

              {/* Position */}
              <div style={{ fontSize: 10, color: C.mute, fontFamily: C.mono }}>
                x: {(positions[selected.id]?.x ?? selected.position_x).toFixed(1)}%
                {" · "}
                y: {(positions[selected.id]?.y ?? selected.position_y).toFixed(1)}%
              </div>
            </div>
          )}

          {/* Hint when nothing selected */}
          {!selected && !creating && regularTables.length > 0 && (
            <div style={{
              background: C.bg, border: `1px solid ${C.border}`, borderRadius: 12,
              padding: 16, fontSize: 12, color: C.mute, lineHeight: 1.5,
            }}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>Tips:</div>
              <div>• Click una mesa para editar forma y rotación</div>
              <div>• Arrastra para mover</div>
              <div>• Click en espacio vacío para crear</div>
              <div>• "Guardar" persiste las posiciones</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
