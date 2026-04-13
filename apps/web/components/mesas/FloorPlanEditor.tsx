"use client";
import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Btn, Spinner } from "@/components/ui";
import type { Table, TableShape as TShape } from "./types";

const COLS = 8;
const ROWS = 6;

interface FloorPlanEditorProps {
  tables: Table[];
  onRefresh: () => void;
}

const ZONE_COLORS = [
  { bg: "#EEF2FF", bd: "#C7D2FE", text: "#4F46E5", cell: "#E0E7FF" },
  { bg: "#ECFDF5", bd: "#A7F3D0", text: "#16A34A", cell: "#D1FAE5" },
  { bg: "#FFFBEB", bd: "#FDE68A", text: "#D97706", cell: "#FEF3C7" },
  { bg: "#FFF1F2", bd: "#FECDD3", text: "#E11D48", cell: "#FFE4E6" },
  { bg: "#F0F9FF", bd: "#BAE6FD", text: "#0284C7", cell: "#E0F2FE" },
  { bg: "#FAF5FF", bd: "#DDD6FE", text: "#7C3AED", cell: "#EDE9FE" },
];

export function FloorPlanEditor({ tables, onRefresh }: FloorPlanEditorProps) {
  const regularTables = tables.filter(t => !t.is_counter);
  const tableZones = [...new Set(regularTables.map(t => t.zone).filter(Boolean))].sort();
  const [extraZones, setExtraZones] = useState<string[]>([]);
  const zones = [...new Set([...tableZones, ...extraZones])].sort();

  const [activeZone, setActiveZone] = useState<string>(zones[0] || "");
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState<{ col: number; row: number } | null>(null);
  const [newName, setNewName] = useState("");
  const [newCapacity, setNewCapacity] = useState("4");
  const [newShape, setNewShape] = useState<"square" | "round">("square");
  const [addingZone, setAddingZone] = useState(false);
  const [newZoneName, setNewZoneName] = useState("");
  const [dragging, setDragging] = useState<number | null>(null);

  const toggleShape = async (table: Table) => {
    const next = table.shape === "round" ? "square" : "round";
    try {
      await apiFetch(`/tables/tables/${table.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ shape: next }),
      });
      onRefresh();
    } catch (e) { console.error("FloorPlanEditor: error cambiando forma de mesa:", e); }
  };

  const zoneTables = activeZone
    ? regularTables.filter(t => t.zone === activeZone)
    : regularTables.filter(t => !t.zone);

  const zoneIdx = zones.indexOf(activeZone);
  const zc = ZONE_COLORS[zoneIdx >= 0 ? zoneIdx % ZONE_COLORS.length : 0];

  // Build grid map: {col-row: table}
  const gridMap = new Map<string, Table>();
  zoneTables.forEach(t => {
    const col = Math.round(t.position_x);
    const row = Math.round(t.position_y);
    if (col >= 0 && col < COLS && row >= 0 && row < ROWS) {
      gridMap.set(`${col}-${row}`, t);
    }
  });

  useEffect(() => {
    if (activeZone && !zones.includes(activeZone) && zones.length > 0) {
      setActiveZone(zones[0]);
    }
  }, [zones, activeZone]);

  const handleCellClick = (col: number, row: number) => {
    if (gridMap.has(`${col}-${row}`)) return; // occupied
    setCreating({ col, row });
    setNewName(`Mesa ${regularTables.length + 1}`);
    setNewCapacity("4");
  };

  const createTable = async () => {
    if (!creating || !newName.trim()) return;
    setSaving(true);
    try {
      await apiFetch("/tables/tables/", {
        method: "POST",
        body: JSON.stringify({
          name: newName.trim(),
          capacity: Number(newCapacity) || 4,
          shape: newShape,
          position_x: creating.col,
          position_y: creating.row,
          zone: activeZone,
        }),
      });
      setCreating(null);
      onRefresh();
    } catch (e) { console.error("FloorPlanEditor: error creando mesa:", e); }
    finally { setSaving(false); }
  };

  const deleteTable = async (tableId: number) => {
    if (!confirm("¿Eliminar esta mesa?")) return;
    try {
      await apiFetch(`/tables/tables/${tableId}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: false }),
      });
      onRefresh();
    } catch (e) { console.error("FloorPlanEditor: error eliminando mesa:", e); }
  };

  const moveTable = async (tableId: number, col: number, row: number) => {
    try {
      await apiFetch(`/tables/tables/${tableId}/`, {
        method: "PATCH",
        body: JSON.stringify({ position_x: col, position_y: row }),
      });
      onRefresh();
    } catch (e) { console.error("FloorPlanEditor: error moviendo mesa:", e); }
  };

  const handleDrop = (col: number, row: number) => {
    if (dragging === null) return;
    if (gridMap.has(`${col}-${row}`)) return; // occupied
    moveTable(dragging, col, row);
    setDragging(null);
  };

  const createZone = () => {
    const name = newZoneName.trim();
    if (!name || zones.includes(name)) return;
    setExtraZones(prev => [...prev, name]);
    setActiveZone(name);
    setAddingZone(false);
    setNewZoneName("");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Zone tabs */}
      <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
        {zones.map((z, i) => {
          const zColor = ZONE_COLORS[i % ZONE_COLORS.length];
          const count = regularTables.filter(t => t.zone === z).length;
          return (
            <button key={z} type="button" onClick={() => { setActiveZone(z); setCreating(null); }} style={{
              padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer",
              border: activeZone === z ? `2px solid ${zColor.text}` : `1px solid ${C.border}`,
              background: activeZone === z ? zColor.bg : C.surface,
              color: activeZone === z ? zColor.text : C.mid,
              fontFamily: C.font, display: "flex", alignItems: "center", gap: 6,
            }}>
              {z}
              <span style={{
                fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 6,
                background: activeZone === z ? zColor.text + "18" : "#F4F4F5",
                color: activeZone === z ? zColor.text : C.mute,
              }}>{count}</span>
            </button>
          );
        })}

        {regularTables.some(t => !t.zone) && (
          <button type="button" onClick={() => { setActiveZone(""); setCreating(null); }} style={{
            padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer",
            border: activeZone === "" ? `2px solid ${C.border}` : `1px solid ${C.border}`,
            background: activeZone === "" ? C.bg : C.surface,
            color: activeZone === "" ? C.text : C.mute,
            fontFamily: C.font,
          }}>
            Sin zona ({regularTables.filter(t => !t.zone).length})
          </button>
        )}

        {addingZone ? (
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <input value={newZoneName} onChange={e => setNewZoneName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && createZone()}
              placeholder="Nombre de la sala" autoFocus
              style={{ padding: "7px 12px", borderRadius: 8, fontSize: 13, border: `1.5px solid ${C.accent}`, fontFamily: C.font, outline: "none", width: 160 }} />
            <Btn variant="primary" size="sm" onClick={createZone} disabled={!newZoneName.trim()}>OK</Btn>
            <Btn variant="ghost" size="sm" onClick={() => { setAddingZone(false); setNewZoneName(""); }}>✕</Btn>
          </div>
        ) : (
          <button type="button" onClick={() => setAddingZone(true)} style={{
            padding: "8px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer",
            border: `1px dashed ${C.border}`, background: "transparent", color: C.accent, fontFamily: C.font,
          }}>+ Nueva Sala</button>
        )}
      </div>

      <div style={{ display: "flex", gap: 16, flexDirection: typeof window !== "undefined" && window.innerWidth < 768 ? "column" : "row" }}>
        {/* Grid */}
        <div style={{
          display: "grid",
          gridTemplateColumns: `repeat(${COLS}, 1fr)`,
          gridTemplateRows: `repeat(${ROWS}, 1fr)`,
          gap: 3,
          flex: 1,
          aspectRatio: `${COLS}/${ROWS}`,
          background: C.border,
          border: `2px solid ${zc.bd}`,
          borderRadius: 12,
          padding: 3,
          overflow: "hidden",
        }}>
          {Array.from({ length: ROWS * COLS }).map((_, idx) => {
            const col = idx % COLS;
            const row = Math.floor(idx / COLS);
            const key = `${col}-${row}`;
            const table = gridMap.get(key);
            const isCreatingHere = creating?.col === col && creating?.row === row;

            return (
              <div
                key={key}
                onClick={() => !table && handleCellClick(col, row)}
                onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }}
                onDrop={() => handleDrop(col, row)}
                style={{
                  background: table ? zc.cell : isCreatingHere ? `${zc.text}15` : C.surface,
                  borderRadius: 6,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: table ? "grab" : "pointer",
                  position: "relative",
                  transition: "background .15s",
                  minHeight: 70,
                  border: isCreatingHere ? `2px dashed ${zc.text}` : "1px solid transparent",
                }}
              >
                {table ? (
                  <div
                    draggable
                    onDragStart={() => setDragging(table.id)}
                    onDragEnd={() => setDragging(null)}
                    style={{
                      width: "100%", height: "100%",
                      display: "flex", flexDirection: "column",
                      alignItems: "center", justifyContent: "center",
                      borderRadius: table.shape === "round" ? "50%" : 6,
                      background: table.status === "OPEN" ? "#FFFBEB" : zc.cell,
                      border: `2.5px solid ${table.status === "OPEN" ? "#D97706" : zc.text}`,
                      position: "relative",
                      transition: "border-radius .2s",
                    }}
                  >
                    <div style={{ fontSize: 16, fontWeight: 800, color: table.status === "OPEN" ? "#D97706" : zc.text }}>
                      {table.name}
                    </div>
                    <div style={{ fontSize: 10, color: C.mute }}>{table.capacity} pers.</div>

                    {/* Shape toggle */}
                    <button type="button" onClick={(e) => { e.stopPropagation(); toggleShape(table); }}
                      aria-label="Cambiar forma"
                      title={table.shape === "round" ? "Cambiar a cuadrada" : "Cambiar a redonda"}
                      style={{
                        position: "absolute", bottom: 3, left: "50%", transform: "translateX(-50%)",
                        fontSize: 11, color: zc.text, background: "rgba(255,255,255,.8)",
                        border: "none", cursor: "pointer", padding: "1px 4px", borderRadius: 4,
                        opacity: 0.7, lineHeight: 1,
                      }}>
                      {table.shape === "round" ? "⬛" : "⬤"}
                    </button>

                    {table.status === "OPEN" && (
                      <div style={{
                        position: "absolute", top: 2, right: table.shape === "round" ? 8 : 2,
                        width: 8, height: 8, borderRadius: "50%",
                        background: "#D97706",
                      }} />
                    )}
                    {/* Delete button */}
                    <button type="button" onClick={(e) => { e.stopPropagation(); deleteTable(table.id); }}
                      aria-label="Eliminar mesa"
                      style={{
                        position: "absolute", top: table.shape === "round" ? 0 : -6, right: table.shape === "round" ? 0 : -6,
                        width: 18, height: 18, borderRadius: "50%",
                        background: C.red, color: "#fff",
                        border: "2px solid #fff", fontSize: 10, lineHeight: 1,
                        cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                        opacity: 0.7,
                      }}>✕</button>
                  </div>
                ) : !isCreatingHere ? (
                  <span style={{ fontSize: 20, color: C.border, opacity: 0.5 }}>+</span>
                ) : null}
              </div>
            );
          })}
        </div>

        {/* Right panel: create form */}
        <div style={{ width: typeof window !== "undefined" && window.innerWidth < 768 ? "100%" : 220, flexShrink: 0, display: "flex", flexDirection: "column", gap: 12, alignSelf: "flex-start" }}>
          {creating && (
            <div style={{
              background: C.surface, border: `2px solid ${zc.text}`,
              borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 10,
            }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: zc.text }}>
                Nueva mesa {activeZone ? `en ${activeZone}` : ""}
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", marginBottom: 4 }}>Nombre</div>
                <input value={newName} onChange={e => setNewName(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && createTable()}
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
                <div style={{ display: "flex", gap: 6 }}>
                  {([["square", "⬛", "Cuadrada"], ["round", "⬤", "Redonda"]] as const).map(([sh, icon, label]) => (
                    <button key={sh} type="button" onClick={() => setNewShape(sh)} style={{
                      flex: 1, padding: "8px 0", borderRadius: 8, cursor: "pointer",
                      border: `2px solid ${newShape === sh ? zc.text : C.border}`,
                      background: newShape === sh ? zc.bg : C.surface,
                      display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
                      fontFamily: C.font,
                    }}>
                      <span style={{ fontSize: 16 }}>{icon}</span>
                      <span style={{ fontSize: 9, fontWeight: 600, color: newShape === sh ? zc.text : C.mute }}>{label}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <Btn variant="ghost" size="sm" onClick={() => setCreating(null)}>Cancelar</Btn>
                <Btn variant="primary" size="sm" onClick={createTable} disabled={!newName.trim() || saving}>
                  {saving ? <Spinner size={12} /> : "Crear"}
                </Btn>
              </div>
            </div>
          )}

          {!creating && (
            <div style={{
              background: C.bg, border: `1px solid ${C.border}`, borderRadius: 12,
              padding: 16, fontSize: 12, color: C.mute, lineHeight: 1.6,
            }}>
              <div style={{ fontWeight: 700, marginBottom: 4, color: C.mid }}>Instrucciones</div>
              <div>• Click en celda vacía = crear mesa</div>
              <div>• Arrastra una mesa a otra celda</div>
              <div>• ✕ rojo = eliminar mesa</div>
              <div>• 1 mesa por celda, sin superposición</div>
              <div>• "+ Nueva Sala" para agregar zonas</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
