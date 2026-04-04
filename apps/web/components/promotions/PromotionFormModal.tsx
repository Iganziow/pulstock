"use client";

import { C } from "@/lib/theme";
import { Btn, Spinner } from "@/components/ui";
import { formatCLP } from "@/lib/format";
import { promoPrice } from "./helpers";
import type { PromotionForm, Product, Conflict } from "./types";

interface PromotionFormModalProps {
  editingId: number | null;
  form: PromotionForm;
  setForm: React.Dispatch<React.SetStateAction<PromotionForm>>;
  saving: boolean;
  formError: string;
  products: Product[];
  productSearch: string;
  setProductSearch: (v: string) => void;
  loadingProducts: boolean;
  conflicts: Conflict[];
  selectedIds: number[];
  overridesMap: Map<number, string | null | undefined>;
  filteredProducts: Product[];
  onSave: () => void;
  onClose: () => void;
  toggleProduct: (id: number) => void;
  selectAll: () => void;
  deselectAll: () => void;
  setOverride: (pid: number, value: string) => void;
}

const inputStyle: React.CSSProperties = {
  width: "100%", height: 38, padding: "0 12px",
  border: `1px solid ${C.border}`, borderRadius: C.r,
  fontSize: 13, color: C.text, background: C.surface,
  outline: "none", transition: C.ease,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, color: C.mid,
  marginBottom: 4, display: "block",
};

