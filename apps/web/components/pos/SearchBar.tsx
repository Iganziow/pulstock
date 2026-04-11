"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { formatCLP } from "@/lib/format";
import { Btn, Spinner } from "@/components/ui";
import type { Product, PromoInfo, CartLine } from "./types";
import { toNumber } from "./types";

/* ── Props ─────────────────────────────────────────────────────────────────── */

interface SearchBarProps {
  onSelect: (product: Product) => void;
  warehouseId?: number | null;
  disabled?: boolean;
  busy?: boolean;
  mob?: boolean;
  cart: CartLine[];
  promoMap: Record<number, PromoInfo>;
  onPromosFound: (map: Record<number, PromoInfo>) => void;
  inputRef?: React.RefObject<HTMLInputElement | null>;
}

export function SearchBar({
  onSelect, warehouseId, disabled, busy, mob, cart, promoMap, onPromosFound, inputRef: externalRef,
}: SearchBarProps) {
  const localRef    = useRef<HTMLInputElement | null>(null);
  const inputRef    = externalRef ?? localRef;
  const wrapRef     = useRef<HTMLDivElement | null>(null);

  const [term, setTerm]                      = useState("");
  const [searching, setSearching]            = useState(false);
  const [suggestions, setSuggestions]         = useState<Product[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggHighlight, setSuggHighlight]     = useState(0);
  const [err, setErr]                        = useState<string | null>(null);

  // Close suggestions on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
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
            onPromosFound(map);
          } catch (e) { console.error("SearchBar: error cargando promociones activas:", e); }
        }
      } catch {
        setSuggestions([]); setShowSuggestions(false);
      } finally { setSearching(false); }
    }, 280);
    return () => { clearTimeout(t); setSearching(false); };
  }, [term, onPromosFound]);

  // ── Lookup (exact -- barcode/SKU) ──
  const lookupAndAdd = useCallback(async (raw: string) => {
    const cleaned = raw.trim();
    if (!cleaned) return;
    setShowSuggestions(false);
    setErr(null);
    try {
      const url     = `/catalog/products/lookup/?term=${encodeURIComponent(cleaned)}`;
      const product = (await apiFetch(url)) as Product;
      if (!product?.id)              { setErr("Producto no encontrado.");              return; }
      if (!product.is_active)        { setErr("Producto inactivo. No se puede vender."); return; }
      onSelect(product);
      setTerm("");
      requestAnimationFrame(() => inputRef.current?.focus());
    } catch (e: any) { setErr(e?.message ?? "No se pudo buscar el producto."); }
  }, [onSelect, inputRef]);

  // Pick from dropdown
  const pickSuggestion = useCallback((product: Product) => {
    setShowSuggestions(false);
    setSuggestions([]);
    setTerm("");
    if (!product.is_active) { setErr("Producto inactivo. No se puede vender."); return; }
    onSelect(product);
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [onSelect, inputRef]);

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

  const isDisabled = disabled || busy || !warehouseId;

  return (
    <>
      <div ref={wrapRef} style={{ position:"relative" }}>
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
            placeholder={mob?"Buscar producto...":"Escanea barcode, escribe SKU o nombre del producto..."}
            style={{ flex:1, border:"none", background:"transparent", fontSize:mob?14:15, outline:"none", fontFamily:C.font, minHeight:mob?44:undefined }}
            disabled={isDisabled}
          />
          {term && (
            <button onClick={() => { setTerm(""); setSuggestions([]); setShowSuggestions(false); inputRef.current?.focus(); }} className="xb"
              style={{ background:"none", border:"none", color:C.mute, cursor:"pointer", fontSize:16, padding:"0 4px", lineHeight:1 }}>✕</button>
          )}
          {!mob && <div style={{ width:1, height:20, background:C.border }}/>}
          <Btn variant="primary" size={mob?"md":"sm"} onClick={() => lookupAndAdd(term)} disabled={isDisabled || !term.trim()}>
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

      {/* Search error (inline) */}
      {err && (
        <div style={{ padding:"11px 14px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, color:C.red, fontSize:13 }}>
          <div style={{ display:"flex", alignItems:"flex-start", gap:8 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink:0, marginTop:1 }}>
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span style={{ flex:1, fontWeight:500 }}>{err}</span>
            <button onClick={() => setErr(null)} className="xb"
              style={{ background:"none", border:"none", color:C.red, padding:0, fontSize:16, cursor:"pointer", lineHeight:1 }}>✕</button>
          </div>
        </div>
      )}
    </>
  );
}
