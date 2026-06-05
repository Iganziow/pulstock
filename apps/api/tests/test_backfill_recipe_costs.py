"""
Test backfill_recipe_line_costs — recalcula line_cost/line_gross_profit de
SaleLines de productos-receta con el conversor correcto (fix del costo
histórico inflado que rompía el reporte ABC).
"""
import pytest
from decimal import Decimal

from django.core.management import call_command

from catalog.models import Product, Recipe, RecipeLine
from inventory.models import StockItem
from sales.models import Sale, SaleLine


def _prod(tenant, name):
    return Product.objects.create(tenant=tenant, name=name, sku=f"SKU-{name}",
                                  price=Decimal("1000.00"), is_active=True)


@pytest.mark.django_db
def test_backfill_recompute_inflated_cost(tenant, warehouse, owner):
    # Ingrediente con costo 10 (sin conversión: RecipeLine.unit=None → identidad)
    cafe = _prod(tenant, "Cafe grano")
    StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=cafe,
                             on_hand=Decimal("1000"), avg_cost=Decimal("10.000"))
    # Producto-receta: 2 de café por unidad → costo unitario = 20
    espresso = _prod(tenant, "Espresso")
    recipe = Recipe.objects.create(tenant=tenant, product=espresso, is_active=True)
    RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=cafe,
                              qty=Decimal("2.0000"), unit=None)

    sale = Sale.objects.create(
        tenant=tenant, store=warehouse.store, warehouse=warehouse, created_by=owner,
        subtotal=Decimal("300"), total=Decimal("300"), status="COMPLETED",
    )
    # SaleLine con costo INFLADO (como lo dejó el import de Fudo)
    ln = SaleLine.objects.create(
        tenant=tenant, sale=sale, product=espresso, qty=Decimal("3.000"),
        unit_price=Decimal("100.00"), line_total=Decimal("300.00"),
        line_cost=Decimal("99999.000"), line_gross_profit=Decimal("-99699.000"),
    )

    call_command("backfill_recipe_line_costs", "--tenant", str(tenant.id), "--apply")

    ln.refresh_from_db()
    # costo unitario 20 × qty 3 = 60 ; ganancia = 300 - 60 = 240
    assert ln.line_cost == Decimal("60.000"), f"costo recalculado mal: {ln.line_cost}"
    assert ln.line_gross_profit == Decimal("240.000"), f"ganancia mal: {ln.line_gross_profit}"


@pytest.mark.django_db
def test_backfill_dry_run_no_cambia(tenant, warehouse, owner):
    cafe = _prod(tenant, "Cafe2")
    StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=cafe,
                             on_hand=Decimal("1000"), avg_cost=Decimal("10.000"))
    esp = _prod(tenant, "Espresso2")
    r = Recipe.objects.create(tenant=tenant, product=esp, is_active=True)
    RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=cafe, qty=Decimal("2"), unit=None)
    sale = Sale.objects.create(tenant=tenant, store=warehouse.store, warehouse=warehouse,
                               created_by=owner, subtotal=Decimal("300"), total=Decimal("300"), status="COMPLETED")
    ln = SaleLine.objects.create(tenant=tenant, sale=sale, product=esp, qty=Decimal("3"),
                                 unit_price=Decimal("100"), line_total=Decimal("300"),
                                 line_cost=Decimal("99999"), line_gross_profit=Decimal("-99699"))
    call_command("backfill_recipe_line_costs", "--tenant", str(tenant.id))  # dry-run
    ln.refresh_from_db()
    assert ln.line_cost == Decimal("99999"), "dry-run no debe cambiar nada"
