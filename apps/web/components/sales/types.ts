export type SaleRow = {
  id: number;
  sale_number?: number | null;
  created_at: string;
  store_id: number;
  warehouse_id: number;
  subtotal: string;
  total: string;
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
  status: string;
  payments: SalePayment[];
  lines: SaleLine[];
};

export type Warehouse = { id: number; name: string; is_active: boolean; warehouse_type?: string };
