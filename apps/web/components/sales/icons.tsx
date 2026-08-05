"use client";

/**
 * Íconos SVG del detalle de venta (reemplazan los emojis 💵💳🏦💰ⓘ).
 *
 * Por qué SVG y no emoji: el emoji se renderiza distinto en cada sistema
 * (Windows, Android, iOS), no respeta el color del tema y desentona con los
 * demás íconos de la app, que ya eran SVG de trazo. Mismo estilo que el resto:
 * stroke=currentColor (hereda el color del texto que acompaña), esquinas
 * redondeadas, sin relleno.
 */
import type { CSSProperties } from "react";

type IconProps = { size?: number; style?: CSSProperties };

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

/** Billete — efectivo. */
export function BanknoteIcon({ size = 14, style }: IconProps) {
  return (
    <svg {...base(size)} style={style} aria-hidden>
      <rect x="2" y="6" width="20" height="12" rx="2" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M6 12h.01M18 12h.01" />
    </svg>
  );
}

/** Tarjeta — débito / crédito. */
export function CardIcon({ size = 14, style }: IconProps) {
  return (
    <svg {...base(size)} style={style} aria-hidden>
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <line x1="2" y1="10" x2="22" y2="10" />
    </svg>
  );
}

/** Banco — transferencia. */
export function BankIcon({ size = 14, style }: IconProps) {
  return (
    <svg {...base(size)} style={style} aria-hidden>
      <path d="M3 21h18" />
      <path d="M4 10h16" />
      <path d="M12 3L4 8h16L12 3z" />
      <path d="M6 10v8M10 10v8M14 10v8M18 10v8" />
    </svg>
  );
}

/** Monedas — método de pago desconocido. */
export function CoinsIcon({ size = 14, style }: IconProps) {
  return (
    <svg {...base(size)} style={style} aria-hidden>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v10M15 9.5c0-1-1.3-1.8-3-1.8s-3 .8-3 1.8 1 1.6 3 2 3 1 3 2-1.3 1.8-3 1.8-3-.8-3-1.8" />
    </svg>
  );
}

/** Persona — garzón. */
export function UserIcon({ size = 14, style }: IconProps) {
  return (
    <svg {...base(size)} style={style} aria-hidden>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

/** Info — avisos. */
export function InfoIcon({ size = 14, style }: IconProps) {
  return (
    <svg {...base(size)} style={style} aria-hidden>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-5M12 8h.01" />
    </svg>
  );
}

/** Cerrar. */
export function XIcon({ size = 14, style }: IconProps) {
  return (
    <svg {...base(size)} style={style} aria-hidden>
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

/** Volver (móvil). */
export function ArrowLeftIcon({ size = 14, style }: IconProps) {
  return (
    <svg {...base(size)} style={style} aria-hidden>
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </svg>
  );
}

/** Ícono por método de pago (cash/debit/card/transfer → SVG). */
export function PayMethodIcon({ method, size = 14, style }: IconProps & { method: string }) {
  switch (method) {
    case "cash": return <BanknoteIcon size={size} style={style} />;
    case "debit":
    case "card": return <CardIcon size={size} style={style} />;
    case "transfer": return <BankIcon size={size} style={style} />;
    default: return <CoinsIcon size={size} style={style} />;
  }
}
