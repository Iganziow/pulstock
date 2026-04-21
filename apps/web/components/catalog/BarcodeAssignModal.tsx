"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Btn, Spinner, iS } from "@/components/ui";

type NoBarcodeProduct = { id: number; name: string; sku: string | null; category__name: string | null };

export function BarcodeAssignModal({ onClose }: { onClose: () => void }) {
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
          <button type="button" aria-label="Cerrar" onClick={onClose} className="ib" style={{
            width: 30, height: 30, borderRadius: C.r, border: `1px solid ${C.border}`,
            background: C.surface, color: C.mid, fontSize: 14,
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>{"✕"}</button>
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
                    {"Saltar →"}
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
