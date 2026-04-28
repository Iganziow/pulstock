"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Btn, Spinner, SkeletonPage } from "@/components/ui";
import { SaleStatusBadge } from "@/components/sales/SaleStatusBadge";
import { SaleStatCard } from "@/components/sales/SaleStatCard";
import { DetailPanel } from "@/components/sales/DetailPanel";
import { toNum, fCLP, isoDate, fDate, profitPct } from "@/components/sales/helpers";
import type { SaleRow, Warehouse } from "@/components/sales/types";
import ExportButtons from "@/components/ExportButtons";

// ─── Main ─────────────────────────────────────────────────────────────────────

const PAGE_CSS = `
.prow.active{background:#EEF2FF}
.panel-in{animation:panelIn 0.2s cubic-bezier(0.4,0,0.2,1) both}
@keyframes panelIn{from{opacity:0;transform:translateX(12px)}to{opacity:1;transform:none}}
`;

export default function SalesPage() {
  useGlobalStyles(PAGE_CSS);
  const mob = useIsMobile();

  const [items, setItems]       = useState<SaleRow[]>([]);
  const [loading, setLoading]   = useState(true);
  const [err, setErr]           = useState<string|null>(null);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);

  // Filters
  const [q, setQ]               = useState("");
  const [status, setStatus]     = useState<"ALL"|"COMPLETED"|"VOID">("ALL");
  const [range, setRange]       = useState<"TODAY"|"7D"|"30D"|"MONTH"|"YEAR"|"CUSTOM"|"ALL">("30D");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo]     = useState("");
  const [warehouseId, setWarehouseId] = useState<number|"ALL">("ALL");

  // Selected row -> detail panel
  const [selectedId, setSelectedId] = useState<number|null>(null);

  // Endpoint
  const endpoint = useMemo(() => {
    const base = "/sales/sales/list/";
    const p    = new URLSearchParams();
    const qq   = q.trim();
    if (qq) p.set("q", qq);
    if (status !== "ALL") p.set("status", status);
    if (warehouseId !== "ALL") p.set("warehouse_id", String(warehouseId));
    if (range !== "ALL") {
      const now = new Date();
      let start = new Date(now);
      let end   = now;
      if (range === "TODAY") start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      else if (range === "7D") start.setDate(now.getDate()-7);
      else if (range === "30D") start.setDate(now.getDate()-30);
      else if (range === "MONTH") start = new Date(now.getFullYear(), now.getMonth(), 1);
      else if (range === "YEAR") start = new Date(now.getFullYear(), 0, 1);
      else if (range === "CUSTOM") {
        if (customFrom) start = new Date(customFrom + "T00:00:00");
        if (customTo)   end   = new Date(customTo   + "T23:59:59");
      }
      p.set("date_from", isoDate(start));
      p.set("date_to", isoDate(end));
    }
    const qs = p.toString();
    return qs ? `${base}?${qs}` : base;
  }, [q, status, range, warehouseId, customFrom, customTo]);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const data = await apiFetch(endpoint);
      setItems(data?.results ?? data ?? []);
    } catch (e:any) { setErr(e?.message ?? "Error cargando ventas"); setItems([]); }
    finally { setLoading(false); }
  }, [endpoint]);

  // Para el export: trae TODAS las páginas filtradas (no solo la actual).
  // El backend usa page_size=50 por default (DRF). Loopeamos hasta que
  // no haya `next` link o la página venga con menos resultados.
  // Tope de seguridad de 100 páginas (~5000 ventas) para no colgar el
  // browser. Si Mario alguna vez exporta más, agregamos un endpoint
  // de export dedicado en el backend.
  const fetchAllForExport = useCallback(async (): Promise<SaleRow[]> => {
    const sep = endpoint.includes("?") ? "&" : "?";
    const all: SaleRow[] = [];
    const MAX_PAGES = 100;
    const PAGE_SIZE = 50;  // matchea el default DRF
    for (let page = 1; page <= MAX_PAGES; page++) {
      const url = `${endpoint}${sep}page=${page}`;
      let data: any;
      try { data = await apiFetch(url); } catch { break; }
      const rows = data?.results ?? (Array.isArray(data) ? data : []);
      if (!rows || rows.length === 0) break;
      all.push(...rows);
      // Endpoint no paginado, o última página
      if (!data?.next || rows.length < PAGE_SIZE) break;
    }
    return all;
  }, [endpoint]);

  // Estado del export — usado para mostrar "Cargando..." mientras pre-carga
  const [exportRows, setExportRows] = useState<SaleRow[] | null>(null);
  const [exportLoading, setExportLoading] = useState(false);
  const handlePrepareExport = useCallback(async () => {
    setExportLoading(true);
    try {
      const all = await fetchAllForExport();
      setExportRows(all);
    } catch (e: any) {
      setErr(e?.message ?? "Error preparando export");
    } finally {
      setExportLoading(false);
    }
  }, [fetchAllForExport]);

  useEffect(() => {
    (async () => {
      try {
        const ws = (await apiFetch("/core/warehouses/")) as Warehouse[];
        setWarehouses(Array.isArray(ws) ? ws : []);
      } catch { setWarehouses([]); }
    })();
  }, []);

  useEffect(() => {
    const t = setTimeout(() => load(), 250);
    // Si cambian los filtros, descartamos el cache de export para no
    // exportar datos viejos por error.
    setExportRows(null);
    return () => clearTimeout(t);
  }, [load]);

  // ── Metrics ─────────────────────────────────────────────────────────────────
  const metrics = useMemo(() => {
    const completed = items.filter(s => s.status.toUpperCase() === "COMPLETED");
    const total     = completed.reduce((a, s) => a + toNum(s.total), 0);
    const profit    = completed.reduce((a, s) => a + toNum(s.gross_profit), 0);
    const pct       = total > 0 ? Math.round((profit / total) * 100) : 0;
    return {
      ventas:    items.length,
      completadas: completed.length,
      total,
      profit,
      pct,
      anuladas:  items.filter(s => s.status.toUpperCase() === "VOID").length,
    };
  }, [items]);

  // ─────────────────────────────── RENDER ──────────────────────────────────
  return (
    <div style={{ fontFamily:C.font, color:C.text, background:C.bg, minHeight:"100vh", padding:mob?"16px 12px":"24px 28px", display:"flex", flexDirection:"column", gap:16 }}>

      {/* HEADER */}
      <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between", gap:12, flexWrap:"wrap" }}>
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:4 }}>
            <div style={{ width:4, height:26, background:C.accent, borderRadius:2 }}/>
            <h1 style={{ margin:0, fontSize:mob?18:22, fontWeight:800, color:C.text, letterSpacing:"-0.04em" }}>Ventas</h1>
          </div>
          {!mob && <p style={{ margin:0, fontSize:13, color:C.mute, paddingLeft:14 }}>
            Historial de ventas · haz clic en una fila para ver el detalle
          </p>}
        </div>
        <div style={{ display:"flex", gap:8, alignItems:"center", flexWrap:"wrap" }}>
          {/* Export Excel/PDF — Mario lo pidió. Pre-carga TODAS las
              ventas filtradas (no solo la pagina actual) y genera el
              archivo. Si no hay datos pre-cargados, primero hace la
              carga y luego el ExportButtons aparece. */}
          {exportRows && exportRows.length > 0 ? (
            <ExportButtons
              title="Reporte de Ventas"
              subtitle={(() => {
                if (range === "TODAY") return "Hoy";
                if (range === "7D") return "Últimos 7 días";
                if (range === "30D") return "Últimos 30 días";
                if (range === "MONTH") return "Mes actual";
                if (range === "YEAR") return "Año en curso";
                if (range === "CUSTOM") return `${customFrom || "—"} a ${customTo || "—"}`;
                return "Todo el histórico";
              })()}
              columns={[
                { key:"id", label:"#", width:6, format:"number" },
                { key:"sale_number", label:"Venta", width:8, format:"number" },
                { key:"created_at", label:"Fecha", width:18, format:"date" },
                { key:"context", label:"Contexto", width:14 },
                { key:"status", label:"Estado", width:12 },
                { key:"subtotal", label:"Subtotal", width:12, format:"money" },
                { key:"tip", label:"Propina", width:10, format:"money" },
                { key:"total", label:"Total venta", width:13, format:"money" },
                { key:"total_cobrado", label:"Total cobrado", width:14, format:"money" },
                { key:"total_cost", label:"Costo", width:12, format:"money" },
                { key:"gross_profit", label:"Utilidad", width:12, format:"money" },
              ]}
              rows={exportRows.map(s => ({
                id: s.id,
                sale_number: s.sale_number ?? s.id,
                created_at: fDate(s.created_at),
                context: s.table_name ? `Mesa ${s.table_name}` : "POS",
                status: s.status === "COMPLETED" ? "Completada" : s.status === "VOID" ? "Anulada" : s.status,
                subtotal: toNum(s.subtotal),
                tip: toNum(s.tip ?? 0),
                total: toNum(s.total),
                total_cobrado: toNum(s.total) + toNum(s.tip ?? 0),
                total_cost: toNum(s.total_cost),
                gross_profit: toNum(s.gross_profit),
              }))}
              summaryRows={[{
                label: `Total (${exportRows.filter(s => s.status === "COMPLETED").length} completadas)`,
                subtotal: exportRows.filter(s => s.status === "COMPLETED").reduce((a, s) => a + toNum(s.subtotal), 0),
                tip: exportRows.filter(s => s.status === "COMPLETED").reduce((a, s) => a + toNum(s.tip ?? 0), 0),
                total: exportRows.filter(s => s.status === "COMPLETED").reduce((a, s) => a + toNum(s.total), 0),
                total_cobrado: exportRows.filter(s => s.status === "COMPLETED").reduce((a, s) => a + toNum(s.total) + toNum(s.tip ?? 0), 0),
                total_cost: exportRows.filter(s => s.status === "COMPLETED").reduce((a, s) => a + toNum(s.total_cost), 0),
                gross_profit: exportRows.filter(s => s.status === "COMPLETED").reduce((a, s) => a + toNum(s.gross_profit), 0),
              }]}
              fileName={`ventas-${(new Date()).toISOString().slice(0,10)}`}
            />
          ) : (
            <Btn variant="secondary" size="sm" onClick={handlePrepareExport} disabled={exportLoading || items.length === 0}>
              {exportLoading ? <Spinner/> : (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
              )}
              {exportLoading ? "Cargando..." : "Preparar export"}
            </Btn>
          )}
          <Btn variant="secondary" size="sm" onClick={() => { setExportRows(null); load(); }} disabled={loading}>
            {loading ? <Spinner/> : (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
              </svg>
            )}
            {loading ? "Cargando…" : "Recargar"}
          </Btn>
        </div>
      </div>

      {/* STAT CARDS */}
      <div style={{ display:"grid", gridTemplateColumns:mob?"1fr 1fr":"repeat(auto-fit, minmax(160px,1fr))", gap:10 }}>
        <SaleStatCard label="Total ventas" value={String(metrics.ventas)}
          sub={`${metrics.completadas} completadas · ${metrics.anuladas} anuladas`}
          color={C.accent}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 01-8 0"/></svg>}
        />
        <SaleStatCard label="Ingresos" value={`$${fCLP(metrics.total)}`}
          sub="Solo ventas completadas"
          color={C.accent}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>}
        />
        <SaleStatCard label="Utilidad bruta" value={`$${fCLP(metrics.profit)}`}
          sub={`Margen ${metrics.pct}%`}
          color={metrics.profit >= 0 ? C.green : C.red}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>}
        />
        <SaleStatCard label="Anuladas" value={String(metrics.anuladas)}
          color={C.red}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>}
        />
      </div>

      {/* FILTERS — en mobile (≤768px) los separadores verticales se ocultan
          porque al wrappear quedan flotando raros. Padding/font de los botones
          también se reducen para que entren todos los range buttons en 1-2
          filas máximo en pantallas chicas (~360px). */}
      <div style={{
        background:C.surface, border:`1px solid ${C.border}`,
        borderRadius:C.rMd, padding: mob ? "10px 12px" : "12px 16px", boxShadow:C.sh,
        display:"flex", gap: mob ? 6 : 10, alignItems:"center", flexWrap:"wrap",
      }}>
        {/* Search */}
        <div style={{ position:"relative", flex:1, minWidth: mob ? 0 : 200 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round"
            style={{ position:"absolute", left:10, top:"50%", transform:"translateY(-50%)", pointerEvents:"none" }}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Buscar por # venta o ID…"
            style={{
              width:"100%", height:36, padding:"0 10px 0 34px",
              border:`1px solid ${C.border}`, borderRadius:C.r,
              fontSize:13, background:C.bg,
            }}
          />
        </div>

        {!mob && <div style={{ width:1, height:24, background:C.border }}/>}

        {/* Range — Mario lo pidió: histórico por mes/año/personalizado
            además de los rangos cortos para reportes contables. */}
        {([
          { v:"TODAY", l:"Hoy" },
          { v:"7D",    l:"7 dias" },
          { v:"30D",   l:"30 dias" },
          { v:"MONTH", l:"Mes" },
          { v:"YEAR",  l:"Año" },
          { v:"CUSTOM", l:"Personal." },
          { v:"ALL",   l:"Todo" },
        ] as const).map(b => (
          <button key={b.v} type="button" onClick={() => setRange(b.v)} className="xb" style={{
            height: 32, padding: mob ? "0 8px" : "0 12px",
            borderRadius:C.r, fontSize: mob ? 11 : 12, fontWeight:600,
            border:`1px solid ${range===b.v ? C.accent : C.border}`,
            background:range===b.v ? C.accentBg : C.surface,
            color:range===b.v ? C.accent : C.mid,
          }}>{b.l}</button>
        ))}

        {/* Date pickers para CUSTOM */}
        {range === "CUSTOM" && (
          <>
            <input type="date" value={customFrom} onChange={e => setCustomFrom(e.target.value)}
              style={{ height:32, padding:"0 8px", border:`1px solid ${C.border}`, borderRadius:C.r, fontSize:12, fontFamily:"inherit" }} />
            <span style={{ fontSize:11, color:C.mute }}>→</span>
            <input type="date" value={customTo} onChange={e => setCustomTo(e.target.value)}
              style={{ height:32, padding:"0 8px", border:`1px solid ${C.border}`, borderRadius:C.r, fontSize:12, fontFamily:"inherit" }} />
          </>
        )}

        {!mob && <div style={{ width:1, height:24, background:C.border }}/>}

        {/* Status */}
        <select value={status} onChange={e => setStatus(e.target.value as any)} style={{
          height:36, padding:"0 10px", border:`1px solid ${C.border}`,
          borderRadius:C.r, fontSize:13, background:C.bg,
        }}>
          <option value="ALL">Todos los estados</option>
          <option value="COMPLETED">Completadas</option>
          <option value="VOID">Anuladas</option>
        </select>

        {/* Warehouse */}
        {warehouses.length > 0 && (
          <select value={warehouseId} onChange={e => setWarehouseId(e.target.value === "ALL" ? "ALL" : Number(e.target.value))} style={{
            height:36, padding:"0 10px", border:`1px solid ${C.border}`,
            borderRadius:C.r, fontSize:13, background:C.bg,
          }}>
            <option value="ALL">Todas las bodegas</option>
            {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}{w.warehouse_type==="sales_floor"?" (Sala)":" (Bodega)"}</option>)}
          </select>
        )}
      </div>

      {/* MAIN: TABLE + PANEL */}
      <div style={{ display:"flex", gap:14, alignItems:"flex-start", flexDirection:mob?"column":"row" }}>

        {/* TABLE */}
        <div style={{ flex:1, minWidth:0, display:"flex", flexDirection:"column", gap:0, width:mob?"100%":undefined }}>
          <div style={{
            background:C.surface, border:`1px solid ${C.border}`,
            borderRadius:C.rMd, overflow:"hidden", boxShadow:C.sh,
          }}>
          <div style={{ overflowX:"auto" }}>
            {/* Header */}
            <div style={{
              display:"grid", gridTemplateColumns:mob?"60px 1fr 90px 80px":"80px 1fr 80px 140px 120px 120px 110px",
              columnGap:mob?8:12, padding:mob?"10px 12px":"10px 18px",
              background:C.bg, borderBottom:`1px solid ${C.border}`,
              fontSize:10.5, fontWeight:700, color:C.mute,
              textTransform:"uppercase", letterSpacing:"0.08em",
            }}>
              <div>Folio</div>
              <div>Fecha</div>
              {!mob && <div>Origen</div>}
              {!mob && <div>Bodega</div>}
              <div style={{ textAlign:"right" }}>Total</div>
              {!mob && <div style={{ textAlign:"right" }}>Utilidad</div>}
              <div style={{ textAlign:"center" }}>Estado</div>
            </div>

            {loading && <SkeletonPage cards={0} rows={6} />}

            {err && (
              <div style={{ padding:"20px 18px" }}>
                <div style={{ padding:"11px 14px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, color:C.red, fontSize:13 }}>
                  {err}
                </div>
              </div>
            )}

            {!loading && !err && items.length === 0 && (
              <div style={{ padding:"56px 24px", textAlign:"center" }}>
                <div style={{ fontSize:36, marginBottom:10 }}>&#x1F4CB;</div>
                <div style={{ fontSize:15, fontWeight:700, color:C.text, marginBottom:4 }}>No hay ventas</div>
                <div style={{ fontSize:13, color:C.mute }}>Cambia los filtros o el rango de fechas</div>
              </div>
            )}

            {!loading && !err && items.map((s, i) => {
              const isSelected = s.id === selectedId;
              const isVoid     = s.status.toUpperCase() === "VOID";
              const profit     = toNum(s.gross_profit);
              const pct        = profitPct(s.gross_profit, s.total);
              const whName     = warehouses.find(w => w.id === s.warehouse_id)?.name ?? `#${s.warehouse_id}`;
              return (
                <div
                  key={s.id}
                  className={`prow${isSelected ? " active" : ""}`}
                  onClick={() => setSelectedId(isSelected ? null : s.id)}
                  style={{
                    display:"grid", gridTemplateColumns:mob?"60px 1fr 90px 80px":"80px 1fr 80px 140px 120px 120px 110px",
                    columnGap:mob?8:12, padding:mob?"11px 12px":"13px 18px",
                    borderBottom:i<items.length-1?`1px solid ${C.border}`:"none",
                    alignItems:"center",
                    opacity:isVoid ? 0.6 : 1,
                    borderLeft:isSelected ? `3px solid ${C.accent}` : "3px solid transparent",
                  }}
                >
                  {/* Folio */}
                  <div style={{ fontFamily:C.mono, fontWeight:700, fontSize:mob?12:13, color:isSelected?C.accent:C.text }}>
                    #{s.sale_number ?? s.id}
                  </div>

                  {/* Date */}
                  <div>
                    <div style={{ fontSize:mob?12:13, fontWeight:500 }}>{fDate(s.created_at)}</div>
                    <div style={{ fontSize:11, color:C.mute, marginTop:1 }}>
                      {new Date(s.created_at).toLocaleTimeString("es-CL", { hour:"2-digit", minute:"2-digit" })}
                    </div>
                  </div>

                  {/* Origin */}
                  {!mob && <div>
                    {s.open_order_id ? (
                      <span style={{ fontSize:10, padding:"2px 7px", borderRadius:99, background:"#FFFBEB", color:"#D97706", border:"1px solid #FDE68A", fontWeight:600 }}>
                        {s.table_name || "Mesa"}
                      </span>
                    ) : (
                      <span style={{ fontSize:10, padding:"2px 7px", borderRadius:99, background:"#EEF2FF", color:"#4F46E5", border:"1px solid #C7D2FE", fontWeight:600 }}>
                        POS
                      </span>
                    )}
                  </div>}

                  {/* Warehouse */}
                  {!mob && <div style={{ fontSize:12, color:C.mid }}>{whName}</div>}

                  {/* Total — patrón Fudo: la fila muestra el total de
                      la VENTA (sin propina). Si hubo propina, se indica
                      con un "+" en pequeño abajo para que Mario sepa
                      que el cobro al cliente fue mayor. */}
                  <div style={{ textAlign:"right", fontVariantNumeric:"tabular-nums" }}>
                    <div style={{ fontWeight:800, fontSize:mob?13:14 }}>
                      {isVoid ? <span style={{ textDecoration:"line-through", color:C.mute }}>${fCLP(s.total)}</span> : `$${fCLP(s.total)}`}
                    </div>
                    {!isVoid && s.tip && toNum(s.tip) > 0 && (
                      <div style={{ fontSize:10, color:"#d97706", fontWeight:700, marginTop:1 }}>
                        +${fCLP(s.tip)} prop.
                      </div>
                    )}
                  </div>

                  {/* Profit */}
                  {!mob && <div style={{ textAlign:"right" }}>
                    {!isVoid && (
                      <>
                        <div style={{ fontWeight:700, fontSize:13, color:profit>=0?C.green:C.red, fontVariantNumeric:"tabular-nums" }}>
                          ${fCLP(s.gross_profit)}
                        </div>
                        {pct !== null && (
                          <div style={{ fontSize:10, color:C.mute, marginTop:1 }}>{pct}%</div>
                        )}
                      </>
                    )}
                  </div>}

                  {/* Status */}
                  <div style={{ display:"flex", justifyContent:"center" }}>
                    <SaleStatusBadge status={s.status}/>
                  </div>
                </div>
              );
            })}
          </div>
          </div>

          {!loading && items.length > 0 && (
            <div style={{ padding:"10px 4px", fontSize:12, color:C.mute }}>
              {items.length} venta{items.length!==1?"s":""} · haz clic en una fila para ver el detalle
            </div>
          )}
        </div>

        {/* DETAIL PANEL */}
        {selectedId !== null && (
          <DetailPanel
            saleId={selectedId}
            warehouses={warehouses}
            mob={mob}
            onClose={() => setSelectedId(null)}
            onVoided={() => { load(); setSelectedId(null); }}
          />
        )}
      </div>
    </div>
  );
}
