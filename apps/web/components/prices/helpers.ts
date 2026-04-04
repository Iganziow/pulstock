export function sanitizePrice(v: string): string {
  return v.replace(/[^0-9]/g, "");
}

export function calcMargin(cost: string, price: string): number | null {
  const c = Number(cost);
  const p = Number(price);
  if (!Number.isFinite(c) || !Number.isFinite(p) || p === 0) return null;
  return ((p - c) / p) * 100;
}
