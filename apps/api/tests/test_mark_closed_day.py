"""
Command mark_closed_day: marca una fecha como no operativa (local cerrado /
caída del sistema) para que el forecast la INTERPOLE en vez de aprender un 0.

Caso real: 28-jul-2026, bloqueo de Hetzner → el café no pudo vender y quedó
como "martes de 0 ventas".
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product
from forecast.models import DailySales
from forecast.engine.utils import clean_series

D = Decimal


def _ds(tenant, wh, product, day, qty):
    return DailySales.objects.create(
        tenant=tenant, product=product, warehouse=wh, date=day, qty_sold=D(str(qty)),
    )


@pytest.fixture
def serie(db, tenant, warehouse, product):
    """14 días de ventas ~10/día terminando ayer; el día objetivo queda sin fila."""
    today = datetime.date.today()
    target = today - datetime.timedelta(days=3)
    for i in range(4, 18):
        _ds(tenant, warehouse, product, today - datetime.timedelta(days=i), 10)
    return target


@pytest.mark.django_db
def test_dry_run_no_escribe(serie, tenant, warehouse, product):
    target = serie
    call_command("mark_closed_day", "--date", target.isoformat(), "--tenant", str(tenant.id))
    assert not DailySales.objects.filter(tenant=tenant, date=target).exists()


@pytest.mark.django_db
def test_apply_crea_fila_marcada_como_cerrado(serie, tenant, warehouse, product):
    target = serie
    call_command("mark_closed_day", "--date", target.isoformat(), "--tenant", str(tenant.id), "--apply")
    row = DailySales.objects.get(tenant=tenant, date=target, product=product, warehouse=warehouse)
    assert row.is_stockout is True
    assert row.qty_sold == D("0.000")  # no inventa demanda


@pytest.mark.django_db
def test_idempotente(serie, tenant, warehouse, product):
    target = serie
    for _ in range(2):
        call_command("mark_closed_day", "--date", target.isoformat(), "--tenant", str(tenant.id), "--apply")
    assert DailySales.objects.filter(tenant=tenant, date=target, product=product).count() == 1


@pytest.mark.django_db
def test_marca_fila_existente_con_cero(tenant, warehouse, product):
    """Si ya había fila (ej. una merma suelta ese día), la marca igual."""
    today = datetime.date.today()
    target = today - datetime.timedelta(days=3)
    for i in range(4, 18):
        _ds(tenant, warehouse, product, today - datetime.timedelta(days=i), 10)
    existing = _ds(tenant, warehouse, product, target, 0)
    call_command("mark_closed_day", "--date", target.isoformat(), "--tenant", str(tenant.id), "--apply")
    existing.refresh_from_db()
    assert existing.is_stockout is True


@pytest.mark.django_db
def test_no_toca_productos_sin_historial(tenant, warehouse, product):
    """Un producto sin ventas recientes no recibe fila (no inventa series)."""
    today = datetime.date.today()
    target = today - datetime.timedelta(days=3)
    for i in range(4, 18):
        _ds(tenant, warehouse, product, today - datetime.timedelta(days=i), 10)
    otro = Product.objects.create(tenant=tenant, name="Sin historial", price=D("100"), is_active=True)
    call_command("mark_closed_day", "--date", target.isoformat(), "--tenant", str(tenant.id), "--apply")
    assert not DailySales.objects.filter(tenant=tenant, date=target, product=otro).exists()


@pytest.mark.django_db
def test_el_motor_interpola_en_vez_de_aprender_cero(serie, tenant, warehouse, product):
    """LO QUE IMPORTA: tras marcar, clean_series imputa el día en vez de dejar 0."""
    target = serie
    today = datetime.date.today()
    # Serie como la arma el motor: rellena huecos con 0 → el día cerrado entra como 0
    raw = []
    for i in range(17, 3, -1):
        raw.append((today - datetime.timedelta(days=i), D("10")))
    raw.append((target, D("0")))  # día del bloqueo, sin marcar

    # clean_series devuelve (fecha, qty, peso)
    def qty_en(serie_limpia, dia):
        return next(float(row[1]) for row in serie_limpia if row[0] == dia)

    sin_marcar = clean_series(raw, stockout_dates=set())
    assert qty_en(sin_marcar, target) == 0.0  # aprende el cero (contaminación)

    call_command("mark_closed_day", "--date", target.isoformat(), "--tenant", str(tenant.id), "--apply")
    marcadas = set(
        DailySales.objects.filter(tenant=tenant, is_stockout=True).values_list("date", flat=True)
    )
    assert target in marcadas
    con_marca = clean_series(raw, stockout_dates=marcadas)
    assert qty_en(con_marca, target) > 0.0  # imputado, ya no es un cero falso
