"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Btn, Spinner } from "@/components/ui";
import { useIsMobile } from "@/hooks/useIsMobile";
import { extractErr } from "@/lib/format";
import { formatDatetimeLocal } from "@/components/promotions/helpers";
import { PromotionTable } from "@/components/promotions/PromotionTable";
import { PromotionFormModal } from "@/components/promotions/PromotionFormModal";
import { DeleteConfirmDialog } from "@/components/promotions/DeleteConfirmDialog";
import type { Promotion, Product, PromotionForm, Conflict, Toast } from "@/components/promotions/types";
import { EMPTY_FORM } from "@/components/promotions/types";

// ─── Main page ────────────────────────────────────────────────────────────────

export default function PromotionsPage() {
  const mob = useIsMobile();
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState<Toast>(null);

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

  // Conflicts
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const conflictTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const flash = (type: "ok" | "err", text: string) => {
    setToast({ type, text });
    setTimeout(() => setToast(null), 4500);
  };

  // Helper: get product_ids from product_items
  const selectedIds = form.product_items.map(i => i.product_id);
  const overridesMap = new Map(form.product_items.map(i => [i.product_id, i.override_discount_value]));

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
      const data = await apiFetch("/catalog/products/?page_size=500");
      setProducts(data?.results ?? []);
    } catch {
      // silently fail
    } finally {
      setLoadingProducts(false);
    }
  }, []);

  // ── Conflict detection (debounced) ──────────────────────────────────────
  const checkConflicts = useCallback(async (pids: number[], sd: string, ed: string, excludeId?: number | null) => {
    if (!pids.length || !sd || !ed) { setConflicts([]); return; }
    try {
      const body: any = {
        product_ids: pids,
        start_date: new Date(sd).toISOString(),
        end_date: new Date(ed).toISOString(),
      };
      if (excludeId) body.exclude_promotion_id = excludeId;
      const res = await apiFetch("/promotions/check-conflicts/", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setConflicts(res?.conflicts ?? []);
    } catch {
      setConflicts([]);
    }
  }, []);

  // Trigger conflict check when products/dates change
  useEffect(() => {
    if (!showModal) return;
    clearTimeout(conflictTimer.current);
    conflictTimer.current = setTimeout(() => {
      checkConflicts(selectedIds, form.start_date, form.end_date, editingId);
    }, 800);
    return () => clearTimeout(conflictTimer.current);
  }, [selectedIds.length, form.start_date, form.end_date, showModal]); // eslint-disable-line

  // ── Open create modal ───────────────────────────────────────────────────
  const openCreate = () => {
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    setFormError("");
    setProductSearch("");
    setConflicts([]);
    setShowModal(true);
    loadProducts();
  };

  // ── Clone promotion ─────────────────────────────────────────────────────
  const clonePromotion = async (promo: Promotion) => {
    setEditingId(null);
    setForm({
      name: `${promo.name} (copia)`,
      discount_type: promo.discount_type,
      discount_value: promo.discount_value,
      start_date: "",
      end_date: "",
      product_items: [],
    });
    setFormError("");
    setProductSearch("");
    setConflicts([]);
    setShowModal(true);
    loadProducts();
    try {
      const detail = await apiFetch(`/promotions/${promo.id}/`);
      if (detail?.product_ids) {
        setForm(f => ({ ...f, product_items: detail.product_ids.map((pid: number) => ({ product_id: pid })) }));
      }
      if (detail?.items) {
        setForm(f => ({
          ...f,
          product_items: detail.items.map((item: any) => ({
            product_id: item.product_id,
            override_discount_value: item.override_discount_value || null,
          })),
        }));
      }
    } catch { /* use empty */ }
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
      product_items: [],
    });
    setFormError("");
    setProductSearch("");
    setConflicts([]);
    setShowModal(true);
    loadProducts();
    try {
      const detail = await apiFetch(`/promotions/${promo.id}/`);
      if (detail?.items) {
        setForm(f => ({
          ...f,
          product_items: detail.items.map((item: any) => ({
            product_id: item.product_id,
            override_discount_value: item.override_discount_value || null,
          })),
        }));
      } else if (detail?.product_ids) {
        setForm(f => ({ ...f, product_items: detail.product_ids.map((pid: number) => ({ product_id: pid })) }));
      }
    } catch { /* use empty */ }
  };

  // ── Save (create or update) ─────────────────────────────────────────────
  const handleSave = async () => {
    if (!form.name.trim()) { setFormError("El nombre es obligatorio"); return; }
    if (!form.discount_value || Number(form.discount_value) <= 0) { setFormError("El valor del descuento debe ser mayor a 0"); return; }
    if (form.discount_type === "percentage" && Number(form.discount_value) > 100) {
      setFormError("El porcentaje no puede ser mayor a 100%"); return;
    }
    if (!form.start_date || !form.end_date) { setFormError("Las fechas son obligatorias"); return; }
    if (new Date(form.end_date) <= new Date(form.start_date)) {
      setFormError("La fecha de fin debe ser posterior a la de inicio"); return;
    }
    if (selectedIds.length === 0) { setFormError("Debes seleccionar al menos un producto"); return; }

    setSaving(true);
    setFormError("");
    try {
      const body = {
        name: form.name.trim(),
        discount_type: form.discount_type,
        discount_value: form.discount_value,
        start_date: new Date(form.start_date).toISOString(),
        end_date: new Date(form.end_date).toISOString(),
        product_items: form.product_items,
      };

      if (editingId) {
        await apiFetch(`/promotions/${editingId}/`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
        flash("ok", "Oferta actualizada correctamente");
      } else {
        await apiFetch("/promotions/", {
          method: "POST",
          body: JSON.stringify(body),
        });
        flash("ok", "Oferta creada correctamente");
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
      flash("ok", "Oferta desactivada");
      loadPromotions();
    } catch (e: any) {
      flash("err", extractErr(e, "Error al desactivar oferta"));
      setConfirmDeleteId(null);
    }
  };

  // ── Toggle product selection ────────────────────────────────────────────
  const toggleProduct = (id: number) => {
    setForm(f => ({
      ...f,
      product_items: selectedIds.includes(id)
        ? f.product_items.filter(x => x.product_id !== id)
        : [...f.product_items, { product_id: id }],
    }));
  };

  const filteredProducts = products.filter((p) => {
    const q = productSearch.toLowerCase();
    return p.name.toLowerCase().includes(q) || (p.sku && p.sku.toLowerCase().includes(q));
  });

  const selectAll = () => {
    const newItems = [...form.product_items];
    for (const p of filteredProducts) {
      if (!selectedIds.includes(p.id)) {
        newItems.push({ product_id: p.id });
      }
    }
    setForm(f => ({ ...f, product_items: newItems }));
  };

  const deselectAll = () => {
    const filteredIds = new Set(filteredProducts.map(p => p.id));
    setForm(f => ({
      ...f,
      product_items: f.product_items.filter(i => !filteredIds.has(i.product_id)),
    }));
  };

  const setOverride = (pid: number, value: string) => {
    setForm(f => ({
      ...f,
      product_items: f.product_items.map(i =>
        i.product_id === pid
          ? { ...i, override_discount_value: value || null }
          : i
      ),
    }));
  };

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>

      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20, zIndex: 2000,
          padding: "12px 20px", borderRadius: C.rMd,
          background: toast.type === "ok" ? C.greenBg : C.redBg,
          color: toast.type === "ok" ? C.green : C.red,
          border: `1px solid ${toast.type === "ok" ? C.greenBd : C.redBd}`,
          fontSize: 13, fontWeight: 600, boxShadow: C.shMd,
        }}>
          {toast.text}
        </div>
      )}

      <div style={{ padding: mob ? "16px 12px" : "28px 32px", maxWidth: 1200, margin: "0 auto", fontFamily: C.font }}>

        {/* Header — en mobile el botón cae abajo del título para no
            apretar el wrap del subtítulo. */}
        <div style={{ display: "flex", flexDirection: mob ? "column" : "row", justifyContent: "space-between", alignItems: mob ? "stretch" : "center", gap: mob ? 12 : 0, marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: mob ? 18 : 22, fontWeight: 700, color: C.text, margin: 0 }}>
              Ofertas y Promociones
            </h1>
            <p style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>
              Gestiona descuentos y ofertas para tus productos
            </p>
          </div>
          <Btn variant="primary" onClick={openCreate}>+ Crear Oferta</Btn>
        </div>

        {/* Error */}
        {error && (
          <div style={{
            padding: "10px 14px", marginBottom: 16, borderRadius: C.r,
            background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red,
            fontSize: 13,
          }}>
            {error}
          </div>
        )}

        {/* Table */}
        <PromotionTable
          promotions={promotions}
          loading={loading}
          onEdit={openEdit}
          onClone={clonePromotion}
          onDelete={(id) => setConfirmDeleteId(id)}
        />
      </div>

      {/* Delete confirmation dialog */}
      {confirmDeleteId !== null && (
        <DeleteConfirmDialog
          onCancel={() => setConfirmDeleteId(null)}
          onConfirm={() => handleDelete(confirmDeleteId)}
        />
      )}

      {/* Create / Edit Modal */}
      {showModal && (
        <PromotionFormModal
          editingId={editingId}
          form={form}
          setForm={setForm}
          saving={saving}
          formError={formError}
          products={products}
          productSearch={productSearch}
          setProductSearch={setProductSearch}
          loadingProducts={loadingProducts}
          conflicts={conflicts}
          selectedIds={selectedIds}
          overridesMap={overridesMap}
          filteredProducts={filteredProducts}
          onSave={handleSave}
          onClose={() => setShowModal(false)}
          toggleProduct={toggleProduct}
          selectAll={selectAll}
          deselectAll={deselectAll}
          setOverride={setOverride}
        />
      )}
    </>
  );
}
