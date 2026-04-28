export type Product = {
  id: number; name: string; sku?: string | null; unit?: string | null;
  has_recipe?: boolean; is_active?: boolean;
  unit_obj_id?: number | null; unit_obj_family?: string | null;
};

export type UnitType = {
  id: number; code: string; name: string; family: string; is_base: boolean;
};

export type RecipeLine = {
  id?: number; ingredient_id: number;
  ingredient_name?: string; ingredient_sku?: string; ingredient_unit?: string;
  /** ID del Unit del producto (FK). Si null, el producto solo tiene
      unit como string (ej. "UN") sin Unit asociado → no se puede
      validar familia ni convertir. */
  ingredient_unit_obj_id?: number | null;
  ingredient_unit_family?: string | null;
  qty: string;
  unit_id?: number | null; unit_code?: string | null;
};

export type Recipe = {
  id?: number; product_id?: number; is_active: boolean; notes: string; lines: RecipeLine[];
};
