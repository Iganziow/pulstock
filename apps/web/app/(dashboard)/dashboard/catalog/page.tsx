"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { apiFetch, apiUpload } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";

// ─── Responsive hook ─────────────────────────────────────────────────────────

function useIsMobile(){const[m,setM]=useState(false);useEffect(()=>{const fn=()=>setM(window.innerWidth<768);fn();window.addEventListener("resize",fn);return()=>window.removeEventListener("resize",fn);},[]);return m;}

// ─── Types ────────────────────────────────────────────────────────────────────

type Category = { id: number; name: string; code?: string | null; parent_id?: number | null; parent_name?: string | null;  is_active: boolean;  };
type Barcode  = { id: number; code: string };
type Product  = {
  id: number; sku?: string | null; name: string;
  description?: string | null; unit?: string | null;
  price: string; is_active: boolean;
  category?: Category | null; barcodes?: Barcode[];
  cost?: string | null; min_stock?: string | null;
  brand?: string | null; image_url?: string | null;
  allow_negative_stock?: boolean;
  has_recipe?: boolean;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatCLP(value: string | number) {
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("es-CL");
}
function parseBarcodeCodes(input: string) {
  return input.split(",").map((s) => s.trim()).filter(Boolean);
}
function extractErr(e: any, fallback: string) {
  if (e?.data) {
    try { return typeof e.data === "string" ? e.data : JSON.stringify(e.data); }
    catch { return fallback; }
  }
  return e?.message ?? fallback;
}
// apiUpload imported from @/lib/api (handles 401 refresh automatically)

// ─── Units ────────────────────────────────────────────────────────────────────

const UNITS = ["UN","KG","GR","LT","ML","MT","CM","CAJA","PAQ","DOC"] as const;
function normalizeUnit(u: string) { return ((u || "UN").trim().toUpperCase()) || "UN"; }
function unitOptions(current: string): string[] {
  const cur = normalizeUnit(current);
  return UNITS.includes(cur as any) ? [...UNITS] : [cur, ...UNITS];
}
const PAGE_SIZE = 50;

// ─── Micro-components ─────────────────────────────────────────────────────────

function Spinner({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
      style={{ animation:"spin 0.7s linear infinite", display:"block", flexShrink:0 }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
    </svg>
  );
}

type BadgeColor = "green"|"orange"|"gray"|"amber";
function Badge({ color, children }: { color: BadgeColor; children: React.ReactNode }) {
  const m: Record<BadgeColor,{bg:string;bd:string;c:string}> = {
    green:  { bg:C.greenBg, bd:C.greenBd, c:C.green },
    orange: { bg:C.redBg,   bd:C.redBd,   c:C.red   },
    gray:   { bg:"#F4F4F5", bd:C.border,  c:C.mid   },
    amber:  { bg:C.amberBg, bd:C.amberBd, c:C.amber },
  };
  const s = m[color];
  return (
    <span style={{ display:"inline-flex", alignItems:"center", gap:5,
      padding:"3px 9px", borderRadius:99, fontSize:11, fontWeight:600,
      letterSpacing:"0.02em", border:`1px solid ${s.bd}`, background:s.bg, color:s.c }}>
      <span style={{ width:5, height:5, borderRadius:"50%", background:s.c, flexShrink:0 }}/>
      {children}
    </span>
  );
}

type BtnV = "primary"|"secondary"|"ghost"|"danger"|"success";
function Btn({ children, onClick, variant="secondary", disabled, size="md" }: {
  children: React.ReactNode; onClick?: ()=>void;
  variant?: BtnV; disabled?: boolean; size?: "sm"|"md";
}) {
  const vs: Record<BtnV, React.CSSProperties> = {
    primary:   { background:C.accent,  color:"#fff",  border:`1px solid ${C.accent}`   },
    secondary: { background:C.surface, color:C.text,  border:`1px solid ${C.borderMd}` },
    ghost:     { background:"transparent", color:C.mid, border:"1px solid transparent" },
    danger:    { background:C.redBg,   color:C.red,   border:`1px solid ${C.redBd}`    },
    success:   { background:C.greenBg, color:C.green, border:`1px solid ${C.greenBd}`  },
  };
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="xb" style={{
      ...vs[variant], display:"inline-flex", alignItems:"center", justifyContent:"center", gap:6,
      height:size==="sm"?32:38, padding:size==="sm"?"0 12px":"0 16px",
      borderRadius:C.r, fontSize:size==="sm"?12:13, fontWeight:600,
      letterSpacing:"0.01em", whiteSpace:"nowrap",
    }}>
      {children}
    </button>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v:boolean)=>void }) {
  return (
    <div onClick={()=>onChange(!on)} style={{
      width:38, height:22, borderRadius:11,
      background:on?C.accent:C.borderMd,
      position:"relative", transition:C.ease, cursor:"pointer", flexShrink:0,
    }}>
      <div style={{
        width:16, height:16, borderRadius:"50%", background:"#fff",
        position:"absolute", top:3, left:on?19:3,
        transition:C.ease, boxShadow:"0 1px 3px rgba(0,0,0,0.22)",
      }}/>
    </div>
  );
}

