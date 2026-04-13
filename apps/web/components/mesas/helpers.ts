/** Format CLP number (no symbol, dot-separated thousands). */
export function fmt(v: string | number) {
  const n = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(n) ? Math.round(n).toLocaleString("es-CL") : "0";
}

/** Format an ISO timestamp to HH:MM (es-CL locale). */
export function fmtTime(iso: string) {
  return new Date(iso).toLocaleString("es-CL", { hour: "2-digit", minute: "2-digit" });
}

/** Relative time label from ISO timestamp (e.g. "5m", "1h 20m"). */
export function timeAgo(iso: string) {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (diff < 1) return "ahora";
  if (diff < 60) return `${diff}m`;
  const h = Math.floor(diff / 60);
  return `${h}h${diff % 60 > 0 ? ` ${diff % 60}m` : ""}`;
}

/** CSS injected once into the document head for mesa-card hover animations. */
export const PAGE_CSS = `
@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
@keyframes fadeIn{from{opacity:0;transform:scale(0.97)}to{opacity:1;transform:scale(1)}}
* { box-sizing: border-box; }
.mesa-card{transition:all 0.13s ease;cursor:pointer;}
.mesa-card:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,0,0,0.1);}
.summary-row{transition:background 0.12s ease;cursor:pointer;}
.summary-row:hover{background:#F4F4F5 !important;}
`;

export const PAY_METHODS = [
  { value: "cash", label: "Efectivo" },
  { value: "debit", label: "Débito" },
  { value: "card", label: "Crédito" },
  { value: "transfer", label: "Transferencia" },
] as const;
