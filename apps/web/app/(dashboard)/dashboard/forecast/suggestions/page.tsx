"use client";

import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";
import { SuggestionCard, SuggestionConfirmModal, type Suggestion } from "@/components/forecast/SuggestionCard";

const fmtMoney = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL"); };

export default function SuggestionsPage() {
  const mob = useIsMobile();
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<number | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"PENDING" | "APPROVED" | "DISMISSED">("PENDING");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [confirmAction, setConfirmAction] = useState<{ id: number; action: "approve" | "dismiss" } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/forecast/suggestions/");
      const results: Suggestion[] = data?.results || [];
      setSuggestions(results);
      const firstPending = results.find(s => s.status === "PENDING");
      if (firstPending && expandedId === null) setExpandedId(firstPending.id);
    } catch (e: any) { setError(e?.message || "Error cargando sugerencias"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!confirmAction) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") setConfirmAction(null); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [confirmAction]);

  const handleApprove = async (id: number) => {
    setActing(id); setError(null); setConfirmAction(null);
    try {
      const res = await apiFetch(`/forecast/suggestions/${id}/approve/`, { method: "POST" });
      setSuccess(`✅ Orden de compra #${res.purchase_id} creada exitosamente.`);
      await load(); setTimeout(() => setSuccess(null), 5000);
    } catch (e: any) { setError(e?.data?.detail || e?.message || "Error al aprobar"); }
    finally { setActing(null); }
  };

  const handleDismiss = async (id: number) => {
    setActing(id); setError(null); setConfirmAction(null);
    try {
      await apiFetch(`/forecast/suggestions/${id}/dismiss/`, { method: "POST" });
      setSuccess("Sugerencia descartada.");
      await load(); setTimeout(() => setSuccess(null), 4000);
    } catch (e: any) { setError(e?.data?.detail || e?.message || "Error al descartar"); }
    finally { setActing(null); }
  };

  const filtered = suggestions.filter(s => s.status === tab);
  const pending = suggestions.filter(s => s.status === "PENDING");
  const approved = suggestions.filter(s => s.status === "APPROVED");
  const dismissed = suggestions.filter(s => s.status === "DISMISSED");

  const totalPendingCost = pending.reduce((s, p) => s + parseFloat(p.total_estimated || "0"), 0);
  const totalPendingProducts = pending.reduce((s, p) => s + p.lines_count, 0);
  const criticalCount = pending.filter(p => p.priority === "CRITICAL").length;

  const confirmSuggestion = confirmAction ? suggestions.find(x => x.id === confirmAction.id) : null;

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "20px 16px" : "40px 48px", display: "flex", flexDirection: "column", gap: 24 }}>

      {/* HEADER */}
      <div>
        <Link href="/dashboard/forecast" style={{ fontSize: 13, color: C.mute, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 12 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
          Volver a prediccion
        </Link>
        <h1 style={{ margin: 0, fontSize: mob ? 24 : 32, fontWeight: 700, letterSpacing: "-.02em", color: C.text }}>Pedidos sugeridos</h1>
        <p style={{ margin: "6px 0 0", fontSize: 15, color: C.mute }}>Recomendaciones automatizadas basadas en tu ritmo de ventas.</p>
      </div>

      {/* MESSAGES */}
      {error && (
        <div style={{ padding: "12px 16px", background: C.redBg, borderLeft: `4px solid ${C.red}`, borderRadius: 6, fontSize: 14, color: C.red, display: "flex", justifyContent: "space-between" }}>
          <span>{error}</span>
          <button onClick={() => setError(null)} style={{ background: "none", border: "none", cursor: "pointer", color: C.red, fontSize: 18 }}>×</button>
        </div>
      )}
      {success && (
        <div style={{ padding: "12px 16px", background: C.greenBg, borderLeft: `4px solid ${C.green}`, borderRadius: 6, fontSize: 14, color: C.green, fontWeight: 500 }}>{success}</div>
      )}

      {/* SKELETON LOADING */}
      {loading && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(3, 1fr)", gap: 16, marginBottom: 16 }}>
            {[1, 2, 3].map(i => (
              <div key={`sum-skel-${i}`} style={{ background: C.surface, borderRadius: C.r, padding: "20px", boxShadow: C.sh, gridColumn: mob && i === 3 ? "1 / -1" : "auto" }}>
                <div className="skeleton" style={{ width: "40%", height: 12, marginBottom: 12 }} />
                <div className="skeleton" style={{ width: "60%", height: 32, marginBottom: 8 }} />
                <div className="skeleton" style={{ width: "80%", height: 12 }} />
              </div>
            ))}
          </div>
          {[1, 2, 3].map(i => (
            <div key={`card-skel-${i}`} style={{ background: C.surface, borderRadius: C.r, padding: mob ? "16px" : "20px 24px", border: `1px solid ${C.border}`, boxShadow: C.sh }}>
              <div style={{ display: "flex", gap: 12, marginBottom: 16, alignItems: "center" }}>
                <div className="skeleton" style={{ width: 24, height: 24, borderRadius: "50%" }} />
                <div style={{ flex: 1 }}>
                  <div className="skeleton" style={{ width: mob ? "60%" : "30%", height: 16, marginBottom: 6 }} />
                  <div className="skeleton" style={{ width: mob ? "80%" : "50%", height: 12 }} />
                </div>
              </div>
              <div style={{ display: "flex", gap: 24, paddingTop: 12, borderTop: `1px dashed ${C.border}` }}>
                <div className="skeleton" style={{ width: 60, height: 36 }} />
                <div className="skeleton" style={{ width: 60, height: 36 }} />
                <div className="skeleton" style={{ width: 80, height: 36 }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* MAIN CONTENT */}
      {!loading && (
        <>
          {/* SUMMARY CARDS */}
          {pending.length > 0 && tab === "PENDING" && (
            <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(3, 1fr)", gap: 16 }}>
              <div style={{ background: C.surface, borderRadius: C.r, padding: "20px", boxShadow: C.sh }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em" }}>Pendientes</div>
                <div style={{ fontSize: 32, fontWeight: 700, color: C.text, marginTop: 8 }}>{pending.length}</div>
                <div style={{ fontSize: 13, color: criticalCount > 0 ? C.red : C.mute, marginTop: 4, fontWeight: criticalCount > 0 ? 600 : 400 }}>
                  {criticalCount > 0 ? `⚠️ ${criticalCount} requieren atencion hoy` : "Sin urgencias inmediatas"}
                </div>
              </div>
              <div style={{ background: C.surface, borderRadius: C.r, padding: "20px", boxShadow: C.sh }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em" }}>Productos</div>
                <div style={{ fontSize: 32, fontWeight: 700, color: C.text, marginTop: 8 }}>{totalPendingProducts}</div>
                <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>Para reponer en total</div>
              </div>
              <div style={{ background: C.surface, borderRadius: C.r, padding: "20px", boxShadow: C.sh, gridColumn: mob ? "1 / -1" : "auto" }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em" }}>Inversion Estimada</div>
                <div style={{ fontSize: 32, fontWeight: 700, color: C.text, marginTop: 8 }}>{fmtMoney(totalPendingCost)}</div>
                <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>Al aprobar todos los pedidos</div>
              </div>
            </div>
          )}

          {/* TABS */}
          <div style={{ display: "flex", gap: 24, borderBottom: `1px solid ${C.border}` }}>
            {([
              { key: "PENDING" as const, label: "Pendientes", count: pending.length },
              { key: "APPROVED" as const, label: "Aprobados", count: approved.length },
              { key: "DISMISSED" as const, label: "Descartados", count: dismissed.length },
            ]).map(t => (
              <button key={t.key} onClick={() => setTab(t.key)} style={{
                padding: "0 0 12px 0", fontSize: 14, fontWeight: tab === t.key ? 600 : 400, color: tab === t.key ? C.accent : C.mute,
                background: "none", border: "none", cursor: "pointer", borderBottom: tab === t.key ? `2px solid ${C.accent}` : "2px solid transparent",
                marginBottom: -1, fontFamily: C.font, display: "flex", alignItems: "center", gap: 8, transition: "all .2s"
              }}>
                {t.label}
                {t.count > 0 && <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 12, background: tab === t.key ? C.accentBg : "#F4F4F5", color: tab === t.key ? C.accent : C.mute }}>{t.count}</span>}
              </button>
            ))}
          </div>

          {/* EMPTY STATES */}
          {filtered.length === 0 && (
            <div style={{ background: C.surface, borderRadius: C.r, padding: "64px 20px", textAlign: "center", boxShadow: C.sh }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>{tab === "PENDING" ? "☕" : tab === "APPROVED" ? "📦" : "🗂"}</div>
              <div style={{ fontWeight: 600, fontSize: 18, color: C.text }}>
                {tab === "PENDING" && "Todo al dia, no hay pedidos pendientes"}
                {tab === "APPROVED" && "Aun no has aprobado sugerencias"}
                {tab === "DISMISSED" && "No hay sugerencias descartadas"}
              </div>
              <div style={{ fontSize: 14, color: C.mute, marginTop: 8, maxWidth: 400, margin: "8px auto 0", lineHeight: 1.6 }}>
                {tab === "PENDING" && "El sistema esta monitoreando tu inventario. Te avisaremos cuando sea momento de reponer."}
                {tab === "APPROVED" && "Cuando apruebes una sugerencia, se convertira en una orden de compra."}
              </div>
              {tab === "PENDING" && (
                <div style={{ marginTop: 24 }}>
                  <Link href="/dashboard/inventory" style={{ padding: "10px 20px", background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, color: C.text, textDecoration: "none", fontWeight: 600, fontSize: 14, display: "inline-flex", alignItems: "center", gap: 8, boxShadow: C.sh, transition: "all .2s" }} className="btn-secondary">📦 Revisar mi inventario</Link>
                </div>
              )}
              {tab === "APPROVED" && (
                <div style={{ marginTop: 24 }}>
                  <Link href="/dashboard/purchases" style={{ padding: "10px 20px", background: C.accent, borderRadius: 8, color: "#fff", textDecoration: "none", fontWeight: 600, fontSize: 14, display: "inline-flex", alignItems: "center", gap: 8, boxShadow: "0 2px 8px rgba(79,70,229,.25)", transition: "all .2s" }} className="btn-primary">Ir a Ordenes de Compra →</Link>
                </div>
              )}
            </div>
          )}

          {/* SUGGESTION CARDS */}
          {filtered.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {filtered.map(s => (
                <SuggestionCard key={s.id} s={s} expanded={expandedId === s.id} onToggle={() => setExpandedId(expandedId === s.id ? null : s.id)} mob={mob} acting={acting} onConfirmAction={setConfirmAction} />
              ))}
            </div>
          )}
        </>
      )}

      {/* CONFIRM MODAL */}
      {confirmAction && confirmSuggestion && (
        <SuggestionConfirmModal suggestion={confirmSuggestion} action={confirmAction.action} mob={mob} acting={acting} onClose={() => setConfirmAction(null)} onApprove={handleApprove} onDismiss={handleDismiss} />
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }
        @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(10px) } to { opacity: 1; transform: translateY(0) } }
        @keyframes skeleton-pulse { 0% { background-color: #E4E4E7; } 50% { background-color: #F4F4F5; } 100% { background-color: #E4E4E7; } }
        .skeleton { animation: skeleton-pulse 1.5s ease-in-out infinite; border-radius: 6px; }
        .sug-header:hover { background: #F8FAFC !important; }
        .btn-dismiss:hover { background: #F4F4F5 !important; }
        .btn-approve:hover, .btn-primary:hover { filter: brightness(1.1); }
        .btn-secondary:hover { background: #F8FAFC !important; }
      `}</style>
    </div>
  );
}
