"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { apiFetch, apiUpload } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { useIsMobile } from "@/hooks/useIsMobile";
import { formatCLP, extractErr } from "@/lib/format";
import { Btn, Spinner, Modal, Badge, Toggle, StatCard, ErrBox, FLabel, Hint, iS, tS, FL, G2 } from "@/components/ui";
import { BarcodeAssignModal } from "@/components/catalog/BarcodeAssignModal";
import { CategoryTree } from "@/components/catalog/CategoryTree";
import { CascadeSelect } from "@/components/catalog/CascadeSelect";
import type { Category, Barcode, Product } from "@/components/catalog/types";

export type { Category, Barcode, Product };

// ─── Helpers ──────────────────────────────────────────────────────────────────

function parseBarcodeCodes(input: string) {
  return input.split(",").map((s) => s.trim()).filter(Boolean);
}

// ─── Units ────────────────────────────────────────────────────────────────────

const UNITS = ["UN","KG","GR","LT","ML","MT","CM","CAJA","PAQ","DOC"] as const;
function normalizeUnit(u: string) { return ((u || "UN").trim().toUpperCase()) || "UN"; }
function unitOptions(current: string): string[] {
  const cur = normalizeUnit(current);
  return UNITS.includes(cur as any) ? [...UNITS] : [cur, ...UNITS];
}
const PAGE_SIZE = 50;

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function CatalogPage() {
  useGlobalStyles();
  const mob = useIsMobile();

  // Búsqueda y paginación
  const [q, setQ]                     = useState("");
  const [page, setPage]               = useState(1);
  const [totalCount, setTotalCount]   = useState(0);

  // Datos
  const [items, setItems]             = useState<Product[]>([]);
  const [loading, setLoading]         = useState(true);
  const [err, setErr]                 = useState<string | null>(null);
  const [success, setSuccess]         = useState<string | null>(null);
  const [categories, setCategories]   = useState<Category[]>([]);
  const [catErr, setCatErr]           = useState<string | null>(null);

  // Modales
  const [showCat, setShowCat]             = useState(false);   // quick-create inline
  const [showCatManager, setShowCatManager] = useState(false); // full tree manager
  const [showProd, setShowProd]           = useState(false);
  const [showEditProd, setShowEditProd]   = useState(false);
  const [showImport, setShowImport]       = useState(false);
  const [showBarcodeAssign, setShowBarcodeAssign] = useState(false);
  // Import CSV
  const [importFile, setImportFile]       = useState<File | null>(null);
  const [importResult, setImportResult]   = useState<any>(null);

  // Form: categoría
  const [catName, setCatName]   = useState("");
  const [catCode, setCatCode]   = useState("");
  const [catParentId, setCatParentId] = useState<number | "">("");

  // Form: producto (crear)
  const [pSku, setPSku]               = useState("");
  const [pName, setPName]             = useState("");
  const [pDesc, setPDesc]             = useState("");
  const [pUnit, setPUnit]             = useState("UN");
  const [pPrice, setPPrice]           = useState("0");
  const [pActive, setPActive]         = useState(true);
  const [pCategoryId, setPCategoryId] = useState<number | "">("");
  const [pBarcodes, setPBarcodes]     = useState("");
  const [pCost, setPCost]             = useState("0");
  const [pMinStock, setPMinStock]     = useState("0");
  const [pBrand, setPBrand]           = useState("");
  const [pImageUrl, setPImageUrl]     = useState("");
  const [pAllowNeg, setPAllowNeg]     = useState(false);

  // Form: producto (editar)
  const [editId, setEditId]           = useState<number | null>(null);
  const [eSku, setESku]               = useState("");
  const [eName, setEName]             = useState("");
  const [eDesc, setEDesc]             = useState("");
  const [eUnit, setEUnit]             = useState("UN");
  const [ePrice, setEPrice]           = useState("0");
  const [eActive, setEActive]         = useState(true);
  const [eCategoryId, setECategoryId] = useState<number | "">("");
  const [eBarcodes, setEBarcodes]     = useState("");
  const [eCost, setECost]             = useState("0");
  const [eMinStock, setEMinStock]     = useState("0");
  const [eBrand, setEBrand]           = useState("");
  const [eImageUrl, setEImageUrl]     = useState("");
  const [eAllowNeg, setEAllowNeg]     = useState(false);

  const [saving, setSaving] = useState(false);

  // ── Endpoint con paginación ──────────────────────────────────────────────

  const endpoint = useMemo(() => {
    const params = new URLSearchParams();
    const qq = q.trim();
    if (qq) params.set("q", qq);
    params.set("page", String(page));
    return `/catalog/products/?${params.toString()}`;
  }, [q, page]);

  // Reset página al cambiar búsqueda
  useEffect(() => { setPage(1); }, [q]);

  // Carga de productos — UN SOLO useEffect con debounce
  const load = useCallback(async (url: string) => {
    setLoading(true); setErr(null);
    try {
      const data = await apiFetch(url);
      const list = Array.isArray(data) ? data : (data?.results ?? []);
      setItems(list);
      setTotalCount(data?.count ?? list.length);
    } catch (e: any) {
      setErr(extractErr(e, "Error cargando cat\u00e1logo"));
      setItems([]); setTotalCount(0);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => load(endpoint), 350);
    return () => clearTimeout(t);
  }, [endpoint, load]);

  // Carga de categorías
  const loadCategories = useCallback(async () => {
    setCatErr(null);
    try {
      const data = await apiFetch("/catalog/categories/");
      const list = Array.isArray(data) ? data : (data?.results ?? []);
      list.sort((a: Category, b: Category) => a.name.localeCompare(b.name));
      setCategories(list);
    } catch (e: any) {
      setCatErr(extractErr(e, "Error cargando categor\u00edas")); setCategories([]);
    }
  }, []);
  useEffect(() => { loadCategories(); }, [loadCategories]);

  // Resets
  const resetCatForm  = () => { setCatName(""); setCatCode(""); setCatParentId(""); };
  const resetProdForm = () => {
    setPSku(""); setPName(""); setPDesc(""); setPUnit("UN");
    setPPrice("0"); setPActive(true); setPCategoryId(""); setPBarcodes("");
    setPCost("0"); setPMinStock("0"); setPBrand(""); setPImageUrl(""); setPAllowNeg(false);
  };
  const closeEditModal = () => { setShowEditProd(false); setEditId(null); };

  const openEditProduct = (p: Product) => {
    setEditId(p.id); setESku(p.sku ?? ""); setEName(p.name ?? "");
    setEDesc(p.description ?? ""); setEUnit(normalizeUnit(p.unit ?? "UN"));
    setEPrice(p.price ?? "0"); setEActive(!!p.is_active);
    setECategoryId(p.category?.id ?? "");
    setEBarcodes(p.barcodes?.map((b) => b.code).join(", ") ?? "");
    setECost(p.cost ?? "0"); setEMinStock(p.min_stock ?? "0");
    setEBrand(p.brand ?? ""); setEImageUrl(p.image_url ?? "");
    setEAllowNeg(!!p.allow_negative_stock);
    setShowEditProd(true);
  };

  // CRUD Categoría
  const createCategory = async () => {
    if (!catName.trim()) return;
    setSaving(true); setCatErr(null);
    try {
      const body: any = { name: catName.trim() };
      if (catCode.trim()) body.code = catCode.trim();
      if (catParentId !== "") body.parent_id = catParentId;
      const created = await apiFetch("/catalog/categories/", { method:"POST", body:JSON.stringify(body) });
      await loadCategories();
      if (created?.id) setPCategoryId(created.id);
      resetCatForm(); setShowCat(false);
    } catch (e: any) { setCatErr(extractErr(e, "Error creando categor\u00eda")); }
    finally { setSaving(false); }
  };

  // CRUD Producto — Crear
  const createProduct = async () => {
    const name = pName.trim();
    if (!name) { setErr("El nombre del producto es obligatorio."); return; }
    const price = parseFloat(pPrice);
    if (isNaN(price) || price < 0) { setErr("El precio debe ser un n\u00famero positivo."); return; }
    setSaving(true); setErr(null);
    try {
      const created: Product = await apiFetch("/catalog/products/", {
        method:"POST",
        body:JSON.stringify({
          name, sku:pSku.trim()||"", description:pDesc.trim()||"",
          unit:normalizeUnit(pUnit), price:pPrice||"0",
          is_active:pActive, category:pCategoryId===""?null:pCategoryId,
          barcode_codes:parseBarcodeCodes(pBarcodes),
          cost:pCost||"0", min_stock:pMinStock||"0",
          brand:pBrand.trim(), image_url:pImageUrl.trim(),
          allow_negative_stock:pAllowNeg,
        }),
      });
      setItems((prev) => {
        const next = [created,...prev.filter((x)=>x.id!==created.id)];
        next.sort((a,b)=>(a.name||"").localeCompare(b.name||"")); return next;
      });
      setTotalCount((c)=>c+1);
      resetProdForm(); setShowProd(false);
      setSuccess("Producto guardado correctamente"); setTimeout(()=>setSuccess(null),4000);
    } catch (e: any) { setErr(extractErr(e,"Error creando producto")); }
    finally { setSaving(false); }
  };

  // CRUD Producto — Editar
  const saveEditProduct = async () => {
    if (!editId) return;
    const name = eName.trim();
    if (!name) { setErr("El nombre del producto es obligatorio."); return; }
    const price = parseFloat(ePrice);
    if (isNaN(price) || price < 0) { setErr("El precio debe ser un n\u00famero positivo."); return; }
    setSaving(true); setErr(null);
    try {
      const updated: Product = await apiFetch(`/catalog/products/${editId}/`, {
        method:"PATCH",
        body:JSON.stringify({
          name, sku:eSku.trim()||"", description:eDesc.trim()||"",
          unit:normalizeUnit(eUnit), price:ePrice||"0",
          is_active:eActive, category:eCategoryId===""?null:eCategoryId,
          barcode_codes:parseBarcodeCodes(eBarcodes),
          cost:eCost||"0", min_stock:eMinStock||"0",
          brand:eBrand.trim(), image_url:eImageUrl.trim(),
          allow_negative_stock:eAllowNeg,
        }),
      });
      setItems((prev) => {
        const next = prev.map((x)=>(x.id===updated.id?updated:x));
        next.sort((a,b)=>(a.name||"").localeCompare(b.name||"")); return next;
      });
      closeEditModal();
      setSuccess("Producto guardado correctamente"); setTimeout(()=>setSuccess(null),4000);
    } catch (e: any) { setErr(extractErr(e,"Error guardando producto")); }
    finally { setSaving(false); }
  };

  // Toggle activo
  const toggleActive = async (p: Product) => {
    setSaving(true); setErr(null);
    try {
      const updated: Product = await apiFetch(`/catalog/products/${p.id}/`, {
        method:"PATCH", body:JSON.stringify({ is_active:!p.is_active }),
      });
      setItems((prev)=>prev.map((x)=>(x.id===updated.id?updated:x)));
      setSuccess("Producto actualizado"); setTimeout(()=>setSuccess(null),4000);
    } catch (e: any) { setErr(extractErr(e,"Error cambiando estado")); }
    finally { setSaving(false); }
  };

  // Import CSV
  const runImport = async () => {
    if (!importFile) return;
    setSaving(true); setErr(null); setImportResult(null);
    try {
      const fd = new FormData(); fd.append("file", importFile);
      const result = await apiUpload("/catalog/products/import-csv/", fd);
      setImportResult(result); setPage(1);
      await load("/catalog/products/?page=1");
    } catch (e: any) { setErr(extractErr(e,"Error importando CSV")); }
    finally { setSaving(false); }
  };

  // Download sample Excel
  const downloadSample = async () => {
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("access") : null;
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/catalog/products/import-sample/`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Error descargando archivo");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = "ejemplo_productos.xlsx";
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e: any) { setErr(extractErr(e, "Error descargando ejemplo")); }
  };

  const totalPages  = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const activeCount = items.filter((p) => p.is_active).length;
  const clearSearch = () => { setQ(""); setPage(1); };

  // ── RENDER ────────────────────────────────────────────────────────────────

  return (
    <div style={{ fontFamily:C.font, color:C.text, padding:mob?"16px 12px":"28px 32px", background:C.bg, minHeight:"100vh", display:"grid", gap:16, alignContent:"start" }}>

      {/* HEADER */}
      <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between", gap:16, flexWrap:"wrap" }}>
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:4 }}>
            <div style={{ width:4, height:26, background:C.accent, borderRadius:2 }}/>
            <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:C.text, letterSpacing:"-0.04em" }}>Cat\u00e1logo</h1>
          </div>
          <p style={{ margin:0, fontSize:13, color:C.mute, paddingLeft:14 }}>Busca por nombre, SKU o c\u00f3digo de barras</p>
        </div>

        <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
          <Btn variant="ghost" onClick={()=>{setImportFile(null);setImportResult(null);setShowImport(true);}} disabled={saving}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            Importar productos
          </Btn>
          <Btn variant="secondary" onClick={()=>setShowBarcodeAssign(true)} disabled={saving}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M3 5v14"/><path d="M8 5v14"/><path d="M12 5v14"/><path d="M17 5v14"/><path d="M21 5v14"/>
            </svg>
            Asignar Barcodes
          </Btn>
          <Btn variant="secondary" onClick={()=>{resetCatForm();setShowCat(true);}} disabled={saving}>+ Categor\u00eda</Btn>
          <Btn variant="ghost" onClick={()=>setShowCatManager(true)} disabled={saving}>Organizar</Btn>
          <Btn variant="primary" onClick={()=>{resetProdForm();setShowProd(true);}} disabled={saving}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            + Producto
          </Btn>
          <Btn variant="secondary" onClick={()=>load(endpoint)} disabled={saving}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
          </Btn>
        </div>
      </div>

      {/* STAT CARDS */}
      <div style={{ display:"grid", gridTemplateColumns:mob?"1fr 1fr":"repeat(auto-fit,minmax(148px,1fr))", gap:10 }}>
        <StatCard label="Total"      value={totalCount}               icon="\ud83d\udce6" color={C.accent} />
        <StatCard label="Activos"    value={activeCount}              icon="\u2705" color={C.green}  />
        <StatCard label="Inactivos"  value={totalCount-activeCount}   icon="\u23f8\ufe0f" color={C.amber}  />
        <StatCard label="Categor\u00edas" value={categories.length}        icon="\ud83d\uddc2\ufe0f" color={C.violet} />
      </div>

      {/* SEARCH */}
      <div style={{
        background:C.surface, border:`1px solid ${C.border}`,
        borderRadius:C.rMd, padding:"10px 14px",
        display:"flex", gap:10, alignItems:"center", boxShadow:C.sh, flexWrap:"wrap",
      }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink:0 }}>
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input
          value={q}
          onChange={(e)=>setQ(e.target.value)}
          onKeyDown={(e)=>{ if(e.key==="Enter"){ e.preventDefault(); setPage(1); load(endpoint); } }}
          placeholder="Ej: arroz, 1002521, 7802810050232\u2026"
          style={{ flex:1, minWidth:180, border:"none", background:"transparent", fontSize:14, outline:"none" }}
        />
        {q && (
          <button onClick={clearSearch} className="ib" style={{ background:"none", border:"none", color:C.mute, cursor:"pointer", fontSize:16, padding:"0 4px", lineHeight:1 }}>{"\u2715"}</button>
        )}
        <div style={{ width:1, height:20, background:C.border }}/>
        <Btn variant="secondary" size="sm" onClick={()=>{setPage(1);load(endpoint);}}>Buscar</Btn>
        <Btn variant="ghost"     size="sm" onClick={clearSearch}>Limpiar</Btn>
        <div style={{ fontSize:12, color:C.mute, whiteSpace:"nowrap" }}>
          Total: <b style={{ color:C.text }}>{totalCount}</b> {"\u00b7"} Categor\u00edas: <b style={{ color:C.text }}>{categories.length}</b>
          {catErr && <span style={{ marginLeft:8, color:C.red }}>({catErr})</span>}
        </div>
      </div>

      {/* SUCCESS */}
      {success && <div style={{padding:"10px 14px",borderRadius:C.r,background:C.greenBg,border:`1px solid ${C.greenBd}`,color:C.green,fontSize:13,fontWeight:600}}>{success}</div>}

      {/* ERROR */}
      {err && <ErrBox msg={err} onClose={()=>setErr(null)}/>}

      {/* LOADING */}
      {loading && (
        <div style={{ padding:"52px 0", display:"flex", alignItems:"center", justifyContent:"center", gap:10, color:C.mute }}>
          <Spinner size={16}/><span style={{ fontSize:13 }}>Cargando\u2026</span>
        </div>
      )}

      {/* TABLE */}
      {!loading && !err && (
        <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>
        <div style={{ overflowX:"auto" }}>
          {/* Header row */}
          <div style={{
            display:"grid",
            gridTemplateColumns:mob?"minmax(0,1.8fr) 90px 80px 100px":"110px minmax(0,1.8fr) 160px 120px minmax(0,1fr) 100px 170px",
            columnGap:mob?8:16,
            padding:mob?"11px 12px":"11px 20px", background:C.bg, borderBottom:`1px solid ${C.border}`,
            fontSize:10.5, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.08em",
          }}>
            {!mob && <div>SKU</div>}<div>Producto</div>{!mob && <div>Categor\u00eda</div>}
            <div style={{ textAlign:"right" }}>Precio</div>
            {!mob && <div>Barcodes</div>}<div style={{ textAlign:"center" }}>Activo</div>
            <div style={{ textAlign:"right" }}>Acciones</div>
          </div>

          {items.length === 0 ? (
            <div style={{ padding:"60px 24px", textAlign:"center" }}>
              <div style={{ fontSize:38, marginBottom:10 }}>{"\ud83d\udced"}</div>
              <div style={{ fontSize:15, fontWeight:700, color:C.text, marginBottom:6 }}>
                No hay productos para mostrar.
              </div>
              <div style={{ fontSize:13, color:C.mute }}>
                Si esperabas ver productos: revisa que tu usuario tenga <b>tenant</b> asignado.
              </div>
            </div>
          ) : (
            items.map((p, i) => (
              <div key={p.id} className="prow" style={{
                display:"grid",
                gridTemplateColumns:mob?"minmax(0,1.8fr) 90px 80px 100px":"110px minmax(0,1.8fr) 160px 120px minmax(0,1fr) 100px 170px",
                columnGap:mob?8:16,
                padding:mob?"12px 12px":"14px 20px",
                borderBottom:i<items.length-1?`1px solid ${C.border}`:"none",
                alignItems:"center",
              }}>
                {/* SKU */}
                {!mob && <div style={{ fontFamily:C.mono, fontSize:12, color:C.mid, fontWeight:500 }}>
                  {p.sku || <span style={{ color:C.mute }}>{"\u2014"}</span>}
                </div>}

                {/* Name */}
                <div style={{ minWidth:0 }}>
                  <div style={{ fontWeight:700, fontSize:mob?13:14, marginBottom:1, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{p.name}</div>
                  {!mob && p.description && <div style={{ fontSize:12, color:C.mute, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{p.description}</div>}
                  <div style={{ fontSize:11, color:C.mute, marginTop:2, fontFamily:C.mono }}>
                    {mob ? (p.sku || `ID:${p.id}`) : `ID: ${p.id} \u00b7 ${normalizeUnit(p.unit??"UN")}`}
                  </div>
                </div>

                {/* Category */}
                {!mob && <div>
                  {p.category
                    ? <span style={{ fontSize:12, fontWeight:500, color:C.mid, background:C.bg, border:`1px solid ${C.border}`, borderRadius:4, padding:"2px 8px" }}>{p.category.name}</span>
                    : <span style={{ color:C.mute, fontSize:12 }}>{"\u2014"}</span>
                  }
                </div>}

                {/* Price */}
                <div style={{ textAlign:"right", fontWeight:800, fontSize:mob?13:14, fontVariantNumeric:"tabular-nums", letterSpacing:"-0.01em" }}>
                  ${formatCLP(p.price)}
                </div>

                {/* Barcodes */}
                {!mob && <div style={{ fontSize:12, color:C.mid, fontFamily:C.mono, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", minWidth:0 }}>
                  {p.barcodes?.length ? p.barcodes.map((b)=>b.code).join(", ") : <span style={{ color:C.mute }}>{"\u2014"}</span>}
                </div>}

                {/* Status */}
                <div style={{ display:"flex", justifyContent:"center", gap:6, flexWrap:"wrap" }}>
                  <Badge color={p.is_active?"green":"orange"}>{p.is_active?"Activo":"Inactivo"}</Badge>
                </div>

                {/* Actions */}
                <div style={{ display:"flex", gap:6, justifyContent:"flex-end", flexShrink:0, ...(mob?{}:{opacity:0, transition:"opacity 0.13s ease"}) }} className={mob?undefined:"ra"}>
                  <Btn variant="secondary" size="sm" onClick={()=>openEditProduct(p)} disabled={saving}>Editar</Btn>
                  {!mob && <Btn variant={p.is_active?"danger":"success"} size="sm" onClick={()=>toggleActive(p)} disabled={saving}>
                    {p.is_active?"Desactivar":"Activar"}
                  </Btn>}
                </div>
              </div>
            ))
          )}
        </div>
        </div>
      )}

      {/* PAGINATION */}
      {!loading && totalPages > 1 && (
        <div style={{ display:"flex", gap:8, alignItems:"center", justifyContent:"center", padding:"4px 0" }}>
          <Btn variant="secondary" size="sm" disabled={page<=1||saving} onClick={()=>setPage((p)=>Math.max(1,p-1))}>{"\u2190 Anterior"}</Btn>
          <span style={{ fontSize:13, color:C.mid }}>P\u00e1gina <b style={{ color:C.text }}>{page}</b> de <b style={{ color:C.text }}>{totalPages}</b></span>
          <Btn variant="secondary" size="sm" disabled={page>=totalPages||saving} onClick={()=>setPage((p)=>Math.min(totalPages,p+1))}>{"Siguiente \u2192"}</Btn>
        </div>
      )}

      {/* ── MODAL: BARCODE ASSIGN ──────────────────────────────────────── */}
      {showBarcodeAssign && (
        <BarcodeAssignModal onClose={()=>{ setShowBarcodeAssign(false); load(endpoint); }} />
      )}

      {/* ── MODAL: IMPORT CSV ──────────────────────────────────────────── */}
      {showImport && (
        <Modal onClose={()=>!saving&&setShowImport(false)} width={600} accentColor={C.teal}
          title="Importar productos"
          subtitle="Sube un archivo CSV o Excel (.xls, .xlsx) con tus productos"
          footer={<>
            <Btn variant="ghost" onClick={()=>!saving&&setShowImport(false)} disabled={saving}>Cerrar</Btn>
            <Btn variant="primary" onClick={runImport} disabled={saving||!importFile}>
              {saving?<><Spinner/>Importando\u2026</>:"Importar"}
            </Btn>
          </>}
        >
          <div style={{ display:"grid", gap:14 }}>
            <div style={{ display:"flex", gap:8, alignItems:"center" }}>
              <button onClick={()=>downloadSample()}
                style={{ background:"none", border:`1px solid ${C.teal}`, color:C.teal, borderRadius:C.r,
                  padding:"6px 14px", fontSize:12, fontWeight:700, cursor:"pointer", display:"flex", alignItems:"center", gap:6 }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Descargar ejemplo Excel
              </button>
              <span style={{ fontSize:11, color:C.mute }}>Incluye instrucciones y datos de ejemplo</span>
            </div>
            <div style={FL}>
              <FLabel>Archivo CSV o Excel</FLabel>
              <input type="file" accept=".csv,.xls,.xlsx,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(e)=>{ setImportFile(e.target.files?.[0]??null); setImportResult(null); }}
                style={{ ...iS, paddingTop:9, height:"auto", cursor:"pointer" }} disabled={saving}
              />
              <Hint>Sube directamente tu Excel o CSV. Los headers en espa\u00f1ol se mapean autom\u00e1ticamente.</Hint>
            </div>

            {importResult && (
              <div style={{ border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden" }}>
                <div style={{ padding:"11px 16px", background:C.bg, borderBottom:`1px solid ${C.border}`, fontWeight:700, fontSize:13 }}>Resultado</div>
                <div style={{ padding:"14px 18px", display:"flex", gap:28 }}>
                  {[
                    { l:"Creados",      v:importResult.created, c:C.green },
                    { l:"Actualizados", v:importResult.updated, c:C.accent},
                    { l:"Omitidos",     v:importResult.skipped, c:C.amber },
                  ].map((s)=>(
                    <div key={s.l} style={{ textAlign:"center" }}>
                      <div style={{ fontSize:26, fontWeight:900, color:s.c, letterSpacing:"-0.04em" }}>{s.v}</div>
                      <div style={{ fontSize:10.5, color:C.mute, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.07em" }}>{s.l}</div>
                    </div>
                  ))}
                </div>
                {importResult.errors?.length > 0 && (
                  <div style={{ borderTop:`1px solid ${C.border}` }}>
                    <div style={{ padding:"9px 16px", fontWeight:600, fontSize:12, color:C.red, background:C.redBg }}>
                      Errores ({importResult.errors.length})
                    </div>
                    <div style={{ maxHeight:200, overflowY:"auto" }}>
                      <div style={{ display:"grid", gridTemplateColumns:"64px 1fr", fontSize:11.5, fontWeight:700, color:C.mute, padding:"7px 16px", background:C.bg, textTransform:"uppercase", letterSpacing:"0.06em" }}>
                        <div>Fila</div><div>Error</div>
                      </div>
                      {importResult.errors.map((x: any, idx: number) => (
                        <div key={idx} style={{ display:"grid", gridTemplateColumns:"64px 1fr", padding:"7px 16px", borderBottom:`1px solid ${C.border}`, fontSize:12 }}>
                          <span style={{ fontFamily:C.mono, color:C.mute }}>{x.line??"-"}</span>
                          <span style={{ color:C.red }}>{x.error}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* ── MODAL: CATEGOR\u00cdA ──────────────────────────────────────────── */}
      {showCat && (
        <Modal onClose={()=>!saving&&setShowCat(false)} width={420} accentColor={C.violet}
          title="Nueva categor\u00eda"
          footer={<>
            <Btn variant="ghost" onClick={()=>!saving&&setShowCat(false)} disabled={saving}>Cancelar</Btn>
            <Btn variant="primary" onClick={createCategory} disabled={saving||!catName.trim()}>
              {saving?<><Spinner/>Creando\u2026</>:"Crear"}
            </Btn>
          </>}
        >
          <div style={{ display:"grid", gap:14 }}>
            <div style={FL}>
              <FLabel>Categor\u00eda padre (opcional)</FLabel>
              <select value={catParentId} onChange={(e)=>setCatParentId(e.target.value?Number(e.target.value):"")} style={iS} disabled={saving}>
                <option value="">Nivel principal (ra\u00edz)</option>
                {categories.filter(c=>!c.parent_id).map(c=>(
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              <span style={{ fontSize:11, color:C.mute, marginTop:2 }}>Deja vac\u00edo para crear una categor\u00eda principal</span>
            </div>
            <div style={FL}>
              <FLabel req>Nombre</FLabel>
              <input value={catName} onChange={(e)=>setCatName(e.target.value)}
                placeholder="Ej: Abarrotes" style={iS} disabled={saving} autoFocus/>
            </div>
            <div style={FL}>
              <FLabel>C\u00f3digo (opcional)</FLabel>
              <input value={catCode} onChange={(e)=>setCatCode(e.target.value)}
                placeholder="Ej: ABAR" style={{ ...iS, fontFamily:C.mono }} disabled={saving}/>
            </div>
            {catErr && <ErrBox msg={catErr} onClose={()=>setCatErr(null)}/>}
          </div>
        </Modal>
      )}

      {/* ── MODAL: ADMINISTRAR CATEGOR\u00cdAS (\u00c1RBOL) ─────────────────────── */}
      {showCatManager && (
        <Modal onClose={()=>setShowCatManager(false)} width={560} accentColor={C.violet}
          title="Administrar categor\u00edas"
          subtitle="Organiza tu cat\u00e1logo en categor\u00edas y subcategor\u00edas"
          footer={<Btn variant="ghost" onClick={()=>setShowCatManager(false)}>Cerrar</Btn>}
        >
          <CategoryTree
            categories={categories}
            onRefresh={loadCategories}
          />
        </Modal>
      )}

      {/* ── MODAL: PRODUCTO (CREAR) ────────────────────────────────────── */}
      {showProd && (
        <Modal onClose={()=>!saving&&setShowProd(false)} width={700}
          title="Nuevo producto"
          subtitle="Crea un producto y opcionalmente define barcodes."
          footer={<>
            <Btn variant="ghost" onClick={()=>!saving&&setShowProd(false)} disabled={saving}>Cancelar</Btn>
            <Btn variant="primary" onClick={createProduct} disabled={saving||!pName.trim()}>
              {saving?<><Spinner/>Creando\u2026</>:"Crear"}
            </Btn>
          </>}
        >
          <div style={{ display:"grid", gap:14 }}>
            <div style={G2}>
              <div style={FL}>
                <FLabel req>Nombre</FLabel>
                <input value={pName} onChange={(e)=>setPName(e.target.value)}
                  placeholder="Ej: Arroz 1kg" style={iS} disabled={saving} autoFocus/>
              </div>
              <div style={FL}>
                <FLabel>SKU</FLabel>
                <input value={pSku} onChange={(e)=>setPSku(e.target.value)}
                  placeholder="Ej: 1002521" style={{ ...iS, fontFamily:C.mono }} disabled={saving}/>
              </div>
            </div>

            <div style={FL}>
              <FLabel>Descripci\u00f3n</FLabel>
              <textarea value={pDesc} onChange={(e)=>setPDesc(e.target.value)}
                placeholder="Descripci\u00f3n (opcional)" style={tS} disabled={saving}/>
            </div>

            <div style={G2}>
              <div style={FL}>
                <FLabel>Unidad</FLabel>
                <select value={normalizeUnit(pUnit)} onChange={(e)=>setPUnit(e.target.value)} style={iS} disabled={saving}>
                  {unitOptions(pUnit).map((u)=><option key={u} value={u}>{u}</option>)}
                </select>
              </div>
              <div style={FL}>
                <FLabel req>Precio venta</FLabel>
                <input value={pPrice} onChange={(e)=>setPPrice(e.target.value)}
                  placeholder="1990" style={iS} disabled={saving} inputMode="decimal"/>
              </div>
            </div>

            <div style={G2}>
              <div style={FL}>
                <FLabel>Costo compra</FLabel>
                <input value={pCost} onChange={(e)=>setPCost(e.target.value)}
                  placeholder="0" style={iS} disabled={saving} inputMode="decimal"/>
                <Hint>Costo inicial. Se actualiza con compras.</Hint>
              </div>
              <div style={FL}>
                <FLabel>Stock m\u00ednimo</FLabel>
                <input value={pMinStock} onChange={(e)=>setPMinStock(e.target.value)}
                  placeholder="0" style={iS} disabled={saving} inputMode="decimal"/>
                <Hint>Alerta cuando baje de este nivel.</Hint>
              </div>
            </div>

            <div style={G2}>
              <div style={FL}>
                <FLabel>Marca</FLabel>
                <input value={pBrand} onChange={(e)=>setPBrand(e.target.value)}
                  placeholder="Ej: Col\u00fan, Polpaico\u2026" style={iS} disabled={saving}/>
              </div>
              <div style={FL}>
                <FLabel>Categor\u00eda</FLabel>
                <CascadeSelect categories={categories} value={pCategoryId} onChange={setPCategoryId} disabled={saving} />
              </div>
            </div>

            <div style={FL}>
              <FLabel>URL de imagen</FLabel>
              <input value={pImageUrl} onChange={(e)=>setPImageUrl(e.target.value)}
                placeholder="https://ejemplo.com/foto.jpg" style={iS} disabled={saving}/>
            </div>

            <label style={{ display:"flex", alignItems:"center", gap:12, cursor:"pointer", userSelect:"none" }}>
              <Toggle on={pActive} onChange={setPActive}/>
              <span style={{ fontSize:13, fontWeight:600, color:pActive?C.text:C.mid }}>Activo</span>
              <Badge color={pActive?"green":"gray"}>{pActive?"Visible":"Oculto"}</Badge>
            </label>

            <label style={{ display:"flex", alignItems:"center", gap:12, cursor:"pointer", userSelect:"none" }}>
              <Toggle on={pAllowNeg} onChange={setPAllowNeg}/>
              <span style={{ fontSize:13, fontWeight:600, color:pAllowNeg?C.amber:C.mid }}>Permitir stock negativo</span>
              {pAllowNeg && <Badge color="amber">Venta sin stock</Badge>}
            </label>

            <div style={FL}>
              <FLabel>Barcodes</FLabel>
              <input value={pBarcodes} onChange={(e)=>setPBarcodes(e.target.value)}
                placeholder="7802810050232, 123123\u2026" style={{ ...iS, fontFamily:C.mono }} disabled={saving}/>
              <Hint>Separados por coma. Guardar crea la lista.</Hint>
            </div>
          </div>
        </Modal>
      )}

      {/* ── MODAL: PRODUCTO (EDITAR) ───────────────────────────────────── */}
      {showEditProd && (
        <Modal onClose={()=>!saving&&closeEditModal()} width={700} accentColor={C.amber}
          title={<>Editar producto <span style={{ fontFamily:C.mono, fontSize:12, fontWeight:400, color:C.mute }}>ID: {editId}</span></>}
          subtitle="Actualiza los campos del producto."
          footer={<>
            <Btn variant="ghost" onClick={()=>!saving&&closeEditModal()} disabled={saving}>Cancelar</Btn>
            <Btn variant="primary" onClick={saveEditProduct} disabled={saving||!eName.trim()}>
              {saving?<><Spinner/>Guardando\u2026</>:"Guardar"}
            </Btn>
          </>}
        >
          <div style={{ display:"grid", gap:14 }}>
            <div style={G2}>
              <div style={FL}>
                <FLabel>SKU</FLabel>
                <input value={eSku} onChange={(e)=>setESku(e.target.value)} style={{ ...iS, fontFamily:C.mono }} disabled={saving}/>
              </div>
              <div style={FL}>
                <FLabel req>Nombre</FLabel>
                <input value={eName} onChange={(e)=>setEName(e.target.value)} style={iS} disabled={saving} autoFocus/>
              </div>
            </div>

            <div style={FL}>
              <FLabel>Descripci\u00f3n</FLabel>
              <textarea value={eDesc} onChange={(e)=>setEDesc(e.target.value)} style={tS} disabled={saving}/>
            </div>

            <div style={G2}>
              <div style={FL}>
                <FLabel>Unidad</FLabel>
                <select value={normalizeUnit(eUnit)} onChange={(e)=>setEUnit(e.target.value)} style={iS} disabled={saving}>
                  {unitOptions(eUnit).map((u)=><option key={u} value={u}>{u}</option>)}
                </select>
              </div>
              <div style={FL}>
                <FLabel req>Precio venta</FLabel>
                <input value={ePrice} onChange={(e)=>setEPrice(e.target.value)} style={iS} disabled={saving} inputMode="decimal"/>
              </div>
            </div>

            <div style={G2}>
              <div style={FL}>
                <FLabel>Costo compra</FLabel>
                <input value={eCost} onChange={(e)=>setECost(e.target.value)}
                  placeholder="0" style={iS} disabled={saving} inputMode="decimal"/>
                <Hint>Se actualiza autom\u00e1ticamente con compras.</Hint>
              </div>
              <div style={FL}>
                <FLabel>Stock m\u00ednimo</FLabel>
                <input value={eMinStock} onChange={(e)=>setEMinStock(e.target.value)}
                  placeholder="0" style={iS} disabled={saving} inputMode="decimal"/>
                <Hint>Alerta cuando baje de este nivel.</Hint>
              </div>
            </div>

            <div style={G2}>
              <div style={FL}>
                <FLabel>Marca</FLabel>
                <input value={eBrand} onChange={(e)=>setEBrand(e.target.value)}
                  placeholder="Ej: Col\u00fan, Polpaico\u2026" style={iS} disabled={saving}/>
              </div>
              <div style={FL}>
                <FLabel>Categor\u00eda</FLabel>
                <CascadeSelect categories={categories} value={eCategoryId} onChange={setECategoryId} disabled={saving} />
              </div>
            </div>

            <div style={FL}>
              <FLabel>URL de imagen</FLabel>
              <input value={eImageUrl} onChange={(e)=>setEImageUrl(e.target.value)}
                placeholder="https://ejemplo.com/foto.jpg" style={iS} disabled={saving}/>
            </div>

            <label style={{ display:"flex", alignItems:"center", gap:12, cursor:"pointer", userSelect:"none" }}>
              <Toggle on={eActive} onChange={setEActive}/>
              <span style={{ fontSize:13, fontWeight:600, color:eActive?C.text:C.mid }}>Activo</span>
              <Badge color={eActive?"green":"gray"}>{eActive?"Visible":"Oculto"}</Badge>
            </label>

            <label style={{ display:"flex", alignItems:"center", gap:12, cursor:"pointer", userSelect:"none" }}>
              <Toggle on={eAllowNeg} onChange={setEAllowNeg}/>
              <span style={{ fontSize:13, fontWeight:600, color:eAllowNeg?C.amber:C.mid }}>Permitir stock negativo</span>
              {eAllowNeg && <Badge color="amber">Venta sin stock</Badge>}
            </label>

            <div style={FL}>
              <FLabel>Barcodes</FLabel>
              <input value={eBarcodes} onChange={(e)=>setEBarcodes(e.target.value)}
                placeholder="7802810050232, 123123\u2026" style={{ ...iS, fontFamily:C.mono }} disabled={saving}/>
              <Hint>Guardar reemplaza la lista completa.</Hint>
            </div>
          </div>
        </Modal>
      )}

    </div>
  );
}
