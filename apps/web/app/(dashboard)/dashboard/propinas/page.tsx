"use client";

/**
 * Apartado de Propinas — vista DEDICADA, separada de Ventas/Reportes.
 *
 * ¿Por qué separado?
 *   Las propinas pertenecen al equipo (mesero/cajero) — NO al negocio.
 *   Mostrarlas mezcladas con ingresos confunde al dueño y le hace pensar
 *   que está ganando más de lo que realmente gana. En `apps/api/sales/models.py`
 *   `Sale.tip` se guarda separado y NO se incluye en `Sale.total` ni en
 *   `gross_profit` (ver comentario línea 64-65). Los reportes de ingresos
 *   suman `Sale.total`, así que ya están limpios.
 *
 * Diseño:
 *   Mario lo pidió tipo Fudo — tabla detallada con filtros, no gráficos.
 *   "Cuando son 1000 mil registros es más fácil con tabla". Los gráficos
 *   anteriores no escalaban bien y daban poca info accionable. La tabla
 *   permite filtrar por garzón, método, caja y exportar/auditar.
 */

import { useEffect, useState } from "react";
import { C } from "@/lib/theme";
import { apiFetch } from "@/lib/api";
import { TipsTable } from "@/components/propinas/TipsTable";
import { WithdrawTipModal } from "@/components/caja/CajaModals";
import type { Session } from "@/components/caja/CajaShared";

export default function PropinasPage() {
  // Traer la sesión activa para saber si se puede retirar y mostrar
  // cuántas propinas en efectivo hay disponibles del turno actual.
  const [session, setSession] = useState<Session | null>(null);
  const [showWithdraw, setShowWithdraw] = useState(false);
  const [tipAmount, setTipAmount] = useState("");
  const [tipWho, setTipWho] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let alive = true;
    apiFetch("/caja/sessions/current/")
      .then((s: any) => { if (alive) setSession(s as Session); })
      .catch(() => { if (alive) setSession(null); });
    return () => { alive = false; };
  }, [refreshKey]);

  async function withdrawTip() {
    if (!session) return;
    const amt = Number(tipAmount);
    if (!amt || amt <= 0) return;
    setBusy(true);
    try {
      const desc = tipWho.trim()
        ? `Retiro de propinas — ${tipWho.trim()}`
        : "Retiro de propinas";
      await apiFetch(`/caja/sessions/${session.id}/movements/`, {
        method: "POST",
        body: JSON.stringify({
          type: "OUT",
          amount: amt,
          description: desc,
          category: "TIP_WITHDRAW",
        }),
      });
      setShowWithdraw(false); setTipAmount(""); setTipWho("");
      // Refresca sesión para que el monto disponible se actualice
      // y el TipsTable también se reconstruya con datos frescos.
      setRefreshKey(k => k + 1);
    } catch (e: any) {
      alert(e?.message ?? "Error registrando el retiro de propinas");
    } finally {
      setBusy(false);
    }
  }

  const hasOpenSession = !!(session && session.status === "OPEN");
  const cashTips = session?.live ? Number(session.live.cash_tips) || 0 : null;

  return (
    <div style={{ padding: "16px 20px", maxWidth: 1400, margin: "0 auto" }}>
      <header style={{
        marginBottom: 16,
        display: "flex", alignItems: "flex-start", justifyContent: "space-between",
        gap: 12, flexWrap: "wrap",
      }}>
        <div>
          <h1 style={{
            fontSize: 22, fontWeight: 800, color: C.text,
            letterSpacing: "-0.02em", margin: 0,
          }}>
            💵 Propinas
          </h1>
          <p style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>
            Detalle de propinas por venta. Las propinas son del equipo (no se
            mezclan con ingresos del local). Filtra por fecha, garzón, método
            de pago o caja.
          </p>
        </div>

        {/* Botón Retirar propinas — abre el mismo flujo que en /caja.
            Si no hay sesión abierta, el modal mostrará el mensaje de error
            (no necesitamos esconder el botón porque el modal es informativo). */}
        <button
          type="button"
          onClick={() => setShowWithdraw(true)}
          disabled={busy}
          style={{
            padding: "10px 18px", borderRadius: 8,
            border: `1px solid ${C.amberBd}`, background: C.amberBg,
            color: C.amber, cursor: busy ? "not-allowed" : "pointer",
            fontSize: 13, fontWeight: 700,
            display: "inline-flex", alignItems: "center", gap: 6,
            fontFamily: "inherit",
            flexShrink: 0,
          }}
          title="Registrar retiro de propinas en efectivo"
        >
          💸 Retirar propinas
        </button>
      </header>

      <TipsTable key={refreshKey} showFilters defaultDaysRange={30} />

      <div style={{
        marginTop: 16,
        padding: "10px 14px",
        background: C.amberBg,
        border: `1px solid ${C.amberBd}`,
        borderRadius: 8,
        fontSize: 12,
        color: C.mid,
        lineHeight: 1.5,
      }}>
        ℹ️ Las propinas en débito/crédito/transferencia llegan al banco con
        las ventas; el dueño debe pagarlas en efectivo al equipo. Las propinas
        en efectivo ya están físicamente en la caja — al retirarlas, registralas
        con el botón de arriba para que la caja cuadre al cierre.
      </div>

      {showWithdraw && (
        <WithdrawTipModal
          hasOpenSession={hasOpenSession}
          cashTipsAvailable={cashTips}
          amount={tipAmount} setAmount={setTipAmount}
          who={tipWho} setWho={setTipWho}
          busy={busy}
          onClose={() => { setShowWithdraw(false); setTipAmount(""); setTipWho(""); }}
          onSubmit={withdrawTip}
        />
      )}
    </div>
  );
}
