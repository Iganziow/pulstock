import React from "react";
import { C } from "@/lib/theme";

/**
 * Íconos de estado del checkout.
 *
 * Reemplazan los emojis (⏳ ⏱️ ✓ 🎉 ⚠️) que había en la pantalla de resultado
 * del pago. Un emoji lo dibuja el sistema operativo: el mismo ⏱️ es distinto
 * en Windows, Android y iPhone, y ninguna de esas versiones combina con el
 * resto. En la pantalla donde alguien acaba de entregar plata, verse
 * improvisado cuesta caro.
 *
 * Cada ícono va dentro de un disco de color que ya comunica el estado antes
 * de leer una palabra: verde = listo, índigo = en curso, ámbar = espera,
 * rojo = no se pudo.
 */

type Props = { size?: number };

const svgBase = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
});

export function Disco({ tono, children }: {
  tono: "verde" | "indigo" | "ambar" | "rojo";
  children: React.ReactNode;
}) {
  const tonos = {
    verde:  { fg: C.green,  bg: C.greenBg,  bd: C.greenBd },
    indigo: { fg: C.accent, bg: C.accentBg, bd: C.accentBd },
    ambar:  { fg: C.amber,  bg: C.amberBg,  bd: C.amberBd },
    rojo:   { fg: C.red,    bg: C.redBg,    bd: C.redBd },
  }[tono];

  return (
    <div style={{
      width: 56, height: 56, borderRadius: "50%",
      background: tonos.bg, border: `1px solid ${tonos.bd}`, color: tonos.fg,
      display: "flex", alignItems: "center", justifyContent: "center",
      margin: "0 auto 18px",
    }}>
      {children}
    </div>
  );
}

/** Pago confirmado. */
export function CheckIcon({ size = 26 }: Props) {
  return (
    <svg {...svgBase(size)}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

/** Todo listo — la cuenta quedó creada. */
export function ListoIcon({ size = 26 }: Props) {
  return (
    <svg {...svgBase(size)}>
      <path d="M22 11.1V12a10 10 0 1 1-5.9-9.1" />
      <path d="M22 4 12 14.01l-3-3" />
    </svg>
  );
}

/** Esperando la confirmación del banco. */
export function RelojIcon({ size = 26 }: Props) {
  return (
    <svg {...svgBase(size)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.2 1.9" />
    </svg>
  );
}

/** No se pudo procesar. */
export function AlertaIcon({ size = 26 }: Props) {
  return (
    <svg {...svgBase(size)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v4.5" />
      <path d="M12 16h.01" />
    </svg>
  );
}

/** El enlace venció. */
export function VencidoIcon({ size = 26 }: Props) {
  return (
    <svg {...svgBase(size)}>
      <circle cx="12" cy="12" r="9" />
      <path d="m9 9 6 6" />
      <path d="m15 9-6 6" />
    </svg>
  );
}

/** Rueda de carga, del mismo trazo que el resto.
 *
 * Trae su propia definicion de `girar`: es un componente suelto y no puede
 * asumir que la pagina que lo use ya tenga ese keyframe. Sin esto el spinner
 * se renderiza congelado, que es peor que no tenerlo -- parece que la pagina
 * se colgo justo despues de que la persona pago.
 */
export function Cargando({ size = 22 }: Props) {
  return (
    <>
      <style>{`
        @keyframes girar { to { transform: rotate(360deg) } }
        @media (prefers-reduced-motion: reduce) {
          .pulstock-girando { animation: none !important; opacity: .65 }
        }
      `}</style>
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true"
        className="pulstock-girando"
        style={{ animation: "girar 0.9s linear infinite" }}>
        <circle cx="12" cy="12" r="9" stroke={C.border} strokeWidth="2.5" />
        <path d="M21 12a9 9 0 0 0-9-9" stroke={C.accent} strokeWidth="2.5" strokeLinecap="round" />
      </svg>
    </>
  );
}
