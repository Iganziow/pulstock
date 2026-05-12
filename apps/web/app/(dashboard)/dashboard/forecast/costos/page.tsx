"use client";

/**
 * /dashboard/forecast/costos
 * ==========================
 * Inline editor para cargar rápido los costos de productos que no los tienen.
 *
 * Por qué esta página existe:
 * Sin costo cargado en cada producto, el módulo de predicción no puede
 * calcular margen → todos los productos caen en "margen bajo" → cobertura
 * de stock corta (7-10 días en vez de 14-21). Esto baja muchísimo la
 * calidad de las sugerencias de compra.
 *
 * Arreglar esto manualmente entrando a cada producto es tedioso. Acá lo
 * resolvemos en bloque: lista ordenada por ventas (los más vendidos
 * primero, mayor impacto), input inline en cada fila, "Guardar todos"
 * al final.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { useBreakpoint } from "@/hooks/useIsMobile";

type MissingProduct = {
  id: number;
  name: string;
  sku: string | null;
  category: string | null;
  unit_code: string;
  price: string;
  sold_30d: number;
  revenue_30d: string;
};

type ApiResp = {
  results: MissingProduct[];
  total_missing: number;
  total_active: number;
};

const fmtCLP = (n: number | string) => {
  const v = typeof n === "string" ? Number(n) : n;
  if (!Number.isFinite(v)) return "0";
  return Math.round(v).toLocaleString("es-CL");
};

export default function MissingCostsPage() {
  const { isMobile } = useBreakpoint();
  const [data, setData] = useState<ApiResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Mapa product_id → costo ingresado (string para no romper con decimales
  // mientras escribís — convertimos a Decimal recién al enviar).
  const [costs, setCosts] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveOk, setSaveOk] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Carga inicial + recargas tras guardar
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(null);
    apiFetch("/catalog/products/missing-costs/")
      .then((d: any) => { if (alive) { setData(d); setCosts({}); } })
      .catch((e: any) => { if (alive) setErr(e?.message ?? "Error"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [refreshKey]);

  // Cantos costos están listos para guardar (no vacíos, número válido > 0)
  const filledCount = useMemo(
    () => Object.values(costs).filter(c => c && Number(c) > 0).length,
    [costs]
  );

  async function handleSaveAll() {
    if (filledCount === 0) return;
    setSaving(true);
    setSaveErr(null);
    setSaveOk(null);
    try {
      const updates = Object.entries(costs)
        .filter(([_, v]) => v && Number(v) > 0)
        .map(([pid, v]) => ({ product_id: Number(pid), cost: v }));

      const resp = await apiFetch("/catalog/products/costs/bulk/", {
        method: "POST",
        body: JSON.stringify({ updates }),
      });
      setSaveOk(`✓ ${resp.updated} costo${resp.updated !== 1 ? "s" : ""} guardado${resp.updated !== 1 ? "s" : ""}.`);
      setRefreshKey(k => k + 1);
      setTimeout(() => setSaveOk(null), 5000);
    } catch (e: any) {
      setSaveErr(e?.message ?? "Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  // Total estimado de margen rescatado: suma de price * sold_30d para los
  // productos con costo ingresado (asumiendo costo razonable, aprox 50% del
  // precio para que el cálculo sirva de motivación pero no engañe).
  const potentialMargin = useMemo(() => {
    if (!data) return 0;
    let total = 0;
    for (const p of data.results) {
      const c = costs[p.id];
      if (c && Number(c) > 0) {
        const price = Number(p.price) || 0;
        const cost = Number(c);
        const margin = Math.max(0, price - cost) * p.sold_30d;
        total += margin;
      }
    }
    return total;
  }, [data, costs]);

  return (
    <div style={{ background: C.bg, minHeight: "100vh", padding: isMobile ? "16px 12px" : "24px 28px" }}>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        {/* Volver */}
        <Link href="/dashboard/forecast" style={{
          display: "inline-flex", alignItems: "center", gap: 4,
          fontSize: 13, color: C.mid, textDecoration: "none",
          marginBottom: 14, fontWeight: 500,
        }}>
          ← Volver a predicción
        </Link>

        {/* Header */}
        <div style={{ marginBottom: 20 }}>
          <h1 style={{ fontSize: isMobile ? 22 : 28, fontWeight: 800, color: C.text, margin: 0, letterSpacing: "-0.02em" }}>
            💰 Cargar costos faltantes
          </h1>
          <p style={{ fontSize: 14, color: C.mid, marginTop: 6, lineHeight: 1.6, maxWidth: 720 }}>
            Estos productos no tienen costo cargado, lo que limita las predicciones del sistema.
            Están ordenados por <b>cantidad vendida en 30 días</b> — cargá los más vendidos primero
            para tener el mayor impacto.
          </p>
        </div>

        {/* Mensajes */}
        {err && (
          <div style={{ padding: "10px 14px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 8, color: C.red, fontSize: 13, marginBottom: 12 }}>
            {err}
          </div>
        )}
        {saveOk && (
          <div style={{ padding: "10px 14px", background: C.greenBg, border: `1px solid ${C.greenBd}`, borderRadius: 8, color: C.green, fontSize: 13, marginBottom: 12, fontWeight: 600 }}>
            {saveOk}
          </div>
        )}
        {saveErr && (
          <div style={{ padding: "10px 14px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 8, color: C.red, fontSize: 13, marginBottom: 12 }}>
            {saveErr}
          </div>
        )}

        {/* KPIs arriba */}
        {data && (
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(3, 1fr)", gap: 12, marginBottom: 16 }}>
            <div style={{ background: C.surface, padding: 14, borderRadius: 10, border: `1px solid ${C.border}` }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em" }}>Sin costo</div>
              <div style={{ fontSize: 26, fontWeight: 800, color: C.amber, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>
                {data.total_missing}
              </div>
              <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>
                de {data.total_active} productos activos
              </div>
            </div>
            <div style={{ background: C.surface, padding: 14, borderRadius: 10, border: `1px solid ${C.border}` }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em" }}>Listos para guardar</div>
              <div style={{ fontSize: 26, fontWeight: 800, color: filledCount > 0 ? C.green : C.mute, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>
                {filledCount}
              </div>
              <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>
                con costo ingresado
              </div>
            </div>
            <div style={{ background: C.surface, padding: 14, borderRadius: 10, border: `1px solid ${C.border}`, gridColumn: isMobile ? "1 / -1" : "auto" }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em" }}>Margen calculable</div>
              <div style={{ fontSize: 26, fontWeight: 800, color: C.accent, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>
                ${fmtCLP(potentialMargin)}
              </div>
              <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>
                en últimos 30 días con los costos cargados ahora
              </div>
            </div>
          </div>
        )}

        {/* Botón guardar (sticky arriba) */}
        {data && data.results.length > 0 && (
          <div style={{
            position: "sticky", top: 0, zIndex: 10,
            background: C.bg,
            padding: "10px 0",
            marginBottom: 12,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
          }}>
            <div style={{ fontSize: 13, color: C.mid }}>
              {filledCount > 0
                ? <>Tenés <b>{filledCount}</b> costo{filledCount !== 1 ? "s" : ""} listo{filledCount !== 1 ? "s" : ""} para guardar</>
                : <>Empezá ingresando el costo de los productos más vendidos (arriba)</>
              }
            </div>
            <button
              type="button"
              onClick={handleSaveAll}
              disabled={filledCount === 0 || saving}
              style={{
                padding: "10px 20px",
                background: filledCount > 0 ? C.accent : C.border,
                color: filledCount > 0 ? "#fff" : C.mute,
                border: "none",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 700,
                cursor: filledCount > 0 && !saving ? "pointer" : "not-allowed",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                minHeight: 40,
                boxShadow: filledCount > 0 ? "0 1px 2px rgba(79,70,229,0.18)" : "none",
              }}
            >
              {saving ? <><Spinner size={14} /> Guardando…</> : `Guardar ${filledCount > 0 ? `(${filledCount})` : "todos"}`}
            </button>
          </div>
        )}

        {/* Tabla */}
        <div style={{ background: C.surface, borderRadius: 10, border: `1px solid ${C.border}`, overflow: "hidden" }}>
          {loading && (
            <div style={{ padding: 32, textAlign: "center" }}><Spinner /></div>
          )}

          {!loading && data && data.results.length === 0 && (
            <div style={{ padding: 48, textAlign: "center" }}>
              <div style={{ fontSize: 48, marginBottom: 10 }}>🎉</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.green, marginBottom: 4 }}>
                ¡Todos tus productos tienen costo cargado!
              </div>
              <div style={{ fontSize: 13, color: C.mute }}>
                Las predicciones del sistema ya están aprovechando esa información al máximo.
              </div>
            </div>
          )}

          {!loading && data && data.results.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              {/* HEADER */}
              <div style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr 90px 110px" : "1fr 110px 130px 110px 130px",
                gap: 10,
                padding: "10px 14px",
                background: C.bg,
                borderBottom: `1px solid ${C.border}`,
                fontSize: 11,
                fontWeight: 700,
                color: C.mute,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                minWidth: isMobile ? 360 : undefined,
              }}>
                <div>Producto</div>
                {!isMobile && <div style={{ textAlign: "right" }}>Vendido 30d</div>}
                <div style={{ textAlign: "right" }}>Precio venta</div>
                {!isMobile && <div style={{ textAlign: "right" }}>Margen sugerido</div>}
                <div style={{ textAlign: "right" }}>Costo ($)</div>
              </div>

              {/* FILAS */}
              {data.results.map((p, i) => {
                const price = Number(p.price) || 0;
                const inputCost = costs[p.id];
                const numCost = Number(inputCost);
                const validCost = inputCost && Number.isFinite(numCost) && numCost > 0;
                const margin = validCost ? Math.max(0, price - numCost) : null;
                const marginPct = validCost && price > 0 ? Math.round((margin! / price) * 100) : null;
                // Sugerencia: 50% del precio como costo si no sabes cuánto vale
                const suggested = price > 0 ? Math.round(price * 0.5) : 0;

                return (
                  <div key={p.id} style={{
                    display: "grid",
                    gridTemplateColumns: isMobile ? "1fr 90px 110px" : "1fr 110px 130px 110px 130px",
                    gap: 10,
                    padding: isMobile ? "10px 12px" : "12px 14px",
                    borderBottom: i < data.results.length - 1 ? `1px solid ${C.border}` : "none",
                    alignItems: "center",
                    background: validCost ? C.greenBg : "transparent",
                    minWidth: isMobile ? 360 : undefined,
                  }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: isMobile ? 13 : 14, color: C.text, lineHeight: 1.3 }}>
                        {p.name}
                      </div>
                      <div style={{ fontSize: 10.5, color: C.mute, marginTop: 2, display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {p.category && <span>{p.category}</span>}
                        {isMobile && p.sold_30d > 0 && <span>· {p.sold_30d.toFixed(0)} vendidos</span>}
                        {p.unit_code && p.unit_code !== "UN" && <span style={{ color: C.mid }}>· {p.unit_code.toLowerCase()}</span>}
                      </div>
                    </div>

                    {!isMobile && (
                      <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: p.sold_30d > 0 ? C.text : C.mute }}>
                          {p.sold_30d > 0 ? Math.round(p.sold_30d).toLocaleString("es-CL") : "—"}
                        </div>
                        {p.sold_30d > 0 && p.revenue_30d && (
                          <div style={{ fontSize: 10, color: C.mute }}>${fmtCLP(p.revenue_30d)}</div>
                        )}
                      </div>
                    )}

                    <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: price > 0 ? C.text : C.mute }}>
                        {price > 0 ? `$${fmtCLP(price)}` : "—"}
                      </div>
                    </div>

                    {!isMobile && (
                      <div style={{ textAlign: "right", fontSize: 12 }}>
                        {validCost ? (
                          <span style={{ color: marginPct! >= 30 ? C.green : marginPct! >= 10 ? C.amber : C.red, fontWeight: 700 }}>
                            +${fmtCLP(margin!)} <span style={{ fontSize: 10, fontWeight: 500 }}>({marginPct}%)</span>
                          </span>
                        ) : (
                          <span style={{ color: C.mute, fontStyle: "italic" }}>—</span>
                        )}
                      </div>
                    )}

                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                      <input
                        type="number"
                        inputMode="decimal"
                        value={inputCost ?? ""}
                        onChange={e => {
                          const v = e.target.value;
                          setCosts(c => ({ ...c, [p.id]: v }));
                        }}
                        placeholder={suggested > 0 ? String(suggested) : "0"}
                        min={0}
                        step={1}
                        style={{
                          width: isMobile ? "100%" : 110,
                          padding: "7px 10px",
                          border: `1px solid ${validCost ? C.green : C.border}`,
                          borderRadius: 6,
                          fontSize: 13,
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          background: C.surface,
                          color: C.text,
                          outline: "none",
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Botón guardar abajo también */}
        {data && data.results.length > 0 && filledCount > 0 && (
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
            <button
              type="button"
              onClick={handleSaveAll}
              disabled={saving}
              style={{
                padding: "11px 24px",
                background: C.accent,
                color: "#fff",
                border: "none",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 700,
                cursor: saving ? "wait" : "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                minHeight: 44,
                boxShadow: "0 1px 2px rgba(79,70,229,0.18)",
              }}
            >
              {saving ? <><Spinner size={14} /> Guardando…</> : `Guardar ${filledCount} costo${filledCount !== 1 ? "s" : ""}`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