export function PromotionFormModal({
  editingId, form, setForm, saving, formError,
  products, productSearch, setProductSearch, loadingProducts,
  conflicts, selectedIds, overridesMap, filteredProducts,
  onSave, onClose, toggleProduct, selectAll, deselectAll, setOverride,
}: PromotionFormModalProps) {
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.4)", display: "flex",
      alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <div style={{
        background: C.surface, borderRadius: C.rMd,
        width: 620, maxWidth: "95vw", maxHeight: "90vh",
        display: "flex", flexDirection: "column",
        boxShadow: C.shLg,
      }} onClick={(e) => e.stopPropagation()}>

        {/* Modal header */}
        <div style={{
          padding: "20px 24px", borderBottom: `1px solid ${C.border}`,
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <h2 style={{ fontSize: 17, fontWeight: 700, color: C.text, margin: 0 }}>
            {editingId ? "Editar Oferta" : "Crear Oferta"}
          </h2>
          <button onClick={onClose} style={{
            background: "none", border: "none", cursor: "pointer",
            fontSize: 20, color: C.mute, padding: 4, lineHeight: 1,
          }}>&#x2715;</button>
        </div>

        {/* Modal body */}
        <div style={{ padding: 24, overflowY: "auto", flex: 1 }}>
          {formError && (
            <div style={{
              padding: "8px 12px", marginBottom: 16, borderRadius: C.r,
              background: C.redBg, border: `1px solid ${C.redBd}`,
              color: C.red, fontSize: 12,
            }}>
              {formError}
            </div>
          )}

          {/* Conflict warning */}
          {conflicts.length > 0 && (
            <div style={{
              padding: "8px 12px", marginBottom: 16, borderRadius: C.r,
              background: C.amberBg, border: `1px solid ${C.amberBd}`,
              color: C.amber, fontSize: 12,
            }}>
              <strong>Conflictos detectados:</strong> {conflicts.length} producto(s) ya estan en otras promociones activas en el mismo periodo.
              <ul style={{ margin: "4px 0 0", paddingLeft: 16 }}>
                {conflicts.slice(0, 5).map((c, i) => (
                  <li key={i}>{c.product_name} — ya en &quot;{c.conflicting_promotion_name}&quot;</li>
                ))}
                {conflicts.length > 5 && <li>...y {conflicts.length - 5} mas</li>}
              </ul>
            </div>
          )}

          {/* Name */}
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Nombre de la oferta</label>
            <input
              style={inputStyle}
              placeholder="Ej: Promo Verano 2026"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>

          {/* Discount type */}
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Tipo de descuento</label>
            <div style={{ display: "flex", gap: 16 }}>
              {(["percentage", "fixed"] as const).map((t) => (
                <label key={t} style={{
                  display: "flex", alignItems: "center", gap: 8,
                  fontSize: 13, color: C.text, cursor: "pointer",
                }}>
                  <input
                    type="radio" name="discount_type"
                    checked={form.discount_type === t}
                    onChange={() => setForm((f) => ({ ...f, discount_type: t }))}
                  />
                  {t === "percentage" ? "Porcentaje (%)" : "Precio fijo ($)"}
                </label>
              ))}
            </div>
          </div>

          {/* Discount value */}
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Valor del descuento</label>
            <div style={{ position: "relative" }}>
              <span style={{
                position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)",
                fontSize: 13, color: C.mute, fontWeight: 600, pointerEvents: "none",
              }}>
                {form.discount_type === "percentage" ? "%" : "$"}
              </span>
              <input
                style={{
                  ...inputStyle,
                  paddingLeft: 32,
                  borderColor: form.discount_type === "percentage" && Number(form.discount_value) > 100 ? C.red : C.border,
                }}
                type="number" min="0" step="1"
                max={form.discount_type === "percentage" ? "100" : undefined}
                placeholder={form.discount_type === "percentage" ? "Ej: 30" : "Ej: 2500"}
                value={form.discount_value}
                onChange={(e) => setForm((f) => ({ ...f, discount_value: e.target.value }))}
              />
            </div>
            {form.discount_type === "percentage" && Number(form.discount_value) > 100 && (
              <span style={{ fontSize: 11, color: C.red }}>El porcentaje no puede ser mayor a 100%</span>
            )}
          </div>

          {/* Dates */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
            <div>
              <label style={labelStyle}>Fecha inicio</label>
              <input
                type="datetime-local"
                style={inputStyle}
                value={form.start_date}
                onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
              />
            </div>
            <div>
              <label style={labelStyle}>Fecha fin</label>
              <input
                type="datetime-local"
                style={{
                  ...inputStyle,
                  borderColor: form.start_date && form.end_date && new Date(form.end_date) <= new Date(form.start_date) ? C.red : C.border,
                }}
                value={form.end_date}
                onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
              />
              {form.start_date && form.end_date && new Date(form.end_date) <= new Date(form.start_date) && (
                <span style={{ fontSize: 11, color: C.red }}>Debe ser posterior a la fecha de inicio</span>
              )}
            </div>
          </div>

          {/* Product selector */}
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <label style={{ ...labelStyle, marginBottom: 0 }}>
                Productos ({selectedIds.length} seleccionados)
              </label>
              <div style={{ display: "flex", gap: 6 }}>
                <button onClick={selectAll} style={{ fontSize: 11, color: C.accent, background: "none", border: "none", cursor: "pointer", fontWeight: 600 }}>
                  Seleccionar todos ({filteredProducts.length})
                </button>
                <span style={{ color: C.mute }}>|</span>
                <button onClick={deselectAll} style={{ fontSize: 11, color: C.mid, background: "none", border: "none", cursor: "pointer", fontWeight: 600 }}>
                  Deseleccionar
                </button>
              </div>
            </div>
            <input
              style={{ ...inputStyle, marginBottom: 8 }}
              placeholder="Buscar por nombre o SKU..."
              value={productSearch}
              onChange={(e) => setProductSearch(e.target.value)}
            />
            <div style={{
              border: `1px solid ${C.border}`, borderRadius: C.r,
              maxHeight: 260, overflowY: "auto", background: C.bg,
            }}>
              {loadingProducts ? (
                <div style={{ display: "flex", justifyContent: "center", padding: 20 }}>
                  <Spinner size={16} />
                </div>
              ) : filteredProducts.length === 0 ? (
                <div style={{ padding: 16, textAlign: "center", color: C.mute, fontSize: 12 }}>
                  No se encontraron productos
                </div>
              ) : (
                filteredProducts.map((p) => {
                  const isSelected = selectedIds.includes(p.id);
                  const hasDiscount = form.discount_value && Number(form.discount_value) > 0;
                  const override = overridesMap.get(p.id);
                  return (
                    <div
                      key={p.id}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "8px 12px",
                        background: isSelected ? C.accentBg : "transparent",
                        borderBottom: `1px solid ${C.border}`,
                        transition: C.ease,
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleProduct(p.id)}
                        style={{ flexShrink: 0, accentColor: C.accent, cursor: "pointer" }}
                      />
                      <div style={{ flex: 1, minWidth: 0, cursor: "pointer" }} onClick={() => toggleProduct(p.id)}>
                        <div style={{ fontSize: 13, fontWeight: 500, color: C.text }}>
                          {p.name}
                        </div>
                        <div style={{ fontSize: 11, color: C.mute }}>
                          SKU: {p.sku || "\u2014"}
                        </div>
                      </div>
                      {/* Override input -- only visible for selected products */}
                      {isSelected && (
                        <input
                          type="number"
                          placeholder={form.discount_type === "percentage" ? "%" : "$"}
                          value={override || ""}
                          onChange={(e) => { e.stopPropagation(); setOverride(p.id, e.target.value); }}
                          onClick={(e) => e.stopPropagation()}
                          title="Override descuento para este producto"
                          style={{
                            width: 65, height: 26, padding: "0 6px",
                            border: `1px solid ${override ? C.amberBd : C.border}`,
                            borderRadius: C.r, fontSize: 11, fontFamily: C.mono,
                            textAlign: "right", background: override ? C.amberBg : C.surface,
                          }}
                        />
                      )}
                      <div style={{ textAlign: "right", flexShrink: 0, minWidth: 70 }}>
                        <div style={{ fontSize: 12, color: C.mid }}>
                          ${formatCLP(p.price)}
                        </div>
                        {isSelected && hasDiscount && (
                          <div style={{ fontSize: 12, fontWeight: 600, color: C.green }}>
                            &rarr; ${promoPrice(p.price, form.discount_type, form.discount_value, override)}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Modal footer */}
        <div style={{
          padding: "16px 24px", borderTop: `1px solid ${C.border}`,
          display: "flex", justifyContent: "flex-end", gap: 8,
        }}>
          <Btn variant="secondary" onClick={onClose}>Cancelar</Btn>
          <Btn variant="primary" onClick={onSave} disabled={saving}>
            {saving ? <><Spinner size={14} /> Guardando...</> : editingId ? "Guardar cambios" : "Crear oferta"}
          </Btn>
        </div>
      </div>
    </div>
  );
}
