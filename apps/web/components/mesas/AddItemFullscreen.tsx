"use client";

/**
 * AddItemFullscreen — modal pantalla completa para agregar items a una mesa.
 * UX inspirado en Wabi/Justo: search arriba, tabs de categorías, lista
 * vertical de productos grandes, botón "Confirmar" sticky abajo.
 *
 * Por qué un modal y no un panel embebido:
 *   En móvil, cuando el AddItemPanel inline mostraba sus sugerencias, el
 *   botón "Cobrar" del PaymentSection competía por espacio visual y
 *   tapaba el dropdown. Mario/Nadia reportaban "no aparece nada al
 *   buscar". Este full-screen elimina la competencia: el search ocupa
 *   toda la pantalla con espacio de sobra.
 *
 * Solo se usa en mobile. Desktop sigue con AddItemPanel embebido.
 */

import { useState, useEffect, useMemo, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { fmt } from "./helpers";

// El Product del catálogo trae más campos que el Product mínimo de mesas/types.
// Definimos un type local con lo que necesitamos para renderizar la lista
// (incluyendo is_active y category) sin tocar el type compartido.
interface CatalogProduct {
  id: number;
  name: string;
  price: string;
  sku?: string | null;
  is_active?: boolean;
  category?: { id: number; name: string } | null;
}

interface CategoryLite { id: number; name: string; }
interface CartItem {
  product: CatalogProduct;
  qty: number;
  unit_price: string;
  note: string;
}

interface AddItemFullscreenProps {
  orderId: number;
  tableName: string;
  /** Llamado cuando el user agrega items con éxito y queremos refrescar. */
  onAdded: () => void;
  /** Llamado cuando cierra sin agregar (← o cancelar). */
  onClose: () => void;
}

export function AddItemFullscreen({ orderId, tableName, onAdded, onClose }: AddItemFullscreenProps) {
  const [q, setQ]                       = useState("");
  const [searching, setSearching]       = useState(false);
  const [categories, setCategories]     = useState<CategoryLite[]>([]);
  const [activeCatId, setActiveCatId]   = useState<number | "all">("all");
  const [products, setProducts]         = useState<CatalogProduct[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [cart, setCart]                 = useState<CartItem[]>([]);
  const [saving, setSaving]             = useState(false);
  const [err, setErr]                   = useState("");
  const debounce                        = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Cargar categorías una sola vez
  useEffect(() => {
    apiFetch("/catalog/categories/")
      .then((data: any) => {
        const list: CategoryLite[] = Array.isArray(data) ? data : (data?.results ?? []);
        // Solo categorías activas y con productos. Para clientes con muchas
        // categorías filtramos las inactivas para no llenar la barra.
        const active = list.filter(c => (c as any).is_active !== false);
        setCategories(active.map(c => ({ id: c.id, name: c.name })));
      })
      .catch(() => setCategories([]));
  }, []);

  // Cargar productos al cambiar tab o búsqueda. Search global ignora la tab.
  useEffect(() => {
    clearTimeout(debounce.current);
    const params = new URLSearchParams();
    params.set("page_size", "60");
    if (q.trim()) {
      // Buscar global (case-insensitive en name/sku/barcode) — no filtramos
      // por categoría porque el usuario está buscando algo específico.
      params.set("q", q.trim());
    } else if (activeCatId !== "all") {
      params.set("category", String(activeCatId));
    }

    debounce.current = setTimeout(async () => {
      setSearching(!!q.trim());
      setLoadingProducts(!q.trim());
      try {
        const data: any = await apiFetch(`/catalog/products/?${params.toString()}`);
        const list: CatalogProduct[] = Array.isArray(data) ? data : (data?.results ?? []);
        setProducts(list.filter(p => p.is_active));
      } catch {
        setProducts([]);
      } finally {
        setSearching(false);
        setLoadingProducts(false);
      }
    }, q.trim() ? 280 : 0);

    return () => { clearTimeout(debounce.current); };
  }, [q, activeCatId]);

  // ── Helpers ──
  const addToCart = (p: CatalogProduct) => {
    setCart(prev => {
      const existing = prev.find(c => c.product.id === p.id);
      if (existing) return prev.map(c => c.product.id === p.id ? { ...c, qty: c.qty + 1 } : c);
      return [...prev, { product: p, qty: 1, unit_price: p.price || "0", note: "" }];
    });
  };
  const removeFromCart = (productId: number) => {
    setCart(prev => prev.filter(c => c.product.id !== productId));
  };
  const updateQty = (productId: number, delta: number) => {
    setCart(prev => prev.flatMap(c => {
      if (c.product.id !== productId) return [c];
      const newQty = c.qty + delta;
      return newQty <= 0 ? [] : [{ ...c, qty: newQty }];
    }));
  };

  // Mapa de productId → cantidad en carrito (para mostrar badges en la lista)
  const cartQtyMap = useMemo(() => {
    const m = new Map<number, number>();
    for (const c of cart) m.set(c.product.id, c.qty);
    return m;
  }, [cart]);

  const cartTotal = useMemo(
    () => cart.reduce((s, c) => s + Math.round(Number(c.unit_price) * c.qty), 0),
    [cart],
  );
  const cartItems = useMemo(() => cart.reduce((s, c) => s + c.qty, 0), [cart]);

  async function save() {
    if (!cart.length) return;
    setSaving(true); setErr("");
    try {
      await apiFetch(`/tables/orders/${orderId}/add-lines/`, {
        method: "POST",
        body: JSON.stringify({
          lines: cart.map(c => ({
            product_id: c.product.id,
            qty: c.qty,
            unit_price: c.unit_price,
            note: c.note,
          })),
        }),
      });
      onAdded();
      onClose();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Error al agregar items");
    } finally {
      setSaving(false);
    }
  }

  // Cerrar modal con tecla Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 200,
      background: C.bg,
      display: "flex", flexDirection: "column",
      animation: "slideUp 0.18s cubic-bezier(.4,0,.2,1)",
    }}>
      <style>{`
        @keyframes slideUp { from { opacity: 0; transform: translateY(20px) } to { opacity: 1; transform: none } }
        .cat-tab-active { background: ${C.accent} !important; color: #fff !important; }
        .add-prod-card:active { background: ${C.accentBg} !important; }
      `}</style>

      {/* ── Header sticky con search ────────────────────────────────────── */}
      <div style={{
        background: C.surface,
        borderBottom: `1px solid ${C.border}`,
        padding: "10px 12px",
        display: "flex", flexDirection: "column", gap: 8,
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button type="button" onClick={onClose} aria-label="Cerrar"
            style={{
              width: 36, height: 36, borderRadius: 8, border: `1px solid ${C.border}`,
              background: C.bg, cursor: "pointer", color: C.mid,
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11, color: C.mute, lineHeight: 1 }}>Agregar a</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: C.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {tableName}
            </div>
          </div>
        </div>

        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "10px 12px",
          border: `2px solid ${q ? C.accent : C.border}`,
          borderRadius: 10, background: C.surface,
          transition: "border-color .15s",
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={q ? C.accent : C.mute} strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink: 0 }}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Buscar producto, SKU o código de barra..."
            autoFocus
            inputMode="search"
            style={{
              flex: 1, border: "none", background: "transparent",
              fontSize: 14, fontFamily: C.font, outline: "none", color: C.text,
              minHeight: 24,
            }}
          />
          {searching && <Spinner size={14} />}
          {q && !searching && (
            <button type="button" onClick={() => setQ("")} aria-label="Limpiar"
              style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 2, display: "flex" }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* ── Tabs de categorías (oculto cuando hay búsqueda activa) ─────── */}
      {!q.trim() && categories.length > 0 && (
        <div style={{
          display: "flex", gap: 6, overflowX: "auto", padding: "8px 12px",
          background: C.surface, borderBottom: `1px solid ${C.border}`,
          flexShrink: 0,
          // Oculta scrollbar pero mantiene scroll
          scrollbarWidth: "none",
          msOverflowStyle: "none",
        }}>
          <button
            type="button"
            onClick={() => setActiveCatId("all")}
            className={activeCatId === "all" ? "cat-tab-active" : ""}
            style={{
              padding: "6px 14px", borderRadius: 99,
              border: `1px solid ${activeCatId === "all" ? C.accent : C.border}`,
              background: activeCatId === "all" ? C.accent : C.surface,
              color: activeCatId === "all" ? "#fff" : C.mid,
              fontSize: 12, fontWeight: 700, whiteSpace: "nowrap",
              cursor: "pointer", fontFamily: C.font, flexShrink: 0,
            }}
          >
            Todos
          </button>
          {categories.map(c => (
            <button
              key={c.id}
              type="button"
              onClick={() => setActiveCatId(c.id)}
              className={activeCatId === c.id ? "cat-tab-active" : ""}
              style={{
                padding: "6px 14px", borderRadius: 99,
                border: `1px solid ${activeCatId === c.id ? C.accent : C.border}`,
                background: activeCatId === c.id ? C.accent : C.surface,
                color: activeCatId === c.id ? "#fff" : C.mid,
                fontSize: 12, fontWeight: 600, whiteSpace: "nowrap",
                cursor: "pointer", fontFamily: C.font, flexShrink: 0,
              }}
            >
              {c.name}
            </button>
          ))}
        </div>
      )}

      {/* ── Lista de productos (scrolleable) ──────────────────────────── */}
      <div style={{
        flex: 1, overflowY: "auto",
        padding: "10px 12px",
        // Espacio para el footer sticky de "Confirmar"
        paddingBottom: cart.length > 0 ? 96 : 16,
      }}>
        {loadingProducts && products.length === 0 && (
          <div style={{ textAlign: "center", padding: 40, color: C.mute }}>
            <Spinner size={24} />
          </div>
        )}
        {!loadingProducts && products.length === 0 && (
          <div style={{ textAlign: "center", padding: 40, color: C.mute, fontSize: 13 }}>
            {q.trim()
              ? `No se encontró ningún producto con "${q.trim()}".`
              : "No hay productos en esta categoría."}
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {products.map(p => {
            const inCart = cartQtyMap.get(p.id) ?? 0;
            return (
              <div
                key={p.id}
                className="add-prod-card"
                // Tap en card vacía → agrega 1 (UX rápida: tocar = agregar).
                // Cuando ya hay items en el carrito, el card NO agrega
                // — el user usa los botones +/- explícitos para controlar
                // cantidad (sino sería muy fácil agregar de más sin querer).
                onClick={inCart === 0 ? () => addToCart(p) : undefined}
                style={{
                  background: C.surface,
                  border: `1px solid ${inCart > 0 ? C.accentBd : C.border}`,
                  borderRadius: 10,
                  padding: "12px 14px",
                  display: "flex", alignItems: "center", gap: 12,
                  cursor: inCart === 0 ? "pointer" : "default",
                  transition: "background .12s, border-color .12s",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>
                    {p.name}
                  </div>
                  <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>
                    {p.category?.name && <span>{p.category.name}</span>}
                    {p.sku && <span style={{ fontFamily: C.mono, marginLeft: 6 }}>· {p.sku}</span>}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                  <span style={{ fontSize: 14, fontWeight: 800, color: C.text, fontVariantNumeric: "tabular-nums" }}>
                    ${fmt(p.price)}
                  </span>
                  {inCart === 0 ? (
                    // Sin items en carrito → solo botón "+" grande
                    <button
                      type="button"
                      onClick={e => { e.stopPropagation(); addToCart(p); }}
                      aria-label={`Agregar ${p.name}`}
                      style={{
                        width: 36, height: 36, borderRadius: 8,
                        border: "none", background: C.accent,
                        color: "#fff", cursor: "pointer",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontWeight: 800, fontSize: 18,
                      }}
                    >
                      +
                    </button>
                  ) : (
                    // Con items → grupo [- N +] para controlar cantidad.
                    // El "-" cuando llega a 0 elimina el item del carrito
                    // (lógica en updateQty: newQty <= 0 → flatMap [] saca).
                    <div style={{
                      display: "flex", alignItems: "center", gap: 2,
                      background: C.accentBg, borderRadius: 8,
                      border: `1px solid ${C.accentBd}`, padding: 2,
                    }}>
                      <button
                        type="button"
                        onClick={e => { e.stopPropagation(); updateQty(p.id, -1); }}
                        aria-label={`Quitar uno de ${p.name}`}
                        style={{
                          width: 32, height: 32, borderRadius: 6,
                          border: "none", background: "transparent",
                          color: C.accent, cursor: "pointer",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontWeight: 800, fontSize: 18, lineHeight: 1,
                        }}
                      >
                        −
                      </button>
                      {/* Cantidad editable directamente con teclado para casos
                          como "93 gramos de chocolate" — Mario lo pidió. Para
                          que tipear gramos no requiera apretar + 93 veces. */}
                      <input
                        type="number"
                        inputMode="decimal"
                        min="1"
                        step="any"
                        value={inCart}
                        onClick={e => e.stopPropagation()}
                        onFocus={e => { e.stopPropagation(); e.target.select(); }}
                        onChange={e => {
                          e.stopPropagation();
                          const raw = e.target.value;
                          const n = raw === "" ? 0 : Number(raw);
                          if (isNaN(n) || n < 0) return;
                          // Reemplaza la cantidad del item directamente.
                          // Si n=0, lo saca del carrito.
                          setCart(prev => {
                            const exists = prev.find(c => c.product.id === p.id);
                            if (!exists) {
                              if (n <= 0) return prev;
                              return [...prev, { product: p, qty: n, unit_price: p.price || "0", note: "" }];
                            }
                            if (n <= 0) return prev.filter(c => c.product.id !== p.id);
                            return prev.map(c => c.product.id === p.id ? { ...c, qty: n } : c);
                          });
                        }}
                        onBlur={e => {
                          // Si quedó en 0/vacío al perder foco, mantenerlo
                          // fuera del carrito (no forzar a 1) — el usuario
                          // ya lo había sacado intencionalmente.
                          const n = Number(e.target.value);
                          if (isNaN(n) || n < 0) {
                            setCart(prev => prev.filter(c => c.product.id !== p.id));
                          }
                        }}
                        className="qty-input-no-spin"
                        aria-label={`Cantidad de ${p.name}`}
                        style={{
                          width: 48, textAlign: "center",
                          border: "none", background: "transparent",
                          fontSize: 14, fontWeight: 800, color: C.accent,
                          fontFamily: C.font, outline: "none",
                          padding: "0 4px",
                          MozAppearance: "textfield",
                        }}
                      />
                      <button
                        type="button"
                        onClick={e => { e.stopPropagation(); addToCart(p); }}
                        aria-label={`Agregar otro ${p.name}`}
                        style={{
                          width: 32, height: 32, borderRadius: 6,
                          border: "none", background: C.accent,
                          color: "#fff", cursor: "pointer",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontWeight: 800, fontSize: 16, lineHeight: 1,
                        }}
                      >
                        +
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Footer sticky con "Confirmar" ─────────────────────────────── */}
      {cart.length > 0 && (
        <div style={{
          position: "absolute", bottom: 0, left: 0, right: 0,
          background: C.surface, borderTop: `1px solid ${C.border}`,
          padding: "10px 12px",
          boxShadow: "0 -6px 20px rgba(0,0,0,0.08)",
          display: "flex", flexDirection: "column", gap: 6,
        }}>
          {err && (
            <div style={{ fontSize: 12, color: C.red, padding: "4px 8px", background: C.redBg, borderRadius: 6 }}>
              {err}
            </div>
          )}
          <button
            type="button"
            onClick={save}
            disabled={saving}
            style={{
              width: "100%", padding: "14px 16px", borderRadius: 10,
              border: "none", background: C.accent, color: "#fff",
              fontSize: 15, fontWeight: 800, cursor: saving ? "not-allowed" : "pointer",
              opacity: saving ? 0.6 : 1, fontFamily: C.font,
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            }}
          >
            {saving ? <Spinner size={16} /> : null}
            {saving
              ? "Agregando…"
              : `Agregar ${cartItems} item${cartItems !== 1 ? "s" : ""} · $${fmt(cartTotal)}`}
          </button>
        </div>
      )}
    </div>
  );
}
