export function sanitizePrice(v: string): string {
  return v.replace(/[^0-9]/g, "");
}

/**
 * Margen porcentual, o null si no se puede calcular honestamente.
 *
 * Devuelve null cuando el COSTO es cero, y eso es deliberado.
 *
 * Un costo en cero casi nunca significa "me sale gratis": significa que nadie
 * lo cargo todavia. En Marbrava son 141 de 242 productos activos. Con la
 * formula cruda, todos esos mostraban "100,0%" pintado de verde --el dato
 * menos confiable con la apariencia mas tranquilizadora-- y el dueno tomaba
 * decisiones de precio sobre un margen inventado.
 *
 * Preferimos un guion. "No lo se" es informacion; "100%" es mentira.
 */
export function calcMargin(cost: string, price: string): number | null {
  const c = Number(cost);
  const p = Number(price);
  if (!Number.isFinite(c) || !Number.isFinite(p) || p === 0) return null;
  if (c === 0) return null;
  return ((p - c) / p) * 100;
}

/** Si el producto no tiene costo cargado — el motivo mas comun de un margen vacio. */
export function sinCosto(cost: string): boolean {
  const c = Number(cost);
  return !Number.isFinite(c) || c === 0;
}
