"use client";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Card, SectionHeader, Btn, Spinner, Label, Hint, iS, FL, type Store, type Warehouse } from "./SettingsUI";

interface StoresTabProps {
  stores: Store[];
  onRefresh: () => void;
  flash: (type: "ok" | "err", text: string) => void;
}

export default function StoresTab({ stores, onRefresh, flash }: StoresTabProps) {
  const [saving, setSaving] = useState(false);

  // Nueva tienda
  const [newStoreName, setNewStoreName] = useState("");
  const [newStoreCode, setNewStoreCode] = useState("");
  const [newWHName, setNewWHName] = useState("Bodega Principal");
  const [showAddStore, setShowAddStore] = useState(false);

  // Editar tienda
  const [editingStoreId, setEditingStoreId] = useState<number | null>(null);
  const [editingStoreName, setEditingStoreName] = useState("");
  const [editingStoreCode, setEditingStoreCode] = useState("");

  // Añadir bodega
  const [addWHForStore, setAddWHForStore] = useState<number | null>(null);
  const [newWHNameForStore, setNewWHNameForStore] = useState("");
  const [newWHType, setNewWHType] = useState("storage");

  // Editar bodega
  const [editingWHId, setEditingWHId] = useState<number | null>(null);
  const [editingWHName, setEditingWHName] = useState("");

  const createStore = async () => {
    if (!newStoreName.trim()) return;
    setSaving(true);
    try {
      await apiFetch("/core/stores/", {
        method: "POST",
        body: JSON.stringify({ name: newStoreName.trim(), code: newStoreCode.trim(), warehouse_name: newWHName.trim() || "Bodega Principal" }),
      });
      onRefresh();
      setNewStoreName(""); setNewStoreCode(""); setNewWHName("Bodega Principal");
      setShowAddStore(false);
      flash("ok", "Tienda creada");
    } catch (e: any) { flash("err", e?.message || "Error creando tienda"); }
    finally { setSaving(false); }
  };

  const saveStoreEdit = async (storeId: number) => {
    if (!editingStoreName.trim()) return;
    setSaving(true);
    try {
      await apiFetch(`/core/stores/${storeId}/`, {
        method: "PATCH",
        body: JSON.stringify({ name: editingStoreName.trim(), code: editingStoreCode.trim() }),
      });
      onRefresh();
      setEditingStoreId(null);
      flash("ok", "Tienda actualizada");
    } catch (e: any) { flash("err", e?.message || "Error actualizando tienda"); }
    finally { setSaving(false); }
  };

  const toggleStore = async (store: Store) => {
    try {
      await apiFetch(`/core/stores/${store.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !store.is_active }),
      });
      onRefresh();
      flash("ok", store.is_active ? "Tienda desactivada" : "Tienda reactivada");
    } catch (e: any) { flash("err", e?.message || "Error"); }
  };

  const addWarehouse = async (storeId: number) => {
    if (!newWHNameForStore.trim()) return;
    setSaving(true);
    try {
      await apiFetch("/core/warehouses/", {
        method: "POST",
        body: JSON.stringify({ store: storeId, name: newWHNameForStore.trim(), warehouse_type: newWHType }),
      });
      onRefresh();
      setAddWHForStore(null); setNewWHNameForStore("");
      flash("ok", "Bodega agregada");
    } catch (e: any) { flash("err", e?.message || "Error creando bodega"); }
    finally { setSaving(false); }
  };

  const saveWarehouseEdit = async (whId: number) => {
    if (!editingWHName.trim()) return;
    setSaving(true);
    try {
      await apiFetch(`/core/warehouses/${whId}/`, {
        method: "PATCH",
        body: JSON.stringify({ name: editingWHName.trim() }),
      });
      onRefresh();
      setEditingWHId(null);
      flash("ok", "Bodega actualizada");
    } catch (e: any) { flash("err", e?.message || "Error"); }
    finally { setSaving(false); }
  };

  const toggleWarehouse = async (wh: Warehouse) => {
    try {
      await apiFetch(`/core/warehouses/${wh.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !wh.is_active }),
      });
      onRefresh();
      flash("ok", wh.is_active ? "Bodega desactivada" : "Bodega reactivada");
    } catch (e: any) { flash("err", e?.message || "Error"); }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-.02em" }}>Tiendas y bodegas</div>
          <div style={{ fontSize: 13, color: C.mute, marginTop: 2 }}>
            {stores.length} tienda{stores.length !== 1 ? "s" : ""} · {stores.reduce((acc, s) => acc + s.warehouses.length, 0)} bodega{stores.reduce((acc, s) => acc + s.warehouses.length, 0) !== 1 ? "s" : ""} en total
          </div>
        </div>
        <Btn onClick={() => { setShowAddStore(!showAddStore); setEditingStoreId(null); }} style={{ padding: "8px 14px", fontSize: 12 }}>
          {showAddStore ? "Cancelar" : "+ Nueva tienda"}
        </Btn>
      </div>

      {/* Formulario nueva tienda */}
      {showAddStore && (
        <Card style={{ borderColor: C.accentBd, borderStyle: "dashed" }}>
          <SectionHeader icon="🏪" title="Nueva tienda" desc="Se crea con una bodega principal incluida" />
          <div style={{ display: "grid", gap: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 10 }}>
              <div style={FL}><Label req>Nombre de la tienda</Label><input value={newStoreName} onChange={e => setNewStoreName(e.target.value)} placeholder="Ej: Local Centro" style={iS} autoFocus /></div>
              <div style={FL}><Label>Código</Label><input value={newStoreCode} onChange={e => setNewStoreCode(e.target.value)} placeholder="LOCAL-2" style={{ ...iS, width: 110, fontFamily: C.mono }} /></div>
            </div>
            <div style={FL}>
              <Label>Nombre bodega inicial</Label>
              <input value={newWHName} onChange={e => setNewWHName(e.target.value)} placeholder="Bodega Principal" style={iS} />
              <Hint>Puedes agregar más bodegas después</Hint>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <Btn onClick={() => setShowAddStore(false)} variant="outline" color={C.mute} style={{ padding: "9px 16px", fontSize: 13 }}>Cancelar</Btn>
              <Btn onClick={createStore} disabled={saving || !newStoreName.trim()} color={C.green}>
                {saving ? <><Spinner /> Creando...</> : "Crear tienda"}
              </Btn>
            </div>
          </div>
        </Card>
      )}

      {/* Lista de tiendas */}
      {stores.map(s => {
        const isEditingThisStore = editingStoreId === s.id;
        return (
          <Card key={s.id} style={{ padding: "0", overflow: "hidden" }}>
            {/* Store header */}
            <div style={{
              padding: "14px 18px",
              borderBottom: s.warehouses.length > 0 ? `1px solid ${C.border}` : "none",
              display: "flex", justifyContent: "space-between", alignItems: "flex-start",
              gap: 12, flexWrap: "wrap",
              background: s.is_active ? C.surface : "#FAFAFA",
            }}>
              {!isEditingThisStore ? (
                <>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ fontWeight: 700, fontSize: 14, color: s.is_active ? C.text : C.mute }}>
                        🏪 {s.name}
                      </span>
                      {s.code && (
                        <code style={{ fontFamily: C.mono, fontSize: 11, color: C.mute, background: "#F4F4F5", padding: "1px 6px", borderRadius: 4 }}>
                          {s.code}
                        </code>
                      )}
                      <span className="wh-tag" style={{
                        background: s.is_active ? C.greenBg : "#F4F4F5",
                        border: `1px solid ${s.is_active ? C.greenBd : "#D4D4D8"}`,
                        color: s.is_active ? C.green : C.mute,
                      }}>
                        {s.is_active ? "Activa" : "Inactiva"}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: C.mute, marginTop: 3 }}>
                      {s.warehouses.length} bodega{s.warehouses.length !== 1 ? "s" : ""}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <button
                      onClick={() => { setEditingStoreId(s.id); setEditingStoreName(s.name); setEditingStoreCode(s.code || ""); setShowAddStore(false); }}
                      style={{ fontSize: 12, fontWeight: 700, color: C.accent, background: "none", border: `1px solid ${C.accentBd}`, borderRadius: 7, padding: "5px 10px", cursor: "pointer", fontFamily: C.font }}
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => toggleStore(s)}
                      style={{ fontSize: 12, fontWeight: 700, color: s.is_active ? C.red : C.green, background: "none", border: `1px solid ${s.is_active ? C.redBd : C.greenBd}`, borderRadius: 7, padding: "5px 10px", cursor: "pointer", fontFamily: C.font }}
                    >
                      {s.is_active ? "Desactivar" : "Activar"}
                    </button>
                  </div>
                </>
              ) : (
                <div style={{ flex: 1, display: "grid", gap: 10 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: C.accent, marginBottom: -4 }}>Editando tienda</div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 10 }}>
                    <div style={FL}>
                      <Label req>Nombre</Label>
                      <input value={editingStoreName} onChange={e => setEditingStoreName(e.target.value)} style={iS} autoFocus
                        onKeyDown={e => { if (e.key === "Enter") saveStoreEdit(s.id); if (e.key === "Escape") setEditingStoreId(null); }} />
                    </div>
                    <div style={FL}>
                      <Label>Código</Label>
                      <input value={editingStoreCode} onChange={e => setEditingStoreCode(e.target.value)} style={{ ...iS, width: 110, fontFamily: C.mono }}
                        onKeyDown={e => { if (e.key === "Enter") saveStoreEdit(s.id); }} />
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <Btn onClick={() => setEditingStoreId(null)} variant="outline" color={C.mute} style={{ padding: "7px 14px", fontSize: 12 }}>Cancelar</Btn>
                    <Btn onClick={() => saveStoreEdit(s.id)} disabled={saving || !editingStoreName.trim()} color={C.green} style={{ padding: "7px 14px", fontSize: 12 }}>
                      {saving ? <Spinner /> : "Guardar"}
                    </Btn>
                  </div>
                </div>
              )}
            </div>

            {/* Warehouses list */}
            {s.warehouses.length > 0 && (
              <div style={{ padding: "10px 18px 14px" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 8 }}>
                  Bodegas
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {s.warehouses.map(w => (
                    <div key={w.id} style={{
                      display: "flex", alignItems: "center", gap: 8, padding: "8px 10px",
                      borderRadius: 8, border: `1px solid ${C.border}`,
                      background: w.is_active ? "#FAFAFA" : "#F4F4F5",
                      flexWrap: "wrap",
                    }}>
                      {editingWHId === w.id ? (
                        <>
                          <input
                            value={editingWHName}
                            onChange={e => setEditingWHName(e.target.value)}
                            style={{ ...iS, flex: 1, minWidth: 120, padding: "6px 10px", fontSize: 12 }}
                            autoFocus
                            onKeyDown={e => { if (e.key === "Enter") saveWarehouseEdit(w.id); if (e.key === "Escape") setEditingWHId(null); }}
                          />
                          <Btn onClick={() => saveWarehouseEdit(w.id)} disabled={saving || !editingWHName.trim()} color={C.green} style={{ padding: "6px 12px", fontSize: 12 }}>
                            {saving ? <Spinner /> : "✓"}
                          </Btn>
                          <Btn onClick={() => setEditingWHId(null)} variant="ghost" color={C.mute} style={{ padding: "6px 10px", fontSize: 12 }}>✕</Btn>
                        </>
                      ) : (
                        <>
                          <span style={{ fontSize: 13, color: w.is_active ? C.text : C.mute, flex: 1 }}>
                            📦 {w.name}
                            {!w.is_active && <span style={{ fontSize: 11, color: C.mute, marginLeft: 6 }}>(inactiva)</span>}
                            <span style={{fontSize:9,fontWeight:700,padding:"1px 5px",borderRadius:4,background:w.warehouse_type==="sales_floor"?C.greenBg:C.bg,color:w.warehouse_type==="sales_floor"?C.green:C.mute,border:"1px solid "+(w.warehouse_type==="sales_floor"?C.greenBd:C.border),marginLeft:6}}>{w.warehouse_type==="sales_floor"?"Sala":"Bodega"}</span>
                          </span>
                          <button
                            onClick={() => { setEditingWHId(w.id); setEditingWHName(w.name); }}
                            style={{ fontSize: 11, fontWeight: 700, color: C.mid, background: "none", border: "none", cursor: "pointer", padding: "2px 6px" }}
                          >Editar</button>
                          <button
                            onClick={() => toggleWarehouse(w)}
                            style={{ fontSize: 11, fontWeight: 700, color: w.is_active ? C.red : C.green, background: "none", border: "none", cursor: "pointer", padding: "2px 6px" }}
                          >
                            {w.is_active ? "Desactivar" : "Activar"}
                          </button>
                        </>
                      )}
                    </div>
                  ))}
                </div>

                {/* Add warehouse button */}
                {addWHForStore === s.id ? (
                  <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                    <input
                      value={newWHNameForStore}
                      onChange={e => setNewWHNameForStore(e.target.value)}
                      placeholder="Nombre de la bodega"
                      style={{ ...iS, flex: 1, minWidth: 160, fontSize: 12, padding: "8px 10px" }}
                      autoFocus
                      onKeyDown={e => { if (e.key === "Enter") addWarehouse(s.id); }}
                    />
                    <select value={newWHType} onChange={e => setNewWHType(e.target.value)} style={{height:32, padding:"0 8px", border:"1px solid "+C.border, borderRadius:8, fontSize:12, background:C.bg}}>
                      <option value="storage">Bodega</option>
                      <option value="sales_floor">Sala de venta</option>
                    </select>
                    <Btn onClick={() => addWarehouse(s.id)} disabled={saving || !newWHNameForStore.trim()} color={C.green} style={{ padding: "8px 14px", fontSize: 12 }}>
                      {saving ? <Spinner /> : "Crear"}
                    </Btn>
                    <Btn onClick={() => setAddWHForStore(null)} variant="outline" color={C.mute} style={{ padding: "8px 12px", fontSize: 12 }}>
                      Cancelar
                    </Btn>
                  </div>
                ) : (
                  <button
                    onClick={() => { setAddWHForStore(s.id); setNewWHNameForStore(""); }}
                    style={{
                      marginTop: 8, fontSize: 12, fontWeight: 600, color: C.accent,
                      background: "none", border: `1px dashed ${C.accentBd}`,
                      borderRadius: 8, padding: "6px 12px", cursor: "pointer", fontFamily: C.font,
                      width: "100%",
                    }}
                  >
                    + Agregar bodega
                  </button>
                )}
              </div>
            )}

            {/* If no warehouses */}
            {s.warehouses.length === 0 && (
              <div style={{ padding: "10px 18px 14px" }}>
                <button
                  onClick={() => { setAddWHForStore(s.id); setNewWHNameForStore(""); }}
                  style={{
                    fontSize: 12, fontWeight: 600, color: C.accent,
                    background: "none", border: `1px dashed ${C.accentBd}`,
                    borderRadius: 8, padding: "6px 12px", cursor: "pointer", fontFamily: C.font,
                    width: "100%",
                  }}
                >+ Agregar primera bodega</button>
                {addWHForStore === s.id && (
                  <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                    <input value={newWHNameForStore} onChange={e => setNewWHNameForStore(e.target.value)} placeholder="Nombre de la bodega" style={{ ...iS, flex: 1, minWidth: 160, fontSize: 12, padding: "8px 10px" }} autoFocus onKeyDown={e => { if (e.key === "Enter") addWarehouse(s.id); }} />
                    <select value={newWHType} onChange={e => setNewWHType(e.target.value)} style={{height:32, padding:"0 8px", border:"1px solid "+C.border, borderRadius:8, fontSize:12, background:C.bg}}>
                      <option value="storage">Bodega</option>
                      <option value="sales_floor">Sala de venta</option>
                    </select>
                    <Btn onClick={() => addWarehouse(s.id)} disabled={saving || !newWHNameForStore.trim()} color={C.green} style={{ padding: "8px 14px", fontSize: 12 }}>{saving ? <Spinner /> : "Crear"}</Btn>
                    <Btn onClick={() => setAddWHForStore(null)} variant="outline" color={C.mute} style={{ padding: "8px 12px", fontSize: 12 }}>Cancelar</Btn>
                  </div>
                )}
              </div>
            )}
          </Card>
        );
      })}

      {stores.length === 0 && !showAddStore && (
        <div style={{ textAlign: "center", padding: "40px 20px", color: C.mute, border: `1.5px dashed ${C.border}`, borderRadius: 10 }}>
          <div style={{ fontSize: 36, marginBottom: 10 }}>🏪</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: C.mid, marginBottom: 4 }}>No hay tiendas todavía</div>
          <div style={{ fontSize: 13, marginBottom: 14 }}>Crea tu primera tienda para empezar a operar</div>
          <Btn onClick={() => setShowAddStore(true)}>+ Crear primera tienda</Btn>
        </div>
      )}
    </div>
  );
}
