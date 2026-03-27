"""
Sales service layer.

Extracted from SaleCreate view so that table checkout can reuse the same logic.
"""
import logging
from decimal import Decimal

from django.db import transaction, IntegrityError
from django.db.models import F

from core.models import Warehouse

logger = logging.getLogger(__name__)
from catalog.models import Product
from catalog.models import Recipe
from inventory.models import StockItem, StockMove

from .models import Sale, SaleLine, SalePayment, TenantSaleCounter


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class SaleValidationError(Exception):
    """Raised when input data is invalid (product not found, inactive, etc.)."""
    def __init__(self, detail, status_code=400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(str(detail))


class StockShortageError(Exception):
    """Raised when one or more products lack sufficient stock."""
    def __init__(self, shortages):
        self.shortages = shortages
        super().__init__("Insufficient stock")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_has_field(model_cls, field_name: str) -> bool:
    try:
        return any(getattr(f, "name", None) == field_name for f in model_cls._meta.get_fields())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

@transaction.atomic
def create_sale(
    *,
    user,
    tenant_id,
    store_id,
    warehouse_id,
    lines_in,
    payments_in=None,
    idempotency_key="",
    tip=Decimal("0.00"),
    sale_type="VENTA",
):
    """
    Create a sale atomically.

    Parameters
    ----------
    user            : User instance (request.user)
    tenant_id       : int
    store_id        : int
    warehouse_id    : int
    lines_in        : list[dict]  — each dict: {product_id, qty, unit_price}
    payments_in     : list[dict]  — each dict: {method, amount}
    idempotency_key : str (max 64 chars)
    tip             : Decimal     — optional gratuity, NOT added to sale.total

    Returns
    -------
    dict with keys: id, sale_number, store_id, warehouse_id, total, total_cost,
                    gross_profit, lines_count, payment_warning, sale (Sale instance)

    Raises
    ------
    SaleValidationError  — invalid input
    StockShortageError   — not enough stock
    """
    payments_in = payments_in or []

    # ------------------------------------------------------------------
    # 1) Validate warehouse belongs to store
    # ------------------------------------------------------------------
    warehouse = (
        Warehouse.objects
        .select_related("store")
        .filter(id=warehouse_id, tenant_id=tenant_id, store_id=store_id)
        .first()
    )
    if not warehouse:
        raise SaleValidationError(
            {
                "detail": "Warehouse does not belong to active store",
                "active_store_id": store_id,
                "warehouse_id": warehouse_id,
            },
            status_code=409,
        )

    # ------------------------------------------------------------------
    # 2) Fetch products
    # ------------------------------------------------------------------
    if not lines_in:
        raise SaleValidationError({"detail": "Sale must have at least one line"})

    product_ids = [int(l["product_id"]) for l in lines_in]
    products = {p.id: p for p in Product.objects.filter(tenant_id=tenant_id, id__in=product_ids)}

    # ------------------------------------------------------------------
    # 2b) Resolve active promotions
    # ------------------------------------------------------------------
    promo_map = {}  # product_id -> (Promotion, effective_price)
    try:
        from promotions.models import PromotionProduct as PP
        from django.utils import timezone
        now = timezone.now()
        pp_qs = PP.objects.filter(
            product_id__in=product_ids,
            promotion__tenant_id=tenant_id,
            promotion__is_active=True,
            promotion__start_date__lte=now,
            promotion__end_date__gte=now,
        ).select_related("promotion")
        for pp in pp_qs:
            promo = pp.promotion
            original = products[pp.product_id].price
            effective = promo.compute_promo_price(original, pp.override_discount_value)
            pid = pp.product_id
            if pid not in promo_map or effective < promo_map[pid][1]:
                promo_map[pid] = (promo, effective)
    except Exception as e:
        logger.warning("Error cargando promociones para venta (tenant=%s): %s", tenant_id, e)

    # ------------------------------------------------------------------
    # 3) Build agg — original sold products (for SaleLines / customer receipt)
    # ------------------------------------------------------------------
    agg = {}  # product_id -> {qty: Decimal, unit_price: Decimal}
    for l in lines_in:
        pid = int(l["product_id"])
        qty = Decimal(str(l["qty"]))
        unit_price = Decimal(str(l["unit_price"]))

        if qty <= 0:
            raise SaleValidationError({"detail": "qty must be > 0"})

        p = products.get(pid)
        if not p:
            raise SaleValidationError({"detail": f"Product {pid} not found"})
        if not p.is_active:
            raise SaleValidationError({"detail": f"Product {pid} is inactive"})

        if pid in agg:
            if agg[pid]["unit_price"] != unit_price:
                raise SaleValidationError(
                    {"detail": f"Product {pid} appears twice with different prices"}
                )
            agg[pid]["qty"] += qty
        else:
            agg[pid] = {"qty": qty, "unit_price": unit_price}

    # ------------------------------------------------------------------
    # 4) Recipe expansion — build expanded_agg for actual stock ops
    #    Products with an active recipe → replace with their ingredients.
    #    Products without a recipe → pass through unchanged.
    # ------------------------------------------------------------------
    from catalog.unit_conversion import convert_qty

    recipe_map = {
        r.product_id: r
        for r in Recipe.objects.filter(
            tenant_id=tenant_id,
            product_id__in=list(agg.keys()),
            is_active=True,
        ).prefetch_related("lines__ingredient__unit_obj", "lines__unit")
    }

    expanded_agg = {}  # ingredient_or_product_id -> {qty, unit_price}
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
                        raise SaleValidationError({
                            "detail": f"Error de conversión en receta: {line.ingredient.name} — {exc}"
                        })
                elif line.unit_id and not line.ingredient.unit_obj_id:
                    # Recipe line has unit but ingredient has no unit_obj —
                    # try to auto-resolve from ingredient's string unit field
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
                            pass  # Same family check failed — use raw qty
                if ing_id not in expanded_agg:
                    expanded_agg[ing_id] = {"qty": Decimal("0"), "unit_price": Decimal("0")}
                expanded_agg[ing_id]["qty"] += recipe_qty
        else:
            if pid not in expanded_agg:
                expanded_agg[pid] = {"qty": Decimal("0"), "unit_price": data["unit_price"]}
            expanded_agg[pid]["qty"] += data["qty"]

    # ------------------------------------------------------------------
    # 5) Lock StockItems from expanded_agg (ingredients / plain products)
    # ------------------------------------------------------------------
    expanded_ids_sorted = sorted(expanded_agg.keys())
    stock_items = StockItem.objects.select_for_update().filter(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        product_id__in=expanded_ids_sorted,
    )
    stock_map = {int(si.product_id): si for si in stock_items}

    # ------------------------------------------------------------------
    # 6) Check shortages against expanded_agg
    # ------------------------------------------------------------------
    shortages = []
    for pid in expanded_ids_sorted:
        required_qty = expanded_agg[pid]["qty"]
        si = stock_map.get(pid)
        if not si:
            shortages.append({"product_id": pid, "available": "0", "required": str(required_qty)})
            continue
        if si.on_hand - required_qty < 0:
            shortages.append({"product_id": pid, "available": str(si.on_hand), "required": str(required_qty)})

    if shortages:
        raise StockShortageError(shortages)

    # ------------------------------------------------------------------
    # 7) Assign sale_number (atomic counter — no race condition)
    # ------------------------------------------------------------------
    TenantSaleCounter.objects.get_or_create(tenant_id=tenant_id)
    counter = TenantSaleCounter.objects.select_for_update().get(tenant_id=tenant_id)
    TenantSaleCounter.objects.filter(pk=counter.pk).update(last_number=F("last_number") + 1)
    counter.refresh_from_db()
    next_sale_number = counter.last_number

    sale_create_kwargs = dict(
        tenant_id=tenant_id,
        store_id=store_id,
        warehouse_id=warehouse_id,
        created_by=user,
        subtotal=Decimal("0"),
        total=Decimal("0"),
        status="COMPLETED",
        sale_type=sale_type,
        total_cost=Decimal("0.000"),
        gross_profit=Decimal("0.000"),
        idempotency_key=idempotency_key,
        sale_number=next_sale_number,
    )

    if _model_has_field(Sale, "unit_cost_snapshot"):
        sale_create_kwargs["unit_cost_snapshot"] = Decimal("0.000")

    if _model_has_field(Sale, "tip"):
        sale_create_kwargs["tip"] = tip

    # Attach active cash session for this store (if any)
    if _model_has_field(Sale, "cash_session"):
        try:
            from caja.models import CashSession
            open_session = CashSession.objects.filter(
                tenant_id=tenant_id, store_id=store_id, status=CashSession.STATUS_OPEN
            ).first()
            if open_session:
                sale_create_kwargs["cash_session"] = open_session
        except Exception as e:
            logger.warning("Error obteniendo sesión de caja (tenant=%s store=%s): %s", tenant_id, store_id, e)

    # ------------------------------------------------------------------
    # 8) Create Sale (deferred until after stock validation)
    # ------------------------------------------------------------------
    try:
        sale = Sale.objects.create(**sale_create_kwargs)
    except IntegrityError:
        existing = Sale.objects.filter(tenant_id=tenant_id, idempotency_key=idempotency_key).first()
        if existing:
            return _idempotent_response(existing)
        raise

    # ------------------------------------------------------------------
    # 9) Build ingredient avg_cost map for recipe cost attribution
    #    Fetch from expanded_agg stock_map (already locked)
    # ------------------------------------------------------------------
    ingredient_avg_cost = {
        pid: (stock_map[pid].avg_cost or Decimal("0.000")).quantize(Decimal("0.000"))
        for pid in expanded_ids_sorted
        if pid in stock_map
    }

    # Compute recipe product cost: sum(ingredient.avg_cost * converted_qty) per recipe line
    recipe_costs = {}  # product_id -> Decimal
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
                        pass  # use raw qty if conversion fails
                cost += ingredient_avg_cost.get(line.ingredient_id, Decimal("0")) * converted_qty
            recipe_costs[pid] = Decimal(str(cost)).quantize(Decimal("0.000"))

    # ------------------------------------------------------------------
    # 10) Create SaleLines from agg (customer receipt — original products)
    # ------------------------------------------------------------------
    sl_has_unit_cost = _model_has_field(SaleLine, "unit_cost_snapshot")
    sl_has_line_cost = _model_has_field(SaleLine, "line_cost")
    sl_has_line_gp = _model_has_field(SaleLine, "line_gross_profit")

    sale_lines = []
    subtotal = Decimal("0.00")
    total_cost = Decimal("0.000")
    total_qty_costed = Decimal("0.000")

    agg_ids_sorted = sorted(agg.keys())
    for pid in agg_ids_sorted:
        qty = agg[pid]["qty"]
        unit_price = agg[pid]["unit_price"]
        line_total = (qty * unit_price).quantize(Decimal("1"))
        subtotal += line_total

        if pid in recipe_costs:
            # Recipe product: cost = per-unit cost from ingredients × qty
            line_cost = (qty * (recipe_costs[pid] / qty if qty else Decimal("0"))).quantize(Decimal("0.000"))
            # Recalculate: recipe_costs[pid] is already for the qty in expanded_agg
            # But we need cost per unit of the product, then × qty sold
            # Actually recipe_costs[pid] was computed as sum(ing_avg_cost * line.qty) — that's per 1 unit of product
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

        # Promo tracking
        if pid in promo_map:
            promo_obj, promo_price = promo_map[pid]
            sl_kwargs["promotion"] = promo_obj
            sl_kwargs["original_unit_price"] = products[pid].price
            sl_kwargs["discount_amount"] = ((products[pid].price - unit_price) * qty).quantize(Decimal("1"))

        sale_lines.append(SaleLine(**sl_kwargs))
        total_cost += line_cost
        total_qty_costed += qty

    SaleLine.objects.bulk_create(sale_lines)

    # ------------------------------------------------------------------
    # 11) Decrement stock + create StockMoves from expanded_agg (ingredients)
    # ------------------------------------------------------------------
    stock_moves = []
    for pid in expanded_ids_sorted:
        qty = expanded_agg[pid]["qty"]
        si = stock_map.get(pid)
        if not si:
            continue

        unit_cost = (si.avg_cost or Decimal("0.000")).quantize(Decimal("0.000"))
        line_cost_move = (qty * unit_cost).quantize(Decimal("0.000"))

        StockItem.objects.filter(id=si.id).update(
            on_hand=F("on_hand") - qty,
            stock_value=F("stock_value") - line_cost_move,
        )

        stock_moves.append(
            StockMove(
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                product_id=pid,
                move_type=StockMove.OUT,
                qty=qty,
                ref_type="SALE",
                ref_id=sale.id,
                note=f"Sale #{sale.id}",
                created_by=user,
                cost_snapshot=unit_cost,
                value_delta=(line_cost_move * Decimal("-1")).quantize(Decimal("0.000")),
            )
        )

    if stock_moves:
        StockMove.objects.bulk_create(stock_moves)

    # ------------------------------------------------------------------
    # 12) Save payments
    # ------------------------------------------------------------------
    valid_methods = {SalePayment.METHOD_CASH, SalePayment.METHOD_CARD, SalePayment.METHOD_DEBIT, SalePayment.METHOD_TRANSFER}
    payment_rows = []
    total_paid = Decimal("0.00")
    for p in payments_in:
        method = (p.get("method") or "").strip().lower()
        try:
            amount = Decimal(str(p.get("amount") or 0))
        except Exception:
            continue
        if method in valid_methods and amount > 0:
            payment_rows.append(SalePayment(sale=sale, tenant_id=tenant_id, method=method, amount=amount))
            total_paid += amount
    if payment_rows:
        SalePayment.objects.bulk_create(payment_rows)

    # ------------------------------------------------------------------
    # 13) Save final totals
    # ------------------------------------------------------------------
    sale.subtotal = subtotal
    sale.total = subtotal
    sale.total_cost = total_cost.quantize(Decimal("0.000"))
    sale.gross_profit = (sale.total - sale.total_cost).quantize(Decimal("1"))

    save_fields = ["subtotal", "total", "total_cost", "gross_profit"]

    if _model_has_field(Sale, "unit_cost_snapshot"):
        if total_qty_costed > 0:
            sale.unit_cost_snapshot = (sale.total_cost / total_qty_costed).quantize(Decimal("0.000"))
        else:
            sale.unit_cost_snapshot = Decimal("0.000")
        save_fields.append("unit_cost_snapshot")

    sale.save(update_fields=save_fields)

    # ------------------------------------------------------------------
    # 14) Payment warning
    # ------------------------------------------------------------------
    payment_warning = None
    if sale_type != Sale.SALE_TYPE_CONSUMO and payment_rows and total_paid < subtotal:
        payment_warning = f"Pago registrado ({total_paid}) es inferior al total ({subtotal})"

    return {
        "id": sale.id,
        "sale_number": sale.sale_number,
        "store_id": store_id,
        "warehouse_id": warehouse_id,
        "total": str(sale.total),
        "total_cost": str(sale.total_cost),
        "gross_profit": str(sale.gross_profit),
        "lines_count": len(sale_lines),
        "payment_warning": payment_warning,
        "sale_type": sale_type,
        "sale": sale,
    }


def _idempotent_response(existing: Sale) -> dict:
    return {
        "id": existing.id,
        "sale_number": existing.sale_number,
        "store_id": existing.store_id,
        "warehouse_id": existing.warehouse_id,
        "total": str(existing.total),
        "total_cost": str(existing.total_cost),
        "gross_profit": str(existing.gross_profit),
        "lines_count": existing.lines.count(),
        "payment_warning": None,
        "idempotent": True,
        "sale": existing,
    }
