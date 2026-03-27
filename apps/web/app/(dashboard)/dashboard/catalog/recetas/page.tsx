"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, apiUpload } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";

function useIsMobile(){const[m,setM]=useState(false);useEffect(()=>{const fn=()=>setM(window.innerWidth<768);fn();window.addEventListener("resize",fn);return()=>window.removeEventListener("resize",fn);},[]);return m;}

// ─── Types ────────────────────────────────────────────────────────────────────

type Product = {
  id: number; name: string; sku?: string | null; unit?: string | null;
  has_recipe?: boolean; is_active?: boolean;
  unit_obj_id?: number | null; unit_obj_family?: string | null;
};
type UnitType = {
  id: number; code: string; name: string; family: string; is_base: boolean;
};
type RecipeLine = {
  id?: number; ingredient_id: number;
  ingredient_name?: string; ingredient_sku?: string; ingredient_unit?: string;
  ingredient_unit_family?: string;
  qty: string;
  unit_id?: number | null; unit_code?: string | null;
};
type Recipe = {
  id?: number; product_id?: number; is_active: boolean; notes: string; lines: RecipeLine[];
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function extractErr(e: unknown, fallback: string) {
  const err = e as { data?: unknown; message?: string };
  if (err?.data) {
    try { return typeof err.data === "string" ? err.data : JSON.stringify(err.data); }
    catch { return fallback; }
  }
  return err?.message ?? fallback;
}

// ─── Components ───────────────────────────────────────────────────────────────

function Spinner({ size = 14 }: { size?: number }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%",
      border: `${size < 16 ? 2 : 2.5}px solid #E4E4E7`,
      borderTopColor: C.accent,
      animation: "spin 0.7s linear infinite", flexShrink: 0,
    }}/>
  );
}

type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "success";
function Btn({
  variant = "secondary", onClick, disabled, children, size = "md",
}: {
  variant?: BtnVariant; onClick?: () => void; disabled?: boolean;
  children: React.ReactNode; size?: "sm" | "md";
}) {
  const base: React.CSSProperties = {
    display: "inline-flex", alignItems: "center", gap: 6,
    fontFamily: C.font, fontWeight: 600, cursor: "pointer",
    border: "1px solid transparent", borderRadius: C.r,
    transition: C.ease, whiteSpace: "nowrap",
    padding: size === "sm" ? "5px 11px" : "8px 16px",
    fontSize: size === "sm" ? 12 : 13,
  };
  const styles: Record<BtnVariant, React.CSSProperties> = {
    primary:   { background: C.accent,   color: "#fff",    borderColor: C.accent },
    secondary: { background: C.surface,  color: C.mid,     borderColor: C.border },
    ghost:     { background: "transparent", color: C.mid,  borderColor: "transparent" },
    danger:    { background: "#FEF2F2",  color: C.red,     borderColor: "#FECACA" },
    success:   { background: C.greenBg,  color: C.green,   borderColor: C.greenBd },
  };
  return (
    <button className="xb" onClick={onClick} disabled={disabled}
      style={{ ...base, ...styles[variant] }}>
      {children}
    </button>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={() => onChange(!on)} style={{
      width: 36, height: 20, borderRadius: 99, border: "none", cursor: "pointer",
      background: on ? C.accent : C.border, position: "relative", transition: C.ease, flexShrink: 0,
    }}>
      <span style={{
        position: "absolute", top: 2, left: on ? 18 : 2,
        width: 16, height: 16, borderRadius: "50%", background: "#fff",
        transition: C.ease, display: "block",
      }}/>
    </button>
  );
}

function Badge({ color, children }: { color: string; children: React.ReactNode }) {
  const colors: Record<string, { bg: string; fg: string; bd: string }> = {
    green:  { bg: C.greenBg,  fg: C.green,  bd: C.greenBd },
    gray:   { bg: "#F4F4F5",  fg: C.mid,    bd: C.border  },
    amber:  { bg: C.amberBg,  fg: C.amber,  bd: "#FDE68A" },
    accent: { bg: C.accentBg, fg: C.accent, bd: C.accentBd },
  };
  const s = colors[color] ?? colors.gray;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "3px 9px", borderRadius: 99, fontSize: 11, fontWeight: 600,
      background: s.bg, border: `1px solid ${s.bd}`, color: s.fg,
    }}>
      {children}
    </span>
  );
}

