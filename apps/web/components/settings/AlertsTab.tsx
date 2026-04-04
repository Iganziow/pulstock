"use client";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Card, SectionHeader } from "./SettingsUI";

interface AlertsTabProps {
  initialStates: Record<string, boolean>;
}

const ALERTS = [
  { key: "stock_bajo", label: "Stock bajo mínimo", desc: "Alerta cuando un producto baja del stock mínimo configurado" },
  { key: "forecast_urgente", label: "Predicción: producto por agotarse", desc: "Alerta cuando el sistema predice que un producto se agota en menos de 3 días" },
  { key: "sugerencia_compra", label: "Sugerencia de compra lista", desc: "Notificación cuando el sistema genera un pedido sugerido para aprobar" },
  { key: "merma_alta", label: "Merma inusual detectada", desc: "Alerta cuando las pérdidas de un producto superan lo histórico" },
  { key: "sin_rotacion", label: "Productos sin rotación", desc: "Aviso semanal de productos con stock pero sin ventas en 30+ días" },
  { key: "resumen_diario", label: "Resumen diario de ventas", desc: "Email con ventas, margen y productos más vendidos del día" },
];

export default function AlertsTab({ initialStates }: AlertsTabProps) {
  const [alertStates, setAlertStates] = useState<Record<string, boolean>>(initialStates);

  return (
    <Card>
      <SectionHeader icon="🔔" title="Alertas y notificaciones" desc="Cuáles alertas quieres recibir en tu dashboard" />
      <div style={{ display: "flex", flexDirection: "column" }}>
        {ALERTS.map((n, i, arr) => {
          const on = alertStates[n.key] ?? false;
          return (
            <div key={n.key} style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "13px 0",
              borderBottom: i < arr.length - 1 ? `1px solid ${C.border}` : "none",
              gap: 12,
            }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{n.label}</div>
                <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>{n.desc}</div>
              </div>
              <label className="toggle-switch" style={{ cursor: "pointer" }}>
                <input type="checkbox" checked={on} onChange={async () => {
                  const newVal = !on;
                  setAlertStates(prev => ({ ...prev, [n.key]: newVal }));
                  try {
                    await apiFetch("/core/alerts/", { method: "PATCH", body: JSON.stringify({ [n.key]: newVal }) });
                  } catch { setAlertStates(prev => ({ ...prev, [n.key]: on })); }
                }} />
                <div className="toggle-track" style={{ background: on ? C.accent : "#D4D4D8" }}>
                  <div className="toggle-knob" style={{ left: on ? 21 : 3 }} />
                </div>
              </label>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 16, padding: "10px 13px", background: C.accentBg, border: `1px solid ${C.accentBd}`, borderRadius: 8, fontSize: 12, color: C.accent, display: "flex", gap: 8 }}>
        <span>💡</span>
        <span>Tus preferencias se guardan automáticamente.</span>
      </div>
    </Card>
  );
}
