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
  /** Propina (puede ser "0" o ausente). Se muestra en el detalle como
      apartado separado para que Mario y los chicos puedan cuadrar el
      cobro vs. lo que entró al banco/caja. */
  tip?: string | null;
  status: string;
  payments: SalePayment[];
  lines: SaleLine[];
};

export type Warehouse = { id: number; name: string; is_active: boolean; warehouse_type?: string };
