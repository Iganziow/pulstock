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
  const debounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (!q.trim()) { setResults([]); return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await apiFetch(`/catalog/products/?q=${encodeURIComponent(q)}&is_active=true&page_size=15`);
        setResults(data?.results || data || []);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Error al buscar productos";
        setErr(msg);
      } finally { setSearching(false); }
    }, 280);
  }, [q]);

  function addToCart(p: Product) {
    setQ(""); setResults([]);
    setCart(prev => {
      const existing = prev.find(c => c.product.id === p.id);
      if (existing) return prev.map(c => c.product.id === p.id ? { ...c, qty: c.qty + 1 } : c);
      return [...prev, { product: p, qty: 1, unit_price: p.price || "0", note: "" }];
    });
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
      const msg = e instanceof Error ? e.message : "Error al agregar";
      setErr(msg);
    } finally { setSaving(false); }
  }

  return (
    <div>
      <div style={{ position: "relative", marginBottom: 10 }}>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Buscar producto\u2026" autoFocus
          style={{ width: "100%", padding: "8px 11px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 13, fontFamily: "inherit", outline: "none" }} />
        {searching && <div style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", color: C.mute }}><Spinner size={13} /></div>}
        {results.length > 0 && (
          <div style={{ position: "absolute", top: "100%", left: 0, right: 0, background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, boxShadow: C.shMd, zIndex: 10, maxHeight: 200, overflowY: "auto" }}>
            {results.map(p => (
              <div key={p.id} onClick={() => addToCart(p)} style={{ padding: "8px 12px", cursor: "pointer", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{p.name}</div>
                  <div style={{ fontSize: 10, color: C.mute }}>{p.sku}</div>
                </div>
                <div style={{ fontWeight: 700, fontSize: 12, color: C.accent }}>${fmt(p.price)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
      {cart.length > 0 && (
        <div style={{ border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", marginBottom: 10 }}>
          {cart.map((c, i) => (
            <div key={c.product.id} style={{ padding: "8px 10px", borderBottom: i < cart.length - 1 ? `1px solid ${C.border}` : "none", display: "flex", gap: 6, alignItems: "center" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{c.product.name}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 4 }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={c.note ? C.amber : C.mute} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>
                  <input value={c.note} onChange={e => setCart(prev => prev.map((x, j) => j === i ? { ...x, note: e.target.value } : x))}
                    placeholder="Comentario: sin cebolla, extra salsa..."
                    style={{
                      width: "100%", padding: "4px 8px",
                      border: `1px solid ${c.note ? C.amberBd : C.border}`,
                      borderRadius: C.r, fontSize: 11, fontFamily: "inherit", outline: "none",
                      background: c.note ? C.amberBg : C.surface,
                      color: c.note ? C.amber : C.text,
                    }} />
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
                <button onClick={() => setCart(prev => prev.map((x, j) => j === i ? { ...x, qty: Math.max(1, x.qty - 1) } : x))}
                  style={{ width: 22, height: 22, borderRadius: 4, border: `1px solid ${C.border}`, background: C.surface, cursor: "pointer", fontWeight: 700, fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center" }}>{"\u2212"}</button>
                <span style={{ width: 24, textAlign: "center", fontSize: 13, fontWeight: 700 }}>{c.qty}</span>
                <button onClick={() => setCart(prev => prev.map((x, j) => j === i ? { ...x, qty: x.qty + 1 } : x))}
                  style={{ width: 22, height: 22, borderRadius: 4, border: `1px solid ${C.border}`, background: C.surface, cursor: "pointer", fontWeight: 700, fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center" }}>+</button>
              </div>
              <div style={{ fontWeight: 700, fontSize: 12, color: C.text, minWidth: 50, textAlign: "right" }}>${fmt(Number(c.unit_price) * c.qty)}</div>
              <button onClick={() => setCart(prev => prev.filter((_, j) => j !== i))}
                style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 2, display: "flex" }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          ))}
        </div>
      )}
      {err && <div style={{ fontSize: 11, color: C.red, marginBottom: 6 }}>{err}</div>}
      {cart.length > 0 && (
        <MesaBtn variant="primary" full disabled={saving} onClick={save}>
          {saving ? <Spinner size={13} /> : null}
          {saving ? "Agregando\u2026" : `Agregar ${cart.length} item${cart.length !== 1 ? "s" : ""}`}
        </MesaBtn>
      )}
    </div>
  );
}
