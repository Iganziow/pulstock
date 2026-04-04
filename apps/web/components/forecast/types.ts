export type KPIs = {
  at_risk_7d: number; imminent_3d: number; value_at_risk: string;
  avg_mape: number; model_count: number; pending_suggestions: number;
  products_with_forecast: number; products_without_forecast: number;
};

export type FP = {
  product_id: number; product_name: string; sku: string | null;
  category: string | null; warehouse_id: number; on_hand: string;
  avg_daily_demand: string; demand_7d: string; avg_cost?: string;
  days_to_stockout: number | null; algorithm: string;
  mape: number | null; data_points: number; trained_at?: string;
  is_recipe_ingredient?: boolean;
};

export type Detail = {
  product: { id: number; name: string; sku: string; category: string | null };
  stock: { on_hand: string; avg_cost: string; stock_value?: string };
  model: { algorithm: string; version?: number; metrics: any; data_points: number; trained_at?: string; params?: any; demand_pattern?: string } | null;
  suggestion: { suggested_qty: string; target_days: number; estimated_cost: string; reasoning: string | null; priority: string | null; is_estimate?: boolean } | null;
  history: { date: string; qty_sold: string; revenue?: string; qty_lost?: string; qty_received?: string }[];
  forecast: { date: string; qty_predicted: string; lower_bound: string; upper_bound: string; days_to_stockout: number | null; confidence?: string }[];
};

export type PageMeta = { count: number; page: number; page_size: number; total_pages: number; categories: string[] };
