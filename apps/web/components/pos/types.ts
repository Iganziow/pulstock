// ─── POS Shared Types ────────────────────────────────────────────────────────

export type Warehouse = { id: number; name: string; is_active: boolean; warehouse_type?: string };
export type Category  = { id: number; name: string; code?: string | null };
export type Barcode   = { id: number; code: string };
export type Product   = {
  id: number; sku?: string | null; name: string;
  description?: string | null; unit?: string | null;
  price: string; is_active: boolean;
  category?: Category | null; barcodes?: Barcode[];
};
export type PromoInfo = {
  product_id: number; promotion_id: number; promotion_name: string;
  discount_type: string; discount_value: string;
  original_price: string; promo_price: string;
};
export type CartLine = {
  product: Product; qty: number; unitPrice: number;
  discountType: "none" | "pct" | "amt";
  discountValue: number;
  promotion_id?: number;
  original_price?: number;
};
export type Shortage = {
  product_id: number; available: string; required: string;
  name?: string; sku?: string | null;
};

export type PosPayRow = { method: string; amount: string };

export const PAY_METHODS = [
  { value: "cash", label: "Efectivo", icon: "💵" },
  { value: "debit", label: "Débito", icon: "💳" },
  { value: "card", label: "Crédito", icon: "💳" },
  { value: "transfer", label: "Transferencia", icon: "🏦" },
] as const;

// ─── Helpers ─────────────────────────────────────────────────────────────────

export function toNumber(v: string | number) {
  const n = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(n) ? n : 0;
}

export function lineDiscount(line: CartLine): number {
  if (line.discountType === "pct")
    return Math.min(line.unitPrice * line.qty, (line.unitPrice * line.qty * line.discountValue) / 100);
  if (line.discountType === "amt")
    return Math.min(line.unitPrice * line.qty, line.discountValue);
  return 0;
}

export function lineSubtotal(line: CartLine): number {
  return line.unitPrice * line.qty - lineDiscount(line);
}
