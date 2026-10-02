# -*- coding: utf-8 -*-
"""
tests/test_quiebre_sin_movimiento.py — si la venta no toco el stock, no pudo agotarlo.

Hallazgo 3.15 (FORECAST_REVIEW, 10/09/26), medido de nuevo el 13/09/26: la
deteccion de quiebre reconstruia la apertura como "cierre + vendido". Un latte
no tiene stock propio (se descuentan sus ingredientes) y su StockItem vive en
0, asi que cualquier dia que vendia abria "con stock", cerraba en 0 y quedaba
marcado como quiebre: 696 de 697 dias de venta de productos con receta en
produccion, y 109 dias de productos que venden sin mover stock (el Te). Todas
las metricas excluyen los dias de quiebre, asi que se median sin sus ventas.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from catalog.models import Recipe, RecipeLine
from forecast.models import DailySales, ForecastAccuracy
from inventory.models import StockItem, StockMove
from sales.services import create_sale

D = Decimal


def _stock(tenant, warehouse, product, qty):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=D(qty), avg_cost=D("10"), stock_value=(D(qty) * D("10")).quantize(D("0.001")),
    )


def _receta(tenant, padre, ingrediente, qty="30"):
    r = Recipe.objects.create(tenant=tenant, product=padre, is_active=True)
    RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=ingrediente, qty=D(qty))
    return r


def _vender(owner, tenant, store, warehouse, producto, qty="3"):
    return create_sale(
        user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
        lines_in=[{"product_id": producto.id, "qty": qty, "unit_price": "1000"}],
        payments_in=[{"method": "cash", "amount": str(int(qty) * 1000)}], sale_type="VENTA",
    )["sale"]


def _agregar(tenant):
    call_command("aggregate_daily_sales", "--date", date.today().isoformat(), "--tenant", str(tenant.id))


def _ds(tenant, product, warehouse):
    return DailySales.objects.filter(tenant=tenant, product=product, warehouse=warehouse, date=date.today()).first()


@pytest.mark.django_db
class TestDeteccionDiaria:

    def test_el_producto_con_receta_que_vende_no_queda_en_quiebre(
        self, tenant, store, warehouse, product, product_b, owner,
    ):
        ingrediente, latte = product, product_b
        _stock(tenant, warehouse, ingrediente, "1000")
        _stock(tenant, warehouse, latte, "0")
        _receta(tenant, latte, ingrediente, "30")
        venta = _vender(owner, tenant, store, warehouse, latte, "3")
        assert not StockMove.objects.filter(ref_id=venta.id, product=latte).exists(), (
            "precondicion: el latte no mueve stock propio, se descuentan sus ingredientes")

        _agregar(tenant)
        ds = _ds(tenant, latte, warehouse)
        assert ds is not None and ds.qty_sold == D("3.000")
        assert ds.is_stockout is False, "vendio sin tocar su stock: no pudo agotarlo"

    def test_el_quiebre_real_se_sigue_detectando(self, tenant, store, warehouse, product, owner):
        _stock(tenant, warehouse, product, "3")
        _vender(owner, tenant, store, warehouse, product, "3")

        _agregar(tenant)
        ds = _ds(tenant, product, warehouse)
        assert ds.closing_stock == D("0.000")
        assert ds.is_stockout is True, "tenia 3, vendio 3 y cerro en 0: se agoto"


@pytest.mark.django_db
class TestBackfillSinMovimiento:

    def test_venta_sin_movimiento_no_es_quiebre(self, tenant, warehouse, product):
        _stock(tenant, warehouse, product, "0")
        d = DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=date.today() - timedelta(days=2), qty_sold=D("5"),
        )
        call_command("backfill_stockout_detection", "--tenant", str(tenant.id), "--days", "10", "--apply")
        d.refresh_from_db()
        assert d.closing_stock == D("0.000")
        assert d.is_stockout is False, "vendio 5 sin ningun movimiento de stock: la apertura era 0"


def _dia(n):
    return date.today() - timedelta(days=n)


def _mov(tenant, warehouse, product, tipo, qty, dia):
    return StockMove.objects.create(
        tenant=tenant, warehouse=warehouse, product=product, move_type=tipo, qty=D(qty),
        created_at=timezone.make_aware(datetime.combine(dia, time(12, 0))),
    )


def _fila(tenant, warehouse, product, dia, vendido, cierre="0", quiebre=True):
    return DailySales.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, date=dia,
        qty_sold=D(vendido), closing_stock=D(cierre), is_stockout=quiebre,
    )


def _medicion(tenant, warehouse, product, dia, quiebre=True):
    return ForecastAccuracy.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, date=dia,
        qty_predicted=D("1"), qty_actual=D("1"), error=D("0"), abs_pct_error=D("0"),
        algorithm="simple_avg", was_stockout=quiebre,
    )


def _desmarcar(tenant, aplicar=True):
    args = ["desmarcar_quiebres_sin_movimiento", "--tenant", str(tenant.id)]
    if aplicar:
        args.append("--apply")
    call_command(*args, verbosity=0)


@pytest.mark.django_db
class TestDesmarcarQuiebresSinMovimiento:

    def test_desmarca_la_venta_sin_movimiento_y_su_medicion(self, tenant, warehouse, product):
        fila = _fila(tenant, warehouse, product, _dia(2), vendido="5")
        med = _medicion(tenant, warehouse, product, _dia(2))
        _desmarcar(tenant)
        fila.refresh_from_db(); med.refresh_from_db()
        assert fila.is_stockout is False
        assert med.was_stockout is False, "la medicion copio la marca al puntuar: tiene que sincronizarse"

    def test_conserva_el_quiebre_real(self, tenant, warehouse, product):
        _mov(tenant, warehouse, product, StockMove.OUT, "3", _dia(2))
        fila = _fila(tenant, warehouse, product, _dia(2), vendido="3")
        med = _medicion(tenant, warehouse, product, _dia(2))
        _desmarcar(tenant)
        fila.refresh_from_db(); med.refresh_from_db()
        assert fila.is_stockout is True, "abrio con 3 segun el kardex y cerro en 0"
        assert med.was_stockout is True

    def test_conserva_si_recibio_y_cerro_en_cero(self, tenant, warehouse, product):
        _mov(tenant, warehouse, product, StockMove.IN, "2", _dia(4))
        _mov(tenant, warehouse, product, StockMove.OUT, "2", _dia(4))
        fila = _fila(tenant, warehouse, product, _dia(4), vendido="2")
        _desmarcar(tenant)
        fila.refresh_from_db()
        assert fila.is_stockout is True

    def test_no_toca_los_dias_sin_venta(self, tenant, warehouse, product):
        """Los dias cerrados que marca mark_closed_day tienen venta 0."""
        fila = _fila(tenant, warehouse, product, _dia(3), vendido="0")
        _desmarcar(tenant)
        fila.refresh_from_db()
        assert fila.is_stockout is True

    def test_dry_run_no_escribe(self, tenant, warehouse, product):
        fila = _fila(tenant, warehouse, product, _dia(2), vendido="5")
        med = _medicion(tenant, warehouse, product, _dia(2))
        _desmarcar(tenant, aplicar=False)
        fila.refresh_from_db(); med.refresh_from_db()
        assert fila.is_stockout is True and med.was_stockout is True

    def test_es_idempotente(self, tenant, warehouse, product):
        fila = _fila(tenant, warehouse, product, _dia(2), vendido="5")
        _desmarcar(tenant)
        _desmarcar(tenant)
        fila.refresh_from_db()
        assert fila.is_stockout is False

    def test_no_mira_otro_tenant(self, tenant, warehouse, product):
        fila = _fila(tenant, warehouse, product, _dia(2), vendido="5")
        call_command("desmarcar_quiebres_sin_movimiento", "--tenant", str(tenant.id + 999), "--apply", verbosity=0)
        fila.refresh_from_db()
        assert fila.is_stockout is True
