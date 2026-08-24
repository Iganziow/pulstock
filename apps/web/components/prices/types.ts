export type PriceRow = {
  id: number;
  sku: string | null;
  name: string;
  category_name: string | null;
  category_id: number | null;
  cost: string;
  /** De donde sale el costo: 'propio' (se compra), 'receta' (se arma),
   *  'receta_incompleta' (falta el costo de algun ingrediente). */
  cost_source?: "propio" | "receta" | "receta_incompleta" | null;
  /** Que ingredientes bloquean el calculo. Maximo 3. */
  missing_ingredients?: string[];
  price: string;
  margin_pct: string | null;
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
