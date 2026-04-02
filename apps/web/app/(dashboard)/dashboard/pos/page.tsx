"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import type { Me } from "@/lib/me";
import { useGlobalStyles } from "@/lib/useGlobalStyles";

function useIsMobile(){const[m,setM]=useState(false);useEffect(()=>{const fn=()=>setM(window.innerWidth<768);fn();window.addEventListener("resize",fn);return()=>window.removeEventListener("resize",fn);},[]);return m;}

// ─── Types ────────────────────────────────────────────────────────────────────

type Warehouse = { id: number; name: string; is_active: boolean; warehouse_type?: string };
type Category  = { id: number; name: string; code?: string | null };
type Barcode   = { id: number; code: string };
type Product   = {
  id: number; sku?: string | null; name: string;
  description?: string | null; unit?: string | null;
  price: string; is_active: boolean;
  category?: Category | null; barcodes?: Barcode[];
};
type PromoInfo = {
  product_id: number; promotion_id: number; promotion_name: string;
  discount_type: string; discount_value: string;
  original_price: string; promo_price: string;
};
type CartLine = {
  product: Product; qty: number; unitPrice: number;
  discountType: "none" | "pct" | "amt";
  discountValue: number;
  promotion_id?: number;
  original_price?: number;
};
type Shortage = {
  product_id: number; available: string; required: string;
  name?: string; sku?: string | null;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toNumber(v: string | number) { const n = typeof v === "string" ? Number(v) : v; return Number.isFinite(n) ? n : 0; }
function formatCLP(v: number) { return Math.round(v).toLocaleString("es-CL"); }

function lineDiscount(line: CartLine): number {
  if (line.discountType === "pct")
    return Math.min(line.unitPrice * line.qty, (line.unitPrice * line.qty * line.discountValue) / 100);
  if (line.discountType === "amt")
    return Math.min(line.unitPrice * line.qty, line.discountValue);
  return 0;
}
function lineSubtotal(line: CartLine): number {
  return line.unitPrice * line.qty - lineDiscount(line);
}

const POS_WAREHOUSE_STORAGE_KEY = "pos_warehouse_id";
const POS_CART_STORAGE_KEY = "pos_cart_draft";

type CartDraft = {
  cart: CartLine[];
  globalDiscountType: "none"|"pct"|"amt";
  globalDiscountValue: number;
  saleNote: string;
  payRows: { method: string; amount: string }[];
  tipAmount: string;
};

function saveCartDraft(d: CartDraft) {
  try { localStorage.setItem(POS_CART_STORAGE_KEY, JSON.stringify(d)); } catch {}
}
function loadCartDraft(): CartDraft | null {
  try {
    const raw = localStorage.getItem(POS_CART_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}
function clearCartDraft() {
  try { localStorage.removeItem(POS_CART_STORAGE_KEY); } catch {}
}

// ─── Mini-components ──────────────────────────────────────────────────────────

function Spinner({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
      style={{ animation:"spin 0.7s linear infinite", display:"block", flexShrink:0 }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
    </svg>
  );
}

type BtnV = "primary"|"secondary"|"ghost"|"danger"|"success"|"amber";
function Btn({ children, onClick, variant="secondary", disabled, size="md", full, mobFull }: {
  children: React.ReactNode; onClick?: ()=>void;
  variant?: BtnV; disabled?: boolean; size?: "sm"|"md"|"lg"; full?: boolean; mobFull?: boolean;
}) {
  const vs: Record<BtnV, React.CSSProperties> = {
    primary:   { background:C.accent,  color:"#fff",    border:`1px solid ${C.accent}`   },
    secondary: { background:C.surface, color:C.text,    border:`1px solid ${C.borderMd}` },
    ghost:     { background:"transparent", color:C.mid, border:"1px solid transparent"  },
    danger:    { background:C.redBg,   color:C.red,     border:`1px solid ${C.redBd}`    },
    success:   { background:C.greenBg, color:C.green,   border:`1px solid ${C.greenBd}`  },
    amber:     { background:C.amberBg, color:C.amber,   border:`1px solid ${C.amberBd}`  },
  };
  const h = size==="lg"?48:size==="sm"?30:38;
  const px = size==="lg"?"0 20px":size==="sm"?"0 10px":"0 14px";
  const fs = size==="lg"?14:size==="sm"?11:13;
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="xb" style={{
      ...vs[variant], display:"inline-flex", alignItems:"center", justifyContent:"center", gap:6,
      height:h, padding:px, borderRadius:C.r, fontSize:fs, fontWeight:600,
      letterSpacing:"0.01em", whiteSpace:"nowrap", width:(full||mobFull)?"100%":undefined,
    }}>
      {children}
    </button>
  );
}

// ─── Discount cell (per line) ─────────────────────────────────────────────────

function DiscountCell({ line, onChange, disabled }: {
  line: CartLine;
  onChange: (type: CartLine["discountType"], value: number) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const discount = lineDiscount(line);
  const hasDiscount = line.discountType !== "none" && line.discountValue > 0;

  return (
    <div ref={ref} style={{ position:"relative" }}>
      <button
        type="button"
        onClick={() => !disabled && setOpen((o) => !o)}
        className="xb"
        style={{
          height:34, padding:"0 10px", borderRadius:C.r, fontSize:11, fontWeight:600,
          border:`1px solid ${hasDiscount ? C.amberBd : C.border}`,
          background:hasDiscount ? C.amberBg : C.bg,
          color:hasDiscount ? C.amber : C.mute,
          display:"flex", alignItems:"center", gap:4,
        }}
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/>
          <line x1="7" y1="7" x2="7.01" y2="7"/>
        </svg>
        {hasDiscount
          ? line.discountType === "pct"
            ? `-${line.discountValue}%`
            : `-$${formatCLP(line.discountValue)}`
          : "Dscto."}
      </button>

      {open && (
        <div className="dd-in" style={{
          position:"absolute", top:"calc(100% + 6px)", right:0, zIndex:50,
          background:C.surface, border:`1px solid ${C.border}`,
          borderRadius:C.rMd, boxShadow:C.shMd, padding:12,
          width:200, display:"flex", flexDirection:"column", gap:10,
        }}>
          <div style={{ fontSize:11, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.06em" }}>
            Descuento por línea
          </div>

          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:4 }}>
            {(["none","pct","amt"] as const).map((t) => (
              <button key={t} type="button" onClick={() => onChange(t, t==="none"?0:line.discountValue)} className="xb" style={{
                padding:"5px 0", borderRadius:C.r, fontSize:11, fontWeight:600,
                border:`1px solid ${line.discountType===t ? C.accent : C.border}`,
                background:line.discountType===t ? C.accentBg : C.bg,
                color:line.discountType===t ? C.accent : C.mid,
              }}>
                {t==="none"?"Ninguno":t==="pct"?"% desc.":"$ monto"}
              </button>
            ))}
          </div>

          {line.discountType !== "none" && (
            <div>
              <label style={{ fontSize:11, fontWeight:700, color:C.mid, display:"block", marginBottom:4 }}>
                {line.discountType === "pct" ? "Porcentaje (%)" : "Monto ($)"}
              </label>
              <input
                type="number"
                min={0}
                max={line.discountType==="pct"?100:undefined}
                value={line.discountValue || ""}
                onChange={(e) => onChange(line.discountType, Math.max(0, Number(e.target.value)))}
                placeholder={line.discountType==="pct"?"10":"500"}
                autoFocus
                style={{
                  width:"100%", height:34, padding:"0 10px",
                  border:`1px solid ${C.border}`, borderRadius:C.r,
                  fontSize:13, fontWeight:600,
                }}
              />
              {discount > 0 && (
                <div style={{ fontSize:11, color:C.amber, marginTop:4, fontWeight:600 }}>
                  - ${formatCLP(discount)} de descuento
                </div>
              )}
            </div>
          )}

          <button type="button" onClick={() => setOpen(false)} className="xb" style={{
            alignSelf:"flex-end", fontSize:11, fontWeight:600, color:C.mid,
            background:"none", border:"none", padding:0, cursor:"pointer",
          }}>
            Cerrar
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

const PAGE_CSS = `
.toast-in{animation:toastIn 0.22s cubic-bezier(0.34,1.38,0.64,1) both}
@keyframes toastIn{from{opacity:0;transform:translateY(-8px) scale(0.97)}to{opacity:1;transform:none}}
.dd-in{animation:ddIn 0.14s ease both}
@keyframes ddIn{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
`;

export default function PosPage() {
  useGlobalStyles(PAGE_CSS);
  const mob = useIsMobile();
  const inputRef     = useRef<HTMLInputElement | null>(null);
  const searchWrapRef = useRef<HTMLDivElement | null>(null);

  const [me, setMe]                 = useState<Me | null>(null);
  const [meErr, setMeErr]           = useState<string | null>(null);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId, setWarehouseId] = useState<number | null>(null);

  const [term, setTerm]             = useState("");
  const [cartLoaded, setCartLoaded] = useState(false);
  const [draftRecovered, setDraftRecovered] = useState(false);
  const [cart, setCart]             = useState<CartLine[]>([]);
  const [busy, setBusy]             = useState(false);
  const [searching, setSearching]   = useState(false);
  const [err, setErr]               = useState<string | null>(null);
  const [shortages, setShortages]   = useState<Shortage[] | null>(null);
  const [toast, setToast]           = useState<string | null>(null);
  const [paymentWarn, setPaymentWarn] = useState<string | null>(null);
  const [lastSaleId, setLastSaleId]         = useState<number | null>(null);
  const [lastSaleNumber, setLastSaleNumber] = useState<number | null>(null);

  // Suggestions dropdown
  const [suggestions, setSuggestions]   = useState<Product[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggHighlight, setSuggHighlight] = useState(0);

  // Global discount
  const [globalDiscountType, setGlobalDiscountType]   = useState<"none"|"pct"|"amt">("none");
  const [globalDiscountValue, setGlobalDiscountValue] = useState(0);

  // Sale note
  const [saleNote, setSaleNote] = useState("");
  const [showNote, setShowNote] = useState(false);

  // Active promotions cache
  const [promoMap, setPromoMap] = useState<Record<number, PromoInfo>>({});

  // ── PAGO MIXTO (dinámico) ──────────────────────────────────────────────────
  type PosPayRow = { method: string; amount: string };
  const PAY_METHODS = [
    { value: "cash", label: "Efectivo", icon: "\uD83D\uDCB5" },
    { value: "debit", label: "D\u00E9bito", icon: "\uD83D\uDCB3" },
    { value: "card", label: "Cr\u00E9dito", icon: "\uD83D\uDCB3" },
    { value: "transfer", label: "Transferencia", icon: "\uD83C\uDFE6" },
  ] as const;
  const [payRows, setPayRows] = useState<PosPayRow[]>([{ method: "cash", amount: "" }]);

  // ── PROPINA ────────────────────────────────────────────────────────────────
  const [tipAmount, setTipAmount] = useState("");

  useEffect(() => { inputRef.current?.focus(); }, []);

  // ── Restore cart draft from localStorage ────────────────────────────────
  useEffect(() => {
    const draft = loadCartDraft();
    if (draft && draft.cart.length > 0) {
      setCart(draft.cart);
      setGlobalDiscountType(draft.globalDiscountType);
      setGlobalDiscountValue(draft.globalDiscountValue);
      setSaleNote(draft.saleNote);
      setPayRows(draft.payRows);
      setTipAmount(draft.tipAmount);
      setDraftRecovered(true);
    }
    setCartLoaded(true);
  }, []);

  // ── Persist cart draft to localStorage on changes ───────────────────────
  useEffect(() => {
    if (!cartLoaded) return;
    if (cart.length === 0) { clearCartDraft(); return; }
    saveCartDraft({ cart, globalDiscountType, globalDiscountValue, saleNote, payRows, tipAmount });
  }, [cartLoaded, cart, globalDiscountType, globalDiscountValue, saleNote, payRows, tipAmount]);

  // /core/me/
  useEffect(() => {
    (async () => {
      try {
        const data = (await apiFetch("/core/me/")) as Me;
        setMe(data);
        if (!data?.tenant_id) { setMeErr("Tu usuario no tiene tenant asignado."); return; }
        setMeErr(null);
      } catch (e: any) { setMeErr(e?.message ?? "No se pudo cargar /core/me/"); }
    })();
  }, []);

  // /core/warehouses/
  useEffect(() => {
    if (!me?.tenant_id) return;
    (async () => {
      try {
        const ws   = (await apiFetch("/core/warehouses/")) as Warehouse[];
        const list = Array.isArray(ws) ? ws : [];
        setWarehouses(list);
        if (list.length === 0) { setWarehouseId(null); return; }
        const stored     = typeof window !== "undefined" ? localStorage.getItem(POS_WAREHOUSE_STORAGE_KEY) : null;
        const storedId   = stored ? Number(stored) : null;
        const hasStored  = storedId && list.some((w) => w.id === storedId);
        const hasDefault = me.default_warehouse_id && list.some((w) => w.id === me.default_warehouse_id);
        const nextId     = hasStored ? storedId! : hasDefault ? me.default_warehouse_id! : list[0].id;
        setWarehouseId(nextId);
        try { localStorage.setItem(POS_WAREHOUSE_STORAGE_KEY, String(nextId)); } catch {}
      } catch { setWarehouseId(null); }
    })();
  }, [me?.tenant_id, me?.default_warehouse_id]);

  // Close suggestions on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchWrapRef.current && !searchWrapRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Debounced search for suggestions
  useEffect(() => {
    const q = term.trim();
    if (!q || q.length < 2) { setSuggestions([]); setShowSuggestions(false); return; }

    setSearching(true);
    const t = setTimeout(async () => {
      try {
        const data = await apiFetch(`/catalog/products/?q=${encodeURIComponent(q)}&page=1`);
        const list: Product[] = Array.isArray(data) ? data : (data?.results ?? []);
        const active = list.filter((p) => p.is_active).slice(0, 8);
        setSuggestions(active);
        setShowSuggestions(active.length > 0);
        setSuggHighlight(0);
        // Fetch active promos for these products
        if (active.length > 0) {
          try {
            const ids = active.map((p) => p.id).join(",");
            const promoData = await apiFetch(`/promotions/active-for-products/?product_ids=${ids}`);
            const map: Record<number, PromoInfo> = {};
            for (const p of promoData.results || []) map[p.product_id] = p;
            setPromoMap((prev) => ({ ...prev, ...map }));
          } catch {}
        }
      } catch {
        setSuggestions([]); setShowSuggestions(false);
      } finally { setSearching(false); }
    }, 280);
    return () => { clearTimeout(t); setSearching(false); };
  }, [term]);

  // ── Totals ─────────────────────────────────────────────────────────────────

  const subtotalBeforeGlobal = useMemo(() => cart.reduce((a, l) => a + lineSubtotal(l), 0), [cart]);

  const globalDiscountAmt = useMemo(() => {
    if (globalDiscountType === "pct")
      return Math.min(subtotalBeforeGlobal, (subtotalBeforeGlobal * globalDiscountValue) / 100);
    if (globalDiscountType === "amt")
      return Math.min(subtotalBeforeGlobal, globalDiscountValue);
    return 0;
  }, [globalDiscountType, globalDiscountValue, subtotalBeforeGlobal]);

  const total      = useMemo(() => Math.max(0, subtotalBeforeGlobal - globalDiscountAmt), [subtotalBeforeGlobal, globalDiscountAmt]);
  const itemsCount = useMemo(() => cart.reduce((a, l) => a + l.qty, 0), [cart]);
  const totalLineDiscounts = useMemo(() => cart.reduce((a, l) => a + lineDiscount(l), 0), [cart]);

  // ── Cálculos de Pago Mixto ─────────────────────────────────────────────────
  const totalPaid = useMemo(() => {
    return payRows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  }, [payRows]);

  const tip         = useMemo(() => Math.max(0, Number(tipAmount) || 0), [tipAmount]);
  const grandTotal  = useMemo(() => total + tip, [total, tip]);
  const pendingAmount = useMemo(() => Math.max(0, grandTotal - totalPaid), [grandTotal, totalPaid]);

  const change = useMemo(() => {
    if (totalPaid > grandTotal) {
      return totalPaid - grandTotal;
    }
    return null;
  }, [totalPaid, grandTotal]);

  // ── Cart mutations ─────────────────────────────────────────────────────────

  const addToCart = useCallback((product: Product) => {
    const promo = promoMap[product.id];
    const unitPrice = promo ? toNumber(promo.promo_price) : toNumber(product.price);
    setCart((prev) => {
      const idx = prev.findIndex((l) => l.product.id === product.id);
      if (idx >= 0) {
        const copy = prev.slice();
        copy[idx] = { ...copy[idx], qty: copy[idx].qty + 1 };
        return copy;
      }
      return [...prev, {
        product, qty: 1, unitPrice, discountType: "none", discountValue: 0,
        ...(promo ? { promotion_id: promo.promotion_id, original_price: toNumber(promo.original_price) } : {}),
      }];
    });
  }, [promoMap]);

  const removeLine      = useCallback((id: number) => setCart((p) => p.filter((l) => l.product.id !== id)), []);
  const changeQty       = useCallback((id: number, qty: number) => setCart((p) => p.map((l) => l.product.id === id ? {...l,qty} : l).filter((l) => l.qty > 0)), []);
  const changeUnitPrice = useCallback((id: number, unitPrice: number) => setCart((p) => p.map((l) => l.product.id === id ? {...l, unitPrice:Math.max(0,unitPrice)} : l)), []);
  const changeLineDiscount = useCallback((id: number, type: CartLine["discountType"], value: number) => {
    setCart((p) => p.map((l) => l.product.id === id ? {...l, discountType:type, discountValue:value} : l));
  }, []);
  
  const clearCart = useCallback(() => {
    setCart([]);
    setGlobalDiscountType("none");
    setGlobalDiscountValue(0);
    setSaleNote("");
    setPayRows([{ method: "cash", amount: "" }]);
    setTipAmount("");
    clearCartDraft();
  }, []);

  // ── Lookup (exact — barcode/SKU) ───────────────────────────────────────────

  const lookupAndAdd = useCallback(async (raw: string) => {
    const cleaned = raw.trim();
    if (!cleaned) return;
    setShowSuggestions(false);
    setBusy(true); setErr(null); setShortages(null);
    try {
      const url     = `/catalog/products/lookup/?term=${encodeURIComponent(cleaned)}`;
      const product = (await apiFetch(url)) as Product;
      if (!product?.id)              { setErr("Producto no encontrado.");              return; }
      if (!product.is_active)        { setErr("Producto inactivo. No se puede vender."); return; }
      addToCart(product);
      setTerm("");
      requestAnimationFrame(() => inputRef.current?.focus());
    } catch (e: any) { setErr(e?.message ?? "No se pudo buscar el producto."); }
    finally { setBusy(false); }
  }, [addToCart]);

  // Pick from dropdown
  const pickSuggestion = useCallback((product: Product) => {
    setShowSuggestions(false);
    setSuggestions([]);
    setTerm("");
    if (!product.is_active) { setErr("Producto inactivo. No se puede vender."); return; }
    addToCart(product);
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [addToCart]);

  // ── Confirm sale ───────────────────────────────────────────────────────────

  const confirmSale = useCallback(async () => {
    if (!warehouseId)      { setErr("No hay bodega seleccionada.");  return; }
    if (cart.length === 0) { setErr("El carrito está vacío.");       return; }
    if (totalPaid < grandTotal) { setErr(`Falta pagar $${formatCLP(grandTotal - totalPaid)}.`); return; }

    setBusy(true); setErr(null); setShortages(null); setLastSaleId(null);
    try {
      // Desglose de pagos mixto
      const paymentBreakdown = payRows
        .filter(r => Number(r.amount) > 0)
        .map(r => ({ method: r.method, amount: Number(r.amount) }));

      const payload: any = {
        warehouse_id: warehouseId,
        lines: cart.map((l) => ({
          product_id: l.product.id,
          qty: l.qty,
          unit_price: l.unitPrice.toFixed(2),
          ...(l.discountType !== "none" && l.discountValue > 0
            ? { discount_type: l.discountType, discount_value: l.discountValue.toFixed(2) }
            : {}),
          ...(l.promotion_id ? { promotion_id: l.promotion_id } : {}),
        })),
        payments: paymentBreakdown, // Enviamos el array de pagos al API
      };

      if (globalDiscountType !== "none" && globalDiscountValue > 0) {
        payload.global_discount_type  = globalDiscountType;
        payload.global_discount_value = globalDiscountValue.toFixed(2);
      }
      if (saleNote.trim()) payload.note = saleNote.trim();
      if (tip > 0) payload.tip = tip.toFixed(2);

      const res        = await apiFetch("/sales/sales/", { method:"POST", body:JSON.stringify(payload) });
      const saleId     = Number(res?.id ?? 0) || null;
      const saleNumber = Number(res?.sale_number ?? 0) || saleId;
      const saleTotal  = toNumber(res?.total ?? total);

      setLastSaleId(saleId);
      setLastSaleNumber(saleNumber);
      setToast(`Venta${saleNumber ? ` #${saleNumber}` : ""} confirmada · $${formatCLP(saleTotal)}`);
      if (res?.payment_warning) setPaymentWarn(res.payment_warning);

      clearCart(); setTerm(""); setTipAmount("");
      requestAnimationFrame(() => inputRef.current?.focus());
      setTimeout(() => setToast(null), 4500);
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 409 && e.data?.shortages) {
        const raw  = Array.isArray(e.data.shortages) ? (e.data.shortages as Shortage[]) : [];
        const byId = new Map(cart.map((l) => [l.product.id, l.product]));
        setShortages(raw.map((s) => { const p = byId.get(s.product_id); return {...s, name:p?.name, sku:p?.sku}; }));
        setErr("Stock insuficiente para confirmar la venta.");
        return;
      }
      setErr(e?.message ?? "No se pudo confirmar la venta.");
    } finally { setBusy(false); }
  }, [warehouseId, cart, globalDiscountType, globalDiscountValue, saleNote, total, tip, grandTotal, totalPaid, payRows, clearCart]);

  const defaultValidity        = useMemo(() => {
    if (!me?.default_warehouse_id) return "none" as const;
    return warehouses.some((w) => w.id === me.default_warehouse_id) ? "valid" as const : "invalid" as const;
  }, [me?.default_warehouse_id, warehouses]);
  const selectedWarehouseName  = warehouses.find((w) => w.id === warehouseId)?.name ?? "—";

  // Keyboard navigation for suggestions
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (showSuggestions && suggestions.length > 0) {
        pickSuggestion(suggestions[suggHighlight] ?? suggestions[0]);
      } else {
        lookupAndAdd(term);
      }
      return;
    }
    if (!showSuggestions) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSuggHighlight((h) => Math.min(h + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSuggHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Escape") {
      setShowSuggestions(false);
    }
  }, [showSuggestions, suggestions, suggHighlight, pickSuggestion, lookupAndAdd, term]);

  // ─────────────────────────────── RENDER ──────────────────────────────────

  return (
    <div style={{ fontFamily:C.font, color:C.text, background:C.bg, minHeight:"100vh", padding:mob?"16px 12px":"24px 28px", display:"flex", flexDirection:"column", gap:16 }}>

      {/* ── DRAFT RECOVERED BANNER ──────────────────────────────────── */}
      {draftRecovered && (
        <div style={{
          padding:"10px 14px", borderRadius:C.r, border:`1px solid ${C.greenBd}`,
          background:C.greenBg, color:C.green, fontSize:13, fontWeight:500,
          display:"flex", alignItems:"center", justifyContent:"space-between", gap:8,
        }}>
          <span>🛒 Se recuperó un carrito guardado con {cart.length} producto{cart.length !== 1 ? "s" : ""}.</span>
          <button type="button" onClick={() => setDraftRecovered(false)} style={{
            background:"none", border:"none", color:C.green, cursor:"pointer",
            fontSize:18, lineHeight:1, fontWeight:700, padding:"0 4px",
          }}>×</button>
        </div>
      )}

      {/* ── HEADER ─────────────────────────────────────────────────────── */}
      <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between", gap:16, flexWrap:"wrap" }}>
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:4 }}>
            <div style={{ width:4, height:26, background:C.accent, borderRadius:2 }}/>
            <h1 style={{ margin:0, fontSize:mob?18:22, fontWeight:800, color:C.text, letterSpacing:"-0.04em" }}>Punto de Venta</h1>
          </div>
          {mob
            ? <p style={{ margin:0, fontSize:12, color:C.mute, paddingLeft:14 }}>Busca o escanea productos</p>
            : <p style={{ margin:0, fontSize:13, color:C.mute, paddingLeft:14 }}>
                Escanea, escribe SKU o busca por nombre ·{" "}
                <kbd style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:4, padding:"1px 6px", fontSize:11, fontFamily:C.mono }}>↑↓</kbd>{" "}
                navega · <kbd style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:4, padding:"1px 6px", fontSize:11, fontFamily:C.mono }}>Enter</kbd>{" "}
                agrega
              </p>
          }
        </div>

        <div style={{ display:"flex", gap:mob?8:10, alignItems:"center", flexWrap:"wrap", width:mob?"100%":undefined }}>
          {/* Warehouse selector */}
          <div style={{
            display:"flex", alignItems:"center", gap:8, flex:mob?1:undefined,
            background:C.surface, border:`1px solid ${C.border}`,
            borderRadius:C.r, padding:"6px 12px", boxShadow:C.sh,
          }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
            </svg>
            <span style={{ fontSize:12, color:C.mute }}>Bodega</span>
            <select
              value={warehouseId ?? ""}
              onChange={(e) => {
                const next = Number(e.target.value);
                const id   = Number.isFinite(next) && next > 0 ? next : null;
                setWarehouseId(id);
                if (id) { try { localStorage.setItem(POS_WAREHOUSE_STORAGE_KEY, String(id)); } catch {} }
                requestAnimationFrame(() => inputRef.current?.focus());
              }}
              disabled={busy || !!meErr}
              style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:C.r, padding:"6px 10px", fontWeight:700, fontSize:13, color:C.text, outline:"none", cursor:"pointer" }}
            >
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}{w.warehouse_type==="sales_floor"?" (Sala)":" (Bodega)"}</option>)}
            </select>
            {defaultValidity === "invalid" && <span style={{ fontSize:11, color:C.red, fontWeight:700 }}>⚠ fuera del store</span>}
          </div>

          <Btn variant="ghost" size="sm" onClick={() => {
            clearCart(); setErr(null); setShortages(null); setToast(null); setPaymentWarn(null);
            setLastSaleId(null); setTerm("");
            requestAnimationFrame(() => inputRef.current?.focus());
          }} disabled={busy || cart.length === 0}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
              <path d="M10 11v6M14 11v6"/>
            </svg>
            Vaciar
          </Btn>
        </div>
      </div>

      {/* ── CONFIG ERROR ───────────────────────────────────────────────── */}
      {meErr && (
        <div style={{ padding:"11px 14px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, color:C.red, fontSize:13, fontWeight:500, display:"flex", gap:8 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink:0, marginTop:1 }}>
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <b>Config:</b> {meErr}
        </div>
      )}

      {/* ── TOAST ──────────────────────────────────────────────────────── */}
      {toast && (
        <div className="toast-in" style={{
          padding:"12px 16px", borderRadius:C.r,
          border:`1px solid ${C.greenBd}`, background:C.greenBg,
          color:C.green, fontSize:13, fontWeight:600,
          display:"flex", alignItems:"center", gap:12, flexWrap:"wrap",
        }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink:0 }}>
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          <span style={{ flex:1 }}>{toast}</span>
          {lastSaleId && (
            <Link href={`/dashboard/pos/receipt/${lastSaleId}`} style={{
              fontWeight:700, color:C.green, textDecoration:"none",
              borderBottom:`1px solid ${C.green}`, paddingBottom:1, fontSize:13,
            }}>
              Ver recibo #{lastSaleNumber ?? lastSaleId} →
            </Link>
          )}
        </div>
      )}

      {/* ── PAYMENT WARNING ────────────────────────────────────────────── */}
      {paymentWarn && (
        <div className="toast-in" style={{
          padding:"10px 14px", borderRadius:C.r,
          border:`1px solid ${C.amberBd}`, background:C.amberBg,
          color:C.amber, fontSize:13, fontWeight:600,
          display:"flex", alignItems:"center", gap:10,
        }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink:0 }}>
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <span style={{ flex:1 }}>{paymentWarn}</span>
          <button type="button" onClick={() => setPaymentWarn(null)} style={{
            background:"none", border:"none", cursor:"pointer", color:C.amber, fontSize:16, lineHeight:1, padding:"0 2px",
          }}>✕</button>
        </div>
      )}

      {/* ── MAIN SPLIT LAYOUT ──────────────────────────────────────────── */}
      <div style={{ display:"grid", gridTemplateColumns:mob?"1fr":"1fr 360px", gap:16, alignItems:"start" }}>

        {/* ── LEFT ───────────────────────────────────────────────────── */}
        <div style={{ display:"flex", flexDirection:"column", gap:12 }}>

          {/* ── SEARCH BAR with suggestions ──────────────────────────── */}
          <div ref={searchWrapRef} style={{ position:"relative" }}>
            <div style={{
              background:C.surface, border:`1px solid ${showSuggestions ? C.accentBd : C.border}`,
              borderRadius:showSuggestions ? `${C.rMd} ${C.rMd} 0 0` : C.rMd,
              padding:"10px 14px", boxShadow:C.sh,
              display:"flex", gap:10, alignItems:"center",
              transition:"border-color 0.12s ease, border-radius 0.12s ease",
            }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={searching ? C.accent : C.mute} strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink:0, transition:"stroke 0.15s" }}>
                {searching
                  ? <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" style={{ animation:"spin 0.7s linear infinite" }}/>
                  : <><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></>
                }
              </svg>
              <input
                ref={inputRef}
                value={term}
                onChange={(e) => setTerm(e.target.value)}
                onKeyDown={handleKeyDown}
                onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
                placeholder={mob?"Buscar producto…":"Escanea barcode, escribe SKU o nombre del producto…"}
                style={{ flex:1, border:"none", background:"transparent", fontSize:mob?14:15, outline:"none", fontFamily:C.font, minHeight:mob?44:undefined }}
                disabled={busy || !!meErr || !warehouseId}
              />
              {term && (
                <button onClick={() => { setTerm(""); setSuggestions([]); setShowSuggestions(false); inputRef.current?.focus(); }} className="xb"
                  style={{ background:"none", border:"none", color:C.mute, cursor:"pointer", fontSize:16, padding:"0 4px", lineHeight:1 }}>✕</button>
              )}
              {!mob && <div style={{ width:1, height:20, background:C.border }}/>}
              <Btn variant="primary" size={mob?"md":"sm"} onClick={() => lookupAndAdd(term)} disabled={busy || !!meErr || !term.trim() || !warehouseId}>
                {busy ? <Spinner/> : null}
                Agregar
              </Btn>
            </div>

            {/* Suggestions dropdown */}
            {showSuggestions && suggestions.length > 0 && (
              <div className="dd-in" style={{
                position:"absolute", left:0, right:0, top:"100%", zIndex:40,
                background:C.surface,
                border:`1px solid ${C.accentBd}`, borderTop:`1px solid ${C.border}`,
                borderRadius:`0 0 ${C.rMd} ${C.rMd}`,
                boxShadow:C.shMd, overflow:"hidden",
              }}>
                {suggestions.map((p, idx) => {
                  const inCart = cart.some((l) => l.product.id === p.id);
                  const isHl   = idx === suggHighlight;
                  return (
                    <div
                      key={p.id}
                      onMouseEnter={() => setSuggHighlight(idx)}
                      onMouseDown={(e) => { e.preventDefault(); pickSuggestion(p); }}
                      style={{
                        display:"grid", gridTemplateColumns:"1fr auto",
                        padding:mob?"12px 14px":"10px 14px", cursor:"pointer", gap:12,
                        background:isHl ? C.accentBg : C.surface,
                        borderBottom:idx<suggestions.length-1?`1px solid ${C.border}`:"none",
                        transition:"background 0.08s",
                        minHeight:mob?48:undefined,
                        alignItems:"center",
                      }}
                    >
                      <div style={{ minWidth:0 }}>
                        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                          <span style={{ fontWeight:600, fontSize:14, color:isHl?C.accent:C.text }}>
                            {p.name}
                          </span>
                          {inCart && (
                            <span style={{
                              fontSize:10, fontWeight:700, color:C.accent,
                              background:C.accentBg, border:`1px solid ${C.accentBd}`,
                              borderRadius:99, padding:"1px 6px", letterSpacing:"0.04em",
                            }}>EN CARRITO</span>
                          )}
                          {promoMap[p.id] && (
                            <span style={{
                              fontSize:10, fontWeight:700, color:"#f59e0b",
                              background:"#fef3c7", border:"1px solid #fcd34d",
                              borderRadius:99, padding:"1px 6px", letterSpacing:"0.04em",
                            }}>
                              {promoMap[p.id].discount_type === "pct"
                                ? `${promoMap[p.id].discount_value}% OFF`
                                : `PROMO`}
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize:11, color:C.mute, marginTop:2, display:"flex", gap:8 }}>
                          {p.sku && <span style={{ fontFamily:C.mono }}>{p.sku}</span>}
                          {p.category?.name && <span>{p.category.name}</span>}
                          {p.barcodes?.[0]?.code && <span style={{ fontFamily:C.mono }}>{p.barcodes[0].code}</span>}
                        </div>
                      </div>
                      <div style={{ fontWeight:800, fontSize:14, color:isHl?C.accent:C.text, fontVariantNumeric:"tabular-nums", alignSelf:"center" }}>
                        {promoMap[p.id] ? (
                          <span style={{ display:"flex", flexDirection:"column", alignItems:"flex-end" }}>
                            <span style={{ textDecoration:"line-through", fontSize:11, color:C.mute, fontWeight:500 }}>
                              ${formatCLP(toNumber(p.price))}
                            </span>
                            <span style={{ color:"#f59e0b" }}>
                              ${formatCLP(toNumber(promoMap[p.id].promo_price))}
                            </span>
                          </span>
                        ) : (
                          <>${formatCLP(toNumber(p.price))}</>
                        )}
                      </div>
                    </div>
                  );
                })}

                <div style={{
                  padding:"7px 14px", background:C.bg,
                  borderTop:`1px solid ${C.border}`,
                  fontSize:11, color:C.mute,
                  display:"flex", justifyContent:"space-between",
                }}>
                  <span>{suggestions.length} resultado{suggestions.length!==1?"s":""}</span>
                  {!mob && <span>↑↓ navegar · Enter seleccionar · Esc cerrar</span>}
                </div>
              </div>
            )}
          </div>

          {/* ── ERROR ────────────────────────────────────────────────── */}
          {err && (
            <div style={{ padding:"11px 14px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, color:C.red, fontSize:13 }}>
              <div style={{ display:"flex", alignItems:"flex-start", gap:8 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink:0, marginTop:1 }}>
                  <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <span style={{ flex:1, fontWeight:500 }}>{err}</span>
                <button onClick={() => { setErr(null); setShortages(null); }} className="xb"
                  style={{ background:"none", border:"none", color:C.red, padding:0, fontSize:16, cursor:"pointer", lineHeight:1 }}>✕</button>
              </div>
              {shortages?.length ? (
                <div style={{ marginTop:10, paddingTop:10, borderTop:`1px solid ${C.redBd}` }}>
                  <div style={{ fontSize:11, fontWeight:700, color:C.red, textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8 }}>Stock insuficiente</div>
                  {shortages.map((s) => (
                    <div key={s.product_id} style={{
                      display:"flex", justifyContent:"space-between", alignItems:"center",
                      background:"rgba(220,38,38,0.06)", borderRadius:C.r, padding:"7px 10px", marginBottom:4,
                    }}>
                      <div>
                        <span style={{ fontWeight:600 }}>{s.name ?? `Producto #${s.product_id}`}</span>
                        {s.sku && <span style={{ fontSize:11, color:C.mute, fontFamily:C.mono, marginLeft:6 }}>{s.sku}</span>}
                      </div>
                      <div style={{ fontSize:12, color:C.red }}>
                        Requerido <b>{s.required}</b> · Disponible <b>{s.available}</b>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          )}

          {/* ── CART TABLE ───────────────────────────────────────────── */}
          <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>
           <div style={{ overflowX:mob?undefined:"auto" }}>
            {/* Header (desktop only) */}
            {!mob && (
              <div style={{
                display:"grid", gridTemplateColumns:"1fr 90px 120px 90px 80px 100px 36px",
                columnGap:10, padding:"10px 16px", background:C.bg,
                borderBottom:`1px solid ${C.border}`,
                fontSize:10.5, fontWeight:700, color:C.mute,
                textTransform:"uppercase", letterSpacing:"0.08em",
              }}>
                <div>Producto</div><div>SKU</div>
                <div style={{ textAlign:"right" }}>Precio unit.</div>
                <div style={{ textAlign:"center" }}>Cant.</div>
                <div style={{ textAlign:"center" }}>Dscto.</div>
                <div style={{ textAlign:"right" }}>Subtotal</div>
                <div/>
              </div>
            )}

            {cart.length === 0 ? (
              <div style={{ padding:mob?"40px 16px":"56px 24px", textAlign:"center" }}>
                <div style={{ fontSize:mob?28:36, marginBottom:10 }}>🛒</div>
                <div style={{ fontSize:mob?14:15, fontWeight:700, color:C.text, marginBottom:4 }}>Carrito vacío</div>
                <div style={{ fontSize:mob?12:13, color:C.mute }}>Escanea un producto o búscalo por nombre</div>
              </div>
            ) : (
              <>
                {cart.map((line, i) => {
                  const p        = line.product;
                  const subtotal = lineSubtotal(line);
                  const disc     = lineDiscount(line);

                  if (mob) {
                    /* ── MOBILE CARD LAYOUT ── */
                    return (
                      <div key={p.id} style={{
                        padding:"12px 14px",
                        borderBottom:i<cart.length-1?`1px solid ${C.border}`:"none",
                      }}>
                        {/* Row 1: name + remove */}
                        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", gap:8, marginBottom:8 }}>
                          <div style={{ flex:1, minWidth:0 }}>
                            <div style={{ fontWeight:600, fontSize:13, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{p.name}</div>
                            <div style={{ fontSize:11, color:C.mute, marginTop:2 }}>
                              {p.sku && <span style={{ fontFamily:C.mono, marginRight:6 }}>{p.sku}</span>}
                              {p.category?.name ?? "Sin categoría"}
                            </div>
                          </div>
                          <button type="button" onClick={() => removeLine(p.id)} disabled={busy} className="xb" style={{
                            width:32, height:32, borderRadius:C.r, border:`1px solid ${C.border}`,
                            background:C.surface, color:C.mute, fontSize:14, flexShrink:0,
                            display:"flex", alignItems:"center", justifyContent:"center",
                          }}>✕</button>
                        </div>
                        {/* Row 2: price input + qty stepper + discount + subtotal */}
                        <div style={{ display:"flex", alignItems:"center", gap:8, flexWrap:"wrap" }}>
                          {/* Price */}
                          <input
                            value={Number.isFinite(line.unitPrice) ? String(line.unitPrice) : "0"}
                            onChange={(e) => changeUnitPrice(p.id, Number(e.target.value))}
                            inputMode="decimal"
                            style={{
                              width:80, height:36, padding:"0 8px",
                              textAlign:"right", fontWeight:700, fontSize:13,
                              border:`1px solid ${C.border}`, borderRadius:C.r,
                              background:C.bg, fontFamily:C.font,
                            }}
                            disabled={busy}
                          />
                          {/* Qty */}
                          <div style={{ display:"flex", alignItems:"center", gap:3 }}>
                            <button type="button" onClick={() => changeQty(p.id, line.qty-1)} disabled={busy} className="xb" style={{
                              width:36, height:36, borderRadius:C.r, border:`1px solid ${C.border}`,
                              background:C.surface, fontSize:15, fontWeight:700, color:C.mid,
                              display:"flex", alignItems:"center", justifyContent:"center",
                            }}>−</button>
                            <input
                              value={line.qty}
                              onChange={(e) => { const v = Number(e.target.value); changeQty(p.id, Number.isFinite(v)?v:line.qty); }}
                              style={{
                                width:40, height:36, textAlign:"center", fontSize:13, fontWeight:700,
                                border:`1px solid ${C.border}`, borderRadius:C.r, background:C.bg,
                              }}
                              inputMode="numeric" disabled={busy}
                            />
                            <button type="button" onClick={() => changeQty(p.id, line.qty+1)} disabled={busy} className="xb" style={{
                              width:36, height:36, borderRadius:C.r, border:`1px solid ${C.border}`,
                              background:C.surface, fontSize:15, fontWeight:700, color:C.mid,
                              display:"flex", alignItems:"center", justifyContent:"center",
                            }}>+</button>
                          </div>
                          {/* Discount */}
                          <DiscountCell
                            line={line}
                            onChange={(type, value) => changeLineDiscount(p.id, type, value)}
                            disabled={busy}
                          />
                          {/* Subtotal */}
                          <div style={{ marginLeft:"auto", textAlign:"right" }}>
                            {disc > 0 && (
                              <div style={{ fontSize:10, color:C.mute, textDecoration:"line-through", fontVariantNumeric:"tabular-nums" }}>
                                ${formatCLP(line.unitPrice * line.qty)}
                              </div>
                            )}
                            <div style={{ fontWeight:800, fontSize:14, fontVariantNumeric:"tabular-nums", color:disc>0?C.amber:C.text }}>
                              ${formatCLP(subtotal)}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  /* ── DESKTOP ROW LAYOUT ── */
                  return (
                    <div key={p.id} className="prow" style={{
                      display:"grid", gridTemplateColumns:"1fr 90px 120px 90px 80px 100px 36px",
                      columnGap:10, padding:"12px 16px",
                      borderBottom:i<cart.length-1?`1px solid ${C.border}`:"none",
                      alignItems:"center",
                    }}>
                      {/* Product */}
                      <div style={{ minWidth:0 }}>
                        <div style={{ fontWeight:600, fontSize:14, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{p.name}</div>
                        <div style={{ fontSize:11, color:C.mute, marginTop:2 }}>
                          {p.category?.name ?? "Sin categoría"}
                          {p.barcodes?.[0]?.code && <span style={{ fontFamily:C.mono, marginLeft:6 }}>{p.barcodes[0].code}</span>}
                        </div>
                      </div>

                      {/* SKU */}
                      <div style={{ fontFamily:C.mono, fontSize:12, color:C.mid }}>{p.sku ?? "—"}</div>

                      {/* Unit price */}
                      <div style={{ display:"flex", justifyContent:"flex-end" }}>
                        <input
                          value={Number.isFinite(line.unitPrice) ? String(line.unitPrice) : "0"}
                          onChange={(e) => changeUnitPrice(p.id, Number(e.target.value))}
                          inputMode="decimal"
                          style={{
                            width:110, height:32, padding:"0 8px",
                            textAlign:"right", fontWeight:700, fontSize:13,
                            border:`1px solid ${C.border}`, borderRadius:C.r,
                            background:C.bg, fontFamily:C.font,
                          }}
                          disabled={busy}
                        />
                      </div>

                      {/* Qty stepper */}
                      <div style={{ display:"flex", alignItems:"center", justifyContent:"center", gap:3 }}>
                        <button type="button" onClick={() => changeQty(p.id, line.qty-1)} disabled={busy} className="xb" style={{
                          width:24, height:24, borderRadius:C.r, border:`1px solid ${C.border}`,
                          background:C.surface, fontSize:13, fontWeight:700, color:C.mid,
                        }}>−</button>
                        <input
                          value={line.qty}
                          onChange={(e) => { const v = Number(e.target.value); changeQty(p.id, Number.isFinite(v)?v:line.qty); }}
                          style={{
                            width:36, height:24, textAlign:"center", fontSize:12, fontWeight:700,
                            border:`1px solid ${C.border}`, borderRadius:C.r, background:C.bg,
                          }}
                          inputMode="numeric" disabled={busy}
                        />
                        <button type="button" onClick={() => changeQty(p.id, line.qty+1)} disabled={busy} className="xb" style={{
                          width:24, height:24, borderRadius:C.r, border:`1px solid ${C.border}`,
                          background:C.surface, fontSize:13, fontWeight:700, color:C.mid,
                        }}>+</button>
                      </div>

                      {/* Discount cell */}
                      <div style={{ display:"flex", justifyContent:"center" }}>
                        <DiscountCell
                          line={line}
                          onChange={(type, value) => changeLineDiscount(p.id, type, value)}
                          disabled={busy}
                        />
                      </div>

                      {/* Subtotal */}
                      <div style={{ textAlign:"right" }}>
                        {disc > 0 && (
                          <div style={{ fontSize:11, color:C.mute, textDecoration:"line-through", fontVariantNumeric:"tabular-nums" }}>
                            ${formatCLP(line.unitPrice * line.qty)}
                          </div>
                        )}
                        <div style={{ fontWeight:800, fontSize:14, fontVariantNumeric:"tabular-nums", color:disc>0?C.amber:C.text }}>
                          ${formatCLP(subtotal)}
                        </div>
                      </div>

                      {/* Remove */}
                      <div style={{ display:"flex", justifyContent:"center" }}>
                        <button type="button" onClick={() => removeLine(p.id)} disabled={busy} className="xb" style={{
                          width:28, height:28, borderRadius:C.r, border:`1px solid ${C.border}`,
                          background:C.surface, color:C.mute, fontSize:14,
                          display:"flex", alignItems:"center", justifyContent:"center",
                        }}>✕</button>
                      </div>
                    </div>
                  );
                })}

                {/* ── Cart footer ─────────────────────────────────── */}
                <div style={{ padding:"12px 16px", background:C.bg, borderTop:`1px solid ${C.border}` }}>
                  {/* Global discount row */}
                  <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", gap:mob?8:12, marginBottom:10, flexWrap:mob?"wrap":undefined }}>
                    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.amber} strokeWidth="2.5" strokeLinecap="round">
                        <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/>
                        <line x1="7" y1="7" x2="7.01" y2="7"/>
                      </svg>
                      <span style={{ fontSize:12, fontWeight:700, color:C.mid }}>Descuento global</span>
                    </div>
                    <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                      {/* Type toggle */}
                      <div style={{ display:"flex", gap:3 }}>
                        {(["none","pct","amt"] as const).map((t) => (
                          <button key={t} type="button" onClick={() => { setGlobalDiscountType(t); if(t==="none") setGlobalDiscountValue(0); }} className="xb" style={{
                            height:26, padding:"0 8px", borderRadius:C.r, fontSize:11, fontWeight:600,
                            border:`1px solid ${globalDiscountType===t ? C.accent : C.border}`,
                            background:globalDiscountType===t ? C.accentBg : C.surface,
                            color:globalDiscountType===t ? C.accent : C.mute,
                          }}>
                            {t==="none"?"Ninguno":t==="pct"?"%":"$"}
                          </button>
                        ))}
                      </div>
                      {globalDiscountType !== "none" && (
                        <input
                          type="number" min={0}
                          max={globalDiscountType==="pct"?100:undefined}
                          value={globalDiscountValue || ""}
                          onChange={(e) => setGlobalDiscountValue(Math.max(0, Number(e.target.value)))}
                          placeholder={globalDiscountType==="pct"?"10":"500"}
                          style={{
                            width:80, height:26, padding:"0 8px",
                            border:`1px solid ${C.border}`, borderRadius:C.r,
                            fontSize:12, fontWeight:700, textAlign:"right",
                          }}
                        />
                      )}
                      {globalDiscountAmt > 0 && (
                        <span style={{ fontSize:12, fontWeight:700, color:C.amber }}>
                          -${formatCLP(globalDiscountAmt)}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Totals summary */}
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:mob?"flex-start":"center", flexDirection:mob?"column":"row", gap:mob?6:0 }}>
                    <div style={{ fontSize:12, color:C.mute, display:"flex", gap:mob?8:14, flexWrap:"wrap" }}>
                      <span>{itemsCount} unidad{itemsCount!==1?"es":""}</span>
                      {(totalLineDiscounts + globalDiscountAmt) > 0 && (
                        <span style={{ color:C.amber, fontWeight:600 }}>
                          Ahorro total: -${formatCLP(totalLineDiscounts + globalDiscountAmt)}
                        </span>
                      )}
                    </div>
                    <span style={{ fontSize:15, fontWeight:800, color:C.text, fontVariantNumeric:"tabular-nums", alignSelf:mob?"flex-end":undefined }}>
                      Total:{" "}
                      <span style={{ color:C.accent, fontSize:18 }}>${formatCLP(total)}</span>
                    </span>
                  </div>
                </div>
              </>
            )}
           </div>
          </div>

          {/* ── NOTE ─────────────────────────────────────────────────── */}
          {cart.length > 0 && (
            <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>
              <button
                type="button"
                onClick={() => setShowNote((o) => !o)}
                className="xb"
                style={{
                  width:"100%", padding:"10px 16px", background:"transparent", border:"none", cursor:"pointer",
                  display:"flex", alignItems:"center", justifyContent:"space-between", gap:8,
                }}
              >
                <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={saleNote ? C.accent : C.mute} strokeWidth="2.5" strokeLinecap="round">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                  <span style={{ fontSize:13, fontWeight:600, color:saleNote ? C.accent : C.mid }}>
                    Nota de venta {saleNote ? `· "${saleNote.slice(0,30)}${saleNote.length>30?"…":""}"` : "(opcional)"}
                  </span>
                </div>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round"
                  style={{ transition:"transform 0.15s", transform:showNote?"rotate(180deg)":"none" }}>
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </button>
              {showNote && (
                <div style={{ padding:"0 16px 14px" }}>
                  <textarea
                    value={saleNote}
                    onChange={(e) => setSaleNote(e.target.value)}
                    placeholder="Ej: Mesa 4, Pedido #320, Nombre del cliente, instrucciones especiales…"
                    rows={3}
                    maxLength={300}
                    style={{
                      width:"100%", padding:"10px 12px", resize:"vertical",
                      border:`1px solid ${C.border}`, borderRadius:C.r,
                      fontSize:13, lineHeight:1.55, fontFamily:C.font,
                    }}
                    autoFocus
                  />
                  <div style={{ fontSize:11, color:C.mute, textAlign:"right", marginTop:4 }}>
                    {saleNote.length}/300
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── RIGHT: PAYMENT PANEL ───────────────────────────────────── */}
        <div style={{ display:"flex", flexDirection:"column", gap:12, position:"sticky", top:mob?undefined:24, bottom:mob?0:undefined, zIndex:mob?30:undefined, ...(mob?{background:C.bg, margin:"0 -12px", padding:"12px 12px 16px", borderTop:`1px solid ${C.border}`, boxShadow:"0 -4px 12px rgba(0,0,0,0.06)"}:{}) }}>

          {/* Summary */}
          <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>
            <div style={{ padding:"12px 18px", borderBottom:`1px solid ${C.border}`, background:C.bg }}>
              <div style={{ fontSize:11, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.07em" }}>Resumen</div>
            </div>
            <div style={{ padding:"14px 18px", display:"flex", flexDirection:"column", gap:9 }}>
              <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, color:C.mid }}>
                <span>Productos</span><span style={{ fontWeight:600, color:C.text }}>{cart.length}</span>
              </div>
              <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, color:C.mid }}>
                <span>Unidades</span><span style={{ fontWeight:600, color:C.text }}>{itemsCount}</span>
              </div>
              <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, color:C.mid }}>
                <span>Bodega</span><span style={{ fontWeight:600, color:C.text, fontSize:12 }}>{selectedWarehouseName}</span>
              </div>
              {(totalLineDiscounts + globalDiscountAmt) > 0 && (
                <div style={{ display:"flex", justifyContent:"space-between", fontSize:13, color:C.amber }}>
                  <span>Descuentos</span>
                  <span style={{ fontWeight:700 }}>-${formatCLP(totalLineDiscounts + globalDiscountAmt)}</span>
                </div>
              )}
              {saleNote && (
                <div style={{
                  fontSize:12, color:C.mid, background:C.bg,
                  border:`1px solid ${C.border}`, borderRadius:C.r,
                  padding:"6px 10px", fontStyle:"italic",
                }}>
                  "{saleNote.slice(0,60)}{saleNote.length>60?"…":""}"
                </div>
              )}
              <div style={{ height:1, background:C.border }}/>
              <div style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline" }}>
                <span style={{ fontSize:13, color:C.mid }}>Total</span>
                <span style={{ fontSize:22, fontWeight:800, color:C.accent, letterSpacing:"-0.03em", fontVariantNumeric:"tabular-nums" }}>
                  ${formatCLP(total)}
                </span>
              </div>
            </div>
          </div>

          {/* ═══ PAGO ═══ */}
          <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh }}>

            {/* Header */}
            <div style={{ padding:"12px 18px", borderBottom:`1px solid ${C.border}`, background:C.bg, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
              <div style={{ fontSize:11, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.07em" }}>Método de pago</div>
              {payRows.length > 1 && pendingAmount > 0 && (
                <div style={{ fontSize:11, fontWeight:700, color:C.amber }}>Resta: ${formatCLP(pendingAmount)}</div>
              )}
            </div>

            <div style={{ padding:"14px 18px", display:"flex", flexDirection:"column", gap:12 }}>

              {/* ── Método principal (radio — solo 1 activo si no es split) ── */}
              {payRows.length === 1 && (
                <>
                  <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:6 }}>
                    {PAY_METHODS.map(m => {
                      const active = payRows[0].method === m.value;
                      return (
                        <button key={m.value} type="button"
                          onClick={() => setPayRows([{ method: m.value, amount: payRows[0].amount }])}
                          style={{
                            display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center",
                            gap:4, padding:"12px 4px", borderRadius:C.r, cursor:"pointer", fontFamily:"inherit",
                            fontSize:11, fontWeight:700, transition:"all .15s ease",
                            border: active ? `2px solid ${C.accent}` : `1px solid ${C.border}`,
                            background: active ? C.accentBg : C.surface,
                            color: active ? C.accent : C.mid,
                          }}>
                          <span style={{ fontSize:22 }}>{m.icon}</span>
                          {m.label}
                        </button>
                      );
                    })}
                  </div>

                  {/* Input monto único */}
                  <div style={{ position:"relative" }}>
                    <input
                      value={payRows[0].amount}
                      onChange={e => setPayRows([{ ...payRows[0], amount: e.target.value }])}
                      placeholder={`$${formatCLP(grandTotal)}`}
                      inputMode="decimal"
                      style={{
                        width:"100%", height:52, padding:"0 52px 0 16px", boxSizing:"border-box",
                        border:`2px solid ${payRows[0].amount ? C.accent : C.border}`,
                        borderRadius:C.rMd, fontSize:22, fontWeight:800, textAlign:"right",
                        background: payRows[0].amount ? C.accentBg : C.bg, outline:"none", fontFamily:C.mono,
                      }}
                    />
                    <button type="button" title="Cobrar total"
                      onClick={() => setPayRows([{ ...payRows[0], amount: String(grandTotal) }])}
                      disabled={grandTotal <= 0}
                      style={{
                        position:"absolute", right:8, top:"50%", transform:"translateY(-50%)",
                        height:36, width:36, borderRadius:8, border:"none",
                        background: grandTotal > 0 ? C.accent : C.border, color:"#fff",
                        cursor: grandTotal > 0 ? "pointer" : "default", display:"flex",
                        alignItems:"center", justifyContent:"center",
                        opacity: grandTotal <= 0 ? 0.3 : 1,
                      }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                    </button>
                  </div>

                  {/* Botón dividir pago */}
                  <button type="button"
                    onClick={() => {
                      const used = payRows[0].method;
                      const next = PAY_METHODS.find(m => m.value !== used);
                      if (next) setPayRows(prev => [...prev, { method: next.value, amount: "" }]);
                    }}
                    style={{
                      background:"none", border:`1px dashed ${C.borderMd}`, borderRadius:C.r,
                      padding:"8px 0", cursor:"pointer", color:C.mid, fontSize:12,
                      fontWeight:600, fontFamily:"inherit", textAlign:"center",
                    }}>
                    + Dividir pago
                  </button>
                </>
              )}

              {/* ── Pago dividido (múltiples métodos) ── */}
              {payRows.length > 1 && (
                <>
                  {payRows.map((row, i) => {
                    const meta = PAY_METHODS.find(m => m.value === row.method)!;
                    const used = new Set(payRows.map(r => r.method));
                    const available = PAY_METHODS.filter(m => m.value === row.method || !used.has(m.value));
                    return (
                      <div key={`pay-${i}`} style={{ display:"flex", gap:8, alignItems:"center" }}>
                        {/* Selector de método */}
                        <select
                          value={row.method}
                          onChange={e => setPayRows(prev => prev.map((r, j) => j === i ? { ...r, method: e.target.value } : r))}
                          style={{
                            width:130, height:44, padding:"0 8px", border:`1px solid ${C.border}`,
                            borderRadius:C.r, fontSize:13, fontWeight:600, background:C.surface,
                            fontFamily:"inherit", cursor:"pointer",
                          }}>
                          {available.map(m => (
                            <option key={m.value} value={m.value}>{m.icon} {m.label}</option>
                          ))}
                        </select>
                        {/* Monto */}
                        <div style={{ flex:1, position:"relative" }}>
                          <input
                            value={row.amount}
                            onChange={e => setPayRows(prev => prev.map((r, j) => j === i ? { ...r, amount: e.target.value } : r))}
                            placeholder="$0"
                            inputMode="decimal"
                            style={{
                              width:"100%", height:44, padding:"0 44px 0 12px", boxSizing:"border-box",
                              border:`1px solid ${row.amount ? C.accent : C.border}`,
                              borderRadius:C.r, fontSize:18, fontWeight:700, textAlign:"right",
                              background: row.amount ? C.accentBg : C.bg, outline:"none", fontFamily:C.mono,
                            }}
                          />
                          <button type="button" title="Cobrar restante"
                            onClick={() => setPayRows(prev => prev.map((r, j) => j === i ? { ...r, amount: String((Number(r.amount)||0) + pendingAmount) } : r))}
                            disabled={pendingAmount <= 0}
                            style={{
                              position:"absolute", right:4, top:"50%", transform:"translateY(-50%)",
                              height:32, width:32, borderRadius:6, border:"none",
                              background: pendingAmount > 0 ? C.accent : C.border, color:"#fff",
                              cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center",
                              opacity: pendingAmount <= 0 ? 0.3 : 1,
                            }}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                          </button>
                        </div>
                        {/* Quitar */}
                        <button type="button"
                          onClick={() => setPayRows(prev => prev.filter((_, j) => j !== i))}
                          style={{
                            width:32, height:32, borderRadius:6, border:`1px solid ${C.border}`,
                            background:C.bg, color:C.mute, cursor:"pointer", display:"flex",
                            alignItems:"center", justifyContent:"center", fontSize:14, flexShrink:0,
                          }}>✕</button>
                      </div>
                    );
                  })}
                  {/* Agregar otro método */}
                  {payRows.length < PAY_METHODS.length && (
                    <button type="button"
                      onClick={() => {
                        const used = new Set(payRows.map(r => r.method));
                        const next = PAY_METHODS.find(m => !used.has(m.value));
                        if (next) setPayRows(prev => [...prev, { method: next.value, amount: "" }]);
                      }}
                      style={{
                        background:"none", border:`1px dashed ${C.borderMd}`, borderRadius:C.r,
                        padding:"7px 0", cursor:"pointer", color:C.mid, fontSize:12,
                        fontWeight:600, fontFamily:"inherit", textAlign:"center",
                      }}>
                      + Agregar método
                    </button>
                  )}
                </>
              )}

              {/* ── Propina ── */}
              <div style={{ display:"flex", alignItems:"center", gap:10, paddingTop:10, borderTop:`1px solid ${C.border}` }}>
                <div style={{ flexShrink:0, display:"flex", alignItems:"center", gap:6, fontSize:13, fontWeight:600, color:C.mid }}>
                  <span style={{ fontSize:16 }}>🤝</span> Propina
                </div>
                <input
                  value={tipAmount}
                  onChange={e => setTipAmount(e.target.value)}
                  placeholder="$0 (opcional)"
                  inputMode="decimal"
                  style={{
                    flex:1, height:mob?44:36, padding:"0 12px",
                    border:`1px solid ${tipAmount && Number(tipAmount) > 0 ? C.amberBd : C.border}`,
                    borderRadius:C.r, fontSize:14, fontWeight:600, textAlign:"right",
                    background: tipAmount && Number(tipAmount) > 0 ? C.amberBg : C.bg,
                  }}
                />
              </div>
              {tip > 0 && (
                <div style={{ padding:"8px 12px", borderRadius:C.r, background:C.amberBg, border:`1px solid ${C.amberBd}`, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                  <span style={{ fontSize:12, color:C.amber, fontWeight:600 }}>Total con propina</span>
                  <span style={{ fontSize:16, fontWeight:800, color:C.amber, fontVariantNumeric:"tabular-nums" }}>${formatCLP(grandTotal)}</span>
                </div>
              )}

              {/* ── Vuelto ── */}
              {change !== null && change > 0 && (
                <div style={{ padding:"10px 12px", borderRadius:C.r, background:C.greenBg, border:`1px solid ${C.greenBd}`, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                  <span style={{ fontSize:12, color:C.green, fontWeight:600 }}>Vuelto</span>
                  <span style={{ fontSize:20, fontWeight:800, color:C.green, fontVariantNumeric:"tabular-nums" }}>${formatCLP(change)}</span>
                </div>
              )}
            </div>
          </div>

          {/* Confirm */}
          <Btn variant="primary" size="lg" full onClick={confirmSale}
            disabled={busy || !!meErr || cart.length === 0 || !warehouseId || totalPaid < grandTotal}>
            {busy ? <><Spinner size={16}/>Procesando…</> : (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                Confirmar venta · ${formatCLP(grandTotal)}
              </>
            )}
          </Btn>

          {lastSaleId && (
            <Link href={`/dashboard/pos/receipt/${lastSaleId}`} style={{
              display:"flex", alignItems:"center", justifyContent:"center", gap:6,
              fontSize:13, fontWeight:600, color:C.mid, textDecoration:"none", padding:"6px 0",
            }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
              </svg>
              Ver último recibo
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}