export type Category = {
  id: number;
  name: string;
  code?: string | null;
  parent_id?: number | null;
  parent_name?: string | null;
  is_active: boolean;
  // Estación de impresión donde sale la comanda por defecto.
  default_print_station_id?: number | null;
  default_print_station_name?: string | null;
};

export type Barcode = { id: number; code: string };

export type Product = {
  id: number; sku?: string | null; name: string;
  description?: string | null; unit?: string | null;
  price: string; is_active: boolean;
  category?: Category | null; barcodes?: Barcode[];
  cost?: string | null; min_stock?: string | null;
  brand?: string | null; image_url?: string | null;
  allow_negative_stock?: boolean;
  has_recipe?: boolean;
  // Override de estación a nivel producto. null = hereda categoría.
  print_station_override?: number | null;
  // Estación efectiva (override > category default > null) — readonly del backend.
  effective_print_station_id?: number | null;
};
