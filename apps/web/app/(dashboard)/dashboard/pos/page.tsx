"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { formatCLP } from "@/lib/format";
import { useIsMobile } from "@/hooks/useIsMobile";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { Btn, Skeleton } from "@/components/ui";
import type { Me } from "@/lib/me";

import { SearchBar } from "@/components/pos/SearchBar";
import { CartTable } from "@/components/pos/CartTable";
import { PaymentSection } from "@/components/pos/PaymentSection";
import type { Warehouse, Product, CartLine, Shortage, PromoInfo, PosPayRow } from "@/components/pos/types";
import { toNumber, lineDiscount, lineSubtotal } from "@/components/pos/types";

// ─── Storage keys & draft helpers ────────────────────────────────────────────

const POS_WAREHOUSE_STORAGE_KEY = "pos_warehouse_id";
const POS_CART_STORAGE_KEY = "pos_cart_draft";

type CartDraft = {
  cart: CartLine[];
  globalDiscountType: "none"|"pct"|"amt";
  globalDiscountValue: number;
  saleNote: string;
  payRows: PosPayRow[];
  tipAmount: string;
};

function saveCartDraft(d: CartDraft) {
  try { localStorage.setItem(POS_CART_STORAGE_KEY, JSON.stringify(d)); } catch {}
}
function loadCartDraft(): CartDraft | null {
  try {
    const raw = localStorage.getItem(POS_CART_STORAGE_KEY);
    if (!raw) return null;
    const draft = JSON.parse(raw);
    if (!draft?.cart || !Array.isArray(draft.cart)) return null;
    return draft;
  } catch {
    localStorage.removeItem(POS_CART_STORAGE_KEY);
    return null;
  }
}
function clearCartDraft() {
  try { localStorage.removeItem(POS_CART_STORAGE_KEY); } catch {}
}

// ─── CSS ─────────────────────────────────────────────────────────────────────

const PAGE_CSS = `
.toast-in{animation:toastIn 0.22s cubic-bezier(0.34,1.38,0.64,1) both}
@keyframes toastIn{from{opacity:0;transform:translateY(-8px) scale(0.97)}to{opacity:1;transform:none}}
.dd-in{animation:ddIn 0.14s ease both}
@keyframes ddIn{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
`;

// ─── Main ────────────────────────────────────────────────────────────────────

