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
    user,
    sale_type="VENTA",
):
    """
    Checkout (pay) an open table order.

    mode="all"     → pay all unpaid lines
    mode="partial" → pay only the lines in line_ids

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

    # Build sale input from order lines
    lines_in = [
        {
            "product_id": l.product_id,
            "qty": str(l.qty),
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
        sale_type=sale_type,
    )

    sale = result["sale"]

    # Link sale to order (if Sale model has open_order field)
    try:
        sale.open_order = order
        sale.save(update_fields=["open_order"])
    except (AttributeError, ValueError) as e:
        logger.warning("No se pudo vincular sale con open_order: %s", e)

    # Mark lines as paid
    line_pks = [l.pk for l in lines]
    OpenOrderLine.objects.filter(pk__in=line_pks).update(
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
