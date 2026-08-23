"use client";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Card, SectionHeader } from "./SettingsUI";

interface AlertsTabProps {
  initialStates: Record<string, boolean>;
}

type Alerta = {
  key: string;
  label: string;
  desc: string;
  /** Sin emisor todavía: se muestra deshabilitada en vez de prometer un aviso
   *  que no llega. Encender un interruptor y que no pase nunca nada es peor
   *  que no ofrecerlo. */
  proximamente?: boolean;
};

// Separadas por CÓMO llegan, porque no es lo mismo un correo que un aviso en
// la campana: el usuario decide distinto si sabe cuál es cuál.
const POR_CORREO: Alerta[] = [
  {
    key: "stock_bajo",
    label: "Quiebre de stock",
    desc: "Cada mañana, los productos sin stock o por agotarse en los próximos días",
  },
  {
    key: "reporte_abc",
    label: "Reporte ABC semanal",
    desc: "Los lunes: qué productos te dan la mayor parte de la plata y cuáles casi nada",
  },
  {
    key: "resumen_diario",
    label: "Resumen diario de ventas",
    desc: "Ventas, margen y productos más vendidos del día",
    proximamente: true,
  },
];

const EN_LA_APP: Alerta[] = [
  {
    key: "forecast_urgente",
    label: "Producto por agotarse",
    desc: "Cuando la predicción estima que algo se acaba en menos de 3 días",
  },
  {
    key: "sugerencia_compra",
    label: "Sugerencia de compra lista",
    desc: "Cuando el sistema deja preparado un pedido para aprobar",
  },
  {
    key: "merma_alta",
    label: "Merma inusual",
    desc: "Cuando las pérdidas de un producto superan lo habitual",
  },
  {
    key: "sin_rotacion",
    label: "Productos sin rotación",
    desc: "Productos con stock pero sin ventas en más de 30 días",
    proximamente: true,
  },
];

export default function AlertsTab({ initialStates }: AlertsTabProps) {
  const [alertStates, setAlertStates] = useState<Record<string, boolean>>(initialStates);

  async function alternar(key: string, actual: boolean) {
    const nuevo = !actual;
    setAlertStates((prev) => ({ ...prev, [key]: nuevo }));
    try {
      await apiFetch("/core/alerts/", {
        method: "PATCH",
        body: JSON.stringify({ [key]: nuevo }),
      });
    } catch {
      setAlertStates((prev) => ({ ...prev, [key]: actual }));
    }
  }

  function Fila({ a, ultima }: { a: Alerta; ultima: boolean }) {
    const on = alertStates[a.key] ?? false;
    const off = !!a.proximamente;
    return (
      <div
        style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "13px 0", gap: 12,
          borderBottom: ultima ? "none" : `1px solid ${C.border}`,
          opacity: off ? 0.55 : 1,
        }}
      >
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, display: "flex", alignItems: "center", gap: 7 }}>
            {a.label}
            {off && (
              <span style={{
                fontSize: 9.5, fontWeight: 700, letterSpacing: ".06em",
                textTransform: "uppercase", padding: "2px 6px", borderRadius: 4,
                background: C.bg, color: C.mute, border: `1px solid ${C.border}`,
              }}>
                Próximamente
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>{a.desc}</div>
        </div>
        <label
          className="toggle-switch"
          style={{ cursor: off ? "not-allowed" : "pointer" }}
          title={off ? "Todavía no disponible" : undefined}
        >
          <input
            type="checkbox"
            checked={on && !off}
            disabled={off}
            onChange={() => { if (!off) alternar(a.key, on); }}
          />
          <div className="toggle-track" style={{ background: on && !off ? C.accent : "#D4D4D8" }}>
            <div className="toggle-knob" style={{ left: on && !off ? 21 : 3 }} />
          </div>
        </label>
      </div>
    );
  }

  const Grupo = ({ titulo, nota, items }: { titulo: string; nota: string; items: Alerta[] }) => (
    <div style={{ marginBottom: 22 }}>
      <div style={{
        fontSize: 11, fontWeight: 700, letterSpacing: ".07em",
        textTransform: "uppercase", color: C.mute, marginBottom: 2,
      }}>
        {titulo}
      </div>
      <div style={{ fontSize: 12, color: C.mute, marginBottom: 6 }}>{nota}</div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {items.map((a, i) => (
          <Fila key={a.key} a={a} ultima={i === items.length - 1} />
        ))}
      </div>
    </div>
  );

  return (
    <Card>
      <SectionHeader
        icon="🔔"
        title="Alertas y notificaciones"
        desc="Cada persona elige las suyas: esto solo afecta a tu cuenta"
      />

      <Grupo
        titulo="Por correo"
        nota="Llegan a tu dirección registrada."
        items={POR_CORREO}
      />
      <Grupo
        titulo="Dentro de la app"
        nota="Aparecen en la campana, arriba a la derecha."
        items={EN_LA_APP}
      />

      <div style={{
        padding: "10px 13px", background: C.accentBg,
        border: `1px solid ${C.accentBd}`, borderRadius: 8,
        fontSize: 12, color: C.accent, display: "flex", gap: 8,
      }}>
        <span>💡</span>
        <span>Se guardan solas. Los dueños y encargados reciben las alertas por correo; los cajeros no.</span>
      </div>
    </Card>
  );
}
