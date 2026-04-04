"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";


const fmt = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "0" : Math.round(n).toLocaleString("es-CL"); };
const fmtMoney = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL"); };
const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (d: number) => { const t = new Date(); t.setDate(t.getDate() - d); return t.toISOString().slice(0, 10); };

const REASON_LABELS: Record<string, string> = {
  EXPIRED: "Vencimiento", DAMAGED: "Daño", THEFT: "Robo",
  INTERNAL: "Consumo interno", CORRECTION: "Corrección", SIN_MOTIVO: "Sin motivo",
};

type ByReason = { reason: string; qty: string; cost: string; moves: number };
type Detail = { id: number; created_at: string; product_name: string | null; category: string | null; warehouse_name: string | null; reason: string; qty: string; value_lost: string; note: string };

export default function LossesPage() {
  const mob = useIsMobile();
  const [loading, setLoading] = useState(true);
  const [totals, setTotals] = useState<{ qty: string; cost: string; moves: number } | null>(null);
  const [byReason, setByReason] = useState<ByReason[]>([]);
  const [details, setDetails] = useState<Detail[]>([]);
  const [dateFrom, setDateFrom] = useState(daysAgo(30));
  const [dateTo, setDateTo] = useState(today());
  const [showDetails, setShowDetails] = useState(false);
  const [err, setErr] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      setErr("");
      const data = await apiFetch(`/reports/losses/?date_from=${dateFrom}&date_to=${dateTo}`);
      setTotals(data?.totals || null);
      setByReason(data?.by_reason || []);
      setDetails(data?.details || []);
    } catch (e: any) { setErr(e?.message || "Error al cargar el reporte"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const iS: React.CSSProperties = { padding: "7px 10px", border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 13, fontFamily: C.font, background: C.surface, outline: "none" };
  const maxCost = Math.max(...byReason.map(r => parseFloat(r.cost) || 0), 1);

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "14px 10px" : "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <Link href="/dashboard/reports" style={{ fontSize: 12, color: C.mute, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4, marginBottom: 8 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg> Reportes
        </Link>
        <h1 style={{ margin: 0, fontSize: mob ? 19 : 23, fontWeight: 800, letterSpacing: "-.04em" }}>⚠️ Mermas y pérdidas</h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: C.mute }}>Productos perdidos por vencimiento, daño, robo u otros motivos</p>
      </div>

      {err && <div style={{margin:"0 0 16px",padding:"10px 16px",borderRadius:8,background:C.redBg,border:`1px solid ${C.redBd}`,color:C.red,fontSize:13,fontWeight:500}}>{err}</div>}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={iS} />
        <span style={{ fontSize: 12, color: C.mute }}>a</span>
        <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={iS} />
        <button onClick={load} style={{ ...iS, background: C.accent, color: "#fff", border: "none", cursor: "pointer", fontWeight: 600, padding: "7px 14px" }}>Consultar</button>
      </div>

      {loading && <div style={{ padding: 40, textAlign: "center", color: C.mute }}><Spinner /> Cargando…</div>}

      {/* Totals */}
      {totals && !loading && (
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(3, 1fr)", gap: 10 }}>
          <div style={{ background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: C.r, padding: "14px 16px" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.red, textTransform: "uppercase" }}>Total perdido</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: C.red, marginTop: 4 }}>{fmtMoney(totals.cost)}</div>
            <div style={{ fontSize: 11, color: C.mid, marginTop: 2 }}>en costo de productos</div>
          </div>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "14px 16px", boxShadow: C.sh }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Unidades perdidas</div>
            <div style={{ fontSize: 26, fontWeight: 800, marginTop: 4 }}>{fmt(totals.qty)}</div>
          </div>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "14px 16px", boxShadow: C.sh, gridColumn: mob ? "1 / -1" : "auto" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Movimientos</div>
            <div style={{ fontSize: 26, fontWeight: 800, marginTop: 4 }}>{totals.moves}</div>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>registros de pérdida</div>
          </div>
        </div>
      )}

      {/* By Reason */}
      {byReason.length > 0 && !loading && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: mob ? "12px" : "16px", boxShadow: C.sh }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.mid, marginBottom: 10 }}>Pérdida por motivo</div>
          {byReason.map((r, i) => {
            const cost = parseFloat(r.cost) || 0;
            const pct = (cost / maxCost) * 100;
            const label = REASON_LABELS[r.reason] || r.reason;
            return (
              <div key={i} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 3 }}>
                  <span style={{ fontWeight: 600 }}>{label}</span>
                  <span style={{ fontWeight: 700, color: C.red }}>{fmtMoney(cost)}</span>
                </div>
                <div style={{ height: 6, borderRadius: 3, background: "#E4E4E7", overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${pct}%`, background: C.red, borderRadius: 3 }} />
                </div>
                <div style={{ fontSize: 10, color: C.mute, marginTop: 2 }}>{fmt(r.qty)} unidades · {r.moves} movimiento{r.moves > 1 ? "s" : ""}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Detail toggle */}
      {details.length > 0 && !loading && (
        <div>
          <button onClick={() => setShowDetails(!showDetails)} style={{ ...iS, cursor: "pointer", color: C.accent, fontWeight: 600 }}>
            {showDetails ? "▾ Ocultar detalle" : "▸ Ver detalle de movimientos"} ({details.length})
          </button>
          {showDetails && (
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", boxShadow: C.sh, overflowX: "auto", marginTop: 8 }}>
              {details.map((d, i) => (
                <div key={d.id} style={{ padding: mob ? "8px 12px" : "8px 18px", borderBottom: i < details.length - 1 ? `1px solid ${C.border}` : "none", fontSize: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 600 }}>{d.product_name || "—"}</span>
                    <span style={{ fontWeight: 700, color: C.red }}>{fmtMoney(d.value_lost)}</span>
                  </div>
                  <div style={{ fontSize: 10, color: C.mute, marginTop: 2 }}>
                    {new Date(d.created_at).toLocaleDateString("es-CL")} · {REASON_LABELS[d.reason] || d.reason} · {fmt(d.qty)} uds · {d.warehouse_name || ""}
                    {d.note && <> · {d.note}</>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!loading && (!totals || parseFloat(totals.cost) === 0) && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "48px 20px", textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>✅</div>
          <div style={{ fontWeight: 700, fontSize: 15, color: C.green }}>Sin pérdidas registradas</div>
          <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>No hay mermas en este período. ¡Buen trabajo!</div>
        </div>
      )}

      <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}