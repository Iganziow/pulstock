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

const ZONE_COLORS = [
  { bg: "#EEF2FF", bd: "#C7D2FE", label: "#4F46E5" }, // indigo
  { bg: "#ECFDF5", bd: "#A7F3D0", label: "#16A34A" }, // green
  { bg: "#FFFBEB", bd: "#FDE68A", label: "#D97706" }, // amber
  { bg: "#FFF1F2", bd: "#FECDD3", label: "#E11D48" }, // rose
  { bg: "#F0F9FF", bd: "#BAE6FD", label: "#0284C7" }, // sky
  { bg: "#FAF5FF", bd: "#DDD6FE", label: "#7C3AED" }, // violet
];

export function FloorPlanEditor({ tables, onRefresh }: FloorPlanEditorProps) {
  const regularTables = tables.filter(t => !t.is_counter);
  const zones = [...new Set(regularTables.map(t => t.zone).filter(Boolean))].sort();

  const [activeZone, setActiveZone] = useState<string>(zones[0] || "");
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
  const [addingZone, setAddingZone] = useState(false);
  const [newZoneName, setNewZoneName] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  // Tables in active zone (or all if no zone selected)
  const zoneTables = activeZone
    ? regularTables.filter(t => t.zone === activeZone)
    : regularTables.filter(t => !t.zone);

  const zoneColor = ZONE_COLORS[zones.indexOf(activeZone) % ZONE_COLORS.length] || ZONE_COLORS[0];

  // Sync positions when tables change + auto-distribute if all at origin
  useEffect(() => {
    const map: Record<number, { x: number; y: number; rotation: number; shape: TShape }> = {};
    let allAtOrigin = true;
    regularTables.forEach(t => {
      map[t.id] = positions[t.id] || { x: t.position_x, y: t.position_y, rotation: t.rotation, shape: t.shape };
      if (t.position_x > 1 || t.position_y > 1) allAtOrigin = false;
    });

    // Auto-distribute if all tables are at (0,0) — first time setup
    if (allAtOrigin && regularTables.length > 0) {
      const cols = Math.ceil(Math.sqrt(regularTables.length));
      const spacing = 70 / Math.max(cols, 1);
      regularTables.forEach((t, i) => {
        const col = i % cols;
        const row = Math.floor(i / cols);
        map[t.id] = { x: 15 + col * spacing, y: 20 + row * spacing, rotation: 0, shape: t.shape };
      });
    }

    setPositions(map);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tables]);

  // Sync active zone when zones change
  useEffect(() => {
    if (activeZone && !zones.includes(activeZone) && zones.length > 0) {
      setActiveZone(zones[0]);
    }
  }, [zones, activeZone]);

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

  const handleCanvasClick = (e: React.MouseEvent) => {
    if (dragging !== null) return;
    if ((e.target as HTMLElement).closest("[data-table-id]")) return;
    const { x, y } = getRelativePos(e.clientX, e.clientY);
    setClickPos({ x, y });
    setCreating(true);
    const zoneCount = zoneTables.length;
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
          zone: activeZone,
        }),
      });
      setClickPos(null);
      onRefresh();
    } catch { /* silent */ }
  };

  const createZone = () => {
    if (!newZoneName.trim()) return;
    setActiveZone(newZoneName.trim());
    setAddingZone(false);
    setNewZoneName("");
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
    const cols = Math.ceil(Math.sqrt(zoneTables.length));
    if (cols === 0) return;
    const spacing = 80 / Math.max(cols, 1);
    const newPos = { ...positions };
    zoneTables.forEach((t, i) => {
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
      {/* Zone tabs */}
      <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
        {zones.map((z, i) => {
          const zc = ZONE_COLORS[i % ZONE_COLORS.length];
          const count = regularTables.filter(t => t.zone === z).length;
          return (
            <button key={z} type="button" onClick={() => { setActiveZone(z); setSelectedId(null); setCreating(false); }} style={{
              padding: "8px 16px", borderRadius: 10, fontSize: 13, fontWeight: 600, cursor: "pointer",
              border: activeZone === z ? `2px solid ${zc.bd}` : `1px solid ${C.border}`,
              background: activeZone === z ? zc.bg : C.surface,
              color: activeZone === z ? zc.label : C.mid,
              fontFamily: C.font, display: "flex", alignItems: "center", gap: 6,
            }}>
              {z}
              <span style={{
                fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 6,
                background: activeZone === z ? zc.label + "18" : "#F4F4F5",
                color: activeZone === z ? zc.label : C.mute,
              }}>{count}</span>
            </button>
          );
        })}

        {/* No-zone tab if there are tables without zone */}
        {regularTables.some(t => !t.zone) && (
          <button type="button" onClick={() => { setActiveZone(""); setSelectedId(null); setCreating(false); }} style={{
            padding: "8px 16px", borderRadius: 10, fontSize: 13, fontWeight: 600, cursor: "pointer",
            border: activeZone === "" ? `2px solid ${C.border}` : `1px solid ${C.border}`,
            background: activeZone === "" ? C.bg : C.surface,
            color: activeZone === "" ? C.text : C.mute,
            fontFamily: C.font,
          }}>
            Sin zona ({regularTables.filter(t => !t.zone).length})
          </button>
        )}

        {/* Add zone */}
        {addingZone ? (
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <input
              value={newZoneName}
              onChange={e => setNewZoneName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && createZone()}
              placeholder="Nombre de la zona"
              autoFocus
              style={{
                padding: "7px 12px", borderRadius: 8, fontSize: 13,
                border: `1.5px solid ${C.accent}`, fontFamily: C.font, outline: "none", width: 160,
              }}
            />
            <Btn variant="primary" size="sm" onClick={createZone} disabled={!newZoneName.trim()}>OK</Btn>
            <Btn variant="ghost" size="sm" onClick={() => { setAddingZone(false); setNewZoneName(""); }}>✕</Btn>
          </div>
        ) : (
          <button type="button" onClick={() => setAddingZone(true)} style={{
            padding: "8px 14px", borderRadius: 10, fontSize: 12, fontWeight: 600, cursor: "pointer",
            border: `1px dashed ${C.border}`, background: "transparent", color: C.accent,
            fontFamily: C.font,
          }}>
            + Zona
          </button>
        )}
      </div>

      {/* Toolbar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap",
      }}>
        <div style={{ fontSize: 13, color: C.mute }}>
          {activeZone ? (
            <><b style={{ color: zoneColor.label }}>{activeZone}</b> — {zoneTables.length} mesa{zoneTables.length !== 1 ? "s" : ""}. Click para crear aquí.</>
          ) : (
            <>Mesas sin zona asignada. Click para crear.</>
          )}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn variant="ghost" size="sm" onClick={autoDistribute}>Auto-distribuir</Btn>
          <Btn variant="primary" size="sm" onClick={saveLayout} disabled={saving || !dirty}>
            {saving ? <><Spinner size={12} /> Guardando...</> : saved ? "✓ Guardado" : "Guardar"}
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
            minHeight: 460,
            background: activeZone ? zoneColor.bg : C.surface,
            border: `2px dashed ${activeZone ? zoneColor.bd : C.border}`,
            borderRadius: 14,
            overflow: "hidden",
            touchAction: "none",
            cursor: "crosshair",
            transition: "background .2s, border-color .2s",
          }}
        >
          {/* Zone label watermark */}
          {activeZone && (
            <div style={{
              position: "absolute", top: 12, left: 16,
              fontSize: 14, fontWeight: 800, color: zoneColor.label,
              opacity: 0.25, textTransform: "uppercase", letterSpacing: ".1em",
              pointerEvents: "none",
            }}>
              {activeZone}
            </div>
          )}

          {/* Grid */}
          <div style={{
            position: "absolute", inset: 0,
            backgroundImage: `
              linear-gradient(${activeZone ? zoneColor.label + "08" : "rgba(0,0,0,.03)"} 1px, transparent 1px),
              linear-gradient(90deg, ${activeZone ? zoneColor.label + "08" : "rgba(0,0,0,.03)"} 1px, transparent 1px)
            `,
            backgroundSize: "5% 5%",
            pointerEvents: "none",
          }} />

          {/* Tables for this zone */}
          {zoneTables.map(table => {
            const pos = positions[table.id] || { x: table.position_x, y: table.position_y, rotation: table.rotation, shape: table.shape };
            const modifiedTable = { ...table, position_x: pos.x, position_y: pos.y, rotation: pos.rotation, shape: pos.shape };
            return (
              <div
                key={table.id}
                data-table-id={table.id}
                onPointerDown={e => handlePointerDown(table.id, e)}
                style={{
                  position: "absolute",
                  left: `${pos.x}%`, top: `${pos.y}%`,
                  transform: "translate(-50%, -50%)",
                  cursor: dragging === table.id ? "grabbing" : "grab",
                  zIndex: dragging === table.id || selectedId === table.id ? 10 : 1,
                  transition: dragging === table.id ? "none" : "left .15s, top .15s",
                }}
              >
                <TableShape table={modifiedTable} selected={selectedId === table.id} onClick={() => setSelectedId(table.id)} />
              </div>
            );
          })}

          {/* Click ghost */}
          {clickPos && creating && (
            <div style={{
              position: "absolute",
              left: `${clickPos.x}%`, top: `${clickPos.y}%`,
              transform: "translate(-50%, -50%)",
              width: newShape === "rect" ? 100 : 72,
              height: newShape === "rect" ? 56 : 72,
              borderRadius: newShape === "round" ? "50%" : 10,
              border: `2px dashed ${zoneColor.label}`,
              background: `${zoneColor.label}10`,
              pointerEvents: "none",
            }} />
          )}

          {/* Empty */}
          {zoneTables.length === 0 && !creating && (
            <div style={{
              position: "absolute", inset: 0,
              display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center",
              color: C.mute, fontSize: 14, gap: 8,
            }}>
              <div style={{ fontSize: 32 }}>🪑</div>
              <div style={{ fontWeight: 600 }}>
                {activeZone ? `"${activeZone}" está vacía` : "Sin mesas sin zona"}
              </div>
              <div style={{ fontSize: 12 }}>Click en cualquier parte para crear una mesa</div>
            </div>
          )}
        </div>

        {/* Right panel */}
        <div style={{ width: 220, flexShrink: 0, display: "flex", flexDirection: "column", gap: 12, alignSelf: "flex-start" }}>
          {/* Create form */}
          {creating && clickPos && (
            <div style={{
              background: C.surface, border: `2px solid ${zoneColor.label}`,
              borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 10,
            }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: zoneColor.label }}>
                Nueva mesa {activeZone ? `en ${activeZone}` : ""}
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 4 }}>Nombre</div>
                <input value={newName} onChange={e => setNewName(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && createTableAtPosition()}
                  autoFocus style={{
                    width: "100%", padding: "8px 10px", borderRadius: 8, fontSize: 13,
                    border: `1.5px solid ${C.border}`, fontFamily: C.font, outline: "none",
                  }} />
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 4 }}>Capacidad</div>
                <input type="number" min={1} max={20} value={newCapacity} onChange={e => setNewCapacity(e.target.value)}
                  style={{
                    width: "100%", padding: "8px 10px", borderRadius: 8, fontSize: 13,
                    border: `1.5px solid ${C.border}`, fontFamily: C.font, outline: "none",
                  }} />
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 4 }}>Forma</div>
                <div style={{ display: "flex", gap: 4 }}>
                  {(["round", "square", "rect"] as const).map(sh => (
                    <button key={sh} type="button" onClick={() => setNewShape(sh)} style={{
                      flex: 1, padding: "8px 0", borderRadius: 8, fontSize: 18, cursor: "pointer",
                      border: `2px solid ${newShape === sh ? zoneColor.label : C.border}`,
                      background: newShape === sh ? zoneColor.bg : C.surface,
                      fontFamily: C.font,
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

          {/* Properties */}
          {selected && !creating && (
            <div style={{
              background: C.surface, border: `1px solid ${C.border}`,
              borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 12,
            }}>
              <div style={{ fontSize: 14, fontWeight: 800 }}>{selected.name}</div>
              <div style={{ fontSize: 11, color: C.mute }}>
                {selected.capacity} personas · {selected.zone || "Sin zona"}
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 6 }}>Forma</div>
                <div style={{ display: "flex", gap: 4 }}>
                  {(["round", "square", "rect"] as const).map(sh => (
                    <button key={sh} type="button" onClick={() => setShape(selected.id, sh)} style={{
                      flex: 1, padding: "7px 0", borderRadius: 8, fontSize: 16,
                      border: `2px solid ${(positions[selected.id]?.shape ?? selected.shape) === sh ? C.accent : C.border}`,
                      background: (positions[selected.id]?.shape ?? selected.shape) === sh ? C.accentBg : C.surface,
                      cursor: "pointer", fontFamily: C.font,
                    }}>
                      {sh === "round" ? "⬤" : sh === "square" ? "⬛" : "▬"}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 6 }}>
                  Rotación: {positions[selected.id]?.rotation ?? selected.rotation}°
                </div>
                <input type="range" min={0} max={360} step={15}
                  value={positions[selected.id]?.rotation ?? selected.rotation}
                  onChange={e => setRotation(selected.id, Number(e.target.value))}
                  style={{ width: "100%" }} />
              </div>
            </div>
          )}

          {/* Tips */}
          {!selected && !creating && (
            <div style={{
              background: C.bg, border: `1px solid ${C.border}`, borderRadius: 12,
              padding: 16, fontSize: 12, color: C.mute, lineHeight: 1.6,
            }}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>Tips:</div>
              <div>• Click vacío = crear mesa</div>
              <div>• Arrastra = mover</div>
              <div>• Click mesa = editar forma</div>
              <div>• "+ Zona" = nueva sala</div>
              <div>• "Guardar" = persistir posiciones</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