export default function PosPage() {
  useGlobalStyles(PAGE_CSS);
  const mob = useIsMobile();
  const inputRef = useRef<HTMLInputElement | null>(null);

  // ── Core state ─────────────────────────────────────────────────────────────
  const [me, setMe]                 = useState<Me | null>(null);
  const [meErr, setMeErr]           = useState<string | null>(null);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId, setWarehouseId] = useState<number | null>(null);

  const [cartLoaded, setCartLoaded]     = useState(false);
  const [draftRecovered, setDraftRecovered] = useState(false);
  const [cart, setCart]                 = useState<CartLine[]>([]);
  const [busy, setBusy]                 = useState(false);
  const [err, setErr]                   = useState<string | null>(null);
  const [shortages, setShortages]       = useState<Shortage[] | null>(null);
  const [toast, setToast]               = useState<string | null>(null);
  const [paymentWarn, setPaymentWarn]   = useState<string | null>(null);
  const [lastSaleId, setLastSaleId]     = useState<number | null>(null);
  const [lastSaleNumber, setLastSaleNumber] = useState<number | null>(null);

  // Global discount
  const [globalDiscountType, setGlobalDiscountType]   = useState<"none"|"pct"|"amt">("none");
  const [globalDiscountValue, setGlobalDiscountValue] = useState(0);

  // Sale note
  const [saleNote, setSaleNote] = useState("");
  const [showNote, setShowNote] = useState(false);

  // Active promotions cache
  const [promoMap, setPromoMap] = useState<Record<number, PromoInfo>>({});

  // Payment
  const [payRows, setPayRows] = useState<PosPayRow[]>([{ method: "cash", amount: "" }]);
  const [tipAmount, setTipAmount] = useState("");

  useEffect(() => { inputRef.current?.focus(); }, []);

  // ── Restore cart draft from localStorage ───────────────────────────────────
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

  // ── Persist cart draft to localStorage on changes ──────────────────────────
  useEffect(() => {
    if (!cartLoaded) return;
    if (cart.length === 0) { clearCartDraft(); return; }
    saveCartDraft({ cart, globalDiscountType, globalDiscountValue, saleNote, payRows, tipAmount });
  }, [cartLoaded, cart, globalDiscountType, globalDiscountValue, saleNote, payRows, tipAmount]);

  // ── /core/me/ ──────────────────────────────────────────────────────────────
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

  // ── /core/warehouses/ ──────────────────────────────────────────────────────
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

  const totalPaid     = useMemo(() => payRows.reduce((s, r) => s + (Number(r.amount) || 0), 0), [payRows]);
  const tip           = useMemo(() => Math.max(0, Number(tipAmount) || 0), [tipAmount]);
  const grandTotal    = useMemo(() => total + tip, [total, tip]);
  const pendingAmount = useMemo(() => Math.max(0, grandTotal - totalPaid), [grandTotal, totalPaid]);
  const change        = useMemo(() => totalPaid > grandTotal ? totalPaid - grandTotal : null, [totalPaid, grandTotal]);

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

  // ── Promo merge callback ───────────────────────────────────────────────────
  const handlePromosFound = useCallback((map: Record<number, PromoInfo>) => {
    setPromoMap((prev) => ({ ...prev, ...map }));
  }, []);

  // ── Confirm sale ───────────────────────────────────────────────────────────

  const confirmSale = useCallback(async () => {
    if (!warehouseId)      { setErr("No hay bodega seleccionada.");  return; }
    if (cart.length === 0) { setErr("El carrito esta vacio.");       return; }
    if (totalPaid < grandTotal) { setErr(`Falta pagar $${formatCLP(grandTotal - totalPaid)}.`); return; }

    setBusy(true); setErr(null); setShortages(null); setLastSaleId(null);
    try {
      const paymentBreakdown = payRows
        .filter(r => Number(r.amount) > 0)
        .map(r => ({ method: r.method, amount: Number(r.amount) }));

      const payload: any = {
        idempotency_key: crypto.randomUUID(),
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
        payments: paymentBreakdown,
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

      clearCart(); setTipAmount("");
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

  const defaultValidity       = useMemo(() => {
    if (!me?.default_warehouse_id) return "none" as const;
    return warehouses.some((w) => w.id === me.default_warehouse_id) ? "valid" as const : "invalid" as const;
  }, [me?.default_warehouse_id, warehouses]);
  const selectedWarehouseName = warehouses.find((w) => w.id === warehouseId)?.name ?? "—";

  // ─────────────────────────────── RENDER ──────────────────────────────────

  if (!me && !meErr) return (
    <div style={{ fontFamily:C.font, background:C.bg, minHeight:"100vh", padding:mob?"16px 12px":"24px 28px", display:"flex", flexDirection:"column", gap:16 }}>
      <Skeleton style={{ height:40, borderRadius:8 }} />
      <div style={{ display:"grid", gridTemplateColumns:mob?"1fr":"1fr 360px", gap:16 }}>
        <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
          <Skeleton style={{ height:48, borderRadius:8 }} />
          <Skeleton style={{ height:300, borderRadius:8 }} />
        </div>
        <Skeleton style={{ height:360, borderRadius:8 }} />
      </div>
    </div>
  );

  return (
    <div style={{ fontFamily:C.font, color:C.text, background:C.bg, minHeight:"100vh", padding:mob?"16px 12px":"24px 28px", display:"flex", flexDirection:"column", gap:16 }}>

      {/* ── DRAFT RECOVERED BANNER ──────────────────────────────────── */}
      {draftRecovered && (
        <div style={{
          padding:"10px 14px", borderRadius:C.r, border:`1px solid ${C.greenBd}`,
          background:C.greenBg, color:C.green, fontSize:13, fontWeight:500,
          display:"flex", alignItems:"center", justifyContent:"space-between", gap:8,
        }}>
          <span>🛒 Se recupero un carrito guardado con {cart.length} producto{cart.length !== 1 ? "s" : ""}.</span>
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
            setLastSaleId(null);
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

          <SearchBar
            onSelect={addToCart}
            warehouseId={warehouseId}
            disabled={!!meErr}
            busy={busy}
            mob={mob}
            cart={cart}
            promoMap={promoMap}
            onPromosFound={handlePromosFound}
            inputRef={inputRef}
          />

          {/* ── ERROR (sale-level) ─────────────────────────────────── */}
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

          <CartTable
            cart={cart}
            onUpdateQty={changeQty}
            onUpdateUnitPrice={changeUnitPrice}
            onRemove={removeLine}
            onUpdateDiscount={changeLineDiscount}
            mob={mob}
            promoMap={promoMap}
            busy={busy}
            globalDiscountType={globalDiscountType}
            globalDiscountValue={globalDiscountValue}
            globalDiscountAmt={globalDiscountAmt}
            onGlobalDiscountTypeChange={setGlobalDiscountType}
            onGlobalDiscountValueChange={setGlobalDiscountValue}
            total={total}
            itemsCount={itemsCount}
            totalLineDiscounts={totalLineDiscounts}
            saleNote={saleNote}
            showNote={showNote}
            onShowNoteToggle={() => setShowNote((o) => !o)}
            onNoteChange={setSaleNote}
          />
        </div>

        {/* ── RIGHT: PAYMENT PANEL ──────────────────────────────────── */}
        <PaymentSection
          cart={cart}
          mob={mob}
          busy={busy}
          meErr={meErr}
          warehouseId={warehouseId}
          selectedWarehouseName={selectedWarehouseName}
          itemsCount={itemsCount}
          totalLineDiscounts={totalLineDiscounts}
          globalDiscountAmt={globalDiscountAmt}
          total={total}
          saleNote={saleNote}
          payRows={payRows}
          onPayRowsChange={setPayRows}
          tipAmount={tipAmount}
          onTipChange={setTipAmount}
          tip={tip}
          grandTotal={grandTotal}
          totalPaid={totalPaid}
          pendingAmount={pendingAmount}
          change={change}
          onSubmit={confirmSale}
          lastSaleId={lastSaleId}
          lastSaleNumber={lastSaleNumber}
        />
      </div>
    </div>
  );
}
