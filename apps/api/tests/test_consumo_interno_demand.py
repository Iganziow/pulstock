"""
Test F28 — el consumo interno NO contamina la demanda del forecast (Mario 29/05/26).

Una venta CONSUMO_INTERNO (regalo/muestra/staff) descuenta stock pero NO es
demanda de venta. Debe ir a DailySales.qty_sold_internal, NO a qty_sold.
Antes, toda venta generaba StockMove ref_type="SALE" → el forecast contaba
los regalos como demanda → sobre-predecía.
"""
from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product
from inventory.models import StockItem, StockMove
from sales.models import Sale
from sales.services import create_sale
from forecast.models import DailySales


def _stock(tenant, warehouse, product, qty="100", cost="500"):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=Decimal(qty), avg_cost=Decimal(cost),
        stock_value=(Decimal(qty) * Decimal(cost)).quantize(Decimal("0.001")),
    )


@pytest.mark.django_db
class TestConsumoInternoDemand:
    def test_internal_sale_uses_internal_ref_type(self, tenant, store, warehouse, product, owner):
        """Venta CONSUMO_INTERNO genera StockMove ref_type=INTERNAL, no SALE."""
        _stock(tenant, warehouse, product)
        res = create_sale(
            user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
            lines_in=[{"product_id": product.id, "qty": "3", "unit_price": "1000"}],
            payments_in=[], sale_type="CONSUMO_INTERNO",
        )
        sale = res["sale"]
        moves = StockMove.objects.filter(ref_id=sale.id, move_type="OUT")
        assert moves.exists()
        assert all(m.ref_type == "INTERNAL" for m in moves), \
            f"consumo interno debe ser INTERNAL, no {[m.ref_type for m in moves]}"

    def test_normal_sale_uses_sale_ref_type(self, tenant, store, warehouse, product, owner):
        """Venta normal sigue siendo ref_type=SALE."""
        _stock(tenant, warehouse, product)
        res = create_sale(
            user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
            lines_in=[{"product_id": product.id, "qty": "2", "unit_price": "1000"}],
            payments_in=[{"method": "cash", "amount": "2000"}], sale_type="VENTA",
        )
        sale = res["sale"]
        moves = StockMove.objects.filter(ref_id=sale.id, move_type="OUT")
        assert all(m.ref_type == "SALE" for m in moves)

    def test_aggregate_separates_internal_from_demand(self, tenant, store, warehouse, product, owner):
        """E2E: venta real (5) + consumo interno (3) el mismo día.
        DailySales.qty_sold = 5 (demanda), qty_sold_internal = 3 (no demanda)."""
        _stock(tenant, warehouse, product, qty="100")
        # Venta real: 5 unidades
        create_sale(
            user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
            lines_in=[{"product_id": product.id, "qty": "5", "unit_price": "1000"}],
            payments_in=[{"method": "cash", "amount": "5000"}], sale_type="VENTA",
        )
        # Consumo interno: 3 unidades (regalo)
        create_sale(
            user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
            lines_in=[{"product_id": product.id, "qty": "3", "unit_price": "1000"}],
            payments_in=[], sale_type="CONSUMO_INTERNO",
        )

        # Agregar el día de hoy
        call_command("aggregate_daily_sales", "--date", date.today().isoformat(), "--tenant", str(tenant.id))

        ds = DailySales.objects.get(tenant=tenant, product=product, warehouse=warehouse, date=date.today())
        assert ds.qty_sold == Decimal("5.000"), f"demanda debe ser 5 (sin el regalo), es {ds.qty_sold}"
        assert ds.qty_sold_internal == Decimal("3.000"), f"consumo interno debe ser 3, es {ds.qty_sold_internal}"

    def test_only_internal_no_demand(self, tenant, store, warehouse, product, owner):
        """Si SOLO hubo consumo interno (sin venta real), qty_sold = 0."""
        _stock(tenant, warehouse, product, qty="100")
        create_sale(
            user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
            lines_in=[{"product_id": product.id, "qty": "4", "unit_price": "1000"}],
            payments_in=[], sale_type="CONSUMO_INTERNO",
        )
        call_command("aggregate_daily_sales", "--date", date.today().isoformat(), "--tenant", str(tenant.id))

        ds = DailySales.objects.get(tenant=tenant, product=product, warehouse=warehouse, date=date.today())
        assert ds.qty_sold == Decimal("0.000"), f"sin venta real, demanda=0, es {ds.qty_sold}"
        assert ds.qty_sold_internal == Decimal("4.000")
        assert ds.revenue == Decimal("0.00"), "consumo interno no genera ingreso"
