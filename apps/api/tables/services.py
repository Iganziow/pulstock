"""
tables/services.py — Checkout service for open table orders.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

from sales.services import create_sale, SaleValidationError, StockShortageError

from .models import OpenOrder, OpenOrderLine, Table


class CheckoutError(Exception):
    def __init__(self, detail, status_code=400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(str(detail))


@transaction.atomic
def checkout_order(
    *,
    order_id,
    tenant_id,
    store_id,
    mode,          # "all" | "partial"
    line_ids,      # list[int] — used when mode="partial"
    payments_in,   # list[{method, amount}]
    tip=Decimal("0.00"),
    tips_in=None,  # Fase A: opcional, list[{method, amount}] propinas explicitas
    line_qtys=None,  # opcional dict[line_id, qty] para cobro parcial
                     # (1 chaparrita de 2). Si no se pasa, cobra qty completa.
    user,
    sale_type="VENTA",
):
    """
    Checkout (pay) an open table order.

    mode="all"     → pay all unpaid lines
    mode="partial" → pay only the lines in line_ids

    `line_qtys` (opcional, solo aplica con mode="partial"): dict que mapea
    line_id → qty a cobrar. Si la qty es MENOR a la line.qty original,
    se hace cobro PARCIAL: se crea Sale por esa qty y la OpenOrderLine queda
    con el remanente (sigue is_paid=False con qty reducida).
    Si la qty == line.qty (o no se pasa para esa line), comportamiento clasico:
    marca la line completa como pagada.

    Caso de uso (Mario 25/05/26): mesa con 2 chaparritas, cliente quiere
    pagar solo 1 ahora. Antes el checkbox solo permitia "todo o nada" por
    line. Ahora: line_qtys={chaparrita_id: 1} cobra 1, deja 1 pendiente.

    Returns the Sale instance created.
    Raises CheckoutError, SaleValidationError, StockShortageError.
    """
    try:
        order = OpenOrder.objects.select_for_update().select_related("table").get(
            id=order_id, tenant_id=tenant_id, store_id=store_id, status=OpenOrder.STATUS_OPEN
        )
    except OpenOrder.DoesNotExist:
        raise CheckoutError({"detail": "Open order not found"}, status_code=404)

    unpaid_qs = order.lines.filter(is_paid=False, is_cancelled=False).select_related("product")

    if mode == "partial":
        if not line_ids:
            raise CheckoutError({"detail": "line_ids required for partial checkout"})
        unpaid_qs = unpaid_qs.filter(pk__in=line_ids)

    lines = list(unpaid_qs)
    if not lines:
        raise CheckoutError({"detail": "No unpaid lines to checkout"})

    # Validate all requested line_ids exist and are unpaid (for partial)
    if mode == "partial" and len(lines) != len(set(line_ids)):
        raise CheckoutError({"detail": "Some lines not found or already paid"})

    # Resolver qty efectiva por linea (line.qty si no hay override, o el
    # valor de line_qtys si existe). Validar 0 < qty <= line.qty original.
    line_qtys = line_qtys or {}
    effective_qtys = {}  # line.id -> Decimal
    for l in lines:
        # Soportar keys int y str (JSON envia strings). Usar `in` en vez
        # de `or` para que `0` no se trate como ausente.
        if l.id in line_qtys:
            override = line_qtys[l.id]
        elif str(l.id) in line_qtys:
            override = line_qtys[str(l.id)]
        else:
            effective_qtys[l.id] = l.qty
            continue
        try:
            qty = Decimal(str(override))
        except (ValueError, ArithmeticError, TypeError):
            raise CheckoutError({"detail": f"line_qtys[{l.id}] no es un numero valido"})
        if qty <= 0:
            raise CheckoutError({"detail": f"line_qtys[{l.id}] debe ser > 0"})
        if qty > l.qty:
            raise CheckoutError({
                "detail": f"line_qtys[{l.id}]={qty} excede qty disponible {l.qty}"
            })
        effective_qtys[l.id] = qty

    # Build sale input from order lines (con qty parcial si aplica)
    lines_in = [
        {
            "product_id": l.product_id,
            "qty": str(effective_qtys[l.id]),
            "unit_price": str(l.unit_price),
        }
        for l in lines
    ]

    # Create the sale using shared service
    result = create_sale(
        user=user,
        tenant_id=tenant_id,
        store_id=store_id,
        warehouse_id=order.warehouse_id,
        lines_in=lines_in,
        payments_in=payments_in,
        tip=tip,
        tips_in=tips_in,
        sale_type=sale_type,
    )

    sale = result["sale"]

    # Link sale to order (if Sale model has open_order field)
    try:
        sale.open_order = order
        sale.save(update_fields=["open_order"])
    except (AttributeError, ValueError) as e:
        logger.warning("No se pudo vincular sale con open_order: %s", e)

    # Marcar lineas como pagadas o decrementar qty si fue cobro parcial.
    # Caso parcial (qty cobrada < line.qty): line queda con remanente unpaid.
    # Caso completo (qty cobrada == line.qty): line.is_paid=True como siempre.
    fully_paid_pks = []
    for l in lines:
        cobrado = effective_qtys[l.id]
        if cobrado >= l.qty:
            # Pago completo: marca line entera como pagada (atomico mas abajo)
            fully_paid_pks.append(l.pk)
        else:
            # Pago parcial: decrementar qty de la line original
            new_qty = (l.qty - cobrado).quantize(Decimal("0.001"))
            OpenOrderLine.objects.filter(pk=l.pk).update(qty=new_qty)

    if fully_paid_pks:
        OpenOrderLine.objects.filter(pk__in=fully_paid_pks).update(
            is_paid=True,
            paid_by_sale=sale,
        )

    # If no active unpaid lines remain → close order + free table
    if not order.lines.filter(is_paid=False, is_cancelled=False).exists():
        order.status = OpenOrder.STATUS_CLOSED
        order.closed_at = timezone.now()
        order.save(update_fields=["status", "closed_at"])
        Table.objects.filter(pk=order.table_id).update(status=Table.STATUS_FREE)

    return result
