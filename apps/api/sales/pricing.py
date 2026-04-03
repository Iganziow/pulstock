"""
Sales pricing and discount calculation.

Builds SaleLine objects with per-line and global discounts applied.
"""
from decimal import Decimal

from .models import SaleLine


def _model_has_field(model_cls, field_name: str) -> bool:
    try:
        return any(getattr(f, "name", None) == field_name for f in model_cls._meta.get_fields())
    except Exception:
        return False


def build_sale_lines(
    *,
    sale,
    tenant_id,
    agg,
    promo_map,
    products,
    recipe_costs,
    stock_map,
    global_discount_type="none",
    global_discount_value=Decimal("0"),
):
    """
    Build SaleLine objects with discounts, costs, and profit calculated.

    Args:
        sale: Sale instance (already created)
        tenant_id: int
        agg: dict product_id -> {qty, unit_price, discount_type, discount_value, promotion_id}
        promo_map: dict product_id -> (Promotion, effective_price)
        products: dict product_id -> Product
        recipe_costs: dict product_id -> Decimal (cost per unit for recipe products)
        stock_map: dict product_id -> StockItem (for avg_cost lookup)
        global_discount_type: "none" | "pct" | "amt"
        global_discount_value: Decimal

    Returns:
        tuple: (sale_lines, subtotal, total_discount, total_cost, total_qty_costed)
    """
    sl_has_unit_cost = _model_has_field(SaleLine, "unit_cost_snapshot")
    sl_has_line_cost = _model_has_field(SaleLine, "line_cost")
    sl_has_line_gp = _model_has_field(SaleLine, "line_gross_profit")

    sale_lines = []
    subtotal = Decimal("0.00")
    total_discount = Decimal("0.00")
    total_cost = Decimal("0.000")
    total_qty_costed = Decimal("0.000")

    agg_ids_sorted = sorted(agg.keys())
    for pid in agg_ids_sorted:
        qty = agg[pid]["qty"]
        unit_price = agg[pid]["unit_price"]
        gross_line_total = (qty * unit_price).quantize(Decimal("1"))

        # --- Per-line manual discount ---
        dt = agg[pid].get("discount_type", "none")
        dv = agg[pid].get("discount_value", Decimal("0"))
        line_discount = Decimal("0")
        original_up = None

        if dt == "pct" and dv > 0:
            line_discount = (gross_line_total * dv / Decimal("100")).quantize(Decimal("1"))
            original_up = unit_price
        elif dt == "amt" and dv > 0:
            line_discount = min(dv, gross_line_total).quantize(Decimal("1"))
            original_up = unit_price

        # Auto-detected promo (only if no manual discount)
        if pid in promo_map and line_discount == 0:
            promo_obj, promo_price = promo_map[pid]
            original_up = products[pid].price
            line_discount = ((original_up - unit_price) * qty).quantize(Decimal("1"))
            if line_discount < 0:
                line_discount = Decimal("0")

        line_promo_id = agg[pid].get("promotion_id")

        line_total = gross_line_total - line_discount
        if line_total < 0:
            line_total = Decimal("0")

        subtotal += gross_line_total
        total_discount += line_discount

        # Cost calculation
        if pid in recipe_costs:
            line_cost = (qty * recipe_costs[pid]).quantize(Decimal("0.000"))
            unit_cost = recipe_costs[pid]
        else:
            si = stock_map.get(pid)
            unit_cost = (si.avg_cost or Decimal("0.000")).quantize(Decimal("0.000")) if si else Decimal("0.000")
            line_cost = (qty * unit_cost).quantize(Decimal("0.000"))

        line_gp = (line_total - line_cost).quantize(Decimal("1"))

        sl_kwargs = dict(
            sale=sale,
            tenant_id=tenant_id,
            product_id=pid,
            qty=qty,
            unit_price=unit_price,
            line_total=line_total,
        )
        if sl_has_unit_cost:
            sl_kwargs["unit_cost_snapshot"] = unit_cost
        if sl_has_line_cost:
            sl_kwargs["line_cost"] = line_cost
        if sl_has_line_gp:
            sl_kwargs["line_gross_profit"] = line_gp

        # Discount tracking
        if line_discount > 0:
            sl_kwargs["discount_amount"] = line_discount
        if original_up is not None:
            sl_kwargs["original_unit_price"] = original_up

        # Promo FK
        if pid in promo_map and line_discount > 0 and not line_promo_id:
            sl_kwargs["promotion"] = promo_map[pid][0]
        elif line_promo_id:
            try:
                from promotions.models import Promotion
                promo_fk = Promotion.objects.filter(id=line_promo_id, tenant_id=tenant_id).first()
                if promo_fk:
                    sl_kwargs["promotion"] = promo_fk
            except Exception:
                pass

        sale_lines.append(SaleLine(**sl_kwargs))
        total_cost += line_cost
        total_qty_costed += qty

    # --- Global discount (distributed proportionally across lines) ---
    if global_discount_type != "none" and global_discount_value > 0:
        lines_total_sum = sum(sl.line_total for sl in sale_lines)
        if lines_total_sum > 0:
            if global_discount_type == "pct":
                global_disc_amount = (lines_total_sum * global_discount_value / Decimal("100")).quantize(Decimal("1"))
            else:
                global_disc_amount = min(global_discount_value, lines_total_sum).quantize(Decimal("1"))

            remaining = global_disc_amount
            for i, sl in enumerate(sale_lines):
                if lines_total_sum > 0:
                    share = (sl.line_total / lines_total_sum * global_disc_amount).quantize(Decimal("1"))
                else:
                    share = Decimal("0")
                if i == len(sale_lines) - 1:
                    share = remaining
                remaining -= share
                sl.line_total = max(sl.line_total - share, Decimal("0"))
                sl.discount_amount = (sl.discount_amount or Decimal("0")) + share
                if sl.original_unit_price is None:
                    sl.original_unit_price = sl.unit_price
                if sl_has_line_gp:
                    sl.line_gross_profit = (sl.line_total - (sl.line_cost or Decimal("0"))).quantize(Decimal("1"))
            total_discount += global_disc_amount

    return sale_lines, subtotal, total_discount, total_cost, total_qty_costed
