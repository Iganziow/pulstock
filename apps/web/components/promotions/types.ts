// IMPORTANTE — los valores tienen que matchear los choices del backend:
//   apps/api/promotions/models.py
//     TYPE_PCT   = "pct"
//     TYPE_FIXED = "fixed_price"
// Antes el frontend usaba "percentage"/"fixed" y el backend rechazaba
// con 400 "no es una elección válida". Bug detectado el 07/05/26 cuando
// Mario intentó crear su primera oferta del Latte vainilla.
export type DiscountType = "pct" | "fixed_price";

export type Promotion = {
  id: number;
  name: string;
  discount_type: DiscountType;
  discount_value: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
  status: "active" | "scheduled" | "expired" | "inactive";
  product_count: number;
  created_at: string;
};

export type Product = {
  id: number;
  name: string;
  sku: string;
  price: string;
};

export type ProductItem = {
  product_id: number;
  override_discount_value?: string | null;
};

export type PromotionForm = {
  name: string;
  discount_type: DiscountType;
  discount_value: string;
  start_date: string;
  end_date: string;
  product_items: ProductItem[];
};

export type Conflict = {
  product_id: number;
  product_name: string;
  conflicting_promotion_name: string;
};

export type Toast = { type: "ok" | "err"; text: string } | null;

export const EMPTY_FORM: PromotionForm = {
  name: "",
  discount_type: "pct",
  discount_value: "",
  start_date: "",
  end_date: "",
  product_items: [],
};
