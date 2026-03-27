"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";

// ─── Types ────────────────────────────────────────────────────────────────────

type Promotion = {
  id: number;
  name: string;
  discount_type: "percentage" | "fixed";
  discount_value: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
  status: "active" | "scheduled" | "expired" | "inactive";
  product_count: number;
  created_at: string;
};

type Product = {
  id: number;
  name: string;
  sku: string;
  price: string;
};

type PromotionForm = {
  name: string;
  discount_type: "percentage" | "fixed";
  discount_value: string;
  start_date: string;
  end_date: string;
  product_ids: number[];
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatCLP(value: string | number) {
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("es-CL");
}

function formatDate(iso: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
}

function formatDatetimeLocal(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function extractErr(e: any, fallback: string) {
  if (e?.data) {
    try { return typeof e.data === "string" ? e.data : JSON.stringify(e.data); }
    catch { return fallback; }
  }
  return e?.message ?? fallback;
}

function discountLabel(type: "percentage" | "fixed", value: string) {
  if (type === "percentage") return `${value}% OFF`;
  return `$${formatCLP(value)} fijo`;
}

function promoPrice(price: string, type: "percentage" | "fixed", value: string) {
  const p = Number(price);
  const v = Number(value);
  if (Number.isNaN(p) || Number.isNaN(v)) return "—";
  if (type === "percentage") return formatCLP(Math.round(p * (1 - v / 100)));
  return formatCLP(v);
}

const STATUS_MAP: Record<string, { label: string; bg: string; bd: string; c: string }> = {
  active:    { label: "Activa",     bg: C.greenBg,  bd: C.greenBd,  c: C.green },
  scheduled: { label: "Programada", bg: C.skyBg,    bd: C.skyBd,    c: C.sky   },
  expired:   { label: "Expirada",   bg: "#F4F4F5",  bd: C.border,   c: C.mid   },
  inactive:  { label: "Inactiva",   bg: C.redBg,    bd: C.redBd,    c: C.red   },
};

const EMPTY_FORM: PromotionForm = {
  name: "",
  discount_type: "percentage",
  discount_value: "",
  start_date: "",
  end_date: "",
  product_ids: [],
};

// ─── Micro-components ─────────────────────────────────────────────────────────

function Spinner({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
      style={{ animation: "spin 0.7s linear infinite", display: "block", flexShrink: 0 }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  );
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_MAP[status] || STATUS_MAP.inactive;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "3px 9px", borderRadius: 99, fontSize: 11, fontWeight: 600,
      letterSpacing: "0.02em", border: `1px solid ${s.bd}`, background: s.bg, color: s.c,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: s.c, flexShrink: 0 }} />
      {s.label}
    </span>
  );
}

