"""
F-VOID (19/06/26): aggregate_daily_sales contaba las ventas ANULADAS
(status=VOID) como demanda — sus StockMove OUT/SALE sumaban a qty_sold y sus
SaleLines a revenue. Auditoría prod: 22 voids = 3.330 u fugando al forecast.

Fix: excluir ventas VOID tanto en demanda (StockMove) como en revenue (SaleLine).
"""
from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command

from sales.models import Sale, SaleLine
from inventory.models import StockMove
from forecast.models import DailySales


def _sale_with_move(tenant, store, warehouse, product, user, status, qty, price, num):
    total = Decimal(qty) * Decimal(price)
    s = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse, created_by=user,
        subtotal=total, total=total, status=status, sale_type="VENTA",
        total_cost=Decimal("0.000"), gross_profit=total, sale_number=num,
    )
    SaleLine.objects.create(
        sale=s, tenant=tenant, product=product,
        qty=Decimal(qty), unit_price=Decimal(price), line_total=total,
    )
    StockMove.objects.create(
        tenant=tenant, warehouse=warehouse, product=product, created_by=user,
        move_type="OUT", ref_type="SALE", ref_id=s.id, qty=Decimal(qty),
    )
    return s


@pytest.mark.django_db
class TestVoidExcludedFromDemand:
    def test_void_sale_not_counted_as_demand(self, tenant, store, warehouse_a, product, user):
        today = date.today()
        _sale_with_move(tenant, store, warehouse_a, product, user, "COMPLETED", 10, 1000, 1)
        _sale_with_move(tenant, store, warehouse_a, product, user, "VOID", 5, 1000, 2)

        call_command("aggregate_daily_sales", "--date", today.isoformat(),
                     "--tenant", str(tenant.id), verbosity=0)

        ds = DailySales.objects.get(
            tenant=tenant, product=product, warehouse=warehouse_a, date=today)
        # Solo la venta COMPLETED (10) — la VOID (5) NO entra a la demanda.
        assert ds.qty_sold == Decimal("10.000"), f"qty_sold debió ser 10 (sin la void), got {ds.qty_sold}"
        # Revenue también excluye la anulada.
        assert ds.revenue == Decimal("10000.00"), f"revenue debió excluir la void, got {ds.revenue}"

    def test_all_void_means_zero_demand(self, tenant, store, warehouse_a, product, user):
        """Si TODAS las ventas del día se anularon, la demanda del producto es 0
        (no se crea una fila inflada)."""
        today = date.today()
        _sale_with_move(tenant, store, warehouse_a, product, user, "VOID", 7, 1000, 1)

        call_command("aggregate_daily_sales", "--date", today.isoformat(),
                     "--tenant", str(tenant.id), verbosity=0)

        ds = DailySales.objects.filter(
            tenant=tenant, product=product, warehouse=warehouse_a, date=today).first()
        # O no se crea fila, o se crea con qty_sold 0 — nunca con la qty de la void.
        if ds is not None:
            assert ds.qty_sold == Decimal("0.000"), f"una venta anulada NO es demanda, got {ds.qty_sold}"
