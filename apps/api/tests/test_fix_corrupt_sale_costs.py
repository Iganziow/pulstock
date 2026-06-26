"""
Tests del command fix_corrupt_sale_costs: recalcula costos de ventas con
costo corrupto (total_cost > total > 0) desde el avg_cost actual del producto.
"""
import pytest
from decimal import Decimal

from django.core.management import call_command

from sales.models import Sale, SaleLine
from inventory.models import StockItem
from catalog.models import Product


def _corrupt_sale(tenant, store, warehouse, owner, product, *, qty, unit_price,
                  bad_unit_cost, sale_type="VENTA"):
    total = Decimal(str(qty)) * Decimal(str(unit_price))
    bad_cost = Decimal(str(qty)) * Decimal(str(bad_unit_cost))
    sale = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
        status=Sale.STATUS_COMPLETED, sale_type=sale_type,
    )
    Sale.objects.filter(id=sale.id).update(
        total=total, total_cost=bad_cost, gross_profit=total - bad_cost,
    )
    SaleLine.objects.create(
        sale=sale, tenant=tenant, product=product,
        qty=Decimal(str(qty)), unit_price=Decimal(str(unit_price)),
        line_total=total, unit_cost_snapshot=Decimal(str(bad_unit_cost)),
        line_cost=bad_cost, line_gross_profit=total - bad_cost,
    )
    return sale


@pytest.mark.django_db
def test_recompute_corrupt_cost_from_avg_cost(tenant, store, warehouse, owner):
    p = Product.objects.create(tenant=tenant, name="Café", price=Decimal("1000"), is_active=True)
    StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=p,
        on_hand=Decimal("10"), avg_cost=Decimal("100"), stock_value=Decimal("1000"),
    )
    # Venta: 5 × $200 = $1000, pero costo inflado 100× ($10.000/u → costo $50.000)
    sale = _corrupt_sale(tenant, store, warehouse, owner, p, qty=5, unit_price=200, bad_unit_cost=10000)

    # DRY-RUN: no escribe
    call_command("fix_corrupt_sale_costs", "--tenant", str(tenant.id))
    sale.refresh_from_db()
    assert sale.total_cost == Decimal("50000.000")

    # APPLY: recalcula desde avg_cost=100 → costo 5×100 = 500
    call_command("fix_corrupt_sale_costs", "--tenant", str(tenant.id), "--apply")
    sale.refresh_from_db()
    assert sale.total_cost == Decimal("500.000")
    assert sale.gross_profit == Decimal("500.000")  # 1000 − 500
    line = sale.lines.first()
    assert line.unit_cost_snapshot == Decimal("100")
    assert line.line_cost == Decimal("500.000")


@pytest.mark.django_db
def test_healthy_sale_untouched(tenant, store, warehouse, owner):
    p = Product.objects.create(tenant=tenant, name="Té", price=Decimal("1000"), is_active=True)
    StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=p,
        on_hand=Decimal("10"), avg_cost=Decimal("400"), stock_value=Decimal("4000"),
    )
    # Venta sana: costo (400) < ingreso (1000) → NO debe tocarse
    sale = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse, created_by=owner, status=Sale.STATUS_COMPLETED,
    )
    Sale.objects.filter(id=sale.id).update(total=Decimal("1000"), total_cost=Decimal("400"), gross_profit=Decimal("600"))
    SaleLine.objects.create(sale=sale, tenant=tenant, product=p, qty=Decimal("1"), unit_price=Decimal("1000"),
                            line_total=Decimal("1000"), unit_cost_snapshot=Decimal("400"),
                            line_cost=Decimal("400"), line_gross_profit=Decimal("600"))
    call_command("fix_corrupt_sale_costs", "--tenant", str(tenant.id), "--apply")
    sale.refresh_from_db()
    assert sale.total_cost == Decimal("400")  # intacto
    assert sale.gross_profit == Decimal("600")


@pytest.mark.django_db
def test_internal_consumption_untouched(tenant, store, warehouse, owner):
    # CONSUMO_INTERNO con total=0: cost>total siempre, pero NO es corrupción → intacto.
    p = Product.objects.create(tenant=tenant, name="Leche", price=Decimal("0"), is_active=True)
    sale = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
        status=Sale.STATUS_COMPLETED, sale_type="CONSUMO_INTERNO",
    )
    Sale.objects.filter(id=sale.id).update(total=Decimal("0"), total_cost=Decimal("300"), gross_profit=Decimal("-300"))
    call_command("fix_corrupt_sale_costs", "--tenant", str(tenant.id), "--apply")
    sale.refresh_from_db()
    assert sale.total_cost == Decimal("300")  # intacto (total=0 → excluido)
