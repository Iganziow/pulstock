export type PriceRow = {
  id: number;
  sku: string | null;
  name: string;
  category_name: string | null;
  category_id: number | null;
  cost: string;
  price: string;
  margin_pct: string;
};

export type Category = { id: number; name: string };
export type Msg = { type: "ok" | "err"; text: string } | null;

export type BulkPreviewItem = {
  id: number;
  name: string;
  oldPrice: number;
  newPrice: number;
  oldMargin: number | null;
  newMargin: number | null;
};
