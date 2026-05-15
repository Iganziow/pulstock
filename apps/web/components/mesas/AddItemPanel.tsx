"use client";

import { useState, useEffect, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { MesaBtn } from "./MesaBtn";
import { Product } from "./types";
import { fmt } from "./helpers";

interface AddItemPanelProps {
  orderId: number;
  onAdded: () => void;
}

interface CartItem {
  product: Product;
  qty: number;
  unit_price: string;
  note: string;
}

export function AddItemPanel({ orderId, onAdded }: AddItemPanelProps) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Product[]>([]);
  const [searching, setSearching] = useState(false);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [editingNote, setEditingNote] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [promoPriceMap, setPromoPriceMap] = useState<Map<number, string>>(new Map());
  // (15/05/26) BUSQUEDA HIBRIDA — auto-detect por tamaño tenant.
  // Tenants chicos (<500): cargamos TODO al montar, filtro local instant.
  // Tenants grandes (>=500): backend search con debounce (no podemos
  // cargar 5000+ productos al abrir cada vez). Pulstock es SaaS y debe
  // escalar — el threshold protege a tenants grandes futuros.
  const SMALL_TENANT_THRESHOLD = 500;
  const [allProducts, setAllProducts] = useState<Product[]>([]);
  const [hasAllProducts, setHasAllProducts] = useState(false);

  // Cargar primera página al montar — count del backend define el modo.
  useEffect(() => {
    apiFetch(`/catalog/products/?page_size=${SMALL_TENANT_THRESHOLD}&is_active=true`)
      .then((data: any) => {
        const list: Product[] = data?.results || data || [];
        const totalCount = data?.count ?? list.length;
        setAllProducts(list);
        const allLoaded = totalCount <= list.length;
        setHasAllProducts(allLoaded);

        // Bulk fetch promos solo si tenemos todos (tenant chico). Si es
        // tenant grande, cargamos promos por search en backend.
        if (allLoaded && list.length > 0) {
          const ids = list.map(p => p.id).join(",");
          apiFetch(`/promotions/active-for-products/?product_ids=${ids}`)
            .then((promoData: any) => {
              const next = new Map<number, string>();
              for (const promo of promoData?.results ?? []) {
                if (promo.product_id && promo.promo_price) {
                  next.set(promo.product_id, String(promo.promo_price));
                }
              }
              setPromoPriceMap(next);
            })
            .catch(() => {});
        }
      })
      .catch(() => setAllProducts([]));
  }, []);

  // Filtro hibrido: local si tenant chico, backend con debounce si grande.
  useEffect(() => {
    const qq = q.trim().toLowerCase();
    if (!qq) { setResults([]); return; }

    // ── MODO LOCAL (tenant chico) ──
    if (hasAllProducts) {
      setSearching(false);
      const filtered = allProducts.filter(p => {
        const name = (p.name || "").toLowerCase();
        const sku = ((p as any).sku || "").toLowerCase();
        const barcodes = (p as any).barcodes || [];
        const barcodeMatch = Array.isArray(barcodes) && barcodes.some((b: any) => {
          const code = typeof b === "string" ? b : (b?.code || "");
          return code.toLowerCase().includes(qq);
        });
        return name.includes(qq) || sku.includes(qq) || barcodeMatch;
      }).slice(0, 15);
      setResults(filtered);
      return;
    }

    // ── MODO BACKEND (tenant grande) ──
    setSearching(true);
    clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      try {
        const data = await apiFetch(`/catalog/products/?q=${encodeURIComponent(qq)}&is_active=true&page_size=15`);
        const list: Product[] = data?.results || data || [];
        setResults(list);
        // Cargar promos de los resultados (ya no precargamos todos)
        if (list.length > 0) {
          const ids = list.map(p => p.id).join(",");
          apiFetch(`/promotions/active-for-products/?product_ids=${ids}`)
            .then((promoData: any) => {
              setPromoPriceMap(prev => {
                const next = new Map(prev);
                for (const promo of promoData?.results ?? []) {
                  if (promo.product_id && promo.promo_price) {
                    next.set(promo.product_id, String(promo.promo_price));
                  }
                }
                return next;
              });
            })
            .catch(() => {});
        }
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 250);

    return () => clearTimeout(debounce.current);
  }, [q, allProducts, hasAllProducts]);

  // Sin async — instant. Lee promo del map pre-cargado o cae al precio
  // normal. Antes hacía apiFetch por cada click → 1-2s de delay.
  function addToCart(p: Product) {
    setQ(""); setResults([]);
    const unit_price = promoPriceMap.get(p.id) ?? (p.price || "0");
    setCart(prev => {
      const existing = prev.find(c => c.product.id === p.id);
      if (existing) return prev.map(c => c.product.id === p.id ? { ...c, qty: c.qty + 1 } : c);
      return [...prev, { product: p, qty: 1, unit_price, note: "" }];
    });
    inputRef.current?.focus();
  }

  async function save() {
    if (!cart.length) return;
    setSaving(true); setErr("");
    try {
      await apiFetch(`/tables/orders/${orderId}/add-lines/`, {
        method: "POST",
        body: JSON.stringify({ lines: cart.map(c => ({ product_id: c.product.id, qty: c.qty, unit_price: c.unit_price, note: c.note })) }),
      });
      setCart([]);
      onAdded();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Error al agregar");
    } finally { setSaving(false); }
  }

  const cartTotal = cart.reduce((s, c) => s + Math.round(Number(c.unit_price) * c.qty), 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Search bar */}
      <div style={{ position: "relative" }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "10px 14px",
          border: `2px solid ${q ? C.accent : C.border}`,
          borderRadius: 10, background: C.surface,
          transition: "border-color .15s",
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={q ? C.accent : C.mute} strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink: 0 }}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input ref={inputRef} value={q} onChange={e => setQ(e.target.value)} placeholder="Buscar producto, SKU o barcode..."
            autoFocus
            style={{ flex: 1, border: "none", background: "transparent", fontSize: 14, fontFamily: C.font, outline: "none", color: C.text }} />
          {searching && <Spinner size={14} />}
          {q && (
            <button type="button" onClick={() => { setQ(""); setResults([]); inputRef.current?.focus(); }}
              aria-label="Limpiar" style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 2, display: "flex" }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          )}
        </div>

        {/* Search results dropdown */}
        {results.length > 0 && (
          <div style={{
            position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 20,
            background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,.1)",
            maxHeight: 280, overflowY: "auto",
          }}>
            {results.map((p, i) => {
              const inCart = cart.some(c => c.product.id === p.id);
              return (
                <div key={p.id} onClick={() => addToCart(p)} style={{
                  padding: "10px 14px", cursor: "pointer",
                  borderBottom: i < results.length - 1 ? `1px solid ${C.border}` : "none",
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  background: inCart ? "#EEF2FF" : "transparent",
                  transition: "background .1s",
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{p.name}</div>
                    <div style={{ fontSize: 10, color: C.mute, fontFamily: C.mono }}>{p.sku}</div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                    <span style={{ fontWeight: 800, fontSize: 13, color: C.accent }}>${fmt(p.price)}</span>
                    {inCart && (
                      <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 6, background: C.accentBg, color: C.accent, border: `1px solid ${C.accentBd}` }}>
                        En carrito
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Cart items */}
      {cart.length > 0 && (
        <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden", background: C.surface }}>
          {cart.map((c, i) => (
            <div key={c.product.id} style={{
              padding: "10px 12px",
              borderBottom: i < cart.length - 1 ? `1px solid ${C.border}` : "none",
              background: editingNote === i ? "#FFFBEB" : "transparent",
            }}>
              {/* Main row */}
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {/* Product info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: C.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {c.product.name}
                  </div>
                  <div style={{ fontSize: 10, color: C.mute }}>${fmt(c.unit_price)} c/u</div>
                </div>

                {/* Qty controls. Mario lo pidió: "los gramos de chocolate
                    uno pueda poner el número exacto con el teclado no más,
                    seria mas rapido". Productos vendidos por gramo (chocolate
                    a granel, jamón, queso, etc.) tenían que tocarse + 100
                    veces para llegar a 100g. Ahora el centro es un input
                    editable: tipean "100" y listo. Los botones siguen
                    funcionando para ajustes finos (+1/-1). step="any"
                    permite cantidades fraccionarias (ej: 0.5 kg). */}
                <div style={{ display: "flex", alignItems: "center", gap: 2, background: C.bg, borderRadius: 8, border: `1px solid ${C.border}`, padding: 2 }}>
                  <button type="button" aria-label="Disminuir" onClick={() => setCart(prev => prev.map((x, j) => j === i ? { ...x, qty: Math.max(1, x.qty - 1) } : x))}
                    style={{ width: 34, height: 34, borderRadius: 6, border: "none", background: "transparent", cursor: "pointer", fontWeight: 800, fontSize: 16, color: C.mid, display: "flex", alignItems: "center", justifyContent: "center" }}>−</button>
                  <input
                    type="number"
                    inputMode="decimal"
                    min="1"
                    step="any"
                    value={c.qty}
                    onChange={e => {
                      const raw = e.target.value;
                      // Permitir vacío temporalmente mientras tipean (no
                      // resetear a 1 hasta blur), pero no aceptar negativos.
                      if (raw === "") {
                        setCart(prev => prev.map((x, j) => j === i ? { ...x, qty: 0 } : x));
                        return;
                      }
                      const n = Number(raw);
                      if (!isNaN(n) && n >= 0) {
                        setCart(prev => prev.map((x, j) => j === i ? { ...x, qty: n } : x));
                      }
                    }}
                    onBlur={() => {
                      // Si quedó en 0 o vacío al perder foco, asumir 1
                      // (evitar líneas con qty 0 que romperían el cobro).
                      if (c.qty <= 0) {
                        setCart(prev => prev.map((x, j) => j === i ? { ...x, qty: 1 } : x));
                      }
                    }}
                    onFocus={e => e.target.select()}
                    style={{
                      width: 56, textAlign: "center",
                      border: "none", background: "transparent",
                      fontSize: 14, fontWeight: 800, color: C.text,
                      fontFamily: C.font, outline: "none",
                      // Quitar las flechitas nativas del number input — ocupan
                      // espacio y el usuario ya tiene los botones [-] [+].
                      MozAppearance: "textfield",
                    }}
                    className="qty-input-no-spin"
                    aria-label={`Cantidad de ${c.product.name}`}
                  />
                  <button type="button" aria-label="Aumentar" onClick={() => setCart(prev => prev.map((x, j) => j === i ? { ...x, qty: x.qty + 1 } : x))}
                    style={{ width: 34, height: 34, borderRadius: 6, border: "none", background: C.accent, cursor: "pointer", fontWeight: 800, fontSize: 16, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>+</button>
                </div>

                {/* Line total */}
                <div style={{ fontWeight: 800, fontSize: 13, color: C.text, minWidth: 55, textAlign: "right" }}>
                  ${fmt(Number(c.unit_price) * c.qty)}
                </div>

                {/* Actions */}
                <div style={{ display: "flex", gap: 2 }}>
                  <button type="button" aria-label="Nota" onClick={() => setEditingNote(editingNote === i ? null : i)}
                    style={{ width: 32, height: 32, borderRadius: 6, border: "none", background: c.note ? C.amberBg : "transparent", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={c.note ? C.amber : C.mute} strokeWidth="2.5" strokeLinecap="round">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                  </button>
                  <button type="button" aria-label="Eliminar" onClick={() => { setCart(prev => prev.filter((_, j) => j !== i)); if (editingNote === i) setEditingNote(null); }}
                    style={{ width: 32, height: 32, borderRadius: 6, border: "none", background: "transparent", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={C.red} strokeWidth="2.5" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </div>
              </div>

              {/* Note input (expandable) */}
              {editingNote === i && (
                <div style={{ marginTop: 6 }}>
                  <input value={c.note} onChange={e => setCart(prev => prev.map((x, j) => j === i ? { ...x, note: e.target.value } : x))}
                    placeholder="Sin cebolla, extra salsa, bien cocido..."
                    autoFocus
                    style={{
                      width: "100%", padding: "6px 10px",
                      border: `1.5px solid ${C.amberBd}`,
                      borderRadius: 6, fontSize: 12, fontFamily: C.font, outline: "none",
                      background: C.amberBg, color: C.amber,
                    }} />
                </div>
              )}
            </div>
          ))}

          {/* Cart footer */}
          <div style={{
            padding: "10px 12px", background: C.bg, borderTop: `1px solid ${C.border}`,
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <span style={{ fontSize: 12, color: C.mute }}>{cart.length} item{cart.length !== 1 ? "s" : ""}</span>
            <span style={{ fontSize: 15, fontWeight: 800, color: C.text }}>${fmt(cartTotal)}</span>
          </div>
        </div>
      )}

      {/* Error */}
      {err && <div style={{ fontSize: 11, color: C.red, padding: "4px 8px", background: C.redBg, borderRadius: 6, border: `1px solid ${C.redBd}` }}>{err}</div>}

      {/* Submit */}
      {cart.length > 0 && (
        <MesaBtn variant="primary" full disabled={saving} onClick={save}>
          {saving ? <Spinner size={13} /> : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
          )}
          {saving ? "Agregando..." : `Agregar ${cart.length} item${cart.length !== 1 ? "s" : ""} · $${fmt(cartTotal)}`}
        </MesaBtn>
      )}
    </div>
  );
}
