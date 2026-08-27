/**
 * Íconos de trazo para la landing.
 *
 * Reemplazan a los 17 emojis que había antes. Un emoji se dibuja distinto en
 * cada sistema operativo —el mismo 🏪 es otra cosa en Windows, en Android y en
 * un iPhone— así que la página se veía diferente para cada visitante y ninguna
 * de esas versiones combinaba con el resto del diseño.
 *
 * Familia: 24×24, trazo 1.75, extremos redondeados, sin relleno. Heredan
 * `currentColor`, así que el color lo pone quien los usa.
 */

type Props = { size?: number; className?: string };

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  focusable: false as const,
});

/* ── El problema ─────────────────────────────────────────── */

/** Quiebre de stock: el estante vacío. */
export function OutOfStockIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M3 7h18" />
      <path d="M3 12h6" />
      <path d="M3 17h9" />
      <path d="M3 4v16" />
      <circle cx="17.5" cy="15.5" r="4" />
      <path d="M17.5 13.6v2.1" />
      <path d="M17.5 17.6h.01" />
    </svg>
  );
}

/** Sobrestock: cajas apiladas de más. */
export function OverstockIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <rect x="3" y="13" width="8" height="8" rx="1" />
      <rect x="13" y="13" width="8" height="8" rx="1" />
      <rect x="8" y="4.5" width="8" height="8" rx="1" />
      <path d="M8 8.5h8" />
      <path d="M3 17h8" />
      <path d="M13 17h8" />
    </svg>
  );
}

/** Compras a ciegas: se pide sin saber. */
export function BlindBuyIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M3.5 8.5 12 4l8.5 4.5v7L12 20l-8.5-4.5z" />
      <path d="M10.3 10.2a1.8 1.8 0 1 1 2.5 1.9c-.5.3-.8.8-.8 1.4" />
      <path d="M12 16.2h.01" />
    </svg>
  );
}

/* ── Cómo funciona ───────────────────────────────────────── */

/** Subir el catálogo. */
export function CatalogUploadIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M20 13v5.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5V13" />
      <path d="M12 15V4" />
      <path d="m8 7.5 4-3.5 4 3.5" />
    </svg>
  );
}

/** Vender y registrar compras. */
export function CartIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M2.5 3.5h2.2l2.1 10.4a1.6 1.6 0 0 0 1.6 1.3h8.3a1.6 1.6 0 0 0 1.6-1.3l1.3-6.6H5.6" />
      <circle cx="9" cy="19.5" r="1.4" />
      <circle cx="17" cy="19.5" r="1.4" />
    </svg>
  );
}

/** Qué te da plata. */
export function ProfitIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <ellipse cx="12" cy="6.5" rx="7.5" ry="3" />
      <path d="M4.5 6.5v11c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3v-11" />
      <path d="M4.5 12c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3" />
    </svg>
  );
}

/** Decisiones con datos. */
export function ChartIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M4 20V4" />
      <path d="M4 20h16" />
      <rect x="7.5" y="12" width="3.2" height="5" rx=".6" />
      <rect x="13.3" y="8" width="3.2" height="9" rx=".6" />
      <path d="m7 9.5 4-3.5 3 2 4.5-4" />
    </svg>
  );
}

/* ── Beneficios ──────────────────────────────────────────── */

/** Aviso antes del quiebre. */
export function AlertBellIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M18 8.5a6 6 0 1 0-12 0c0 5-2 6.5-2 6.5h16s-2-1.5-2-6.5" />
      <path d="M13.7 19a2 2 0 0 1-3.4 0" />
    </svg>
  );
}

/** Reporte semanal al correo. */
export function MailReportIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <rect x="2.5" y="5" width="19" height="14" rx="2" />
      <path d="m2.5 7 8.4 5.6a2 2 0 0 0 2.2 0L21.5 7" />
      <path d="M8 16.5v-2.2" />
      <path d="M11.5 16.5v-3.6" />
      <path d="M15 16.5v-1.4" />
    </svg>
  );
}

/** Margen real de cada venta. */
export function MarginIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="3.5" />
      <path d="M12 3.5v3" />
      <path d="M12 17.5v3" />
      <path d="M3.5 12h3" />
      <path d="M17.5 12h3" />
    </svg>
  );
}

/** Multi-local y transferencias. */
export function StoresIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M3.5 9.5V20h7V9.5" />
      <path d="M13.5 9.5V20h7V9.5" />
      <path d="M2.5 9.5 4 5h16l1.5 4.5a2.2 2.2 0 0 1-4.3.6 2.2 2.2 0 0 1-4.3 0 2.2 2.2 0 0 1-4.3 0 2.2 2.2 0 0 1-4.3-.6" />
      <path d="M10.5 14.5h3" />
      <path d="m12.2 13.2 1.3 1.3-1.3 1.3" />
    </svg>
  );
}

/* ── Tipos de negocio ────────────────────────────────────── */

/** Restaurant y cafetería: la taza, que es lo que realmente vende Marbrava. */
export function CafeIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M3.5 9h13v6a4 4 0 0 1-4 4h-5a4 4 0 0 1-4-4z" />
      <path d="M16.5 10.5h1.8a2.6 2.6 0 0 1 0 5.2h-1.8" />
      <path d="M7 5.5c0-.9.8-1.2.8-2.1" />
      <path d="M11 5.5c0-.9.8-1.2.8-2.1" />
    </svg>
  );
}

/** Minimarket y retail. */
export function RetailIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M4 10v10h16V10" />
      <path d="M2.5 10 4 4.5h16L21.5 10a2.3 2.3 0 0 1-4.4.6 2.3 2.3 0 0 1-4.5 0 2.3 2.3 0 0 1-4.5 0A2.3 2.3 0 0 1 2.5 10" />
      <path d="M9.5 20v-5.5h5V20" />
    </svg>
  );
}

/** Ferretería y materiales. */
export function HardwareIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M15.2 3.6a5 5 0 0 0-6 6.4L3.8 15.4a2 2 0 0 0 2.8 2.8l5.4-5.4a5 5 0 0 0 6.4-6l-3 3-2.6-.7-.7-2.6z" />
      <path d="M6.2 17.8h.01" />
    </svg>
  );
}

/** Farmacia. */
export function PharmacyIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <rect x="2.8" y="8.8" width="12.4" height="12.4" rx="6.2" transform="rotate(-45 9 15)" />
      <path d="m6.5 11.5 5 5" />
      <path d="M15.5 3.5h5" />
      <path d="M18 1v5" />
    </svg>
  );
}

/** Distribuidora y mayorista. */
export function TruckIcon({ size = 24, className }: Props) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M2.5 6.5h11v10h-11z" />
      <path d="M13.5 10h3.6l2.9 3v3.5h-6.5" />
      <circle cx="7" cy="18.5" r="1.7" />
      <circle cx="17" cy="18.5" r="1.7" />
      <path d="M8.7 18.5h6.6" />
    </svg>
  );
}
