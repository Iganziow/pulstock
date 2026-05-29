"use client";

/**
 * /dashboard/combos — Crear y gestionar combos/packs (Mario 28/05/26).
 *
 * Un combo es un producto a precio fijo armado con otros productos
 * ("Capu amaretto + Brownie = $5.600"). Por detrás el backend crea un
 * Product (is_combo) + su receta; al venderlo descuenta el stock de los
 * componentes. El cajero NO necesita saber de "recetas": elige productos
 * + precio y listo. El combo aparece como ítem en el buscador de mesas.
 */

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Btn, Spinner } from "@/components/ui";
import { useIsMobile } from "@/hooks/useIsMobile";
import { extractErr } from "@/lib/format";

interface ComboComponent {
  product_id: number;
  name: string;
  qty: string;
  unit_price: string;
}
interface Combo {
  id: number;
  name: string;
  price: string;
  category_id: number | null;
  is_active: boolean;
  components: ComboComponent[];
  normal_price: string;
  savings: string;
}
interface PickProduct { id: number; name: string; sku?: string | null; price?: string }
interface FormItem { product_id: number; name: string; qty: number }
type Toast = { type: "ok" | "err"; text: string } | null;

const fmtCLP = (v: string | number) => "$" + Math.round(Number(v) || 0).toLocaleString("es-CL");