function StatCard({ label, value, icon, color }: { label:string; value:React.ReactNode; icon:string; color:string }) {
  return (
    <div className="sc" style={{
      background:C.surface, border:`1px solid ${C.border}`,
      borderRadius:C.rMd, padding:"13px 16px",
      display:"flex", alignItems:"center", gap:13, boxShadow:C.sh,
    }}>
      <div style={{
        width:38, height:38, borderRadius:C.r, flexShrink:0,
        background:`${color}18`, border:`1px solid ${color}28`,
        display:"flex", alignItems:"center", justifyContent:"center", fontSize:18,
      }}>{icon}</div>
      <div>
        <div style={{ fontSize:10, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.07em" }}>{label}</div>
        <div style={{ fontSize:22, fontWeight:800, color:C.text, lineHeight:1.15, marginTop:2, letterSpacing:"-0.03em" }}>{value}</div>
      </div>
    </div>
  );
}

function ErrBox({ msg, onClose }: { msg:string; onClose:()=>void }) {
  return (
    <div style={{
      display:"flex", alignItems:"flex-start", gap:10,
      padding:"11px 14px", borderRadius:C.r,
      border:`1px solid ${C.redBd}`, background:C.redBg,
      color:C.red, fontSize:13, fontWeight:500,
    }}>
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2.5" strokeLinecap="round" style={{ marginTop:1, flexShrink:0 }}>
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      <span style={{ flex:1 }}>{msg}</span>
      <button onClick={onClose} className="ib" style={{
        background:"none", border:"none", color:C.red, padding:0, fontSize:16, cursor:"pointer", lineHeight:1,
      }}>✕</button>
    </div>
  );
}

// ─── Modal ────────────────────────────────────────────────────────────────────

function Modal({ onClose, width=560, accentColor, title, subtitle, footer, children }: {
  onClose:()=>void; width?:number; accentColor?:string;
  title:React.ReactNode; subtitle?:React.ReactNode;
  footer:React.ReactNode; children:React.ReactNode;
}) {
  return (
    <div className="bd-in" onClick={onClose} style={{
      position:"fixed", inset:0, zIndex:60,
      background:"rgba(12,12,20,0.5)", backdropFilter:"blur(3px)",
      display:"grid", placeItems:"center", padding:16,
    }}>
      <div className="m-in" onClick={(e)=>e.stopPropagation()} style={{
        width:`min(${width}px, 96vw)`,
        background:C.surface, borderRadius:C.rLg,
        border:`1px solid ${C.border}`, boxShadow:C.shLg,
        overflow:"hidden", display:"flex", flexDirection:"column", maxHeight:"92vh",
      }}>
        <div style={{ height:3, background:accentColor||C.accent, flexShrink:0 }}/>
        <div style={{
          padding:"18px 22px 15px", borderBottom:`1px solid ${C.border}`,
          display:"flex", justifyContent:"space-between", alignItems:"flex-start", gap:12, flexShrink:0,
        }}>
          <div>
            <div style={{ fontSize:15, fontWeight:700, color:C.text, letterSpacing:"-0.01em" }}>{title}</div>
            {subtitle && <div style={{ fontSize:12, color:C.mute, marginTop:3 }}>{subtitle}</div>}
          </div>
          <button onClick={onClose} className="ib" style={{
            width:30, height:30, borderRadius:C.r, border:`1px solid ${C.border}`,
            background:C.surface, color:C.mid, fontSize:14,
            display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0,
          }}>✕</button>
        </div>
        <div style={{ padding:"20px 22px", overflowY:"auto", flex:1 }}>{children}</div>
        <div style={{
          padding:"13px 22px", borderTop:`1px solid ${C.border}`,
          background:C.bg, display:"flex", justifyContent:"flex-end", gap:8, flexShrink:0,
        }}>{footer}</div>
      </div>
    </div>
  );
}

// ─── Shared form styles ───────────────────────────────────────────────────────

const iS: React.CSSProperties = {
  width:"100%", height:38, padding:"0 12px",
  border:`1px solid ${C.border}`, borderRadius:C.r,
  background:C.surface, fontSize:14, transition:C.ease,
};
const tS: React.CSSProperties = { ...iS, height:"auto", minHeight:90, padding:"10px 12px", resize:"vertical", lineHeight:1.55 };
const FL: React.CSSProperties = { display:"flex", flexDirection:"column", gap:5 };
const G2: React.CSSProperties = { display:"grid", gridTemplateColumns:"1fr 1fr", gap:14 };

function FLabel({ children, req }: { children:React.ReactNode; req?:boolean }) {
  return (
    <label style={{ fontSize:11, fontWeight:700, color:C.mid, letterSpacing:"0.06em", textTransform:"uppercase" }}>
      {children}{req && <span style={{ color:C.accent, marginLeft:2 }}>*</span>}
    </label>
  );
}
function Hint({ children }: { children:React.ReactNode }) {
  return <span style={{ fontSize:11.5, color:C.mute }}>{children}</span>;
}

// =============================================================================
// BARCODE ASSIGN MODAL
// =============================================================================

type NoBarcodeProduct = { id: number; name: string; sku: string | null; category__name: string | null };

function BarcodeAssignModal({ onClose }: { onClose: () => void }) {
  const [products, setProducts] = useState<NoBarcodeProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [assigning, setAssigning] = useState(false);
  const [assigned, setAssigned] = useState(0);
  const [filterQ, setFilterQ] = useState("");
  const inputRef = useCallback((el: HTMLInputElement | null) => { el?.focus(); }, []);

  const fetchProducts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page_size: "200" });
      if (filterQ.trim()) params.set("q", filterQ.trim());
      const res = await apiFetch(`/catalog/products/without-barcode/?${params}`);
      setProducts(res.results ?? res);
      setSelectedIdx(0);
    } catch { /* silent */ }
    setLoading(false);
  }, [filterQ]);

  useEffect(() => { fetchProducts(); }, [fetchProducts]);

  const selected = products[selectedIdx] ?? null;

  async function handleAssign() {
    if (!selected || !code.trim()) return;
    setAssigning(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await apiFetch(`/catalog/products/${selected.id}/assign-barcode/`, {
        method: "POST",
        body: JSON.stringify({ code: code.trim() }),
        headers: { "Content-Type": "application/json" },
      });
      setAssigned(prev => prev + 1);
      setSuccessMsg(`✓ ${code.trim()} → ${selected.name}`);
      setCode("");
      // Remove from list and advance
      setProducts(prev => {
        const next = prev.filter((_, i) => i !== selectedIdx);
        if (selectedIdx >= next.length && next.length > 0) setSelectedIdx(next.length - 1);
        return next;
      });
      // Re-focus input
      setTimeout(() => { document.getElementById("bc-scan-input")?.focus(); }, 50);
    } catch (e: any) {
      const detail = e?.data?.detail || e?.message || "Error al asignar barcode";
      setError(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    setAssigning(false);
  }

  function handleSkip() {
    setSelectedIdx(prev => (prev + 1 < products.length ? prev + 1 : 0));
    setCode("");
    setError(null);
    document.getElementById("bc-scan-input")?.focus();
  }

  return (
    <div className="bd-in" onClick={onClose} style={{
      position: "fixed", inset: 0, zIndex: 60,
      background: "rgba(12,12,20,0.5)", backdropFilter: "blur(3px)",
      display: "grid", placeItems: "center", padding: 16,
    }}>
      <div className="m-in" onClick={e => e.stopPropagation()} style={{
        width: "min(780px, 96vw)", background: C.surface, borderRadius: C.rLg,
        border: `1px solid ${C.border}`, boxShadow: C.shLg,
        overflow: "hidden", display: "flex", flexDirection: "column", maxHeight: "92vh",
      }}>
        <div style={{ height: 3, background: C.violet, flexShrink: 0 }} />

        {/* Header */}
        <div style={{
          padding: "18px 22px 15px", borderBottom: `1px solid ${C.border}`,
          display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexShrink: 0,
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>Asignar Barcodes</div>
            <div style={{ fontSize: 12, color: C.mute, marginTop: 3 }}>
              Escanea con pistola o escribe el código. {products.length} productos sin barcode.
              {assigned > 0 && <span style={{ color: C.green, fontWeight: 600, marginLeft: 6 }}>{assigned} asignados</span>}
            </div>
          </div>
          <button onClick={onClose} className="ib" style={{
            width: 30, height: 30, borderRadius: C.r, border: `1px solid ${C.border}`,
            background: C.surface, color: C.mid, fontSize: 14,
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>✕</button>
        </div>

        {/* Body */}
        <div style={{ display: "flex", flex: 1, overflow: "hidden", minHeight: 0 }}>
          {/* Left: product list */}
          <div style={{ width: 320, borderRight: `1px solid ${C.border}`, display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "10px 12px", borderBottom: `1px solid ${C.border}` }}>
              <input
                value={filterQ}
                onChange={e => setFilterQ(e.target.value)}
                placeholder="Filtrar por nombre/SKU…"
                style={{ ...iS, height: 32, fontSize: 12 }}
              />
            </div>
            <div style={{ flex: 1, overflowY: "auto" }}>
              {loading ? (
                <div style={{ padding: 24, textAlign: "center", color: C.mute }}><Spinner size={16} /></div>
              ) : products.length === 0 ? (
                <div style={{ padding: 24, textAlign: "center", color: C.mute, fontSize: 13 }}>
                  {filterQ ? "Sin resultados" : "Todos los productos tienen barcode"}
                </div>
              ) : products.map((p, i) => (
                <div
                  key={p.id}
                  onClick={() => { setSelectedIdx(i); setCode(""); setError(null); document.getElementById("bc-scan-input")?.focus(); }}
                  style={{
                    padding: "10px 14px", cursor: "pointer",
                    background: i === selectedIdx ? `${C.accent}12` : "transparent",
                    borderBottom: `1px solid ${C.border}`,
                    borderLeft: i === selectedIdx ? `3px solid ${C.accent}` : "3px solid transparent",
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600, color: C.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.name}</div>
                  <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>
                    {p.sku && <span style={{ fontFamily: C.mono }}>{p.sku}</span>}
                    {p.sku && p.category__name && " · "}
                    {p.category__name}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right: scan input */}
          <div style={{ flex: 1, padding: "24px 22px", display: "flex", flexDirection: "column", gap: 16, justifyContent: "center" }}>
            {selected ? (
              <>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em" }}>Producto seleccionado</div>
                  <div style={{ fontSize: 18, fontWeight: 800, color: C.text, marginTop: 6 }}>{selected.name}</div>
                  {selected.sku && <div style={{ fontSize: 13, fontFamily: C.mono, color: C.mid, marginTop: 4 }}>SKU: {selected.sku}</div>}
                </div>

                {successMsg && (
                  <div style={{ padding: "8px 12px", borderRadius: C.r, background: C.greenBg, border: `1px solid ${C.greenBd}`, color: C.green, fontSize: 12, fontWeight: 600, textAlign: "center" }}>
                    {successMsg}
                  </div>
                )}

                {error && (
                  <div style={{ padding: "8px 12px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 12, fontWeight: 600, textAlign: "center" }}>
                    {error}
                  </div>
                )}

                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ fontSize: 11, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em" }}>Código de barras</label>
                  <input
                    id="bc-scan-input"
                    ref={inputRef}
                    value={code}
                    onChange={e => setCode(e.target.value)}
                    onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); handleAssign(); } }}
                    placeholder="Escanea o escribe el código…"
                    style={{ ...iS, fontFamily: C.mono, fontSize: 16, height: 46, textAlign: "center", letterSpacing: "0.05em" }}
                    autoComplete="off"
                    disabled={assigning}
                    autoFocus
                  />
                </div>

                <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
                  <Btn variant="primary" onClick={handleAssign} disabled={assigning || !code.trim()}>
                    {assigning ? <><Spinner /> Asignando…</> : "Asignar"}
                  </Btn>
                  <Btn variant="ghost" onClick={handleSkip} disabled={assigning}>
                    Saltar →
                  </Btn>
                </div>
              </>
            ) : !loading ? (
              <div style={{ textAlign: "center", color: C.mute, fontSize: 14 }}>
                {products.length === 0 ? "No quedan productos sin barcode." : "Selecciona un producto de la lista."}
              </div>
            ) : null}
          </div>
        </div>

        {/* Footer */}
        <div style={{
          padding: "13px 22px", borderTop: `1px solid ${C.border}`,
          background: C.bg, display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <span style={{ fontSize: 12, color: C.mute }}>
            {products.length > 0 ? `${selectedIdx + 1} de ${products.length} pendientes` : ""}
          </span>
          <Btn variant="ghost" onClick={onClose}>Cerrar</Btn>
        </div>
      </div>
    </div>
  );
}

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
      setErr(extractErr(e, "Error cargando catálogo"));
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
      setCatErr(extractErr(e, "Error cargando categorías")); setCategories([]);
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
    } catch (e: any) { setCatErr(extractErr(e, "Error creando categoría")); }
    finally { setSaving(false); }
  };

  // CRUD Producto — Crear
  const createProduct = async () => {
    const name = pName.trim();
    if (!name) { setErr("El nombre del producto es obligatorio."); return; }
    const price = parseFloat(pPrice);
    if (isNaN(price) || price < 0) { setErr("El precio debe ser un número positivo."); return; }
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
    if (isNaN(price) || price < 0) { setErr("El precio debe ser un número positivo."); return; }
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
            <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:C.text, letterSpacing:"-0.04em" }}>Catálogo</h1>
          </div>
          <p style={{ margin:0, fontSize:13, color:C.mute, paddingLeft:14 }}>Busca por nombre, SKU o código de barras</p>
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
          <Btn variant="secondary" onClick={()=>{resetCatForm();setShowCat(true);}} disabled={saving}>+ Categoría</Btn>
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
        <StatCard label="Total"      value={totalCount}               icon="📦" color={C.accent} />
        <StatCard label="Activos"    value={activeCount}              icon="✅" color={C.green}  />
        <StatCard label="Inactivos"  value={totalCount-activeCount}   icon="⏸️" color={C.amber}  />
        <StatCard label="Categorías" value={categories.length}        icon="🗂️" color={C.violet} />
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
          placeholder="Ej: arroz, 1002521, 7802810050232…"
          style={{ flex:1, minWidth:180, border:"none", background:"transparent", fontSize:14, outline:"none" }}
        />
        {q && (
          <button onClick={clearSearch} className="ib" style={{ background:"none", border:"none", color:C.mute, cursor:"pointer", fontSize:16, padding:"0 4px", lineHeight:1 }}>✕</button>
        )}
        <div style={{ width:1, height:20, background:C.border }}/>
        <Btn variant="secondary" size="sm" onClick={()=>{setPage(1);load(endpoint);}}>Buscar</Btn>
        <Btn variant="ghost"     size="sm" onClick={clearSearch}>Limpiar</Btn>
        <div style={{ fontSize:12, color:C.mute, whiteSpace:"nowrap" }}>
          Total: <b style={{ color:C.text }}>{totalCount}</b> · Categorías: <b style={{ color:C.text }}>{categories.length}</b>
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
          <Spinner size={16}/><span style={{ fontSize:13 }}>Cargando…</span>
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
            {!mob && <div>SKU</div>}<div>Producto</div>{!mob && <div>Categoría</div>}
            <div style={{ textAlign:"right" }}>Precio</div>
            {!mob && <div>Barcodes</div>}<div style={{ textAlign:"center" }}>Activo</div>
            <div style={{ textAlign:"right" }}>Acciones</div>
          </div>

          {items.length === 0 ? (
            <div style={{ padding:"60px 24px", textAlign:"center" }}>
              <div style={{ fontSize:38, marginBottom:10 }}>📭</div>
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
                  {p.sku || <span style={{ color:C.mute }}>—</span>}
                </div>}

                {/* Name */}
                <div style={{ minWidth:0 }}>
                  <div style={{ fontWeight:700, fontSize:mob?13:14, marginBottom:1, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{p.name}</div>
                  {!mob && p.description && <div style={{ fontSize:12, color:C.mute, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{p.description}</div>}
                  <div style={{ fontSize:11, color:C.mute, marginTop:2, fontFamily:C.mono }}>
                    {mob ? (p.sku || `ID:${p.id}`) : `ID: ${p.id} · ${normalizeUnit(p.unit??"UN")}`}
                  </div>
                </div>

                {/* Category */}
                {!mob && <div>
                  {p.category
                    ? <span style={{ fontSize:12, fontWeight:500, color:C.mid, background:C.bg, border:`1px solid ${C.border}`, borderRadius:4, padding:"2px 8px" }}>{p.category.name}</span>
                    : <span style={{ color:C.mute, fontSize:12 }}>—</span>
                  }
                </div>}

                {/* Price */}
                <div style={{ textAlign:"right", fontWeight:800, fontSize:mob?13:14, fontVariantNumeric:"tabular-nums", letterSpacing:"-0.01em" }}>
                  ${formatCLP(p.price)}
                </div>

                {/* Barcodes */}
                {!mob && <div style={{ fontSize:12, color:C.mid, fontFamily:C.mono, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", minWidth:0 }}>
                  {p.barcodes?.length ? p.barcodes.map((b)=>b.code).join(", ") : <span style={{ color:C.mute }}>—</span>}
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
          <Btn variant="secondary" size="sm" disabled={page<=1||saving} onClick={()=>setPage((p)=>Math.max(1,p-1))}>← Anterior</Btn>
          <span style={{ fontSize:13, color:C.mid }}>Página <b style={{ color:C.text }}>{page}</b> de <b style={{ color:C.text }}>{totalPages}</b></span>
          <Btn variant="secondary" size="sm" disabled={page>=totalPages||saving} onClick={()=>setPage((p)=>Math.min(totalPages,p+1))}>Siguiente →</Btn>
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
              {saving?<><Spinner/>Importando…</>:"Importar"}
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
              <Hint>Sube directamente tu Excel o CSV. Los headers en español se mapean automáticamente.</Hint>
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

      {/* ── MODAL: CATEGORÍA ──────────────────────────────────────────── */}
      {showCat && (
        <Modal onClose={()=>!saving&&setShowCat(false)} width={420} accentColor={C.violet}
          title="Nueva categoría"
          footer={<>
            <Btn variant="ghost" onClick={()=>!saving&&setShowCat(false)} disabled={saving}>Cancelar</Btn>
            <Btn variant="primary" onClick={createCategory} disabled={saving||!catName.trim()}>
              {saving?<><Spinner/>Creando…</>:"Crear"}
            </Btn>
          </>}
        >
          <div style={{ display:"grid", gap:14 }}>
            <div style={FL}>
              <FLabel>Categoría padre (opcional)</FLabel>
              <select value={catParentId} onChange={(e)=>setCatParentId(e.target.value?Number(e.target.value):"")} style={iS} disabled={saving}>
                <option value="">Nivel principal (raíz)</option>
                {categories.filter(c=>!c.parent_id).map(c=>(
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              <span style={{ fontSize:11, color:C.mute, marginTop:2 }}>Deja vacío para crear una categoría principal</span>
            </div>
            <div style={FL}>
              <FLabel req>Nombre</FLabel>
              <input value={catName} onChange={(e)=>setCatName(e.target.value)}
                placeholder="Ej: Abarrotes" style={iS} disabled={saving} autoFocus/>
            </div>
            <div style={FL}>
              <FLabel>Código (opcional)</FLabel>
              <input value={catCode} onChange={(e)=>setCatCode(e.target.value)}
                placeholder="Ej: ABAR" style={{ ...iS, fontFamily:C.mono }} disabled={saving}/>
            </div>
            {catErr && <ErrBox msg={catErr} onClose={()=>setCatErr(null)}/>}
          </div>
        </Modal>
      )}

      {/* ── MODAL: ADMINISTRAR CATEGORÍAS (ÁRBOL) ─────────────────────── */}
      {showCatManager && (
        <Modal onClose={()=>setShowCatManager(false)} width={560} accentColor={C.violet}
          title="Administrar categorías"
          subtitle="Organiza tu catálogo en categorías y subcategorías"
          footer={<Btn variant="ghost" onClick={()=>setShowCatManager(false)}>Cerrar</Btn>}
        >
          <CategoryTree
            categories={categories}
            onReload={loadCategories}
            iS={iS}
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
              {saving?<><Spinner/>Creando…</>:"Crear"}
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
              <FLabel>Descripción</FLabel>
              <textarea value={pDesc} onChange={(e)=>setPDesc(e.target.value)}
                placeholder="Descripción (opcional)" style={tS} disabled={saving}/>
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
                <FLabel>Stock mínimo</FLabel>
                <input value={pMinStock} onChange={(e)=>setPMinStock(e.target.value)}
                  placeholder="0" style={iS} disabled={saving} inputMode="decimal"/>
                <Hint>Alerta cuando baje de este nivel.</Hint>
              </div>
            </div>

            <div style={G2}>
              <div style={FL}>
                <FLabel>Marca</FLabel>
                <input value={pBrand} onChange={(e)=>setPBrand(e.target.value)}
                  placeholder="Ej: Colún, Polpaico…" style={iS} disabled={saving}/>
              </div>
              <div style={FL}>
                <FLabel>Categoría</FLabel>
                <CascadeSelect categories={categories} value={pCategoryId} onChange={setPCategoryId} disabled={saving} iS={iS} />
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
                placeholder="7802810050232, 123123…" style={{ ...iS, fontFamily:C.mono }} disabled={saving}/>
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
              {saving?<><Spinner/>Guardando…</>:"Guardar"}
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
              <FLabel>Descripción</FLabel>
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
                <Hint>Se actualiza automáticamente con compras.</Hint>
              </div>
              <div style={FL}>
                <FLabel>Stock mínimo</FLabel>
                <input value={eMinStock} onChange={(e)=>setEMinStock(e.target.value)}
                  placeholder="0" style={iS} disabled={saving} inputMode="decimal"/>
                <Hint>Alerta cuando baje de este nivel.</Hint>
              </div>
            </div>

            <div style={G2}>
              <div style={FL}>
                <FLabel>Marca</FLabel>
                <input value={eBrand} onChange={(e)=>setEBrand(e.target.value)}
                  placeholder="Ej: Colún, Polpaico…" style={iS} disabled={saving}/>
              </div>
              <div style={FL}>
                <FLabel>Categoría</FLabel>
                <CascadeSelect categories={categories} value={eCategoryId} onChange={setECategoryId} disabled={saving} iS={iS} />
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
                placeholder="7802810050232, 123123…" style={{ ...iS, fontFamily:C.mono }} disabled={saving}/>
              <Hint>Guardar reemplaza la lista completa.</Hint>
            </div>
          </div>
        </Modal>
      )}

    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// CASCADE SELECT — dynamic selects based on category depth
// ═══════════════════════════════════════════════════════════════════════════════
function CascadeSelect({
  categories, value, onChange, disabled, iS,
}: {
  categories: Category[];
  value: number | "";
  onChange: (v: number | "") => void;
  disabled?: boolean;
  iS: React.CSSProperties;
}) {
  // Build tree helpers
  const roots = categories.filter(c => !c.parent_id);
  const childrenOf = (pid: number) => categories.filter(c => c.parent_id === pid);

  // Walk up to find the chain: [root, child, grandchild, ...]
  const getChain = (id: number | ""): number[] => {
    if (id === "") return [];
    const chain: number[] = [];
    let cur: Category | undefined = categories.find(c => c.id === id);
    while (cur) {
      chain.unshift(cur.id);
      cur = cur.parent_id ? categories.find(c => c.id === cur!.parent_id) : undefined;
    }
    return chain;
  };

  const chain = getChain(value);

  // Build levels: level 0 = roots, level 1 = children of chain[0], etc.
  const levels: { parentId: number | null; options: Category[]; selected: number | "" }[] = [];

  // Level 0: roots
  levels.push({ parentId: null, options: roots, selected: chain[0] ?? "" });

  // Subsequent levels based on selected chain
  for (let i = 0; i < chain.length; i++) {
    const kids = childrenOf(chain[i]);
    if (kids.length > 0) {
      levels.push({
        parentId: chain[i],
        options: kids,
        selected: chain[i + 1] ?? "",
      });
    }
  }

  const labels = ["Categoría", "Subcategoría", "Familia", "Subfamilia", "Nivel 5"];

  const handleChange = (levelIdx: number, newVal: number | "") => {
    if (newVal === "") {
      // Cleared this level — use parent as the selected category
      if (levelIdx === 0) {
        onChange("");
      } else {
        onChange(chain[levelIdx - 1]);
      }
    } else {
      onChange(newVal);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {levels.map((lvl, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {i > 0 && <span style={{ fontSize: 10, color: "#A1A1AA", marginLeft: i * 8 }}>↳</span>}
          <select
            value={lvl.selected}
            onChange={e => handleChange(i, e.target.value ? Number(e.target.value) : "")}
            style={{ ...iS, flex: 1 }}
            disabled={disabled}
          >
            <option value="">{i === 0 ? "Sin categoría" : `Sin ${labels[i] || "subcategoría"}`}</option>
            {lvl.options.map(c => (
              <option key={c.id} value={c.id}>{c.name}{c.code ? ` (${c.code})` : ""}</option>
            ))}
          </select>
        </div>
      ))}
      {levels.length > 0 && value !== "" && (
        <div style={{ fontSize: 10, color: "#A1A1AA" }}>
          {getChain(value).map(id => categories.find(c => c.id === id)?.name).join(" → ")}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// CATEGORY TREE — full manager with expand/collapse, create, rename, toggle
// ═══════════════════════════════════════════════════════════════════════════════
function CategoryTree({
  categories, onReload, iS,
}: {
  categories: Category[];
  onReload: () => Promise<void>;
  iS: React.CSSProperties;
}) {
  

  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [addingTo, setAddingTo] = useState<number | null | "root">(null);  // null=none, "root"=top level, number=parent id
  const [newName, setNewName] = useState("");
  const [newCode, setNewCode] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const roots = categories.filter(c => !c.parent_id).sort((a, b) => a.name.localeCompare(b.name));
  const childrenOf = (pid: number) => categories.filter(c => c.parent_id === pid).sort((a, b) => a.name.localeCompare(b.name));

  const toggle = (id: number) => {
    setExpanded(prev => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };

  const handleCreate = async (parentId: number | null) => {
    if (!newName.trim()) return;
    setBusy(true); setError(null);
    try {
      const body: any = { name: newName.trim() };
      if (newCode.trim()) body.code = newCode.trim();
      if (parentId) body.parent_id = parentId;
      await apiFetch("/catalog/categories/", { method: "POST", body: JSON.stringify(body) });
      await onReload();
      setNewName(""); setNewCode(""); setAddingTo(null);
      if (parentId) setExpanded(prev => new Set(prev).add(parentId));
    } catch (e: any) {
      setError(e?.message || "Error creando categoría");
    } finally { setBusy(false); }
  };

  const handleRename = async (id: number) => {
    if (!editName.trim()) return;
    setBusy(true); setError(null);
    try {
      await apiFetch(`/catalog/categories/${id}/`, { method: "PATCH", body: JSON.stringify({ name: editName.trim() }) });
      await onReload();
      setEditingId(null); setEditName("");
    } catch (e: any) {
      setError(e?.message || "Error renombrando");
    } finally { setBusy(false); }
  };

  const handleToggleActive = async (cat: Category) => {
    setBusy(true); setError(null);
    try {
      await apiFetch(`/catalog/categories/${cat.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: !cat.is_active }) });
      await onReload();
    } catch (e: any) {
      setError(e?.message || "Error");
    } finally { setBusy(false); }
  };

  const renderNode = (cat: Category, depth: number) => {
    const kids = childrenOf(cat.id);
    const hasKids = kids.length > 0;
    const isOpen = expanded.has(cat.id);
    const isEditing = editingId === cat.id;

    return (
      <div key={cat.id}>
        <div style={{
          display: "flex", alignItems: "center", gap: 6,
          padding: "7px 8px", paddingLeft: 8 + depth * 20,
          borderBottom: `1px solid ${C.border}`, fontSize: 13,
          background: isEditing ? "#EEF2FF" : "transparent",
        }}>
          {/* Expand toggle */}
          <button onClick={() => hasKids && toggle(cat.id)} style={{
            width: 18, height: 18, display: "flex", alignItems: "center", justifyContent: "center",
            background: "none", border: "none", cursor: hasKids ? "pointer" : "default",
            color: hasKids ? C.mid : "#ddd", fontSize: 11, flexShrink: 0,
          }}>
            {hasKids ? (isOpen ? "▼" : "▶") : "•"}
          </button>

          {/* Name or edit input */}
          {isEditing ? (
            <div style={{ display: "flex", gap: 4, flex: 1 }}>
              <input value={editName} onChange={e => setEditName(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleRename(cat.id)}
                style={{ ...iS, flex: 1, padding: "4px 8px", fontSize: 12 }} autoFocus disabled={busy} />
              <button onClick={() => handleRename(cat.id)} disabled={busy || !editName.trim()} style={{
                padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                background: C.accent, color: "#fff", border: "none", borderRadius: 4,
              }}>OK</button>
              <button onClick={() => { setEditingId(null); setEditName(""); }} style={{
                padding: "4px 8px", fontSize: 11, cursor: "pointer",
                background: "none", border: `1px solid ${C.border}`, borderRadius: 4, color: C.mid,
              }}>✕</button>
            </div>
          ) : (
            <span style={{
              flex: 1, fontWeight: depth === 0 ? 600 : 400,
              color: cat.is_active !== false ? C.text : C.mute,
              textDecoration: cat.is_active === false ? "line-through" : "none",
            }}>
              {cat.name}
              {cat.code ? <span style={{ fontSize: 10, color: C.mute, marginLeft: 6, fontFamily: "monospace" }}>{cat.code}</span> : null}
              {kids.length > 0 && <span style={{ fontSize: 10, color: C.mute, marginLeft: 4 }}>({kids.length})</span>}
            </span>
          )}

          {/* Actions */}
          {!isEditing && (
            <div style={{ display: "flex", gap: 2, flexShrink: 0 }}>
              <button onClick={() => { setAddingTo(cat.id); setNewName(""); setNewCode(""); }} title="Agregar sub"
                style={{ padding: "2px 6px", fontSize: 12, background: "none", border: "none", cursor: "pointer", color: C.accent }}>＋</button>
              <button onClick={() => { setEditingId(cat.id); setEditName(cat.name); }} title="Renombrar"
                style={{ padding: "2px 6px", fontSize: 12, background: "none", border: "none", cursor: "pointer", color: C.mid }}>✏️</button>
              <button onClick={() => handleToggleActive(cat)} title={cat.is_active !== false ? "Desactivar" : "Activar"}
                style={{ padding: "2px 6px", fontSize: 12, background: "none", border: "none", cursor: "pointer", color: cat.is_active !== false ? C.green : C.red }}>
                {cat.is_active !== false ? "●" : "○"}
              </button>
            </div>
          )}
        </div>

        {/* Inline add form */}
        {addingTo === cat.id && (
          <div style={{
            display: "flex", gap: 4, padding: "6px 8px", paddingLeft: 28 + depth * 20,
            borderBottom: `1px solid ${C.border}`, background: "#FAFAFA",
          }}>
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Nombre subcategoría"
              onKeyDown={e => e.key === "Enter" && handleCreate(cat.id)}
              style={{ ...iS, flex: 1, padding: "4px 8px", fontSize: 12 }} autoFocus disabled={busy} />
            <input value={newCode} onChange={e => setNewCode(e.target.value)} placeholder="Cód."
              style={{ ...iS, width: 60, padding: "4px 6px", fontSize: 11, fontFamily: "monospace" }} disabled={busy} />
            <button onClick={() => handleCreate(cat.id)} disabled={busy || !newName.trim()} style={{
              padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
              background: C.accent, color: "#fff", border: "none", borderRadius: 4,
            }}>Crear</button>
            <button onClick={() => setAddingTo(null)} style={{
              padding: "4px 8px", fontSize: 11, cursor: "pointer",
              background: "none", border: `1px solid ${C.border}`, borderRadius: 4, color: C.mid,
            }}>✕</button>
          </div>
        )}

        {/* Children */}
        {isOpen && kids.map(k => renderNode(k, depth + 1))}
      </div>
    );
  };

  return (
    <div>
      {error && (
        <div style={{ padding: "8px 12px", marginBottom: 8, background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 6, fontSize: 12, color: C.red }}>
          {error}
          <button onClick={() => setError(null)} style={{ marginLeft: 8, background: "none", border: "none", cursor: "pointer", color: C.red }}>✕</button>
        </div>
      )}

      {/* Add root category */}
      <div style={{ display: "flex", gap: 4, padding: "8px 0", marginBottom: 4 }}>
        {addingTo === "root" ? (
          <>
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Nombre categoría principal"
              onKeyDown={e => e.key === "Enter" && handleCreate(null)}
              style={{ ...iS, flex: 1, padding: "6px 10px", fontSize: 13 }} autoFocus disabled={busy} />
            <input value={newCode} onChange={e => setNewCode(e.target.value)} placeholder="Cód."
              style={{ ...iS, width: 60, padding: "6px 6px", fontSize: 12, fontFamily: "monospace" }} disabled={busy} />
            <button onClick={() => handleCreate(null)} disabled={busy || !newName.trim()} style={{
              padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
              background: C.accent, color: "#fff", border: "none", borderRadius: 6,
            }}>Crear</button>
            <button onClick={() => setAddingTo(null)} style={{
              padding: "6px 10px", fontSize: 12, cursor: "pointer",
              background: "none", border: `1px solid ${C.border}`, borderRadius: 6, color: C.mid,
            }}>✕</button>
          </>
        ) : (
          <button onClick={() => { setAddingTo("root"); setNewName(""); setNewCode(""); }} style={{
            padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
            background: "none", border: `1px dashed ${C.border}`, borderRadius: 6,
            color: C.accent, width: "100%",
          }}>+ Nueva categoría principal</button>
        )}
      </div>

      {/* Tree */}
      <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
        {roots.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center", color: C.mute, fontSize: 13 }}>
            No hay categorías creadas. Crea tu primera categoría arriba.
          </div>
        ) : (
          roots.map(c => renderNode(c, 0))
        )}
      </div>

      <div style={{ marginTop: 8, fontSize: 11, color: C.mute }}>
        Tip: Puedes crear tantos niveles como necesites (Categoría → Subcategoría → Familia → etc.)
      </div>
    </div>
  );
}