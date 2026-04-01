"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch, getAccessToken } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";

// ─── Types ────────────────────────────────────────────────────────────────────

type PriceRow = {
  id: number;
  sku: string | null;
  name: string;
  category_name: string | null;
  category_id: number | null;
  cost: string;
  price: string;
  margin_pct: string;
};
type Category = { id: number; name: string };
type Msg = { type: "ok" | "err"; text: string } | null;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatCLP(value: string | number): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("es-CL");
}

function sanitizePrice(v: string): string {
  const c = v.replace(/[^0-9]/g, "");
  return c;
}

function calcMargin(cost: string, price: string): number | null {
  const c = Number(cost);
  const p = Number(price);
  if (!Number.isFinite(c) || !Number.isFinite(p) || p === 0) return null;
  return ((p - c) / p) * 100;
}

function extractErr(e: any, fallback: string): string {
  if (e?.data) {
    try {
      return typeof e.data === "string" ? e.data : JSON.stringify(e.data);
    } catch {
      return fallback;
    }
  }
  return e?.message ?? fallback;
}

// ─── Micro-components ─────────────────────────────────────────────────────────

function Spinner({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: "spin 0.7s linear infinite", display: "block", flexShrink: 0 }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  );
}

type BtnV = "primary" | "secondary" | "ghost" | "danger" | "success";
function Btn({ children, onClick, variant = "secondary", disabled, size = "md", full }: { children: React.ReactNode; onClick?: () => void; variant?: BtnV; disabled?: boolean; size?: "sm" | "md" | "lg"; full?: boolean }) {
  const vs: Record<BtnV, React.CSSProperties> = {
    primary: { background: C.accent, color: "#fff", border: `1px solid ${C.accent}` },
    secondary: { background: C.surface, color: C.text, border: `1px solid ${C.borderMd}` },
    ghost: { background: "transparent", color: C.mid, border: "1px solid transparent" },
    danger: { background: C.redBg, color: C.red, border: `1px solid ${C.redBd}` },
    success: { background: C.greenBg, color: C.green, border: `1px solid ${C.greenBd}` },
  };
  const h = size === "lg" ? 46 : size === "sm" ? 30 : 38;
  const px = size === "lg" ? "0 20px" : size === "sm" ? "0 10px" : "0 14px";
  const fs = size === "lg" ? 14 : size === "sm" ? 11 : 13;
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="xb" style={{ ...vs[variant], display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, height: h, padding: px, borderRadius: C.r, fontSize: fs, fontWeight: 600, letterSpacing: "0.01em", whiteSpace: "nowrap", width: full ? "100%" : undefined, opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer" }}>
      {children}
    </button>
  );
}

function iS(extra?: React.CSSProperties): React.CSSProperties {
  return { width: "100%", height: 36, padding: "0 10px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 13, background: C.surface, ...extra };
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function PricesPage() {
  useGlobalStyles();

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
  const [bulkPreview, setBulkPreview] = useState<Array<{ id: number; name: string; oldPrice: number; newPrice: number; oldMargin: number | null; newMargin: number | null }>>([]);
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

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(rows.map((r) => r.id)));
    }
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
      if (val === "") {
        delete next[id];
      } else {
        next[id] = sanitizePrice(val);
      }
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
    // Build preview
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

  const thStyle: React.CSSProperties = {
    padding: "10px 12px",
    fontSize: 11,
    fontWeight: 700,
    color: C.mute,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    textAlign: "left",
    borderBottom: `2px solid ${C.border}`,
    whiteSpace: "nowrap",
  };

  const tdStyle: React.CSSProperties = {
    padding: "10px 12px",
    fontSize: 13,
    borderBottom: `1px solid ${C.border}`,
    verticalAlign: "middle",
  };

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>

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
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "auto", boxShadow: C.sh }}>
        {loading ? (
          <div style={{ padding: 40, display: "flex", justifyContent: "center", alignItems: "center", gap: 8, color: C.mute, fontSize: 13 }}>
            <Spinner size={16} /> Cargando...
          </div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: C.mute, fontSize: 13 }}>
            No se encontraron productos
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ ...thStyle, width: 40, textAlign: "center" }}>
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    style={{ cursor: "pointer" }}
                  />
                </th>
                <th style={thStyle}>SKU</th>
                <th style={thStyle}>Nombre</th>
                <th style={thStyle}>Categoria</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Costo</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Precio Actual</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Margen %</th>
                <th style={{ ...thStyle, textAlign: "right", minWidth: 130 }}>Nuevo Precio</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Nuevo Margen</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const hasEdit = row.id in edits;
                const newPrice = edits[row.id] ?? "";
                const newMargin = hasEdit ? calcMargin(row.cost, newPrice) : null;
                const currentMargin = Number(row.margin_pct);

                return (
                  <tr key={row.id} style={{ background: hasEdit ? C.amberBg : undefined, transition: C.ease }}>
                    <td style={{ ...tdStyle, textAlign: "center" }}>
                      <input
                        type="checkbox"
                        checked={selected.has(row.id)}
                        onChange={() => toggleOne(row.id)}
                        style={{ cursor: "pointer" }}
                      />
                    </td>
                    <td style={{ ...tdStyle, fontFamily: C.mono, fontSize: 12, color: C.mid }}>
                      {row.sku || "—"}
                    </td>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>
                      {row.name}
                    </td>
                    <td style={{ ...tdStyle, color: C.mid, fontSize: 12 }}>
                      {row.category_name || "—"}
                    </td>
                    <td style={{ ...tdStyle, textAlign: "right", fontFamily: C.mono }}>
                      ${formatCLP(row.cost)}
                    </td>
                    <td style={{ ...tdStyle, textAlign: "right", fontFamily: C.mono, fontWeight: 600 }}>
                      ${formatCLP(row.price)}
                    </td>
                    <td style={{ ...tdStyle, textAlign: "right", fontFamily: C.mono, color: Number.isFinite(currentMargin) ? (currentMargin < 0 ? C.red : currentMargin < 15 ? C.amber : C.green) : C.mute }}>
                      {Number.isFinite(currentMargin) ? `${currentMargin.toFixed(1)}%` : "—"}
                    </td>
                    <td style={{ ...tdStyle, textAlign: "right" }}>
                      <input
                        type="text"
                        inputMode="numeric"
                        placeholder={formatCLP(row.price)}
                        value={newPrice}
                        onChange={(e) => setNewPrice(row.id, e.target.value)}
                        style={{
                          width: 110,
                          height: 30,
                          padding: "0 8px",
                          border: `1px solid ${hasEdit ? C.amberBd : C.border}`,
                          borderRadius: C.r,
                          fontSize: 13,
                          fontFamily: C.mono,
                          textAlign: "right",
                          background: hasEdit ? C.surface : C.bg,
                        }}
                      />
                    </td>
                    <td style={{ ...tdStyle, textAlign: "right", fontFamily: C.mono, fontWeight: hasEdit ? 700 : 400, color: newMargin !== null ? (newMargin < 0 ? C.red : newMargin < 15 ? C.amber : C.green) : C.mute }}>
                      {newMargin !== null ? `${newMargin.toFixed(1)}%` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {/* Paginación */}
        {total > pageSize && (
          <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 12, paddingBottom: 8 }}>
            <button
              disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
              style={{ padding: "6px 14px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: page <= 1 ? "default" : "pointer", opacity: page <= 1 ? 0.4 : 1, fontSize: 13 }}
            >← Anterior</button>
            <span style={{ fontSize: 13, color: C.mid, alignSelf: "center" }}>
              Página {page} de {Math.ceil(total / pageSize)}
            </span>
            <button
              disabled={page >= Math.ceil(total / pageSize)}
              onClick={() => setPage(p => p + 1)}
              style={{ padding: "6px 14px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: page >= Math.ceil(total / pageSize) ? "default" : "pointer", opacity: page >= Math.ceil(total / pageSize) ? 0.4 : 1, fontSize: 13 }}
            >Siguiente →</button>
          </div>
        )}
      </div>

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

          {/* Type: % or fixed */}
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: C.text, cursor: "pointer" }}>
            <input type="radio" name="bulkType" checked={bulkType === "pct"} onChange={() => setBulkType("pct")} /> %
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: C.text, cursor: "pointer" }}>
            <input type="radio" name="bulkType" checked={bulkType === "amt"} onChange={() => setBulkType("amt")} /> Monto fijo
          </label>

          {/* Direction */}
          <select
            value={bulkDir}
            onChange={(e) => setBulkDir(e.target.value as "increase" | "decrease")}
            style={{ height: 30, padding: "0 8px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 12, background: C.surface }}
          >
            <option value="increase">Subir</option>
            <option value="decrease">Bajar</option>
          </select>

          {/* Value */}
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

      {/* ── Save Confirmation Modal ──────────────────────────────────────── */}
      {showSaveConfirm && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => setShowSaveConfirm(false)}>
          <div style={{ background: C.surface, borderRadius: C.rMd, width: 520, maxWidth: "95vw", maxHeight: "80vh", overflow: "auto", boxShadow: C.shLg, padding: 24 }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: "0 0 12px", fontSize: 16, fontWeight: 700 }}>Confirmar cambios de precio</h3>
            <p style={{ margin: "0 0 12px", fontSize: 13, color: C.mid }}>Se actualizarán {changedCount} producto(s):</p>
            <div style={{ maxHeight: 300, overflow: "auto", border: `1px solid ${C.border}`, borderRadius: C.r }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr>
                    <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px" }}>Producto</th>
                    <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Precio actual</th>
                    <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Nuevo precio</th>
                    <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Margen</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(edits).map(([pid, newP]) => {
                    const row = rows.find(r => r.id === Number(pid));
                    if (!row) return null;
                    const nm = calcMargin(row.cost, newP);
                    return (
                      <tr key={pid}>
                        <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}` }}>{row.name}</td>
                        <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono }}>${formatCLP(row.price)}</td>
                        <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono, fontWeight: 700 }}>${formatCLP(newP)}</td>
                        <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono, color: nm !== null ? (nm < 0 ? C.red : nm < 15 ? C.amber : C.green) : C.mute }}>
                          {nm !== null ? `${nm.toFixed(1)}%` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <Btn variant="secondary" onClick={() => setShowSaveConfirm(false)}>Cancelar</Btn>
              <Btn variant="success" onClick={saveChanges}>Confirmar y guardar</Btn>
            </div>
          </div>
        </div>
      )}

      {/* ── Bulk Preview Modal ───────────────────────────────────────────── */}
      {showBulkConfirm && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => setShowBulkConfirm(false)}>
          <div style={{ background: C.surface, borderRadius: C.rMd, width: 600, maxWidth: "95vw", maxHeight: "80vh", overflow: "auto", boxShadow: C.shLg, padding: 24 }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: "0 0 8px", fontSize: 16, fontWeight: 700 }}>Preview — Ajuste masivo</h3>
            <p style={{ margin: "0 0 4px", fontSize: 13, color: C.mid }}>
              {bulkDir === "increase" ? "Subir" : "Bajar"} {bulkType === "pct" ? `${bulkValue}%` : `$${formatCLP(bulkValue)}`} a {bulkPreview.length} producto(s)
            </p>
            {bulkPreview.some(p => (p.newMargin ?? 0) < 0) && (
              <p style={{ margin: "4px 0 8px", fontSize: 12, color: C.red, fontWeight: 600 }}>
                ⚠ Algunos productos quedarán con margen negativo
              </p>
            )}
            <div style={{ maxHeight: 320, overflow: "auto", border: `1px solid ${C.border}`, borderRadius: C.r }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr>
                    <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px" }}>Producto</th>
                    <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Actual</th>
                    <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Nuevo</th>
                    <th style={{ ...thStyle, fontSize: 10, padding: "6px 8px", textAlign: "right" }}>Margen</th>
                  </tr>
                </thead>
                <tbody>
                  {bulkPreview.map(p => (
                    <tr key={p.id} style={{ background: (p.newMargin ?? 0) < 0 ? C.redBg : undefined }}>
                      <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}` }}>{p.name}</td>
                      <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono }}>${formatCLP(p.oldPrice)}</td>
                      <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono, fontWeight: 700 }}>${formatCLP(p.newPrice)}</td>
                      <td style={{ padding: "6px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right", fontFamily: C.mono, color: p.newMargin !== null ? (p.newMargin < 0 ? C.red : p.newMargin < 15 ? C.amber : C.green) : C.mute }}>
                        {p.newMargin !== null ? `${p.newMargin.toFixed(1)}%` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <Btn variant="secondary" onClick={() => setShowBulkConfirm(false)}>Cancelar</Btn>
              <Btn variant="primary" onClick={applyBulk}>Confirmar y aplicar</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
