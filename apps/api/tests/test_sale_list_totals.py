"""
Bug (Mario): en Ventas, al mover el rango de días las tarjetas Ingresos/Utilidad
no cambiaban — el frontend las sumaba sólo sobre la página actual (las ~50 más
recientes, comunes a varios rangos). Fix: SaleList ahora devuelve `totals`
agregados sobre TODO el queryset filtrado (sólo COMPLETADAS para revenue/profit).
"""
import pytest
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from sales.models import Sale

URL = "/api/sales/sales/list/"


def _mk_sale(tenant, store, warehouse, owner, *, days_ago, total, profit, status=Sale.STATUS_COMPLETED):
    s = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse, created_by=owner, status=status,
    )
    when = timezone.now() - timedelta(days=days_ago)
    # created_at es auto_now_add → se setea con update para fechar la venta.
    Sale.objects.filter(id=s.id).update(
        created_at=when, total=Decimal(str(total)),
        total_cost=Decimal("0"), gross_profit=Decimal(str(profit)),
    )
    return s


@pytest.mark.django_db
def test_totals_reflect_full_filtered_range(api_client, tenant, store, warehouse, owner):
    _mk_sale(tenant, store, warehouse, owner, days_ago=1, total=1000, profit=400)
    _mk_sale(tenant, store, warehouse, owner, days_ago=3, total=2000, profit=800)
    _mk_sale(tenant, store, warehouse, owner, days_ago=20, total=5000, profit=2000)

    today = timezone.now().date()
    ti = today.isoformat()
    d7 = (today - timedelta(days=7)).isoformat()
    d30 = (today - timedelta(days=30)).isoformat()

    # Últimos 7 días: solo las dos primeras.
    r7 = api_client.get(f"{URL}?date_from={d7}&date_to={ti}")
    assert r7.status_code == 200, r7.content[:300]
    t7 = r7.json()["totals"]
    assert Decimal(t7["revenue"]) == Decimal("3000"), t7
    assert Decimal(t7["profit"]) == Decimal("1200"), t7
    assert t7["completed_count"] == 2

    # Últimos 30 días: ahora entra la de hace 20 días → cambian los montos.
    r30 = api_client.get(f"{URL}?date_from={d30}&date_to={ti}")
    t30 = r30.json()["totals"]
    assert Decimal(t30["revenue"]) == Decimal("8000"), t30
    assert Decimal(t30["profit"]) == Decimal("3200"), t30
    assert t30["completed_count"] == 3


@pytest.mark.django_db
def test_totals_exclude_void(api_client, tenant, store, warehouse, owner):
    _mk_sale(tenant, store, warehouse, owner, days_ago=1, total=1000, profit=400)
    _mk_sale(tenant, store, warehouse, owner, days_ago=1, total=9999, profit=9999, status=Sale.STATUS_VOID)

    today = timezone.now().date()
    ti = today.isoformat()
    d7 = (today - timedelta(days=7)).isoformat()

    r = api_client.get(f"{URL}?date_from={d7}&date_to={ti}")
    t = r.json()["totals"]
    assert Decimal(t["revenue"]) == Decimal("1000"), t  # la anulada NO suma
    assert t["completed_count"] == 1
    assert t["void_count"] == 1
