"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";


function useIsMobile() { const [m, setM] = useState(false); useEffect(() => { const c = () => setM(window.innerWidth < 768); c(); window.addEventListener("resize", c); return () => window.removeEventListener("resize", c); }, []); return m; }
function Spinner() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ animation: "spin .7s linear infinite" }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" /></svg>; }
const fmt = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "0" : Math.round(n).toLocaleString("es-CL"); };
const fmtMoney = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL"); };

type Row = { warehouse_id: number; warehouse_name: string | null; product_id: number; sku: string | null; name: string | null; on_hand: string; avg_cost: string; stock_value: string };

export default function StockValuedPage() {
  const mob = useIsMobile();
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<Row[]>([]);
  const [totals, setTotals] = useState<{ total_qty: string; total_value: string } | null>(null);
  const [search, setSearch] = useState("");
  const [err, setErr] = useState("");

  const load = async (q = "") => {
    setLoading(true);
    try {
      setErr("");
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      const data = await apiFetch(`/reports/stock-valued/?${params}`);
      setRows(data?.results || []);
      setTotals(data?.totals || null);
    } catch (e: any) { setErr(e?.message || "Error al cargar el reporte"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const iS: React.CSSProperties = { padding: "7px 10px", border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 13, fontFamily: C.font, background: C.surface, outline: "none" };

  // Group by warehouse
  const byWarehouse: Record<string, { name: string; rows: Row[]; totalValue: number }> = {};
  rows.forEach(r => {
    const key = r.warehouse_name || "Sin bodega";
    if (!byWarehouse[key]) byWarehouse[key] = { name: key, rows: [], totalValue: 0 };
    byWarehouse[key].rows.push(r);
    byWarehouse[key].totalValue += parseFloat(r.stock_value || "0");
  });
  const warehouseGroups = Object.values(byWarehouse).sort((a, b) => b.totalValue - a.totalValue);

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "14px 10px" : "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <Link href="/dashboard/reports" style={{ fontSize: 12, color: C.mute, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4, marginBottom: 8 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg> Reportes
        </Link>
        <h1 style={{ margin: 0, fontSize: mob ? 19 : 23, fontWeight: 800, letterSpacing: "-.04em" }}>🏦 Stock valorizado</h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: C.mute }}>Cuánta plata tienes en inventario, desglosado por bodega y producto</p>
      </div>

      {err && <div style={{margin:"0 0 16px",padding:"10px 16px",borderRadius:8,background:C.redBg,border:`1px solid ${C.redBd}`,color:C.red,fontSize:13,fontWeight:500}}>{err}</div>}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <div style={{ position: "relative", flex: mob ? "1 1 100%" : "0 1 260px" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }}><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar producto…" style={{ ...iS, width: "100%", paddingLeft: 32 }}
            onKeyDown={e => e.key === "Enter" && load(search)} />
        </div>
        <button onClick={() => load(search)} style={{ ...iS, background: C.accent, color: "#fff", border: "none", cursor: "pointer", fontWeight: 600, padding: "7px 14px" }}>Consultar</button>
      </div>

      {loading && <div style={{ padding: 40, textAlign: "center", color: C.mute }}><Spinner /> Cargando…</div>}

      {/* Grand Total */}
      {totals && !loading && (
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(2, 1fr)", gap: 10 }}>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "14px 16px", boxShadow: C.sh }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Valor total en inventario</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: C.accent, marginTop: 4 }}>{fmtMoney(totals.total_value)}</div>
          </div>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "14px 16px", boxShadow: C.sh }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Unidades totales</div>
            <div style={{ fontSize: 28, fontWeight: 800, marginTop: 4 }}>{fmt(totals.total_qty)}</div>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{rows.length} producto{rows.length !== 1 ? "s" : ""}</div>
          </div>
        </div>
      )}

      {/* By warehouse */}
      {warehouseGroups.map(wh => (
        <div key={wh.name} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", boxShadow: C.sh, overflowX: "auto" }}>
          <div style={{ padding: "10px 18px", background: C.bg, borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 13, fontWeight: 700 }}>📦 {wh.name}</span>
            <span style={{ fontSize: 13, fontWeight: 800, color: C.accent }}>{fmtMoney(wh.totalValue)}</span>
          </div>
          {wh.rows.slice(0, 100).map((r, i) => (
            <div key={r.product_id} style={{ display: mob ? "block" : "grid", gridTemplateColumns: "1fr 80px 80px 90px", columnGap: 8, padding: mob ? "8px 12px" : "8px 18px", borderBottom: i < wh.rows.length - 1 ? `1px solid ${C.border}` : "none", alignItems: "center", fontSize: 13 }}>
              {mob ? (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ fontWeight: 600 }}>{r.name}</span>
                    <span style={{ fontWeight: 700 }}>{fmtMoney(r.stock_value)}</span>
                  </div>
                  <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>Stock: {fmt(r.on_hand)} · Costo: {fmtMoney(r.avg_cost)}</div>
                </>
              ) : (
                <>
                  <div>
                    <span style={{ fontWeight: 600 }}>{r.name}</span>
                    {r.sku && <span style={{ fontSize: 10, color: C.mute, marginLeft: 6 }}>{r.sku}</span>}
                  </div>
                  <div style={{ textAlign: "right" }}>{fmt(r.on_hand)}</div>
                  <div style={{ textAlign: "right", color: C.mid }}>{fmtMoney(r.avg_cost)}</div>
                  <div style={{ textAlign: "right", fontWeight: 700 }}>{fmtMoney(r.stock_value)}</div>
                </>
              )}
            </div>
          ))}
        </div>
      ))}

      {!loading && rows.length === 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "48px 20px", textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>📦</div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>Sin productos en stock</div>
          <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>No hay productos activos con stock positivo.</div>
        </div>
      )}

      <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}