// =============================================================================
// MAIN PAGE
// =============================================================================

const PAGE_CSS = `
.rec-row{transition:background 0.1s ease;cursor:pointer}
.rec-row:hover{background:#F4F4F5}
`;

export default function RecetasPage() {
  useGlobalStyles(PAGE_CSS);
  const mob = useIsMobile();

  // Left panel — product list
  const [products, setProducts]         = useState<Product[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [searchQ, setSearchQ]           = useState("");
  const [selectedId, setSelectedId]     = useState<number | null>(null);

  // Right panel — recipe state
  const [recipe, setRecipe]             = useState<Recipe | null>(null);
  const [recipeLoading, setRecipeLoading] = useState(false);
  const [recipeLines, setRecipeLines]   = useState<RecipeLine[]>([]);
  const [recipeNotes, setRecipeNotes]   = useState("");
  const [recipeActive, setRecipeActive] = useState(true);
  const [recipeSaving, setRecipeSaving] = useState(false);
  const [recipeErr, setRecipeErr]       = useState<string | null>(null);
  const [creatingNew, setCreatingNew]   = useState(false);

  // Ingredient search
  const [ingSearch, setIngSearch]       = useState("");
  const [ingResults, setIngResults]     = useState<Product[]>([]);
  const [ingSearching, setIngSearching] = useState(false);
  const ingDebounceRef                  = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Units
  const [units, setUnits]                 = useState<UnitType[]>([]);

  // Import
  const [showImport, setShowImport]       = useState(false);
  const [importFile, setImportFile]       = useState<File | null>(null);
  const [importResult, setImportResult]   = useState<any>(null);
  const [importing, setImporting]         = useState(false);
  const [importErr, setImportErr]         = useState<string | null>(null);

  // ── Load products ──────────────────────────────────────────────────────────

  const loadProducts = useCallback(async () => {
    setLoadingProducts(true);
    try {
      const data = await apiFetch("/catalog/products/?page_size=200&ordering=name");
      const list: Product[] = Array.isArray(data) ? data : (data?.results ?? []);
      list.sort((a, b) => a.name.localeCompare(b.name));
      setProducts(list);
    } catch {
      setProducts([]);
    } finally {
      setLoadingProducts(false);
    }
  }, []);

  useEffect(() => { loadProducts(); }, [loadProducts]);

  // ── Load units ───────────────────────────────────────────────────────────
  useEffect(() => {
    apiFetch("/catalog/units/").then((data: UnitType[]) => setUnits(data ?? [])).catch(() => {});
  }, []);

  // ── Select product → load recipe ───────────────────────────────────────────

  const selectProduct = useCallback(async (p: Product) => {
    if (selectedId === p.id) return;
    setSelectedId(p.id);
    setRecipeErr(null);
    setIngSearch(""); setIngResults([]);
    setCreatingNew(false);
    setConfirmDeleteRecipe(false);

    if (!p.has_recipe) {
      setRecipe(null);
      setRecipeLines([]);
      setRecipeNotes("");
      setRecipeActive(true);
      return;
    }

    setRecipeLoading(true);
    try {
      const data = await apiFetch(`/catalog/products/${p.id}/recipe/`);
      setRecipe(data);
      setRecipeLines((data.lines ?? []).map((l: any) => ({
        ...l, qty: String(l.qty),
        unit_id: l.unit_id ?? null, unit_code: l.unit_code ?? null,
        ingredient_unit_family: l.ingredient_unit_family ?? null,
      })));
      setRecipeNotes(data.notes ?? "");
      setRecipeActive(data.is_active ?? true);
    } catch {
      setRecipe(null);
      setRecipeLines([]);
      setRecipeNotes("");
      setRecipeActive(true);
    } finally {
      setRecipeLoading(false);
    }
  }, [selectedId]);

  // ── Ingredient search ──────────────────────────────────────────────────────

  const searchIngredients = (q: string) => {
    setIngSearch(q);
    clearTimeout(ingDebounceRef.current);
    if (!q.trim()) { setIngResults([]); return; }
    ingDebounceRef.current = setTimeout(async () => {
      setIngSearching(true);
      try {
        const data = await apiFetch(`/catalog/products/?q=${encodeURIComponent(q)}&page_size=10`);
        const list: Product[] = Array.isArray(data) ? data : (data?.results ?? []);
        setIngResults(list.filter(x => x.id !== selectedId));
      } catch { setIngResults([]); }
      finally { setIngSearching(false); }
    }, 300);
  };

  const addIngredient = (p: Product) => {
    if (recipeLines.some(l => l.ingredient_id === p.id)) return;
    // Default unit: the ingredient's own unit_obj if it has one
    const defaultUnit = p.unit_obj_id ? units.find(u => u.id === p.unit_obj_id) : null;
    setRecipeLines(prev => [...prev, {
      ingredient_id: p.id, ingredient_name: p.name,
      ingredient_sku: p.sku ?? "", ingredient_unit: p.unit ?? "UN",
      ingredient_unit_family: p.unit_obj_family ?? null,
      qty: "1",
      unit_id: defaultUnit?.id ?? null, unit_code: defaultUnit?.code ?? null,
    }]);
    setIngSearch(""); setIngResults([]);
  };

  // ── Save / delete recipe ───────────────────────────────────────────────────

  const saveRecipe = async () => {
    if (!selectedId) return;
    const validLines = recipeLines.filter(l => Number(l.qty) > 0);
    if (!validLines.length) {
      setRecipeErr("Agrega al menos un ingrediente con cantidad mayor a 0.");
      return;
    }
    setRecipeSaving(true); setRecipeErr(null);
    try {
      const saved = await apiFetch(`/catalog/products/${selectedId}/recipe/`, {
        method: "POST",
        body: JSON.stringify({
          is_active: recipeActive,
          notes: recipeNotes,
          lines: validLines.map(l => ({ ingredient_id: l.ingredient_id, qty: Number(l.qty), unit_id: l.unit_id || null })),
        }),
      });
      setRecipe(saved);
      setRecipeLines((saved.lines ?? []).map((l: any) => ({
        ...l, qty: String(l.qty),
        unit_id: l.unit_id ?? null, unit_code: l.unit_code ?? null,
        ingredient_unit_family: l.ingredient_unit_family ?? null,
      })));
      setCreatingNew(false);
      // update has_recipe in product list
      setProducts(prev => prev.map(x => x.id === selectedId ? { ...x, has_recipe: recipeActive } : x));
    } catch (e) {
      setRecipeErr(extractErr(e, "Error guardando receta"));
    } finally {
      setRecipeSaving(false);
    }
  };

  const [confirmDeleteRecipe, setConfirmDeleteRecipe] = useState(false);
  const deleteRecipe = async () => {
    if (!selectedId || !recipe) return;
    setRecipeSaving(true); setRecipeErr(null);
    try {
      await apiFetch(`/catalog/products/${selectedId}/recipe/`, { method: "DELETE" });
      setRecipe(null);
      setRecipeLines([]);
      setRecipeNotes("");
      setRecipeActive(true);
      setCreatingNew(false);
      setConfirmDeleteRecipe(false);
      setProducts(prev => prev.map(x => x.id === selectedId ? { ...x, has_recipe: false } : x));
    } catch (e) {
      setRecipeErr(extractErr(e, "Error eliminando receta"));
    } finally {
      setRecipeSaving(false);
    }
  };

  // ── Import recetas ───────────────────────────────────────────────────────

  const downloadSample = async () => {
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("access") : null;
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/catalog/recipes/import-sample/`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Error descargando archivo");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = "ejemplo_recetas.xlsx";
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e) { setImportErr(extractErr(e, "Error descargando ejemplo")); }
  };

  const runImport = async () => {
    if (!importFile) return;
    setImporting(true); setImportErr(null); setImportResult(null);
    try {
      const fd = new FormData(); fd.append("file", importFile);
      const result = await apiUpload("/catalog/recipes/import-csv/", fd);
      setImportResult(result);
      loadProducts(); // refresh product list to update has_recipe badges
    } catch (e) { setImportErr(extractErr(e, "Error importando recetas")); }
    finally { setImporting(false); }
  };

  // ── Computed ───────────────────────────────────────────────────────────────

  const selectedProduct = products.find(p => p.id === selectedId) ?? null;

  const filtered = searchQ.trim()
    ? products.filter(p =>
        p.name.toLowerCase().includes(searchQ.toLowerCase()) ||
        (p.sku ?? "").toLowerCase().includes(searchQ.toLowerCase())
      )
    : products;

  const showEditor = selectedId !== null && !recipeLoading;
  const hasRecipe  = !!recipe;
  const editorVisible = showEditor && (hasRecipe || creatingNew);

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div style={{ fontFamily: C.font, color: C.text, padding: mob ? "16px 12px" : "28px 32px", background: C.bg, minHeight: "100vh" }}>

      {/* HEADER */}
      <div style={{ marginBottom: 24, display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <div style={{ width: 4, height: 26, background: C.accent, borderRadius: 2 }}/>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: C.text, letterSpacing: "-0.04em" }}>Recetas</h1>
          </div>
          <p style={{ margin: 0, fontSize: 13, color: C.mute, paddingLeft: 14 }}>
            Define los ingredientes que se descuentan del stock al vender cada producto.
          </p>
        </div>
        <Btn variant="ghost" onClick={() => { setImportFile(null); setImportResult(null); setImportErr(null); setShowImport(true); }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          Importar recetas
        </Btn>
      </div>

      {/* TWO-PANEL LAYOUT */}
      <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "380px 1fr", gap: 16, alignItems: "start" }}>

        {/* ── LEFT PANEL: Product list ────────────────────────────────────── */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden", boxShadow: C.sh }}>

          {/* Search */}
          <div style={{ padding: "12px 14px", borderBottom: `1px solid ${C.border}`, display: "flex", gap: 8, alignItems: "center" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink: 0 }}>
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              value={searchQ}
              onChange={e => setSearchQ(e.target.value)}
              placeholder="Filtrar productos…"
              style={{ flex: 1, border: "none", background: "transparent", fontSize: 13, outline: "none" }}
            />
            {searchQ && (
              <button onClick={() => setSearchQ("")}
                style={{ background: "none", border: "none", color: C.mute, cursor: "pointer", fontSize: 15, padding: 0, lineHeight: 1 }}>✕</button>
            )}
          </div>

          {/* Product rows */}
          <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto" }}>
            {loadingProducts ? (
              <div style={{ padding: "40px 0", display: "flex", justifyContent: "center", alignItems: "center", gap: 8, color: C.mute }}>
                <Spinner size={16}/><span style={{ fontSize: 13 }}>Cargando…</span>
              </div>
            ) : filtered.length === 0 ? (
              <div style={{ padding: "40px 16px", textAlign: "center", color: C.mute, fontSize: 13 }}>
                {searchQ ? "Sin resultados para ese filtro." : "No hay productos."}
              </div>
            ) : (
              filtered.map(p => (
                <div
                  key={p.id}
                  className="rec-row"
                  onClick={() => selectProduct(p)}
                  style={{
                    padding: "11px 16px",
                    borderBottom: `1px solid ${C.border}`,
                    background: p.id === selectedId ? C.accentBg : "transparent",
                    borderLeft: p.id === selectedId ? `3px solid ${C.accent}` : "3px solid transparent",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{
                        fontWeight: p.id === selectedId ? 700 : 600,
                        fontSize: 13,
                        color: p.id === selectedId ? C.accent : C.text,
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                      }}>
                        {p.name}
                      </div>
                      {p.sku && (
                        <div style={{ fontSize: 11, color: C.mute, fontFamily: C.mono, marginTop: 1 }}>{p.sku}</div>
                      )}
                    </div>
                    {p.has_recipe ? (
                      <Badge color="accent">Con receta</Badge>
                    ) : (
                      <Badge color="gray">Sin receta</Badge>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Footer count */}
          {!loadingProducts && (
            <div style={{ padding: "8px 16px", borderTop: `1px solid ${C.border}`, fontSize: 11, color: C.mute, background: C.bg }}>
              {filtered.length} producto{filtered.length !== 1 ? "s" : ""}
              {" · "}
              {products.filter(p => p.has_recipe).length} con receta
            </div>
          )}
        </div>

        {/* ── RIGHT PANEL: Recipe editor ──────────────────────────────────── */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, boxShadow: C.sh, minHeight: 460 }}>

          {/* EMPTY STATE: nothing selected */}
          {selectedId === null && (
            <div style={{ padding: "80px 32px", textAlign: "center" }}>
              <div style={{ fontSize: 44, marginBottom: 14 }}>📖</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: C.text, marginBottom: 6 }}>
                Selecciona un producto
              </div>
              <div style={{ fontSize: 13, color: C.mute }}>
                Haz clic en un producto de la lista izquierda para ver o editar su receta.
              </div>
            </div>
          )}

          {/* LOADING */}
          {selectedId !== null && recipeLoading && (
            <div style={{ padding: "80px 32px", display: "flex", justifyContent: "center", alignItems: "center", gap: 10, color: C.mute }}>
              <Spinner size={20}/><span style={{ fontSize: 14 }}>Cargando receta…</span>
            </div>
          )}

          {/* PANEL CONTENT */}
          {showEditor && (
            <div>
              {/* Panel header */}
              <div style={{
                padding: "16px 22px", borderBottom: `1px solid ${C.border}`,
                display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12,
              }}>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>{selectedProduct?.name}</div>
                  <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>
                    {hasRecipe
                      ? `${recipeLines.length} ingrediente${recipeLines.length !== 1 ? "s" : ""} · ${recipeActive ? "Receta activa" : "Receta inactiva"}`
                      : "Sin receta configurada"}
                  </div>
                </div>
                {hasRecipe || creatingNew ? (
                  <Toggle on={recipeActive} onChange={setRecipeActive}/>
                ) : null}
              </div>

              {/* NO RECIPE + not creating */}
              {!hasRecipe && !creatingNew && (
                <div style={{ padding: "60px 32px", textAlign: "center" }}>
                  <div style={{ fontSize: 36, marginBottom: 12 }}>🍳</div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                    Este producto no tiene receta
                  </div>
                  <div style={{ fontSize: 13, color: C.mute, marginBottom: 20 }}>
                    Crea una receta para definir qué ingredientes se descuentan al vender este producto.
                  </div>
                  <Btn variant="primary" onClick={() => setCreatingNew(true)}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                    </svg>
                    Crear receta
                  </Btn>
                </div>
              )}

              {/* EDITOR (has recipe OR creating new) */}
              {editorVisible && (
                <div style={{ padding: "20px 22px", display: "grid", gap: 18 }}>

                  {/* Error */}
                  {recipeErr && (
                    <div style={{ padding: "10px 14px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: C.r, fontSize: 13, color: C.red, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span>{recipeErr}</span>
                      <button onClick={() => setRecipeErr(null)} style={{ background: "none", border: "none", color: C.red, cursor: "pointer", fontSize: 16, padding: 0 }}>✕</button>
                    </div>
                  )}

                  {/* Ingredient search */}
                  <div style={{ display: "grid", gap: 6 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                      Agregar ingrediente
                    </div>
                    <div style={{ position: "relative" }}>
                      <input
                        value={ingSearch}
                        onChange={e => searchIngredients(e.target.value)}
                        placeholder="Buscar producto o ingrediente…"
                        disabled={recipeSaving}
                        style={{
                          width: "100%", padding: "9px 12px",
                          border: `1px solid ${C.borderMd}`, borderRadius: C.r,
                          fontSize: 13, boxSizing: "border-box",
                        }}
                      />
                      {ingSearching && (
                        <div style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)" }}>
                          <Spinner/>
                        </div>
                      )}
                    </div>
                    {ingResults.length > 0 && (
                      <div style={{ border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", background: C.surface, boxShadow: C.shMd }}>
                        {ingResults.map(ing => (
                          <button key={ing.id}
                            onClick={() => addIngredient(ing)}
                            disabled={recipeSaving || recipeLines.some(l => l.ingredient_id === ing.id)}
                            style={{
                              display: "flex", width: "100%", alignItems: "center", justifyContent: "space-between",
                              padding: "9px 14px", background: "none", border: "none", cursor: "pointer",
                              fontSize: 13, textAlign: "left", gap: 12, borderBottom: `1px solid ${C.border}`,
                            }}>
                            <span style={{ fontWeight: 600 }}>{ing.name}</span>
                            <span style={{ fontSize: 11, color: C.mute, fontFamily: C.mono }}>{ing.sku ?? ""} · {ing.unit ?? "UN"}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Ingredient lines */}
                  {recipeLines.length > 0 ? (
                    <div style={{ display: "grid", gap: 4 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                        Ingredientes
                      </div>
                      <div style={{ border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden" }}>
                        {/* Header */}
                        <div style={{
                          display: "grid", gridTemplateColumns: "1fr 100px 90px 36px",
                          gap: 8, padding: "7px 12px",
                          background: C.bg, borderBottom: `1px solid ${C.border}`,
                          fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.04em",
                        }}>
                          <span>Ingrediente</span>
                          <span style={{ textAlign: "right" }}>Cantidad</span>
                          <span>Unidad</span>
                          <span/>
                        </div>
                        {recipeLines.map((l, i) => {
                          const familyUnits = l.ingredient_unit_family
                            ? units.filter(u => u.family === l.ingredient_unit_family)
                            : [];
                          return (
                          <div key={l.ingredient_id} style={{
                            display: "grid", gridTemplateColumns: "1fr 100px 90px 36px",
                            gap: 8, padding: "9px 12px", alignItems: "center",
                            borderBottom: i < recipeLines.length - 1 ? `1px solid ${C.border}` : "none",
                          }}>
                            <div>
                              <div style={{ fontSize: 13, fontWeight: 600 }}>{l.ingredient_name}</div>
                              <div style={{ fontSize: 11, color: C.mute, fontFamily: C.mono }}>
                                {l.ingredient_sku && `${l.ingredient_sku} · `}{l.ingredient_unit ?? "UN"}
                              </div>
                            </div>
                            <input
                              value={l.qty}
                              onChange={e => setRecipeLines(prev => prev.map((x, j) => j === i ? { ...x, qty: e.target.value } : x))}
                              inputMode="decimal"
                              disabled={recipeSaving}
                              style={{
                                padding: "5px 8px", border: `1px solid ${C.borderMd}`,
                                borderRadius: 4, fontSize: 13, textAlign: "right", width: "100%",
                              }}
                            />
                            {familyUnits.length > 1 ? (
                              <select
                                value={l.unit_id ?? ""}
                                onChange={e => {
                                  const uid = e.target.value ? Number(e.target.value) : null;
                                  const u = units.find(u => u.id === uid);
                                  setRecipeLines(prev => prev.map((x, j) => j === i ? { ...x, unit_id: uid, unit_code: u?.code ?? null } : x));
                                }}
                                disabled={recipeSaving}
                                style={{
                                  padding: "5px 6px", border: `1px solid ${C.borderMd}`,
                                  borderRadius: 4, fontSize: 12, width: "100%", background: C.surface,
                                }}
                              >
                                {familyUnits.map(u => (
                                  <option key={u.id} value={u.id}>{u.code}</option>
                                ))}
                              </select>
                            ) : (
                              <span style={{ fontSize: 12, color: C.mute, padding: "5px 6px" }}>
                                {l.unit_code ?? l.ingredient_unit ?? "UN"}
                              </span>
                            )}
                            <button onClick={() => setRecipeLines(prev => prev.filter((_, j) => j !== i))}
                              disabled={recipeSaving}
                              style={{ background: "none", border: "none", cursor: "pointer", color: C.red, fontSize: 18, padding: 4, display: "flex", alignItems: "center", justifyContent: "center" }}>
                              ✕
                            </button>
                          </div>
                          );
                        })}
                      </div>
                      <div style={{ fontSize: 11, color: C.mute }}>Cantidades por 1 unidad vendida del producto.</div>
                    </div>
                  ) : (
                    <div style={{ padding: "24px 16px", textAlign: "center", color: C.mute, fontSize: 13, border: `1px dashed ${C.border}`, borderRadius: C.r }}>
                      Busca ingredientes arriba para armar la receta.
                    </div>
                  )}

                  {/* Notes */}
                  <div style={{ display: "grid", gap: 5 }}>
                    <label style={{ fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                      Notas internas (opcional)
                    </label>
                    <input
                      value={recipeNotes}
                      onChange={e => setRecipeNotes(e.target.value)}
                      placeholder="Ej: Usar leche entera, café de tueste oscuro…"
                      disabled={recipeSaving}
                      style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 13 }}
                    />
                  </div>

                  {/* Toggle active */}
                  <div style={{ padding: "12px 14px", background: C.bg, borderRadius: C.r, display: "flex", alignItems: "center", gap: 10 }}>
                    <Toggle on={recipeActive} onChange={setRecipeActive}/>
                    <span style={{ fontSize: 13, fontWeight: 600, color: recipeActive ? C.text : C.mid }}>
                      Receta {recipeActive ? "activa" : "inactiva"}
                    </span>
                    <span style={{ fontSize: 12, color: C.mute }}>
                      {recipeActive
                        ? "— Los ingredientes se descontarán al vender este producto"
                        : "— No se descontarán ingredientes al vender"}
                    </span>
                  </div>

                  {/* Actions */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 4, borderTop: `1px solid ${C.border}` }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {hasRecipe && !confirmDeleteRecipe && (
                        <Btn variant="danger" onClick={() => setConfirmDeleteRecipe(true)} disabled={recipeSaving}>
                          Eliminar receta
                        </Btn>
                      )}
                      {hasRecipe && confirmDeleteRecipe && (
                        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: C.r }}>
                          <span style={{ fontSize: 12, fontWeight: 600, color: C.red }}>¿Eliminar esta receta?</span>
                          <Btn variant="danger" onClick={deleteRecipe} disabled={recipeSaving} size="sm">
                            {recipeSaving ? <><Spinner/>Eliminando…</> : "Sí, eliminar"}
                          </Btn>
                          <Btn variant="ghost" onClick={() => setConfirmDeleteRecipe(false)} disabled={recipeSaving} size="sm">
                            Cancelar
                          </Btn>
                        </div>
                      )}
                      {!hasRecipe && creatingNew && (
                        <Btn variant="ghost" onClick={() => { setCreatingNew(false); setRecipeLines([]); setIngSearch(""); setIngResults([]); setRecipeErr(null); }} disabled={recipeSaving}>
                          Cancelar
                        </Btn>
                      )}
                    </div>
                    <Btn
                      variant="primary"
                      onClick={saveRecipe}
                      disabled={recipeSaving || recipeLines.filter(l => Number(l.qty) > 0).length === 0}
                    >
                      {recipeSaving ? <><Spinner/>Guardando…</> : (hasRecipe ? "Guardar cambios" : "Crear receta")}
                    </Btn>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── MODAL: IMPORTAR RECETAS ──────────────────────────────────── */}
      {showImport && (
        <div className="bd-in" onClick={() => !importing && setShowImport(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
          <div className="m-in" onClick={e => e.stopPropagation()}
            style={{ background: C.surface, borderRadius: C.rMd, width: 600, maxWidth: "100%", boxShadow: C.shLg, overflow: "hidden" }}>

            {/* Header */}
            <div style={{ padding: "18px 22px", borderBottom: `1px solid ${C.border}` }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>Importar recetas (CSV)</div>
              <div style={{ fontSize: 13, color: C.mute, marginTop: 2 }}>Carga masiva de recetas: cada fila vincula un producto con un ingrediente</div>
            </div>

            {/* Body */}
            <div style={{ padding: "20px 22px", display: "grid", gap: 14 }}>
              {importErr && (
                <div style={{ padding: "10px 14px", background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 8, fontSize: 13, color: "#DC2626", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>{importErr}</span>
                  <button onClick={() => setImportErr(null)} style={{ background: "none", border: "none", color: "#DC2626", cursor: "pointer", fontSize: 16, padding: 0 }}>✕</button>
                </div>
              )}

              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <button className="xb" onClick={downloadSample}
                  style={{ background: "none", border: `1px solid ${C.accent}`, color: C.accent, borderRadius: 6,
                    padding: "6px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  Descargar ejemplo Excel
                </button>
                <span style={{ fontSize: 11, color: C.mute }}>Con ejemplos de pizza, sándwich y café</span>
              </div>

              <div style={{ display: "grid", gap: 5 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em" }}>Archivo CSV</label>
                <input type="file" accept=".csv,text/csv"
                  onChange={e => { setImportFile(e.target.files?.[0] ?? null); setImportResult(null); }}
                  style={{ padding: "9px 12px", border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 13, cursor: "pointer" }}
                  disabled={importing}
                />
                <div style={{ fontSize: 11, color: C.mute }}>Columnas: product_sku, product_name, ingredient_sku, ingredient_name, qty</div>
              </div>

              {importResult && (
                <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden" }}>
                  <div style={{ padding: "11px 16px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontWeight: 700, fontSize: 13 }}>Resultado</div>
                  <div style={{ padding: "14px 18px", display: "flex", gap: 28 }}>
                    {[
                      { l: "Creadas", v: importResult.created, c: C.green },
                      { l: "Actualizadas", v: importResult.updated, c: C.accent },
                    ].map(s => (
                      <div key={s.l} style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 26, fontWeight: 900, color: s.c, letterSpacing: "-0.04em" }}>{s.v}</div>
                        <div style={{ fontSize: 10.5, color: C.mute, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em" }}>{s.l}</div>
                      </div>
                    ))}
                  </div>
                  {importResult.errors?.length > 0 && (
                    <div style={{ borderTop: `1px solid ${C.border}` }}>
                      <div style={{ padding: "9px 16px", fontWeight: 600, fontSize: 12, color: "#DC2626", background: "#FEF2F2" }}>
                        Errores ({importResult.errors.length})
                      </div>
                      <div style={{ maxHeight: 200, overflowY: "auto" }}>
                        <div style={{ display: "grid", gridTemplateColumns: "64px 1fr", fontSize: 11.5, fontWeight: 700, color: C.mute, padding: "7px 16px", background: C.bg, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                          <div>Fila</div><div>Error</div>
                        </div>
                        {importResult.errors.map((x: any, idx: number) => (
                          <div key={idx} style={{ display: "grid", gridTemplateColumns: "64px 1fr", padding: "7px 16px", borderBottom: `1px solid ${C.border}`, fontSize: 12 }}>
                            <span style={{ fontFamily: "'JetBrains Mono', monospace", color: C.mute }}>{x.line ?? "-"}</span>
                            <span style={{ color: "#DC2626" }}>{x.error}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Footer */}
            <div style={{ padding: "14px 22px", borderTop: `1px solid ${C.border}`, display: "flex", justifyContent: "flex-end", gap: 8, background: C.bg }}>
              <Btn variant="secondary" onClick={() => !importing && setShowImport(false)} disabled={importing}>Cerrar</Btn>
              <Btn variant="primary" onClick={runImport} disabled={importing || !importFile}>
                {importing ? <><Spinner/>Importando…</> : "Importar recetas"}
              </Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
