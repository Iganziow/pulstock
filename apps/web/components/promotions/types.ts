export type Promotion = {
  id: number;
  name: string;
  discount_type: "percentage" | "fixed";
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
  discount_type: "percentage" | "fixed";
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
  discount_type: "percentage",
  discount_value: "",
  start_date: "",
  end_date: "",
  product_items: [],
};
