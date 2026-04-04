export type TableStatus = "FREE" | "OPEN";

export interface TableActiveOrder {
  id: number;
  opened_at: string;
  items_count: number;
  subtotal: string;
  customer_name?: string;
}

export interface Table {
  id: number;
  name: string;
  capacity: number;
  status: TableStatus;
  is_active: boolean;
  zone: string;
  is_counter: boolean;
  active_order: TableActiveOrder | null;
}

export interface OrderLine {
  id: number;
  product_id: number;
  product_name: string;
  qty: string;
  unit_price: string;
  line_total: string;
  note: string;
  added_at: string;
  added_by: string;
  is_paid: boolean;
  is_cancelled: boolean;
  cancel_reason?: string;
}

export interface Order {
  id: number;
  table_id: number;
  table_name: string;
  status: string;
  opened_by: string;
  opened_at: string;
  closed_at: string | null;
  customer_name: string;
  note: string;
  warehouse_id: number;
  lines: OrderLine[];
  subtotal_unpaid: string;
}

export interface Product {
  id: number;
  name: string;
  price: string;
  sku: string;
}

export interface PaymentRow {
  method: string;
  amount: string;
}
