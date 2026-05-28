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

from .models import Sale, SaleLine, SalePayment, SaleTip, TenantSaleCounter
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


def _normalize_tips_in(tips_in, tip_total):
    """
    Valida y normaliza tips_in (formato Fase A: propinas explicitas por metodo).

    Args:
        tips_in: list of {"method": str, "amount": Decimal|str|number}.
        tip_total: Decimal — total de propina esperado (debe coincidir con la
                   suma de tips_in para consistencia con el campo Sale.tip
                   denormalizado).

    Returns:
        list[dict] normalizado: [{"method": <valid>, "amount": Decimal}, ...]
        descartando items con amount <= 0.

    Raises:
        SaleValidationError si:
        - tips_in no es lista
        - algun item tiene method invalido (no en {cash, debit, card, transfer})
        - algun item tiene amount negativo o no parseable
        - sum(items.amount) != tip_total (tolerancia 1 centavo por rounding)

    Items con amount == 0 se filtran silenciosamente (caso comun: UI manda
    metodo seleccionado pero amount=0; equivale a "sin propina por ese metodo").
    """
    if not isinstance(tips_in, list):
        raise SaleValidationError("tips_in debe ser una lista de {method, amount}")

    valid_methods = {
        SalePayment.METHOD_CASH,
        SalePayment.METHOD_CARD,
        SalePayment.METHOD_DEBIT,
        SalePayment.METHOD_TRANSFER,
    }
    normalized = []
    for idx, item in enumerate(tips_in):
        if not isinstance(item, dict):
            raise SaleValidationError(f"tips_in[{idx}] debe ser dict {{method, amount}}")
        method = (item.get("method") or "").strip().lower()
        if method not in valid_methods:
            raise SaleValidationError(
                f"tips_in[{idx}].method '{method}' invalido. "
                f"Permitidos: {sorted(valid_methods)}"
            )
        try:
            amount = Decimal(str(item.get("amount") or 0))
        except (ValueError, ArithmeticError, TypeError):
            raise SaleValidationError(f"tips_in[{idx}].amount no es un numero valido")
        if amount < 0:
            raise SaleValidationError(f"tips_in[{idx}].amount no puede ser negativo")
        if amount == 0:
            continue  # silencioso — UI puede mandar metodos con 0
        normalized.append({"method": method, "amount": amount.quantize(Decimal("0.01"))})

    tip_total_q = Decimal(str(tip_total or 0)).quantize(Decimal("0.01"))
    sum_tips = sum((t["amount"] for t in normalized), Decimal("0")).quantize(Decimal("0.01"))
    # Tolerancia 1 centavo para evitar errores de rounding cliente-servidor.
    if abs(sum_tips - tip_total_q) > Decimal("0.01"):
        raise SaleValidationError(
            f"sum(tips_in)={sum_tips} no coincide con tip={tip_total_q} "
            f"(diferencia {abs(sum_tips - tip_total_q)})"
        )
    return normalized


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
    tips_in=None,
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

    # ── 0. Normalizar tips_in (Fase A: propinas explicitas, opt-in) ──
    # Si tips_in NO se pasa (frontend legacy) → tips_in_explicit = None →
    # camino legacy: SalePayment.amount incluye propina, SaleTip se crea por
    # reparto proporcional o 1 metodo segun len(payments).
    # Si tips_in SE pasa (frontend nuevo / API directa) → tips_in_explicit es
    # la lista normalizada → camino nuevo: SalePayment.amount = SOLO venta,
    # SaleTip rows = lo declarado explicitamente.
    tips_in_explicit = None
    if tips_in is not None:
        tips_in_explicit = _normalize_tips_in(tips_in, tip)

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
    #
    # lock_recipes=True: serializa contra ediciones concurrentes del dueño.
    # Caso del bug: cajero confirma venta de Latte vainilla mientras dueño
    # cambia la receta del Latte (200 → 250 ML). Sin lock, el cajero leía
    # la receta vieja y descontaba 200 ML, pero la receta vigente al
    # momento del commit decía 250 → kardex inconsistente. Con lock, la
    # edición espera. Crítico cuando varias cajas POS venden en paralelo.
    expanded_agg, all_recipes = expand_recipes(agg, tenant_id, lock_recipes=True)

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
    # `allow_neg_pids` combina TRES fuentes:
    #   (a) Productos vendidos directos con la flag (ej: Bombones).
    #   (b) Ingredientes raw expandidos con la flag (ej: leche entera).
    #   (c) PROPAGACIÓN: si un producto vendido directo tiene la flag,
    #       sus ingredientes (recursivos) heredan el permiso SOLO durante
    #       esta venta. Esto matchea la expectativa del dueño: "marco
    #       Latte vainilla como vender sin stock" → debe poder venderse
    #       aunque leche/café/syrup estén en 0. Sin la propagación, el
    #       dueño tenía que marcar manualmente cada ingrediente, y eso
    #       además habilitaría OTRAS ventas (Cappuccino, etc.) a pasar
    #       sin stock — efecto colateral no deseado.
    flagged_in_scope = set(
        Product.objects.filter(
            tenant_id=tenant_id,
            id__in=list(set(list(agg.keys()) + list(expanded_agg.keys()))),
            allow_negative_stock=True,
        ).values_list("id", flat=True)
    )
    # (c) propagación: si un padre en agg tiene la flag, todos sus
    # ingredientes recursivos (vía all_recipes) la heredan durante esta
    # venta. NO modifica la flag en BD, solo extiende el set en memoria.
    propagated_pids = set()
    parents_flagged = flagged_in_scope & set(agg.keys())
    for parent_pid in parents_flagged:
        if parent_pid not in all_recipes:
            continue
        # DFS por la cadena de receta del parent
        stack = [parent_pid]
        seen = set()
        while stack:
            pid_ = stack.pop()
            if pid_ in seen:
                continue
            seen.add(pid_)
            recipe_ = all_recipes.get(pid_)
            if not recipe_:
                continue
            for line in recipe_.lines.all():
                propagated_pids.add(line.ingredient_id)
                stack.append(line.ingredient_id)
    allow_neg_pids = flagged_in_scope | propagated_pids

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
        # Enriquecer con `name` y `unit` (símbolo: "u", "g", "ml", etc.) para
        # que el frontend pueda mostrar exactamente qué producto faltó —
        # como hace Fudo: "FANTA 350cc: 0.0 unid." en vez del genérico
        # "No hay stock suficiente". Una sola query para todos los pids.
        # Product ya está importado a nivel de módulo (línea 18) — NO
        # importarlo de nuevo acá: shadow + UnboundLocalError porque Python
        # marca `Product` como local en toda la función si lo asignás dentro.
        # Si por alguna razón no encontramos el producto (raro), fallback a
        # "Producto #ID" para no romper la respuesta.
        short_pids = [s["product_id"] for s in shortages]
        product_info = {
            p["id"]: p for p in
            Product.objects.filter(id__in=short_pids).values("id", "name", "unit_obj__code")
        }
        for s in shortages:
            info = product_info.get(s["product_id"], {})
            s["name"] = info.get("name") or f"Producto #{s['product_id']}"
            s["unit"] = info.get("unit_obj__code") or "u"
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
    #
    # Fase A (Fudo-style): cuando tips_in_explicit existe, los payments_in
    # representan SOLO el monto de la cuenta — la propina viene aparte en
    # tips_in. Entonces el grand_total_to_charge para clampear payments es
    # SOLO subtotal_neto (sin sumar tip), porque tip se cobra/registra como
    # SaleTip separado, no como SalePayment.
    sale_subtotal_net = max(
        (subtotal - total_discount).quantize(Decimal("1")), Decimal("0")
    )
    if tips_in_explicit is not None:
        grand_total_to_charge = sale_subtotal_net  # payments = solo venta
    else:
        grand_total_to_charge = sale_subtotal_net + tip  # legacy: incluye tip
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

    # ── 9.bis. Record tip rows (SaleTip relacional) ──────────────────
    # Daniel 29/04/26: las propinas viven en su propia tabla para soportar
    # split (ej. cliente paga $5000 débito + $200 propina cash + $300
    # propina transferencia). En la creación inicial no llega split desde
    # el POS — siempre 1 monto único de propina. Se asigna así:
    #   - Si hay 1 solo pago: 100% al método de ese pago.
    #   - Si hay split de pagos: reparto proporcional (última fila absorbe
    #     el redondeo). Cubre el caso típico cafetería (1 método).
    # Si después el dueño edita la propina vía PATCH /sales/{id}/tip/,
    # puede dejar el reparto que quiera (split arbitrario).
    #
    # FASE A (25/05/26): si tips_in_explicit existe (frontend Fudo-style),
    # NO hacemos reparto automatico — cada fila de tips_in_explicit es 1
    # SaleTip exacto. Sin smart-cash heuristic, sin proporcional.
    if tips_in_explicit is not None:
        if tips_in_explicit:
            SaleTip.objects.bulk_create([
                SaleTip(
                    sale=sale, tenant_id=tenant_id,
                    method=t["method"], amount=t["amount"],
                )
                for t in tips_in_explicit
            ])
    elif tip > 0 and payment_rows:
        tip_amount_total = Decimal(str(tip)).quantize(Decimal("0.01"))
        if len(payment_rows) == 1:
            SaleTip.objects.create(
                sale=sale, tenant_id=tenant_id,
                method=payment_rows[0].method,
                amount=tip_amount_total,
            )
        else:
            total_pay_amounts = sum((p.amount for p in payment_rows), Decimal("0"))
            if total_pay_amounts > 0:
                tip_rows = []
                running = Decimal("0")
                for p in payment_rows[:-1]:
                    share = (tip_amount_total * p.amount / total_pay_amounts).quantize(Decimal("0.01"))
                    if share > 0:
                        tip_rows.append(SaleTip(
                            sale=sale, tenant_id=tenant_id,
                            method=p.method, amount=share,
                        ))
                    running += share
                last = payment_rows[-1]
                last_share = (tip_amount_total - running).quantize(Decimal("0.01"))
                if last_share > 0:
                    tip_rows.append(SaleTip(
                        sale=sale, tenant_id=tenant_id,
                        method=last.method, amount=last_share,
                    ))
                if tip_rows:
                    SaleTip.objects.bulk_create(tip_rows)
    elif tip > 0 and not payment_rows:
        # Tip sin payments (caso defensivo: solo debería pasar en CONSUMO_INTERNO,
        # pero ahí tip=0 obligatorio. Si llega de algún flujo nuevo, atribuir a cash).
        SaleTip.objects.create(
            sale=sale, tenant_id=tenant_id,
            method=SalePayment.METHOD_CASH,
            amount=Decimal(str(tip)).quantize(Decimal("0.01")),
        )

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