type BtnV = "primary" | "secondary" | "ghost" | "danger";
function Btn({ children, onClick, variant = "secondary", disabled, size = "md" }: {
  children: React.ReactNode; onClick?: () => void;
  variant?: BtnV; disabled?: boolean; size?: "sm" | "md";
}) {
  const vs: Record<BtnV, React.CSSProperties> = {
    primary:   { background: C.accent,  color: "#fff",  border: `1px solid ${C.accent}` },
    secondary: { background: C.surface, color: C.text,  border: `1px solid ${C.borderMd}` },
    ghost:     { background: "transparent", color: C.mid, border: "1px solid transparent" },
    danger:    { background: C.redBg,   color: C.red,   border: `1px solid ${C.redBd}` },
  };
  return (
    <button type="button" onClick={onClick} disabled={disabled} style={{
      ...vs[variant], display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
      height: size === "sm" ? 32 : 38, padding: size === "sm" ? "0 12px" : "0 16px",
      borderRadius: C.r, fontSize: size === "sm" ? 12 : 13, fontWeight: 600,
      letterSpacing: "0.01em", whiteSpace: "nowrap", cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.5 : 1, transition: C.ease,
    }}>
      {children}
    </button>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function PromotionsPage() {
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<PromotionForm>({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  // Products for selector
  const [products, setProducts] = useState<Product[]>([]);
  const [productSearch, setProductSearch] = useState("");
  const [loadingProducts, setLoadingProducts] = useState(false);

  // Delete confirm
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  // ── Fetch promotions ────────────────────────────────────────────────────
  const loadPromotions = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch("/promotions/");
      setPromotions(data?.results ?? []);
    } catch (e: any) {
      setError(extractErr(e, "Error al cargar ofertas"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadPromotions(); }, [loadPromotions]);

  // ── Fetch products for selector ─────────────────────────────────────────
  const loadProducts = useCallback(async () => {
    setLoadingProducts(true);
    try {
      const data = await apiFetch("/catalog/products/?page_size=200");
      setProducts(data?.results ?? []);
    } catch {
      // silently fail
    } finally {
      setLoadingProducts(false);
    }
  }, []);

  // ── Open create modal ───────────────────────────────────────────────────
  const openCreate = () => {
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    setFormError("");
    setProductSearch("");
    setShowModal(true);
    loadProducts();
  };

  // ── Open edit modal ─────────────────────────────────────────────────────
  const openEdit = async (promo: Promotion) => {
    setEditingId(promo.id);
    setForm({
      name: promo.name,
      discount_type: promo.discount_type,
      discount_value: promo.discount_value,
      start_date: formatDatetimeLocal(promo.start_date),
      end_date: formatDatetimeLocal(promo.end_date),
      product_ids: [],
    });
    setFormError("");
    setProductSearch("");
    setShowModal(true);
    loadProducts();
    // Load promotion detail to get product_ids
    try {
      const detail = await apiFetch(`/promotions/${promo.id}/`);
      if (detail?.product_ids) {
        setForm((f) => ({ ...f, product_ids: detail.product_ids }));
      }
    } catch {
      // use empty product list
    }
  };

  // ── Save (create or update) ─────────────────────────────────────────────
  const handleSave = async () => {
    if (!form.name.trim()) { setFormError("El nombre es obligatorio"); return; }
    if (!form.discount_value || Number(form.discount_value) <= 0) { setFormError("El valor del descuento debe ser mayor a 0"); return; }
    if (!form.start_date || !form.end_date) { setFormError("Las fechas son obligatorias"); return; }

    setSaving(true);
    setFormError("");
    try {
      const body = {
        name: form.name.trim(),
        discount_type: form.discount_type,
        discount_value: form.discount_value,
        start_date: new Date(form.start_date).toISOString(),
        end_date: new Date(form.end_date).toISOString(),
        product_ids: form.product_ids,
      };

      if (editingId) {
        await apiFetch(`/promotions/${editingId}/`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      } else {
        await apiFetch("/promotions/", {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      setShowModal(false);
      loadPromotions();
    } catch (e: any) {
      setFormError(extractErr(e, "Error al guardar oferta"));
    } finally {
      setSaving(false);
    }
  };

  // ── Delete (soft) ───────────────────────────────────────────────────────
  const handleDelete = async (id: number) => {
    try {
      await apiFetch(`/promotions/${id}/`, { method: "DELETE" });
      setConfirmDeleteId(null);
      loadPromotions();
    } catch (e: any) {
      alert(extractErr(e, "Error al desactivar oferta"));
    }
  };

  // ── Toggle product selection ────────────────────────────────────────────
  const toggleProduct = (id: number) => {
    setForm((f) => ({
      ...f,
      product_ids: f.product_ids.includes(id)
        ? f.product_ids.filter((x) => x !== id)
        : [...f.product_ids, id],
    }));
  };

  // ── Filtered products ───────────────────────────────────────────────────
  const filteredProducts = products.filter((p) => {
    const q = productSearch.toLowerCase();
    return p.name.toLowerCase().includes(q) || (p.sku && p.sku.toLowerCase().includes(q));
  });

  // ── Styles ──────────────────────────────────────────────────────────────
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

  const thStyle: React.CSSProperties = {
    padding: "10px 14px", fontSize: 11, fontWeight: 600,
    color: C.mute, textTransform: "uppercase", letterSpacing: "0.04em",
    textAlign: "left", borderBottom: `1px solid ${C.border}`,
    background: C.bg, whiteSpace: "nowrap",
  };

  const tdStyle: React.CSSProperties = {
    padding: "12px 14px", fontSize: 13, color: C.text,
    borderBottom: `1px solid ${C.border}`, whiteSpace: "nowrap",
  };

  return (
    <>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>

      <div style={{ padding: "28px 32px", maxWidth: 1200, margin: "0 auto", fontFamily: C.font }}>

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: C.text, margin: 0 }}>
              Ofertas y Promociones
            </h1>
            <p style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>
              Gestiona descuentos y ofertas para tus productos
            </p>
          </div>
          <Btn variant="primary" onClick={openCreate}>+ Crear Oferta</Btn>
        </div>

        {/* ── Error ──────────────────────────────────────────────────────── */}
        {error && (
          <div style={{
            padding: "10px 14px", marginBottom: 16, borderRadius: C.r,
            background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red,
            fontSize: 13,
          }}>
            {error}
          </div>
        )}

        {/* ── Table ──────────────────────────────────────────────────────── */}
        <div style={{
          background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`,
          boxShadow: C.sh, overflow: "auto",
        }}>
          {loading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
              <Spinner size={22} />
            </div>
          ) : promotions.length === 0 ? (
            <div style={{ padding: 48, textAlign: "center", color: C.mute, fontSize: 14 }}>
              No hay ofertas creadas aún
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={thStyle}>Nombre</th>
                  <th style={thStyle}>Tipo</th>
                  <th style={thStyle}>Fecha inicio</th>
                  <th style={thStyle}>Fecha fin</th>
                  <th style={thStyle}>Estado</th>
                  <th style={thStyle}>N° productos</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {promotions.map((p) => (
                  <tr key={p.id} style={{ transition: C.ease }}>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{p.name}</td>
                    <td style={tdStyle}>{discountLabel(p.discount_type, p.discount_value)}</td>
                    <td style={tdStyle}>{formatDate(p.start_date)}</td>
                    <td style={tdStyle}>{formatDate(p.end_date)}</td>
                    <td style={tdStyle}><StatusBadge status={p.status} /></td>
                    <td style={tdStyle}>{p.product_count}</td>
                    <td style={{ ...tdStyle, textAlign: "right" }}>
                      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                        <Btn size="sm" variant="ghost" onClick={() => openEdit(p)}>Editar</Btn>
                        <Btn size="sm" variant="danger" onClick={() => setConfirmDeleteId(p.id)}>Desactivar</Btn>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── Delete confirmation dialog ───────────────────────────────────── */}
      {confirmDeleteId !== null && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(0,0,0,0.4)", display: "flex",
          alignItems: "center", justifyContent: "center",
        }} onClick={() => setConfirmDeleteId(null)}>
          <div style={{
            background: C.surface, borderRadius: C.rMd, padding: 28,
            width: 400, maxWidth: "90vw", boxShadow: C.shLg,
          }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: C.text, margin: "0 0 8px" }}>
              Desactivar oferta
            </h3>
            <p style={{ fontSize: 13, color: C.mid, margin: "0 0 20px" }}>
              ¿Estás seguro de que deseas desactivar esta oferta? Los productos volverán a su precio normal.
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <Btn variant="secondary" onClick={() => setConfirmDeleteId(null)}>Cancelar</Btn>
              <Btn variant="danger" onClick={() => handleDelete(confirmDeleteId)}>Desactivar</Btn>
            </div>
          </div>
        </div>
      )}

      {/* ── Create / Edit Modal ──────────────────────────────────────────── */}
      {showModal && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(0,0,0,0.4)", display: "flex",
          alignItems: "center", justifyContent: "center",
        }} onClick={() => setShowModal(false)}>
          <div style={{
            background: C.surface, borderRadius: C.rMd,
            width: 580, maxWidth: "95vw", maxHeight: "90vh",
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
              <button onClick={() => setShowModal(false)} style={{
                background: "none", border: "none", cursor: "pointer",
                fontSize: 20, color: C.mute, padding: 4, lineHeight: 1,
              }}>✕</button>
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
                    style={{ ...inputStyle, paddingLeft: 32 }}
                    type="number" min="0" step="1"
                    placeholder={form.discount_type === "percentage" ? "Ej: 30" : "Ej: 2500"}
                    value={form.discount_value}
                    onChange={(e) => setForm((f) => ({ ...f, discount_value: e.target.value }))}
                  />
                </div>
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
                    style={inputStyle}
                    value={form.end_date}
                    onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
                  />
                </div>
              </div>

              {/* Product selector */}
              <div>
                <label style={labelStyle}>
                  Productos ({form.product_ids.length} seleccionados)
                </label>
                <input
                  style={{ ...inputStyle, marginBottom: 8 }}
                  placeholder="Buscar por nombre o SKU..."
                  value={productSearch}
                  onChange={(e) => setProductSearch(e.target.value)}
                />
                <div style={{
                  border: `1px solid ${C.border}`, borderRadius: C.r,
                  maxHeight: 220, overflowY: "auto", background: C.bg,
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
                      const selected = form.product_ids.includes(p.id);
                      const hasDiscount = form.discount_value && Number(form.discount_value) > 0;
                      return (
                        <div
                          key={p.id}
                          onClick={() => toggleProduct(p.id)}
                          style={{
                            display: "flex", alignItems: "center", gap: 10,
                            padding: "8px 12px", cursor: "pointer",
                            background: selected ? C.accentBg : "transparent",
                            borderBottom: `1px solid ${C.border}`,
                            transition: C.ease,
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={selected}
                            readOnly
                            style={{ flexShrink: 0, accentColor: C.accent }}
                          />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 13, fontWeight: 500, color: C.text }}>
                              {p.name}
                            </div>
                            <div style={{ fontSize: 11, color: C.mute }}>
                              SKU: {p.sku || "—"}
                            </div>
                          </div>
                          <div style={{ textAlign: "right", flexShrink: 0 }}>
                            <div style={{ fontSize: 12, color: C.mid }}>
                              ${formatCLP(p.price)}
                            </div>
                            {hasDiscount && (
                              <div style={{ fontSize: 12, fontWeight: 600, color: C.green }}>
                                → ${promoPrice(p.price, form.discount_type, form.discount_value)}
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
              <Btn variant="secondary" onClick={() => setShowModal(false)}>Cancelar</Btn>
              <Btn variant="primary" onClick={handleSave} disabled={saving}>
                {saving ? <><Spinner size={14} /> Guardando...</> : editingId ? "Guardar cambios" : "Crear oferta"}
              </Btn>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
