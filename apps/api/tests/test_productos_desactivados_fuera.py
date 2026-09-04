# -*- coding: utf-8 -*-
"""
tests/test_productos_desactivados_fuera.py — lo que el dueno dio de baja no
se entrena ni se compra.

Medido en Marbrava el 03/09/26: 60 de las ultimas 60 sugerencias de compra
incluian productos desactivados (Muffin, Caja galletas: ultima venta en
junio, stock 0, sin receta que los use). Dos causas encadenadas:

  1. La elegibilidad del entrenamiento era "vendio alguna vez" sin ventana
     de tiempo y sin mirar `is_active`. El modelo del producto seguia
     activo y escribiendo pronosticos.
  2. Las sugerencias parten de los modelos activos, no de los productos
     activos, y el guardian de zombis exime a los lentos (menos de 0,2/dia).

La excepcion que hay que conservar: un ingrediente desactivado en el POS
pero consumido por una receta activa (bolsitas de te dentro del "Te")
SI se entrena y SI se compra.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Recipe, RecipeLine
from forecast.models import DailySales, Forecast, ForecastModel, SuggestionLine
from inventory.models import StockItem

D = Decimal


def _historia(tenant, product, warehouse, dias=60):
    hoy = datetime.date.today()
    patron = [7, 6, 8, 7, 9, 6, 7]
    for i in range(1, dias + 1):
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=hoy - datetime.timedelta(days=i),
            qty_sold=D(str(patron[i % 7])),
        )


def _entrenar(tenant):
    call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)


def _modelo_activo(product):
    return ForecastModel.objects.filter(product=product, is_active=True).exists()


def _sin_stock(tenant, warehouse, product):
    StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=D("0"), avg_cost=D("100"), stock_value=D("0"),
    )


@pytest.mark.django_db
class TestEntrenamiento:
    def test_producto_desactivado_pierde_su_modelo_y_sus_pronosticos(
        self, tenant, store, warehouse, product,
    ):
        _historia(tenant, product, warehouse)
        _entrenar(tenant)
        assert _modelo_activo(product), "el setup no entreno: revisar min_days"

        product.is_active = False
        product.save()
        _entrenar(tenant)

        assert not _modelo_activo(product), (
            "el producto fue dado de baja y su modelo sigue activo: va a "
            "seguir pronosticando y sugiriendo compras"
        )
        hoy = datetime.date.today()
        assert not Forecast.objects.filter(product=product, forecast_date__gt=hoy).exists(), (
            "quedaron pronosticos a futuro de un producto desactivado"
        )

    def test_ingrediente_desactivado_de_receta_activa_conserva_su_modelo(
        self, tenant, store, warehouse, product, product_b,
    ):
        """La excepcion: se saco del POS pero una receta lo consume."""
        _historia(tenant, product, warehouse)
        _entrenar(tenant)
        assert _modelo_activo(product)

        receta = Recipe.objects.create(tenant=tenant, product=product_b, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=receta, ingredient=product, qty=D("1"))
        product.is_active = False
        product.save()
        _entrenar(tenant)

        assert _modelo_activo(product), (
            "es ingrediente de una receta activa: hay que seguir pronosticandolo"
        )

    def test_receta_inactiva_no_salva_al_ingrediente(
        self, tenant, store, warehouse, product, product_b,
    ):
        _historia(tenant, product, warehouse)
        _entrenar(tenant)
        receta = Recipe.objects.create(tenant=tenant, product=product_b, is_active=False)
        RecipeLine.objects.create(tenant=tenant, recipe=receta, ingredient=product, qty=D("1"))
        product.is_active = False
        product.save()
        _entrenar(tenant)
        assert not _modelo_activo(product)


@pytest.mark.django_db
class TestSugerencias:
    def test_no_sugiere_un_producto_desactivado_aunque_su_modelo_siga_activo(
        self, tenant, store, warehouse, product,
    ):
        """No puede depender del orden de los pasos: si las sugerencias corren
        con un modelo viejo todavia activo, igual tienen que saltarlo."""
        _historia(tenant, product, warehouse)
        _entrenar(tenant)
        _sin_stock(tenant, warehouse, product)
        # Se desactiva SIN reentrenar: el modelo sigue activo a proposito.
        product.is_active = False
        product.save()
        assert _modelo_activo(product)

        call_command("generate_purchase_suggestions", tenant=tenant.id, verbosity=0)

        assert not SuggestionLine.objects.filter(product=product).exists(), (
            "le pidio al dueno comprar un producto que el mismo dio de baja"
        )

    def test_el_activo_si_se_sugiere(self, tenant, store, warehouse, product):
        """La otra mitad: el filtro no puede tragarse a los activos."""
        _historia(tenant, product, warehouse)
        _entrenar(tenant)
        _sin_stock(tenant, warehouse, product)
        call_command("generate_purchase_suggestions", tenant=tenant.id, verbosity=0)
        assert SuggestionLine.objects.filter(product=product).exists(), (
            "producto activo con stock 0 y demanda diaria: tenia que sugerirse"
        )