export default function CombosPage() {
  const mob = useIsMobile();
  const [combos, setCombos] = useState<Combo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState<Toast>(null);

  // Modal
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [items, setItems] = useState<FormItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  // Product picker
  const [products, setProducts] = useState<PickProduct[]>([]);
  const [search, setSearch] = useState("");

  const flash = (type: "ok" | "err", text: string) => {
    setToast({ type, text });
    setTimeout(() => setToast(null), 4000);
  };

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const data = await apiFetch("/catalog/combos/");
      setCombos(Array.isArray(data) ? data : []);
    } catch (e: any) {
      setError(extractErr(e, "Error al cargar combos"));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const loadProducts = useCallback(async () => {
    try {
      // Solo productos activos y NO combos (un combo no puede contener combos)
      const data = await apiFetch("/catalog/products/?page_size=500&is_active=true");
      const rows = data?.results ?? data ?? [];
      setProducts(rows.filter((p: any) => !p.is_combo).map((p: any) => ({ id: p.id, name: p.name, sku: p.sku, price: p.price })));
    } catch { /* silent */ }
  }, []);

  const openCreate = () => {
    setEditingId(null); setName(""); setPrice(""); setItems([]);
    setFormError(""); setSearch("");
    setShowModal(true); loadProducts();
  };

  const openEdit = (c: Combo) => {
    setEditingId(c.id);
    setName(c.name);
    setPrice(String(Math.round(Number(c.price))));
    setItems(c.components.map(comp => ({
      product_id: comp.product_id, name: comp.name,
      qty: Number(comp.qty) % 1 === 0 ? Number(comp.qty) : parseFloat(Number(comp.qty).toFixed(3)),
    })));
    setFormError(""); setSearch("");
    setShowModal(true); loadProducts();
  };

  const addItem = (p: PickProduct) => {
    setItems(prev => prev.some(i => i.product_id === p.id)
      ? prev.map(i => i.product_id === p.id ? { ...i, qty: i.qty + 1 } : i)
      : [...prev, { product_id: p.id, name: p.name, qty: 1 }]);
    setSearch("");
  };
  const setItemQty = (pid: number, qty: number) => {
    setItems(prev => prev.map(i => i.product_id === pid ? { ...i, qty: Math.max(1, qty) } : i));
  };
  const removeItem = (pid: number) => setItems(prev => prev.filter(i => i.product_id !== pid));

  // Precio normal (suma de componentes) y ahorro, para mostrar referencia.
  const normalPrice = items.reduce((s, it) => {
    const p = products.find(x => x.id === it.product_id);
    return s + (Number(p?.price) || 0) * it.qty;
  }, 0);
  const priceNum = Number(price) || 0;
  const savings = normalPrice - priceNum;

  const totalUnits = items.reduce((s, i) => s + i.qty, 0);
  const canSave = name.trim() && priceNum > 0 && items.length > 0 && totalUnits >= 2;

  const handleSave = async () => {
    if (!name.trim()) { setFormError("El nombre es obligatorio"); return; }
    if (priceNum <= 0) { setFormError("El precio del combo debe ser mayor a 0"); return; }
    if (totalUnits < 2) { setFormError("Un combo necesita al menos 2 productos (o varias unidades)"); return; }

    setSaving(true); setFormError("");
    try {
      const body = {
        name: name.trim(),
        price: String(priceNum),
        components: items.map(i => ({ product_id: i.product_id, qty: i.qty })),
      };
      if (editingId) {
        await apiFetch(`/catalog/combos/${editingId}/`, { method: "PATCH", body: JSON.stringify(body) });
        flash("ok", "Combo actualizado");
      } else {
        await apiFetch("/catalog/combos/", { method: "POST", body: JSON.stringify(body) });
        flash("ok", "Combo creado — ya aparece en las mesas");
      }
      setShowModal(false);
      load();
    } catch (e: any) {
      setFormError(extractErr(e, "Error al guardar el combo"));
    } finally { setSaving(false); }
  };

  const handleDelete = async (c: Combo) => {
    if (!confirm(`¿Eliminar el combo "${c.name}"?`)) return;
    try {
      await apiFetch(`/catalog/combos/${c.id}/`, { method: "DELETE" });
      flash("ok", "Combo eliminado");
      load();
    } catch (e: any) {
      flash("err", extractErr(e, "Error al eliminar"));
    }
  };

  const filtered = products.filter(p => {
    const q = search.toLowerCase();
    return !q || p.name.toLowerCase().includes(q) || (p.sku && p.sku.toLowerCase().includes(q));
  }).slice(0, 30);

  return (
    <>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20, zIndex: 2000, padding: "12px 20px",
          borderRadius: C.rMd, background: toast.type === "ok" ? C.greenBg : C.redBg,
          color: toast.type === "ok" ? C.green : C.red,
          border: `1px solid ${toast.type === "ok" ? C.greenBd : C.redBd}`,
          fontSize: 13, fontWeight: 600, boxShadow: C.shMd,
        }}>{toast.text}</div>
      )}

      <div style={{ padding: mob ? "16px 12px" : "28px 32px", maxWidth: 1000, margin: "0 auto", fontFamily: C.font }}>
        <div style={{ display: "flex", flexDirection: mob ? "column" : "row", justifyContent: "space-between", alignItems: mob ? "stretch" : "center", gap: mob ? 12 : 0, marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: mob ? 18 : 22, fontWeight: 700, color: C.text, margin: 0 }}>Combos</h1>
            <p style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>
              Agrupa productos a precio de pack (ej: Capu + Brownie = $5.600). Aparecen en las mesas como un ítem.
            </p>
          </div>
          <Btn variant="primary" onClick={openCreate}>+ Nuevo combo</Btn>
        </div>

        {error && (
          <div style={{ padding: "10px 14px", marginBottom: 16, borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 13 }}>{error}</div>
        )}

        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: 40 }}><Spinner /></div>
        ) : combos.length === 0 ? (
          <div style={{ textAlign: "center", padding: "48px 20px", color: C.mute }}>
            <div style={{ fontSize: 36, marginBottom: 10 }}>🍩☕</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.text, marginBottom: 4 }}>Sin combos todavía</div>
            <div style={{ fontSize: 13 }}>Creá tu primer combo para venderlo en las mesas.</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {combos.map(c => (
              <div key={c.id} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "14px 16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>{c.name}</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                      {c.components.map(comp => (
                        <span key={comp.product_id} style={{
                          fontSize: 12, padding: "3px 9px", borderRadius: 99,
                          background: C.bg, color: C.mid, border: `1px solid ${C.border}`, fontWeight: 500,
                        }}>
                          {comp.name} ×{Number(comp.qty) % 1 === 0 ? Math.round(Number(comp.qty)) : Number(comp.qty)}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <div style={{ fontSize: 18, fontWeight: 800, color: C.accent, fontVariantNumeric: "tabular-nums" }}>{fmtCLP(c.price)}</div>
                    {Number(c.savings) > 0 && (
                      <div style={{ fontSize: 11, color: C.green, fontWeight: 600 }}>
                        Ahorro {fmtCLP(c.savings)} <span style={{ color: C.mute, textDecoration: "line-through", fontWeight: 400 }}>{fmtCLP(c.normal_price)}</span>
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
                  <Btn variant="secondary" size="sm" onClick={() => openEdit(c)}>Editar</Btn>
                  <Btn variant="danger" size="sm" onClick={() => handleDelete(c)}>Eliminar</Btn>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modal crear/editar */}
      {showModal && (
        <div onClick={() => !saving && setShowModal(false)} style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 1000,
          display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: C.surface, borderRadius: C.rMd, width: 520, maxWidth: "100%",
            maxHeight: "90vh", overflowY: "auto", boxShadow: C.shMd,
          }}>
            <div style={{ padding: "16px 20px", borderBottom: `1px solid ${C.border}`, fontSize: 16, fontWeight: 800, color: C.text }}>
              {editingId ? "Editar combo" : "Nuevo combo"}
            </div>
            <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
              {formError && (
                <div style={{ padding: "8px 12px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 6, color: C.red, fontSize: 12 }}>{formError}</div>
              )}

              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.05em" }}>Nombre del combo</span>
                <input value={name} onChange={e => setName(e.target.value)} placeholder="Ej: Combo Capu + Brownie"
                  style={{ padding: "8px 10px", border: `1px solid ${C.border}`, borderRadius: 6, fontSize: 13, fontFamily: "inherit", background: C.surface, color: C.text }} />
              </label>

              {/* Productos del combo */}
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.05em" }}>Productos del combo</span>
                {items.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 4 }}>
                    {items.map(it => (
                      <div key={it.product_id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: C.bg, borderRadius: 6, border: `1px solid ${C.border}` }}>
                        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: C.text, minWidth: 0 }}>{it.name}</span>
                        <div style={{ display: "flex", alignItems: "center", border: `1px solid ${C.border}`, borderRadius: 6, overflow: "hidden", background: C.surface }}>
                          <button type="button" onClick={() => setItemQty(it.product_id, it.qty - 1)} style={{ width: 26, height: 26, border: "none", background: "transparent", cursor: "pointer", color: C.accent, fontWeight: 700, fontSize: 14 }}>−</button>
                          <span style={{ minWidth: 24, textAlign: "center", fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{it.qty}</span>
                          <button type="button" onClick={() => setItemQty(it.product_id, it.qty + 1)} style={{ width: 26, height: 26, border: "none", background: "transparent", cursor: "pointer", color: C.accent, fontWeight: 700, fontSize: 14 }}>+</button>
                        </div>
                        <button type="button" onClick={() => removeItem(it.product_id)} aria-label="Quitar" style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 2, display: "flex" }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {/* Buscador para agregar */}
                <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar producto para agregar…"
                  style={{ padding: "8px 10px", border: `1px solid ${C.border}`, borderRadius: 6, fontSize: 13, fontFamily: "inherit", background: C.surface, color: C.text }} />
                {search && (
                  <div style={{ maxHeight: 180, overflowY: "auto", border: `1px solid ${C.border}`, borderRadius: 6 }}>
                    {filtered.length === 0 ? (
                      <div style={{ padding: 10, fontSize: 12, color: C.mute }}>Sin resultados</div>
                    ) : filtered.map(p => (
                      <div key={p.id} onClick={() => addItem(p)} style={{ padding: "8px 10px", fontSize: 13, cursor: "pointer", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", gap: 8 }}>
                        <span style={{ color: C.text }}>{p.name}</span>
                        <span style={{ color: C.mute, fontVariantNumeric: "tabular-nums" }}>{fmtCLP(p.price || 0)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.05em" }}>Precio del combo</span>
                <div style={{ position: "relative" }}>
                  <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", fontSize: 13, color: C.mute }}>$</span>
                  <input type="number" min="0" value={price} onChange={e => setPrice(e.target.value)} placeholder="5600"
                    style={{ width: "100%", padding: "8px 10px 8px 22px", border: `1px solid ${C.border}`, borderRadius: 6, fontSize: 13, fontFamily: "inherit", background: C.surface, color: C.text, fontVariantNumeric: "tabular-nums" }} />
                </div>
              </label>

              {/* Referencia: precio normal vs combo */}
              {items.length > 0 && normalPrice > 0 && (
                <div style={{ padding: "10px 12px", background: C.bg, borderRadius: 6, fontSize: 12, color: C.mid }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>Precio suelto (suma)</span><span style={{ fontVariantNumeric: "tabular-nums" }}>{fmtCLP(normalPrice)}</span>
                  </div>
                  {priceNum > 0 && (
                    <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontWeight: 700, color: savings > 0 ? C.green : C.mid }}>
                      <span>{savings > 0 ? "Ahorro del cliente" : "Diferencia"}</span>
                      <span style={{ fontVariantNumeric: "tabular-nums" }}>{fmtCLP(Math.abs(savings))}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
            <div style={{ padding: "14px 20px", borderTop: `1px solid ${C.border}`, display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <Btn variant="secondary" onClick={() => setShowModal(false)} disabled={saving}>Cancelar</Btn>
              <Btn variant="primary" onClick={handleSave} disabled={saving || !canSave}>
                {saving ? "Guardando…" : editingId ? "Guardar cambios" : "Crear combo"}
              </Btn>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
