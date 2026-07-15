"""
Command clean_phantom_demand: limpia demanda fantasma en DailySales por bug de
expansión de receta (caso Carne Mechada jul-2026: 115× por Selladita).
Recalcula qty_sold desde ventas reales del padre × RecipeLine.qty. Solo reduce.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product, Recipe, RecipeLine
from sales.models import Sale, SaleLine
from forecast.models import DailySales

D = Decimal


def _ds(tenant, wh, product, day, qty):
    return DailySales.objects.create(
        tenant=tenant, product=product, warehouse=wh, date=day, qty_sold=D(str(qty)),
    )


def _sale_with_line(tenant, store, wh, owner, product, day, qty, unit_price="4500"):
    sale = Sale.objects.create(
        tenant=tenant, store=store, warehouse=wh, created_by=owner,
        status=Sale.STATUS_COMPLETED, sale_type=Sale.SALE_TYPE_VENTA,
    )
    # created_at es auto_now_add → forzar la fecha del día objetivo
    Sale.objects.filter(id=sale.id).update(
        created_at=datetime.datetime.combine(day, datetime.time(15, 0)),
    )
    SaleLine.objects.create(
        sale=sale, tenant=tenant, product=product, qty=D(str(qty)),
        unit_price=D(unit_price), line_total=D(str(qty)) * D(unit_price),
    )
    return sale


@pytest.fixture
def recipe_setup(db, tenant, store, warehouse, owner):
    """Ingrediente 'Carne' usado 1:1 en el padre 'Selladita'."""
    carne = Product.objects.create(tenant=tenant, name="Carne", price=D("0"), is_active=True)
    selladita = Product.objects.create(tenant=tenant, name="Selladita", price=D("4500"), is_active=True)
    r = Recipe.objects.create(tenant=tenant, product=selladita, is_active=True)
    RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=carne, qty=D("1"))
    return carne, selladita


@pytest.mark.django_db
def test_phantom_spike_recomputed_from_parent_sales(recipe_setup, tenant, store, warehouse, owner):
    carne, selladita = recipe_setup
    today = datetime.date.today()
    bad_day = today - datetime.timedelta(days=20)

    # historia normal de Carne (consumo ~2/día como ingrediente)
    for i in range(3, 15):
        _ds(tenant, warehouse, carne, today - datetime.timedelta(days=i), 2)
    # el día contaminado: qty_sold=230 (bug 115×) pero se vendieron 2 Selladitas
    bad = _ds(tenant, warehouse, carne, bad_day, 230)
    _sale_with_line(tenant, store, warehouse, owner, selladita, bad_day, qty=2)

    # DRY-RUN: no escribe
    call_command("clean_phantom_demand", "--tenant", str(tenant.id))
    bad.refresh_from_db()
    assert bad.qty_sold == D("230.000")

    # APPLY: corrige a las 2 Selladitas reales × 1
    call_command("clean_phantom_demand", "--tenant", str(tenant.id), "--apply")
    bad.refresh_from_db()
    assert bad.qty_sold == D("2.000"), bad.qty_sold


@pytest.mark.django_db
def test_normal_days_and_direct_sales_untouched(recipe_setup, tenant, store, warehouse, owner):
    carne, selladita = recipe_setup
    today = datetime.date.today()
    # días normales
    normals = [_ds(tenant, warehouse, carne, today - datetime.timedelta(days=i), 2) for i in range(3, 15)]
    # un día con venta directa REAL alta de Carne (no es fantasma: hay SaleLine directa)
    real_day = today - datetime.timedelta(days=2)
    direct = _ds(tenant, warehouse, carne, real_day, 40)
    _sale_with_line(tenant, store, warehouse, owner, carne, real_day, qty=40, unit_price="500")

    call_command("clean_phantom_demand", "--tenant", str(tenant.id), "--apply")

    for n in normals:
        n.refresh_from_db()
        assert n.qty_sold == D("2.000")
    direct.refresh_from_db()
    # 40 se recompone a 40 (venta directa real) → no se reduce
    assert direct.qty_sold == D("40.000")


@pytest.mark.django_db
def test_non_ingredient_product_ignored(tenant, store, warehouse):
    """Un producto que NO es ingrediente de ninguna receta no se revisa."""
    p = Product.objects.create(tenant=tenant, name="Torta", price=D("5000"), is_active=True)
    today = datetime.date.today()
    for i in range(3, 15):
        _ds(tenant, warehouse, p, today - datetime.timedelta(days=i), 2)
    spike = _ds(tenant, warehouse, p, today - datetime.timedelta(days=1), 500)

    call_command("clean_phantom_demand", "--tenant", str(tenant.id), "--apply")
    spike.refresh_from_db()
    assert spike.qty_sold == D("500.000"), "no-ingrediente no debe tocarse"
