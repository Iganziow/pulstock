"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, apiUpload } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Btn } from "@/components/ui";
import { extractErr } from "@/lib/format";
import { ProductListPanel } from "@/components/catalog/recetas/ProductListPanel";
import { RecipeEditor } from "@/components/catalog/recetas/RecipeEditor";
import { ImportRecipesModal } from "@/components/catalog/recetas/ImportRecipesModal";
import type { Product, UnitType, RecipeLine, Recipe } from "@/components/catalog/recetas/types";

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

  // Left panel -- product list
  const [products, setProducts]         = useState<Product[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [searchQ, setSearchQ]           = useState("");
  const [selectedId, setSelectedId]     = useState<number | null>(null);

  // Right panel -- recipe state
  const [recipe, setRecipe]             = useState<Recipe | null>(null);
  const [recipeLoading, setRecipeLoading] = useState(false);
  const [recipeLines, setRecipeLines]   = useState<RecipeLine[]>([]);
  const [recipeNotes, setRecipeNotes]   = useState("");
  const [recipeActive, setRecipeActive] = useState(true);
  const [recipeSaving, setRecipeSaving] = useState(false);
  const [recipeErr, setRecipeErr]       = useState<string | null>(null);
  const [creatingNew, setCreatingNew]   = useState(false);
  const [confirmDeleteRecipe, setConfirmDeleteRecipe] = useState(false);

  // Ingredient search
  const [ingSearch, setIngSearch]       = useState("");
  const [ingResults, setIngResults]     = useState<Product[]>([]);
  const [ingSearching, setIngSearching] = useState(false);
  const ingDebounceRef                  = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Units
  const [units, setUnits]               = useState<UnitType[]>([]);

  // Import
  const [showImport, setShowImport]     = useState(false);
  const [importFile, setImportFile]     = useState<File | null>(null);
  const [importResult, setImportResult] = useState<any>(null);
  const [importing, setImporting]       = useState(false);
  const [importErr, setImportErr]       = useState<string | null>(null);

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

  // ── Select product -> load recipe ───────────────────────────────────────────
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
      setProducts(prev => prev.map(x => x.id === selectedId ? { ...x, has_recipe: recipeActive } : x));
    } catch (e) {
      setRecipeErr(extractErr(e, "Error guardando receta"));
    } finally {
      setRecipeSaving(false);
    }
  };

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
      loadProducts();
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

        {/* LEFT PANEL: Product list */}
        <ProductListPanel
          products={products}
          filtered={filtered}
          loading={loadingProducts}
          searchQ={searchQ}
          setSearchQ={setSearchQ}
          selectedId={selectedId}
          onSelect={selectProduct}
        />

        {/* RIGHT PANEL: Recipe editor */}
        <RecipeEditor
          selectedProduct={selectedProduct}
          recipe={recipe}
          recipeLoading={recipeLoading}
          recipeLines={recipeLines}
          setRecipeLines={setRecipeLines}
          recipeNotes={recipeNotes}
          setRecipeNotes={setRecipeNotes}
          recipeActive={recipeActive}
          setRecipeActive={setRecipeActive}
          recipeSaving={recipeSaving}
          recipeErr={recipeErr}
          setRecipeErr={setRecipeErr}
          creatingNew={creatingNew}
          setCreatingNew={setCreatingNew}
          confirmDeleteRecipe={confirmDeleteRecipe}
          setConfirmDeleteRecipe={setConfirmDeleteRecipe}
          ingSearch={ingSearch}
          searchIngredients={searchIngredients}
          ingResults={ingResults}
          ingSearching={ingSearching}
          addIngredient={addIngredient}
          units={units}
          saveRecipe={saveRecipe}
          deleteRecipe={deleteRecipe}
        />
      </div>

      {/* MODAL: IMPORTAR RECETAS */}
      <ImportRecipesModal
        showImport={showImport}
        importing={importing}
        importFile={importFile}
        importResult={importResult}
        importErr={importErr}
        setImportFile={setImportFile}
        setImportResult={setImportResult}
        setImportErr={setImportErr}
        setShowImport={setShowImport}
        downloadSample={downloadSample}
        runImport={runImport}
      />
    </div>
  );
}
