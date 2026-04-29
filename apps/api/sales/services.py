"""
Sales service layer.

Orchestrates sale creation by delegating to focused modules:
- promotions.py  → resolve active promotions
- recipes.py     → expand BOM / recipe ingredients
- pricing.py     → build sale lines with discounts and costs
"""
import logging
from decimal import Decimal

from django.db import transaction, IntegrityError
from django.db.models import F

from core.models import Warehouse

logger = logging.getLogger(__name__)
from catalog.models import Product
from inventory.models import StockItem, StockMove

from .models import Sale, SaleLine, SalePayment, TenantSaleCounter
from .promotions import resolve_active_promotions
from .recipes import expand_recipes, compute_recipe_costs
from .pricing import build_sale_lines


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
    except (AttributeError, LookupError):
        return False


# ---------------------------------------------------------------------------
# Main orchestrator
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
    global_discount_type="none",
    global_discount_value=Decimal("0"),
):
    """
    Create a sale atomically.

    Flow:
        1. Validate warehouse
        2. Fetch products + resolve promotions
        3. Aggregate lines + capture discounts
        4. Expand recipes (BOM)
        5. Lock stock + check shortages
        6. Create Sale record
        7. Build SaleLines (pricing + discounts + costs)
        8. Decrement stock + create StockMoves
        9. Record payments
        10. Save final totals
    """
    payments_in = payments_in or []

    # ── 1. Validate warehouse ────────────────────────────────────────
    warehouse = (
        Warehouse.objects
        .select_related("store")
        .filter(id=warehouse_id, tenant_id=tenant_id, store_id=store_id)
        .first()
    )
    if not warehouse:
        raise SaleValidationError(
            {"detail": "Warehouse does not belong to active store",
             "active_store_id": store_id, "warehouse_id": warehouse_id},
            status_code=409,
        )

    # ── 2. Fetch products ────────────────────────────────────────────
    if not lines_in:
        raise SaleValidationError({"detail": "Sale must have at least one line"})

    if not any(float(l.get("qty", 0)) > 0 for l in lines_in):
        raise SaleValidationError({"detail": "La venta debe tener al menos un item con cantidad > 0"})

    product_ids = [int(l["product_id"]) for l in lines_in]
    products = {p.id: p for p in Product.objects.filter(tenant_id=tenant_id, id__in=product_ids)}

    # ── 2b. Resolve active promotions ────────────────────────────────
    promo_map = resolve_active_promotions(product_ids, products, tenant_id)

    # ── 3. Aggregate lines ───────────────────────────────────────────
    agg = {}
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

        line_discount_type = str(l.get("discount_type") or "none")
        line_discount_value = Decimal(str(l.get("discount_value") or 0))
        line_promotion_id = l.get("promotion_id")

        if pid in agg:
            if agg[pid]["unit_price"] != unit_price:
                raise SaleValidationError(
                    {"detail": f"Product {pid} appears twice with different prices"}
                )
            agg[pid]["qty"] += qty
        else:
            agg[pid] = {
                "qty": qty,
                "unit_price": unit_price,
                "discount_type": line_discount_type,
                "discount_value": line_discount_value,
                "promotion_id": line_promotion_id,
            }

    if all(agg[pid]["qty"] <= 0 for pid in agg):
        raise SaleValidationError({"detail": "Todos los items tienen cantidad 0."})

    # ── 4. Recipe expansion (recursivo: maneja recetas anidadas) ─────
    # expand_recipes devuelve all_recipes (todas las recetas activas del
    # tenant) en lugar del recipe_map antiguo. Lo usamos también para
    # compute_recipe_costs así el cost se calcula recursivamente.
    expanded_agg, all_recipes = expand_recipes(agg, tenant_id)

    # ── 5. Lock stock + check shortages ──────────────────────────────
    expanded_ids_sorted = sorted(expanded_agg.keys())
    stock_items = StockItem.objects.select_for_update().filter(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        product_id__in=expanded_ids_sorted,
    )
    stock_map = {int(si.product_id): si for si in stock_items}

    # Productos con allow_negative_stock=True: se permite vender aunque
    # no haya stock o quede negativo. Caso de uso: el dueño tiene
    # bombones físicos en la vitrina pero el sistema dice 0 (no actualizó
    # tras compra). En vez de bloquearlo, dejamos que la venta pase y
    # el stock baja a 0 (clampeado por constraint DB) — el dueño después
    # corrige con una entrada manual.
    #
    # Reportado por Marbrava 28/04/26: las mesas con Cappuccino no
    # cerraban porque la leche estaba en 53 ML y la receta requería
    # 150 ML. Antes la query filtraba solo `agg.keys()` (productos
    # directos) → marcar la leche con la flag NO servía (no estaba en
    # agg), marcar el Cappuccino TAMPOCO servía (después de
    # expand_recipes el Capuccino ya no está en expanded_agg). Ahora
    # incluimos también los ingredientes expandidos: marcar la leche
    # ahora deja pasar la venta y su stock se clampea a 0.
    allow_neg_pids = set(
        Product.objects.filter(
            tenant_id=tenant_id,
            id__in=list(set(list(agg.keys()) + list(expanded_agg.keys()))),
            allow_negative_stock=True,
        ).values_list("id", flat=True)
    )

    shortages = []
    for pid in expanded_ids_sorted:
        required_qty = expanded_agg[pid]["qty"]
        si = stock_map.get(pid)
        # Si este id (producto directo o ingrediente expandido) tiene la
        # flag allow_negative_stock=True → no chequeamos shortage.
        if pid in allow_neg_pids:
            continue
        if not si:
            shortages.append({"product_id": pid, "available": "0", "required": str(required_qty)})
            continue
        if si.on_hand - required_qty < 0:
            shortages.append({"product_id": pid, "available": str(si.on_hand), "required": str(required_qty)})

    if shortages:
        raise StockShortageError(shortages)

    # ── 6. Create Sale record ────────────────────────────────────────
    TenantSaleCounter.objects.get_or_create(tenant_id=tenant_id)
    counter = TenantSaleCounter.objects.select_for_update().get(tenant_id=tenant_id)
    TenantSaleCounter.objects.filter(pk=counter.pk).update(last_number=F("last_number") + 1)
    counter.refresh_from_db()

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
        sale_number=counter.last_number,
    )

    if _model_has_field(Sale, "unit_cost_snapshot"):
        sale_create_kwargs["unit_cost_snapshot"] = Decimal("0.000")
    if _model_has_field(Sale, "tip"):
        sale_create_kwargs["tip"] = tip
    if _model_has_field(Sale, "cash_session"):
        try:
            from caja.models import CashSession
            # select_for_update bloquea la sesión mientras commiteamos la
            # venta. Sin esto había race: cajero A cierra caja (toma lock,
            # computa expected_cash) en paralelo cajero B confirma venta
            # (lee sesión OPEN sin lock, attacha cash_session=esa). Al
            # commit del close, la venta queda enganchada pero NO entró
            # en el expected_cash → caja "falta" exactamente esa venta.
            #
            # Re-validamos status=OPEN bajo el lock: si la sesión cerró
            # entre el .first() y el lock, dejamos la venta sin
            # cash_session (queda fuera del arqueo, mejor que enganchada
            # incorrectamente).
            open_session = CashSession.objects.select_for_update().filter(
                tenant_id=tenant_id, store_id=store_id, status=CashSession.STATUS_OPEN
            ).first()
            if open_session and open_session.status == CashSession.STATUS_OPEN:
                sale_create_kwargs["cash_session"] = open_session
        except (ImportError, LookupError) as e:
            logger.warning("Error obteniendo sesión de caja: %s", e)

    try:
        sale = Sale.objects.create(**sale_create_kwargs)
    except IntegrityError:
        # Idempotency key collision — return the existing sale.
        # Lookup is per-tenant+store (matches DB constraint), no created_by
        # filter so retries from any device of the same store hit the same sale.
        existing = Sale.objects.filter(
            tenant_id=tenant_id,
            store_id=store_id,
            idempotency_key=idempotency_key,
        ).first()
        if existing:
            return _idempotent_response(existing)
        raise

    # ── 7. Build SaleLines (pricing + discounts + costs) ─────────────
    # Mario lo pidió: si el StockItem.avg_cost es 0 (porque nunca hubo
    # una compra que lo actualizara) PERO el Producto tiene `cost`
    # configurado en su ficha, usar `Product.cost` como fallback. Sin
    # esto, el reporte ABC mostraba "100% margen" (ganancia=revenue)
    # para todos los productos sin recepciones de compra, lo cual era
    # engañoso. La primera compra que se reciba va a actualizar avg_cost
    # con la fórmula PPP normal y reemplazará este fallback.
    def _effective_cost(si, product):
        avg = (si.avg_cost or Decimal("0.000"))
        if avg > 0:
            return avg.quantize(Decimal("0.000"))
        product_cost = getattr(product, "cost", None) or Decimal("0.000")
        return Decimal(str(product_cost)).quantize(Decimal("0.000"))

    ingredient_avg_cost = {
        pid: _effective_cost(stock_map[pid], products.get(pid))
        for pid in expanded_ids_sorted
        if pid in stock_map
    }
    recipe_costs = compute_recipe_costs(agg, all_recipes, ingredient_avg_cost, tenant_id=tenant_id)

    sale_lines, subtotal, total_discount, total_cost, total_qty_costed = build_sale_lines(
        sale=sale,
        tenant_id=tenant_id,
        agg=agg,
        promo_map=promo_map,
        products=products,
        recipe_costs=recipe_costs,
        stock_map=stock_map,
        global_discount_type=global_discount_type,
        global_discount_value=global_discount_value,
    )
    SaleLine.objects.bulk_create(sale_lines)

    # ── 8. Decrement stock + create StockMoves ───────────────────────
    stock_moves = []
    for pid in expanded_ids_sorted:
        qty = expanded_agg[pid]["qty"]
        si = stock_map.get(pid)
        if not si:
            continue

        # Mismo fallback Product.cost si avg_cost=0 (StockItem nunca tuvo
        # una compra que lo actualizara).
        unit_cost = _effective_cost(si, products.get(pid))

        # Si el producto permite stock negativo y la venta excede el
        # disponible, "clampeamos" el descuento al stock actual (lo deja
        # en 0). El sistema NO viola el constraint stockitem_on_hand_gte_0
        # de la DB, y el dueño puede después corregir con una entrada
        # manual cuando reciba mercadería. La venta se registra completa.
        if pid in allow_neg_pids and si.on_hand < qty:
            actual_decrement = si.on_hand
        else:
            actual_decrement = qty

        line_cost_move = (actual_decrement * unit_cost).quantize(Decimal("0.000"))

        StockItem.objects.filter(id=si.id).update(
            on_hand=F("on_hand") - actual_decrement,
            stock_value=F("stock_value") - line_cost_move,
        )

        # CRÍTICO: el StockMove debe registrar `actual_decrement` (qty REAL
        # descontada), NO `qty` (qty solicitada). Antes guardaba qty solicitada
        # y el void usaba ese valor para restaurar → al voidear ventas con
        # clamping (allow_negative + stock insuficiente) el sistema inflaba
        # el stock, creando "stock fantasma" que jamás existió.
        #
        # Reproducción del bug original (Marbrava 28/04/26):
        # - Leche en 0 ML, allow_negative=True
        # - Vender Latte vainilla (necesita 200 ML) → 201 OK, descuento real=0
        # - StockMove guardaba qty=200, value_delta=0 (inconsistente)
        # - Void → restauraba qty=200 → leche pasaba de 0 a 200 ML fantasmas
        #
        # Si actual_decrement=0, no creamos StockMove: no hubo movimiento
        # físico, y registrar uno con qty=0 ensucia el kardex sin aportar
        # valor (la SaleLine ya registra la venta).
        if actual_decrement > 0:
            stock_moves.append(
                StockMove(
                    tenant_id=tenant_id,
                    warehouse_id=warehouse_id,
                    product_id=pid,
                    move_type=StockMove.OUT,
                    qty=actual_decrement,
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

    # ── 9. Record payments ───────────────────────────────────────────
    # CRÍTICO: SalePayment.amount representa el dinero que ENTRÓ a la
    # caja, NO el dinero que el cliente entregó. Si el cliente paga con
    # cash más del total (ej. $11.000 por una cuenta de $10.000), el
    # cajero le devuelve $1.000 — esos $1.000 NO se quedan en la caja.
    # Si registramos amount=$11.000, el sistema espera ese dinero al
    # cerrar la caja → "falta $1.000" falso. Frontend ya recorta el
    # último pago, pero defensa server-side por si llega request raw
    # (POS direct, retry mal armado, cliente con bug).
    #
    # Lógica: el grandTotal a cobrar es subtotal_neto + tip. Si la suma
    # de payments excede ese grandTotal, recortamos el ÚLTIMO payment al
    # remanente para que sum(payments) == grandTotal exacto.
    grand_total_to_charge = max(
        (subtotal - total_discount).quantize(Decimal("1")), Decimal("0")
    ) + tip
    valid_methods = {SalePayment.METHOD_CASH, SalePayment.METHOD_CARD, SalePayment.METHOD_DEBIT, SalePayment.METHOD_TRANSFER}
    payment_rows = []
    total_paid = Decimal("0.00")
    # Procesamos primero todos los válidos; el clamp se aplica al final.
    raw_pays = []
    for p in payments_in:
        method = (p.get("method") or "").strip().lower()
        try:
            amount = Decimal(str(p.get("amount") or 0))
        except (ValueError, ArithmeticError, TypeError):
            continue
        if amount <= 0:
            logger.warning("Pago con monto no positivo ignorado: method=%s amount=%s sale=%s", method, amount, sale.id)
            continue
        if method in valid_methods:
            raw_pays.append((method, amount))
    # Clamp del último payment si la suma excede el grandTotal
    if raw_pays and grand_total_to_charge > 0:
        running = Decimal("0.00")
        for i, (method, amount) in enumerate(raw_pays):
            is_last = i == len(raw_pays) - 1
            if is_last and (running + amount) > grand_total_to_charge:
                clamped = (grand_total_to_charge - running).quantize(Decimal("0.01"))
                if clamped > 0:
                    payment_rows.append(SalePayment(sale=sale, tenant_id=tenant_id, method=method, amount=clamped))
                    total_paid += clamped
                # Si clamped == 0, el último payment se elimina (totalmente cubierto por previos).
            else:
                payment_rows.append(SalePayment(sale=sale, tenant_id=tenant_id, method=method, amount=amount))
                total_paid += amount
                running += amount
    if payment_rows:
        SalePayment.objects.bulk_create(payment_rows)

    if payment_rows and total_paid < subtotal:
        logger.warning("Pago insuficiente: total_paid=%s subtotal=%s sale=%s", total_paid, subtotal, sale.id)

    # ── 10. Save final totals ────────────────────────────────────────
    sale.subtotal = subtotal
    sale.total = max((subtotal - total_discount).quantize(Decimal("1")), Decimal("0"))
    sale.total_cost = total_cost.quantize(Decimal("0.000"))
    sale.gross_profit = (sale.total - sale.total_cost).quantize(Decimal("1"))

    save_fields = ["subtotal", "total", "total_cost", "gross_profit"]

    if _model_has_field(Sale, "unit_cost_snapshot"):
        sale.unit_cost_snapshot = (
            (sale.total_cost / total_qty_costed).quantize(Decimal("0.000"))
            if total_qty_costed > 0 else Decimal("0.000")
        )
        save_fields.append("unit_cost_snapshot")

    sale.save(update_fields=save_fields)

    # ── Payment warning ──────────────────────────────────────────────
    payment_warning = None
    if sale_type != Sale.SALE_TYPE_CONSUMO and payment_rows and total_paid < subtotal:
        payment_warning = f"Pago registrado ({total_paid}) es inferior al total ({subtotal})"

    return {
        "id": sale.id,
        "sale_number": sale.sale_number,
        "store_id": store_id,
        "warehouse_id": warehouse_id,
        "total": str(sale.total),
        # tip explícito en la respuesta para que el frontend pueda
        # imprimir la boleta con la propina correcta (sin re-fetch).
        "tip": str(getattr(sale, "tip", Decimal("0.00"))),
        "total_cost": str(sale.total_cost),
        "gross_profit": str(sale.gross_profit),
        "lines_count": len(sale_lines),
        "payment_warning": payment_warning,
        "sale_type": sale_type,
        "sale": sale,
    }


def _idempotent_response(existing: Sale) -> dict:
    # tip incluido para que el frontend pueda imprimir la boleta correcta
    # en caso de retry — si no, mostraba el TOTAL sin propina y se
    # confundía al cliente que ya había pagado el total con propina.
    return {
        "id": existing.id,
        "sale_number": existing.sale_number,
        "store_id": existing.store_id,
        "warehouse_id": existing.warehouse_id,
        "total": str(existing.total),
        "tip": str(getattr(existing, "tip", Decimal("0.00"))),
        "total_cost": str(existing.total_cost),
        "gross_profit": str(existing.gross_profit),
        "lines_count": existing.lines.count(),
        "payment_warning": None,
        "idempotent": True,
        "sale": existing,
    }
