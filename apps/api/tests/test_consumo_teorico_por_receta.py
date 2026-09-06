# -*- coding: utf-8 -*-
"""
tests/test_consumo_teorico_por_receta.py — la demanda de un ingrediente no se
pierde porque el stock estaba en cero.

Hallazgo 2.15 (FORECAST_REVIEW, 05/09/26): Jamon granel tiene
allow_negative_stock=True. Con el stock en cero, la venta de la Selladita
pasa, el descuento se clampea a 0 y no se crea StockMove (create_sale, paso
8). aggregate_daily_sales tomaba qty_sold del StockMove: 24 de 32 Selladitas
no dejaron rastro, el consumo registrado del jamon fue un tercio del real,
el modelo directo aprendio esa serie censurada y la sugerencia pedia un
tercio de lo que se usa.

Ahora qty_sold = max(lo movido, lo que la receta dice que se uso). El kardex
(StockMove, closing_stock) no cambia.
"""
from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Recipe, RecipeLine
from forecast.models import DailySales
from inventory.models import StockItem, StockMove
from sales.models import Sale
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


def _vender(owner, tenant, store, warehouse, padre, qty="3"):
    return create_sale(
        user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
        lines_in=[{"product_id": padre.id, "qty": qty, "unit_price": "1000"}],
        payments_in=[{"method": "cash", "amount": str(int(qty) * 1000)}], sale_type="VENTA",
    )["sale"]


def _agregar(tenant):
    call_command("aggregate_daily_sales", "--date", date.today().isoformat(), "--tenant", str(tenant.id))


def _ds(tenant, product, warehouse):
    return DailySales.objects.filter(tenant=tenant, product=product, warehouse=warehouse, date=date.today()).first()


@pytest.mark.django_db
class TestConsumoTeoricoPorReceta:
    def test_ingrediente_en_cero_con_stock_negativo_permitido_conserva_su_demanda(
        self, tenant, store, warehouse, product, product_b, owner,
    ):
        """El caso del jamon: 3 Selladitas, jamon en 0, sin StockMove -> 90 g de demanda."""
        jamon, selladita = product, product_b
        jamon.allow_negative_stock = True
        jamon.save(update_fields=["allow_negative_stock"])
        _stock(tenant, warehouse, jamon, "0")
        _receta(tenant, selladita, jamon, "30")
        venta = _vender(owner, tenant, store, warehouse, selladita, "3")
        assert not StockMove.objects.filter(ref_id=venta.id, product=jamon).exists(), "precondicion: el clamp no deja movimiento"

        _agregar(tenant)
        ds = _ds(tenant, jamon, warehouse)
        assert ds is not None, "el ingrediente sin movimiento tiene que tener fila igual"
        assert ds.qty_sold == D("90.000"), "la demanda es la de la receta, no el cero del kardex"
        assert ds.is_stockout is False, "no es stockout: abrio en 0 y no recibio (regla vigente)"

    def test_clamp_parcial_tambien(self, tenant, store, warehouse, product, product_b, owner):
        """Jamon con 40 g: se mueven 40, la demanda es 90."""
        jamon, selladita = product, product_b
        jamon.allow_negative_stock = True
        jamon.save(update_fields=["allow_negative_stock"])
        _stock(tenant, warehouse, jamon, "40")
        _receta(tenant, selladita, jamon, "30")
        venta = _vender(owner, tenant, store, warehouse, selladita, "3")
        assert StockMove.objects.get(ref_id=venta.id, product=jamon).qty == D("40.000")

        _agregar(tenant)
        ds = _ds(tenant, jamon, warehouse)
        assert ds.qty_sold == D("90.000")
        assert ds.closing_stock == D("0.000"), "el kardex no se inventa nada"

    def test_con_stock_suficiente_nada_cambia(self, tenant, store, warehouse, product, product_b, owner):
        jamon, selladita = product, product_b
        _stock(tenant, warehouse, jamon, "1000")
        _receta(tenant, selladita, jamon, "30")
        _vender(owner, tenant, store, warehouse, selladita, "3")
        _agregar(tenant)
        ds = _ds(tenant, jamon, warehouse)
        assert ds.qty_sold == D("90.000")
        assert ds.closing_stock == D("910.000")
        # el padre con receta vendido directo conserva su propia fila
        assert _ds(tenant, selladita, warehouse).qty_sold == D("3.000")

    def test_la_venta_anulada_no_cuenta(self, tenant, store, warehouse, product, product_b, owner):
        jamon, selladita = product, product_b
        jamon.allow_negative_stock = True
        jamon.save(update_fields=["allow_negative_stock"])
        _stock(tenant, warehouse, jamon, "0")
        _receta(tenant, selladita, jamon, "30")
        venta = _vender(owner, tenant, store, warehouse, selladita, "3")
        Sale.objects.filter(id=venta.id).update(status=Sale.STATUS_VOID)
        _agregar(tenant)
        ds = _ds(tenant, jamon, warehouse)
        assert ds is None or ds.qty_sold == D("0.000")

    def test_receta_rota_no_tumba_la_agregacion(self, tenant, store, warehouse, product, product_b, owner):
        """Si despues de la venta la receta queda activa y sin lineas,
        expand_recipes levanta error: se avisa y qty_sold usa el kardex."""
        jamon, selladita = product, product_b
        _stock(tenant, warehouse, jamon, "1000")
        receta = _receta(tenant, selladita, jamon, "30")
        _vender(owner, tenant, store, warehouse, selladita, "3")
        receta.lines.all().delete()
        _agregar(tenant)
        ds = _ds(tenant, jamon, warehouse)
        assert ds.qty_sold == D("90.000"), "lo movido sigue contando aunque la receta este rota"

    def test_producto_directo_sin_receta_no_se_duplica(self, tenant, store, warehouse, product, owner):
        """Un producto sin receta vendido directo esta en el kardex Y en la
        expansion (pasa tal cual): max() no lo cuenta dos veces."""
        _stock(tenant, warehouse, product, "100")
        create_sale(
            user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
            lines_in=[{"product_id": product.id, "qty": "5", "unit_price": "1000"}],
            payments_in=[{"method": "cash", "amount": "5000"}], sale_type="VENTA",
        )
        _agregar(tenant)
        assert _ds(tenant, product, warehouse).qty_sold == D("5.000")
