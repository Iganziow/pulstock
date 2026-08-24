"use client";

import { C } from "@/lib/theme";
import { Spinner, Badge } from "@/components/ui";
import type { Product } from "./types";

interface ProductListPanelProps {
  products: Product[];
  loading: boolean;
  searchQ: string;
  setSearchQ: (v: string) => void;
  selectedId: number | null;
  onSelect: (p: Product) => void;
  // Paginación server-side
  page: number;
  pageSize: number;
  totalCount: number;
  hasNext: boolean;
  hasPrev: boolean;
  onPrev: () => void;
  onNext: () => void;
}

export function ProductListPanel({
  products, loading, searchQ, setSearchQ, selectedId, onSelect,
  page, pageSize, totalCount, hasNext, hasPrev, onPrev, onNext,
}: ProductListPanelProps) {
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const start = totalCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = (page - 1) * pageSize + products.length;
  const showFooter = !loading || products.length > 0;

  const navBtn = (label: string, onClick: () => void, disabled: boolean) => (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        border: `1px solid ${C.border}`, borderRadius: 6,
        background: disabled ? C.bg : C.surface,
        color: disabled ? C.mute : C.text,
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.5 : 1,
        fontSize: 12, padding: "3px 9px", lineHeight: 1.4,
      }}
    >
      {label}
    </button>
  );

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
          placeholder="Buscar productos…"
          style={{ flex: 1, border: "none", background: "transparent", fontSize: 13, outline: "none" }}
        />
        {searchQ && (
          <button type="button" aria-label="Cerrar" onClick={() => setSearchQ("")}
            style={{ background: "none", border: "none", color: C.mute, cursor: "pointer", fontSize: 15, padding: 0, lineHeight: 1 }}>&#x2715;</button>
        )}
      </div>

      {/* Product rows */}
      {/* overflowX explicito: definir SOLO un eje hace que el otro pase de
          `visible` a `auto` por especificacion, y aparecia una barra
          horizontal en una lista que solo tiene nombre y etiqueta --el
          nombre ya trunca con puntos suspensivos, nada necesita ese
          espacio--. */}
      <div style={{ maxHeight: "calc(100vh - 260px)", overflowY: "auto", overflowX: "hidden" }}>
        {loading ? (
          <div style={{ padding: "40px 0", display: "flex", justifyContent: "center", alignItems: "center", gap: 8, color: C.mute }}>
            <Spinner size={16}/><span style={{ fontSize: 13 }}>Cargando…</span>
          </div>
        ) : products.length === 0 ? (
          <div style={{ padding: "40px 16px", textAlign: "center", color: C.mute, fontSize: 13 }}>
            {searchQ ? "Sin resultados para esa búsqueda." : "No hay productos."}
          </div>
        ) : (
          products.map(p => (
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

      {/* Footer: rango + paginación */}
      {showFooter && (
        <div style={{ padding: "8px 12px", borderTop: `1px solid ${C.border}`, background: C.bg, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <span style={{ fontSize: 11, color: C.mute }}>
            {totalCount === 0
              ? "Sin productos"
              : `Mostrando ${start}–${end} de ${totalCount}`}
          </span>
          {totalCount > pageSize && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              {navBtn("‹ Anterior", onPrev, !hasPrev)}
              <span style={{ fontSize: 11, color: C.mute }}>Pág. {page}/{totalPages}</span>
              {navBtn("Siguiente ›", onNext, !hasNext)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
