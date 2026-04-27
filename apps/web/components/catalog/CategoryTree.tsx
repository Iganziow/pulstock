"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { iS } from "@/components/ui";
import type { Category } from "./types";
import { humanizeError } from "@/lib/errors";

export { type Category } from "./types";

interface StationLite { id: number; name: string; }

export function CategoryTree({
  categories, onRefresh,
}: {
  categories: Category[];
  onRefresh: () => Promise<void>;
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [addingTo, setAddingTo] = useState<number | null | "root">(null);  // null=none, "root"=top level, number=parent id
  const [newName, setNewName] = useState("");
  const [newCode, setNewCode] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Estaciones disponibles — solo se carga si el tenant tiene alguna.
  // Si no hay, no mostramos el selector (sería ruido en la UI).
  const [stations, setStations] = useState<StationLite[]>([]);
  useEffect(() => {
    apiFetch("/printing/stations/")
      .then((d: any[]) => setStations((d || []).map(s => ({ id: s.id, name: s.name }))))
      .catch(() => { /* sin estaciones es OK; selector queda oculto */ });
  }, []);

  const handleSetStation = async (catId: number, stationId: number | null) => {
    setBusy(true); setError(null);
    try {
      await apiFetch(`/catalog/categories/${catId}/`, {
        method: "PATCH",
        body: JSON.stringify({ default_print_station_id: stationId }),
      });
      await onRefresh();
    } catch (e: any) {
      setError(humanizeError(e, "Error al asignar estación"));
    } finally { setBusy(false); }
  };

  const roots = categories.filter(c => !c.parent_id).sort((a, b) => a.name.localeCompare(b.name));
  const childrenOf = (pid: number) => categories.filter(c => c.parent_id === pid).sort((a, b) => a.name.localeCompare(b.name));

  const toggle = (id: number) => {
    setExpanded(prev => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };

  const handleCreate = async (parentId: number | null) => {
    if (!newName.trim()) return;
    setBusy(true); setError(null);
    try {
      const body: any = { name: newName.trim() };
      if (newCode.trim()) body.code = newCode.trim();
      if (parentId) body.parent_id = parentId;
      await apiFetch("/catalog/categories/", { method: "POST", body: JSON.stringify(body) });
      await onRefresh();
      setNewName(""); setNewCode(""); setAddingTo(null);
      if (parentId) setExpanded(prev => new Set(prev).add(parentId));
    } catch (e: any) {
      setError(humanizeError(e, "Error creando categoría"));
    } finally { setBusy(false); }
  };

  const handleRename = async (id: number) => {
    if (!editName.trim()) return;
    setBusy(true); setError(null);
    try {
      await apiFetch(`/catalog/categories/${id}/`, { method: "PATCH", body: JSON.stringify({ name: editName.trim() }) });
      await onRefresh();
      setEditingId(null); setEditName("");
    } catch (e: any) {
      setError(humanizeError(e, "Error renombrando"));
    } finally { setBusy(false); }
  };

  const handleToggleActive = async (cat: Category) => {
    setBusy(true); setError(null);
    try {
      await apiFetch(`/catalog/categories/${cat.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: !cat.is_active }) });
      await onRefresh();
    } catch (e: any) {
      setError(humanizeError(e, "Error"));
    } finally { setBusy(false); }
  };

  const renderNode = (cat: Category, depth: number) => {
    const kids = childrenOf(cat.id);
    const hasKids = kids.length > 0;
    const isOpen = expanded.has(cat.id);
    const isEditing = editingId === cat.id;

    return (
      <div key={cat.id}>
        <div style={{
          display: "flex", alignItems: "center", gap: 6,
          padding: "7px 8px", paddingLeft: 8 + depth * 20,
          borderBottom: `1px solid ${C.border}`, fontSize: 13,
          background: isEditing ? C.accentBg : "transparent",
        }}>
          {/* Expand toggle */}
          <button type="button" onClick={() => hasKids && toggle(cat.id)} style={{
            width: 18, height: 18, display: "flex", alignItems: "center", justifyContent: "center",
            background: "none", border: "none", cursor: hasKids ? "pointer" : "default",
            color: hasKids ? C.mid : "#ddd", fontSize: 11, flexShrink: 0,
          }}>
            {hasKids ? (isOpen ? "▼" : "▶") : "•"}
          </button>

          {/* Name or edit input */}
          {isEditing ? (
            <div style={{ display: "flex", gap: 4, flex: 1 }}>
              <input value={editName} onChange={e => setEditName(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleRename(cat.id)}
                style={{ ...iS, flex: 1, padding: "4px 8px", fontSize: 12 }} autoFocus disabled={busy} />
              <button type="button" onClick={() => handleRename(cat.id)} disabled={busy || !editName.trim()} style={{
                padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                background: C.accent, color: "#fff", border: "none", borderRadius: 4,
              }}>OK</button>
              <button type="button" aria-label="Cerrar" onClick={() => { setEditingId(null); setEditName(""); }} style={{
                padding: "4px 8px", fontSize: 11, cursor: "pointer",
                background: "none", border: `1px solid ${C.border}`, borderRadius: 4, color: C.mid,
              }}>{"✕"}</button>
            </div>
          ) : (
            <span style={{
              flex: 1, fontWeight: depth === 0 ? 600 : 400,
              color: cat.is_active !== false ? C.text : C.mute,
              textDecoration: cat.is_active === false ? "line-through" : "none",
            }}>
              {cat.name}
              {cat.code ? <span style={{ fontSize: 10, color: C.mute, marginLeft: 6, fontFamily: "monospace" }}>{cat.code}</span> : null}
              {kids.length > 0 && <span style={{ fontSize: 10, color: C.mute, marginLeft: 4 }}>({kids.length})</span>}
            </span>
          )}

          {/* Selector de estación (solo si el tenant tiene estaciones). */}
          {!isEditing && stations.length > 0 && (
            <select
              value={cat.default_print_station_id ?? ""}
              disabled={busy}
              onChange={e => {
                const v = e.target.value;
                handleSetStation(cat.id, v === "" ? null : parseInt(v, 10));
              }}
              title="Estación donde sale la comanda de esta categoría"
              style={{
                fontSize: 11, padding: "2px 6px",
                border: `1px solid ${cat.default_print_station_id ? C.accentBd : C.border}`,
                background: cat.default_print_station_id ? C.accentBg : C.surface,
                color: cat.default_print_station_id ? C.accent : C.mute,
                borderRadius: 4, cursor: "pointer", maxWidth: 130,
                fontFamily: "inherit", fontWeight: 600, flexShrink: 0,
              }}
            >
              <option value="">— sin estación —</option>
              {stations.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          )}

          {/* Actions */}
          {!isEditing && (
            <div style={{ display: "flex", gap: 2, flexShrink: 0 }}>
              <button type="button" onClick={() => { setAddingTo(cat.id); setNewName(""); setNewCode(""); }} title="Agregar sub" aria-label="Agregar sub"
                style={{ padding: "2px 6px", fontSize: 12, background: "none", border: "none", cursor: "pointer", color: C.accent }}>{"＋"}</button>
              <button type="button" onClick={() => { setEditingId(cat.id); setEditName(cat.name); }} title="Renombrar" aria-label="Renombrar"
                style={{ padding: "2px 6px", fontSize: 12, background: "none", border: "none", cursor: "pointer", color: C.mid }}>{"✏️"}</button>
              <button type="button" onClick={() => handleToggleActive(cat)} title={cat.is_active !== false ? "Desactivar" : "Activar"} aria-label={cat.is_active !== false ? "Desactivar" : "Activar"}
                style={{ padding: "2px 6px", fontSize: 12, background: "none", border: "none", cursor: "pointer", color: cat.is_active !== false ? C.green : C.red }}>
                {cat.is_active !== false ? "●" : "○"}
              </button>
            </div>
          )}
        </div>

        {/* Inline add form */}
        {addingTo === cat.id && (
          <div style={{
            display: "flex", gap: 4, padding: "6px 8px", paddingLeft: 28 + depth * 20,
            borderBottom: `1px solid ${C.border}`, background: C.bg,
          }}>
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Nombre subcategoría"
              onKeyDown={e => e.key === "Enter" && handleCreate(cat.id)}
              style={{ ...iS, flex: 1, padding: "4px 8px", fontSize: 12 }} autoFocus disabled={busy} />
            <input value={newCode} onChange={e => setNewCode(e.target.value)} placeholder="Cód."
              style={{ ...iS, width: 60, padding: "4px 6px", fontSize: 11, fontFamily: "monospace" }} disabled={busy} />
            <button type="button" onClick={() => handleCreate(cat.id)} disabled={busy || !newName.trim()} style={{
              padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
              background: C.accent, color: "#fff", border: "none", borderRadius: 4,
            }}>Crear</button>
            <button type="button" aria-label="Cerrar" onClick={() => setAddingTo(null)} style={{
              padding: "4px 8px", fontSize: 11, cursor: "pointer",
              background: "none", border: `1px solid ${C.border}`, borderRadius: 4, color: C.mid,
            }}>{"✕"}</button>
          </div>
        )}

        {/* Children */}
        {isOpen && kids.map(k => renderNode(k, depth + 1))}
      </div>
    );
  };

  return (
    <div>
      {error && (
        <div style={{ padding: "8px 12px", marginBottom: 8, background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 6, fontSize: 12, color: C.red }}>
          {error}
          <button type="button" aria-label="Cerrar" onClick={() => setError(null)} style={{ marginLeft: 8, background: "none", border: "none", cursor: "pointer", color: C.red }}>{"✕"}</button>
        </div>
      )}

      {/* Add root category */}
      <div style={{ display: "flex", gap: 4, padding: "8px 0", marginBottom: 4 }}>
        {addingTo === "root" ? (
          <>
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Nombre categoría principal"
              onKeyDown={e => e.key === "Enter" && handleCreate(null)}
              style={{ ...iS, flex: 1, padding: "6px 10px", fontSize: 13 }} autoFocus disabled={busy} />
            <input value={newCode} onChange={e => setNewCode(e.target.value)} placeholder="Cód."
              style={{ ...iS, width: 60, padding: "6px 6px", fontSize: 12, fontFamily: "monospace" }} disabled={busy} />
            <button type="button" onClick={() => handleCreate(null)} disabled={busy || !newName.trim()} style={{
              padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
              background: C.accent, color: "#fff", border: "none", borderRadius: 6,
            }}>Crear</button>
            <button type="button" aria-label="Cerrar" onClick={() => setAddingTo(null)} style={{
              padding: "6px 10px", fontSize: 12, cursor: "pointer",
              background: "none", border: `1px solid ${C.border}`, borderRadius: 6, color: C.mid,
            }}>{"✕"}</button>
          </>
        ) : (
          <button type="button" onClick={() => { setAddingTo("root"); setNewName(""); setNewCode(""); }} style={{
            padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
            background: "none", border: `1px dashed ${C.border}`, borderRadius: 6,
            color: C.accent, width: "100%",
          }}>+ Nueva categoría principal</button>
        )}
      </div>

      {/* Tree */}
      <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
        {roots.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center", color: C.mute, fontSize: 13 }}>
            No hay categorías creadas. Crea tu primera categoría arriba.
          </div>
        ) : (
          roots.map(c => renderNode(c, 0))
        )}
      </div>

      <div style={{ marginTop: 8, fontSize: 11, color: C.mute }}>
        {"Tip: Puedes crear tantos niveles como necesites (Categoría → Subcategoría → Familia → etc.)"}
      </div>
    </div>
  );
}
