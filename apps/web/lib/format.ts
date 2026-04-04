/** Format a number as Chilean Pesos (no symbol, dot-separated thousands). */
export function formatCLP(value: string | number) {
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("es-CL");
}

/** Extract a human-readable error message from an ApiError or generic error. */
export function extractErr(e: any, fallback: string) {
  if (e?.data) {
    try {
      return typeof e.data === "string" ? e.data : JSON.stringify(e.data);
    } catch {
      return fallback;
    }
  }
  return e?.message ?? fallback;
}
