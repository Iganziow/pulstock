"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch, getAccessToken } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Btn, Spinner } from "@/components/ui";
import { formatCLP, extractErr } from "@/lib/format";
import { sanitizePrice, calcMargin } from "@/components/prices/helpers";
import { PriceTable } from "@/components/prices/PriceTable";
import { SaveConfirmModal } from "@/components/prices/SaveConfirmModal";
import { BulkPreviewModal } from "@/components/prices/BulkPreviewModal";
import type { PriceRow, Category, Msg, BulkPreviewItem } from "@/components/prices/types";

// ─── Input style helper ──────────────────────────────────────────────────────

function iS(extra?: React.CSSProperties): React.CSSProperties {
  return { width: "100%", height: 36, padding: "0 10px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 13, background: C.surface, ...extra };
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function PricesPage() {
  useGlobalStyles();
  const mob = useIsMobile();

  // Data
  const [rows, setRows] = useState<PriceRow[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState("");
  const [catFilter, setCatFilter] = useState<number | "">("");

  // Edits: product_id -> new price string
  const [edits, setEdits] = useState<Record<number, string>>({});

  // Selection for bulk
  const [selected, setSelected] = useState<Set<number>>(new Set());

  // Bulk rule
  const [bulkType, setBulkType] = useState<"pct" | "amt">("pct");
  const [bulkDir, setBulkDir] = useState<"increase" | "decrease">("increase");
  const [bulkValue, setBulkValue] = useState("");

  // UI state
  const [saving, setSaving] = useState(false);
  const [applyingBulk, setApplyingBulk] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  // Confirmation modals
  const [showSaveConfirm, setShowSaveConfirm] = useState(false);
  const [showBulkConfirm, setShowBulkConfirm] = useState(false);
  const [bulkPreview, setBulkPreview] = useState<BulkPreviewItem[]>([]);
  const [exporting, setExporting] = useState(false);

  const flash = (type: "ok" | "err", text: string) => {
    setMsg({ type, text });
    setTimeout(() => setMsg(null), 4500);
  };

  // ─── Data fetching ────────────────────────────────────────────────────────
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("q", search.trim());
      if (catFilter) params.set("category_id", String(catFilter));
      params.set("page", String(page));
      const qs = params.toString();
      const res = await apiFetch(`/catalog/products/prices/?${qs}`);
      setRows(res.results || []);
      setTotal(res.total ?? res.results?.length ?? 0);
      if (res.page_size) setPageSize(res.page_size);
    } catch (e: any) {
      flash("err", extractErr(e, "Error cargando precios"));
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [search, catFilter, page]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    (async () => {
      try {
        const res = await apiFetch("/catalog/categories/");
        setCategories(res.results || res || []);
      } catch {
        setCategories([]);
      }
    })();
  }, []);

  // ─── Selection helpers ────────────────────────────────────────────────────
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id));

  function toggleAll() {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(rows.map((r) => r.id)));
  }

  function toggleOne(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // ─── Edit helpers ─────────────────────────────────────────────────────────
  function setNewPrice(id: number, val: string) {
    setEdits((prev) => {
      const next = { ...prev };
      if (val === "") delete next[id];
      else next[id] = sanitizePrice(val);
      return next;
    });
  }

  const changedCount = Object.keys(edits).length;

  // ─── Save individual changes ──────────────────────────────────────────────
  function requestSaveConfirm() {
    if (changedCount === 0) return;
    setShowSaveConfirm(true);
  }

  async function saveChanges() {
    setShowSaveConfirm(false);
    if (changedCount === 0) return;
    setSaving(true);
    try {
      const updates = Object.entries(edits).map(([pid, price]) => ({
        product_id: Number(pid),
        price,
      }));
      await apiFetch("/catalog/products/prices/bulk/", {
        method: "POST",
        body: JSON.stringify({ updates }),
      });
      flash("ok", `${updates.length} precio(s) actualizado(s)`);
      setEdits({});
      await fetchData();
    } catch (e: any) {
      flash("err", extractErr(e, "Error guardando precios"));
    } finally {
      setSaving(false);
    }
  }

  // ─── Apply bulk rule ──────────────────────────────────────────────────────
  function requestBulkConfirm() {
    if (selected.size === 0) {
      flash("err", "Selecciona al menos un producto");
      return;
    }
    const val = Number(bulkValue);
    if (!Number.isFinite(val) || val <= 0) {
      flash("err", "Ingresa un valor mayor a 0");
      return;
    }
    const preview = rows.filter(r => selected.has(r.id)).map(r => {
      const oldPrice = Number(r.price);
      let newPrice: number;
      if (bulkType === "pct") {
        const factor = bulkDir === "increase" ? (1 + val / 100) : (1 - val / 100);
        newPrice = Math.round(oldPrice * factor);
      } else {
        newPrice = bulkDir === "increase" ? oldPrice + val : oldPrice - val;
      }
      if (newPrice < 0) newPrice = 0;
      const cost = Number(r.cost);
      return {
        id: r.id,
        name: r.name,
        oldPrice,
        newPrice,
        oldMargin: calcMargin(r.cost, r.price),
        newMargin: newPrice > 0 ? ((newPrice - cost) / newPrice) * 100 : null,
      };
    });
    setBulkPreview(preview);
    setShowBulkConfirm(true);
  }

  async function applyBulk() {
    setShowBulkConfirm(false);
    const val = Number(bulkValue);
    setApplyingBulk(true);
    try {
      await apiFetch("/catalog/products/prices/bulk/", {
        method: "POST",
        body: JSON.stringify({
          rule: { type: bulkType, value: String(val), direction: bulkDir },
          filter: { product_ids: Array.from(selected) },
        }),
      });
      flash("ok", `Ajuste masivo aplicado a ${selected.size} producto(s)`);
      setBulkValue("");
      setSelected(new Set());
      setEdits({});
      await fetchData();
    } catch (e: any) {
      flash("err", extractErr(e, "Error aplicando ajuste masivo"));
    } finally {
      setApplyingBulk(false);
    }
  }

  // ─── Export ───────────────────────────────────────────────────────────────
  async function exportPrices() {
    setExporting(true);
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("q", search.trim());
      if (catFilter) params.set("category_id", String(catFilter));
      const qs = params.toString();
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
      const token = getAccessToken();
      const res = await fetch(`${apiUrl}/catalog/products/prices/export/?${qs}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: "include",
      });
      if (!res.ok) throw new Error("Error exportando");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "precios_pulstock.xlsx";
      a.click();
      URL.revokeObjectURL(url);
      flash("ok", "Archivo exportado");
    } catch (e: any) {
      flash("err", extractErr(e, "Error exportando precios"));
    } finally {
      setExporting(false);
    }
  }

  // ─── Render ───────────────────────────────────────────────────────────────
  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "16px 12px" : "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>

      {/* Toast */}
      {msg && (
        <div style={{
          position: "fixed", top: 20, right: 20, zIndex: 100,
          padding: "12px 20px", borderRadius: C.rMd,
          background: msg.type === "ok" ? C.greenBg : C.redBg,
          color: msg.type === "ok" ? C.green : C.red,
          border: `1px solid ${msg.type === "ok" ? C.greenBd : C.redBd}`,
          fontSize: 13, fontWeight: 600, boxShadow: C.shMd,
        }}>
          {msg.text}
        </div>
      )}

      {/* Header */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <div style={{ width: 4, height: 26, background: C.accent, borderRadius: 2 }} />
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: "-0.04em" }}>Lista de Precios</h1>
        </div>
        <p style={{ margin: 0, fontSize: 13, color: C.mute, marginLeft: 14 }}>
          {loading ? "Cargando..." : `${total} producto(s)`}
        </p>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <input
          type="text"
          placeholder="Buscar por nombre o SKU..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          style={{ ...iS({ width: 280, maxWidth: "100%" }) }}
        />
        <select
          value={catFilter}
          onChange={(e) => { setCatFilter(e.target.value ? Number(e.target.value) : ""); setPage(1); }}
          style={{ ...iS({ width: 200 }) }}
        >
          <option value="">Todas las categorias</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      <PriceTable
        rows={rows}
        loading={loading}
        edits={edits}
        selected={selected}
        allSelected={allSelected}
        toggleAll={toggleAll}
        toggleOne={toggleOne}
        setNewPrice={setNewPrice}
        total={total}
        pageSize={pageSize}
        page={page}
        setPage={setPage}
      />

      {/* Bottom action bar */}
      <div style={{
        position: "sticky", bottom: 0, left: 0, right: 0,
        background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd,
        padding: "14px 18px", boxShadow: C.shMd,
        display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap",
      }}>
        {/* Left: Bulk rule */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em" }}>Ajuste masivo</span>

          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: C.text, cursor: "pointer" }}>
            <input type="radio" name="bulkType" checked={bulkType === "pct"} onChange={() => setBulkType("pct")} /> %
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: C.text, cursor: "pointer" }}>
            <input type="radio" name="bulkType" checked={bulkType === "amt"} onChange={() => setBulkType("amt")} /> Monto fijo
          </label>

          <select
            value={bulkDir}
            onChange={(e) => setBulkDir(e.target.value as "increase" | "decrease")}
            style={{ height: 30, padding: "0 8px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 12, background: C.surface }}
          >
            <option value="increase">Subir</option>
            <option value="decrease">Bajar</option>
          </select>

          <input
            type="text"
            inputMode="numeric"
            placeholder={bulkType === "pct" ? "10" : "500"}
            value={bulkValue}
            onChange={(e) => setBulkValue(e.target.value.replace(/[^0-9.]/g, ""))}
            style={{ width: 80, height: 30, padding: "0 8px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 12, fontFamily: C.mono, textAlign: "right", background: C.surface }}
          />

          <Btn size="sm" variant="primary" disabled={applyingBulk || selected.size === 0} onClick={requestBulkConfirm}>
            {applyingBulk ? <Spinner size={12} /> : null}
            Aplicar a seleccionados ({selected.size})
          </Btn>
        </div>

        {/* Right: Export + Save changes */}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Btn variant="secondary" disabled={exporting || loading} onClick={exportPrices} size="sm">
            {exporting ? <Spinner size={12} /> : null}
            Exportar
          </Btn>
          <Btn variant="success" disabled={saving || changedCount === 0} onClick={requestSaveConfirm}>
            {saving ? <Spinner size={14} /> : null}
            Guardar {changedCount} cambio(s)
          </Btn>
        </div>
      </div>

      {/* Save Confirmation Modal */}
      {showSaveConfirm && (
        <SaveConfirmModal
          edits={edits}
          rows={rows}
          onCancel={() => setShowSaveConfirm(false)}
          onConfirm={saveChanges}
        />
      )}

      {/* Bulk Preview Modal */}
      {showBulkConfirm && (
        <BulkPreviewModal
          bulkDir={bulkDir}
          bulkType={bulkType}
          bulkValue={bulkValue}
          bulkPreview={bulkPreview}
          onCancel={() => setShowBulkConfirm(false)}
          onConfirm={applyBulk}
        />
      )}
    </div>
  );
}
