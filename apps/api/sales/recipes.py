"""
Sales recipe expansion.

Expands sold products into their ingredients (BOM) for stock operations.
Products without recipes pass through unchanged.
"""
import logging
from decimal import Decimal

from catalog.models import Recipe

logger = logging.getLogger(__name__)


def expand_recipes(agg, tenant_id):
    """
    Expand aggregated sale lines into ingredient-level quantities.

    Args:
        agg: dict product_id -> {qty, unit_price, ...}
        tenant_id: int

    Returns:
        tuple: (expanded_agg, recipe_map, recipe_costs_fn)
            expanded_agg: dict ingredient_or_product_id -> {qty, unit_price}
            recipe_map: dict product_id -> Recipe (for products with recipes)
    """
    from catalog.unit_conversion import convert_qty

    recipe_map = {
        r.product_id: r
        for r in Recipe.objects.filter(
            tenant_id=tenant_id,
            product_id__in=list(agg.keys()),
            is_active=True,
        ).prefetch_related("lines__ingredient__unit_obj", "lines__unit")
    }

    expanded_agg = {}
    for pid, data in agg.items():
        if pid in recipe_map:
            recipe = recipe_map[pid]
            for line in recipe.lines.all():
                ing_id = line.ingredient_id
                recipe_qty = data["qty"] * line.qty
                # Auto-convert units if recipe line specifies a different unit
                if line.unit_id and line.ingredient.unit_obj_id and line.unit_id != line.ingredient.unit_obj_id:
                    try:
                        recipe_qty = convert_qty(recipe_qty, line.unit, line.ingredient.unit_obj)
                    except (ValueError, ZeroDivisionError) as exc:
                        from .services import SaleValidationError
                        raise SaleValidationError({
                            "detail": f"Error de conversión en receta: {line.ingredient.name} — {exc}"
                        })
                elif line.unit_id and not line.ingredient.unit_obj_id:
                    from catalog.models import Unit as UnitModel
                    ing_unit = UnitModel.objects.filter(
                        tenant_id=tenant_id,
                        code=line.ingredient.unit.upper() if line.ingredient.unit else "",
                        is_active=True,
                    ).first()
                    if ing_unit and ing_unit.pk != line.unit_id:
                        try:
                            recipe_qty = convert_qty(recipe_qty, line.unit, ing_unit)
                        except (ValueError, ZeroDivisionError):
                            pass
                if ing_id not in expanded_agg:
                    expanded_agg[ing_id] = {"qty": Decimal("0"), "unit_price": Decimal("0")}
                expanded_agg[ing_id]["qty"] += recipe_qty
        else:
            if pid not in expanded_agg:
                expanded_agg[pid] = {"qty": Decimal("0"), "unit_price": data["unit_price"]}
            expanded_agg[pid]["qty"] += data["qty"]

    return expanded_agg, recipe_map


def compute_recipe_costs(agg, recipe_map, ingredient_avg_cost):
    """
    Compute the cost per unit for recipe products based on ingredient costs.

    Args:
        agg: dict product_id -> {qty, ...}
        recipe_map: dict product_id -> Recipe
        ingredient_avg_cost: dict product_id -> Decimal (avg cost per unit)

    Returns:
        dict: product_id -> Decimal (cost per 1 unit of the recipe product)
    """
    from catalog.unit_conversion import convert_qty

    recipe_costs = {}
    for pid in agg:
        if pid in recipe_map:
            recipe = recipe_map[pid]
            cost = Decimal("0")
            for line in recipe.lines.all():
                converted_qty = line.qty
                if line.unit_id and line.ingredient.unit_obj_id and line.unit_id != line.ingredient.unit_obj_id:
                    try:
                        converted_qty = convert_qty(line.qty, line.unit, line.ingredient.unit_obj)
                    except (ValueError, ZeroDivisionError):
                        pass
                cost += ingredient_avg_cost.get(line.ingredient_id, Decimal("0")) * converted_qty
            recipe_costs[pid] = Decimal(str(cost)).quantize(Decimal("0.000"))
    return recipe_costs
