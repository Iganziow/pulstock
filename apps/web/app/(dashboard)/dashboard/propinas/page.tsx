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

import { C } from "@/lib/theme";
import { TipsTable } from "@/components/propinas/TipsTable";

export default function PropinasPage() {
  return (
    <div style={{ padding: "16px 20px", maxWidth: 1400, margin: "0 auto" }}>
      <header style={{ marginBottom: 16 }}>
        <h1 style={{
          fontSize: 22, fontWeight: 800, color: C.text,
          letterSpacing: "-0.02em", margin: 0,
        }}>
          💵 Propinas
        </h1>
        <p style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>
          Detalle de propinas por venta. Las propinas son del equipo (no se
          mezclan con ingresos del local). Filtrá por fecha, garzón, método
          de pago o caja.
        </p>
      </header>

      <TipsTable showFilters defaultDaysRange={30} />

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
        en efectivo ya están físicamente en la caja.
      </div>
    </div>
  );
}
