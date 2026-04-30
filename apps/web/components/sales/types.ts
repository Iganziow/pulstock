export type SaleRow = {
  id: number;
  sale_number?: number | null;
  created_at: string;
  store_id: number;
  warehouse_id: number;
  subtotal: string;
  total: string;
  /** Propina (puede ser "0" o ausente). Patrón Fudo: total = venta del
      local (sin propina); tip = propina por separado. El total cobrado
      al cliente = total + tip. */
  tip?: string | null;
  total_cost: string;
  gross_profit: string;
  status: string;
  created_by_id: number;
  open_order_id?: number | null;
  table_name?: string | null;
};

export type Product = { id: number; name: string; sku?: string | null };

export type SaleLine = {
  id: number;
  product: Product;
  qty: string;
  unit_price: string;
  line_total: string;
  unit_cost_snapshot?: string | null;
  line_cost?: string | null;
  line_profit?: string | null;
};

export type SalePayment = { method: "cash" | "card" | "debit" | "transfer"; amount: string };

/** Propina relacional (Daniel 29/04/26). Una venta puede tener N filas,
    cada una con su propio método. Sale.tip se mantiene como suma
    denormalizada para compat con queries agregadas. */
export type SaleTip = {
  id?: number;
  method: "cash" | "card" | "debit" | "transfer";
  amount: string;
};

export type SaleDetail = {
  id: number;
  sale_number?: number | null;
  created_at: string;
  store_id: number;
  warehouse_id: number;
  subtotal: string;
  total: string;
  total_cost: string;
  gross_profit: string;
  /** Propina total (suma denormalizada de `tips[]`). */
  tip?: string | null;
  /** Método legacy single-tip (deprecated, mantenido para compat). */
  tip_method?: string | null;
  /** Lista relacional de propinas split. Cada fila = monto + método. */
  tips?: SaleTip[];
  status: string;
  payments: SalePayment[];
  lines: SaleLine[];
};

export type Warehouse = { id: number; name: string; is_active: boolean; warehouse_type?: string };
