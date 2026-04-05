"use client";

import { C } from "@/lib/theme";
import { Spinner, Badge } from "@/components/ui";
import type { Product } from "./types";

interface ProductListPanelProps {
  products: Product[];
  filtered: Product[];
  loading: boolean;
  searchQ: string;
  setSearchQ: (v: string) => void;
  selectedId: number | null;
  onSelect: (p: Product) => void;
}

export function ProductListPanel({
  products, filtered, loading, searchQ, setSearchQ, selectedId, onSelect,
}: ProductListPanelProps) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden", boxShadow: C.sh }}>

      {/* Search */}
      <div style={{ padding: "12px 14px", borderBottom: `1px solid ${C.border}`, display: "flex", gap: 8, alignItems: "center" }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink: 0 }}>
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          placeholder="Filtrar productos\u2026"
          style={{ flex: 1, border: "none", background: "transparent", fontSize: 13, outline: "none" }}
        />
        {searchQ && (
          <button type="button" aria-label="Cerrar" onClick={() => setSearchQ("")}
            style={{ background: "none", border: "none", color: C.mute, cursor: "pointer", fontSize: 15, padding: 0, lineHeight: 1 }}>&#x2715;</button>
        )}
      </div>

      {/* Product rows */}
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto" }}>
        {loading ? (
          <div style={{ padding: "40px 0", display: "flex", justifyContent: "center", alignItems: "center", gap: 8, color: C.mute }}>
            <Spinner size={16}/><span style={{ fontSize: 13 }}>Cargando\u2026</span>
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
              onClick={() => onSelect(p)}
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
      {!loading && (
        <div style={{ padding: "8px 16px", borderTop: `1px solid ${C.border}`, fontSize: 11, color: C.mute, background: C.bg }}>
          {filtered.length} producto{filtered.length !== 1 ? "s" : ""}
          {" \u00B7 "}
          {products.filter(p => p.has_recipe).length} con receta
        </div>
      )}
    </div>
  );
}
