# -*- coding: utf-8 -*-
"""
tests/test_producto_nuevo_sin_categoria.py — un producto que se vende no puede
quedar sin pronostico.

Caso real (30/10/26): "Galletas craqueladas naranja", SIN categoria, se creo con
stock el 13-oct (DailySales de ese dia: vendio 0, cierre 5) y vendio 2 el 29.
Su historia contaba desde el 13 (18 dias, mas que el minimo de 10), asi que fue
al camino normal; ningun algoritmo pudo con una sola venta, y el respaldo a
category_prior exigia categoria con perfil. Quedo sin modelo y sin pronostico,
en silencio: la alerta de cobertura lo vio.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product
from forecast.models import DailySales, Forecast, ForecastModel
from inventory.models import StockItem

D = Decimal


def _hace(n):
    return datetime.date.today() - datetime.timedelta(days=n)


@pytest.mark.django_db
def test_el_producto_sin_categoria_con_una_sola_venta_recibe_pronostico(tenant, store, warehouse, product):
    # Un producto "viejo" con venta normal: que el negocio tenga historia.
    for i in range(1, 40):
        if _hace(i).weekday() != 6:
            DailySales.objects.create(tenant=tenant, product=product, warehouse=warehouse,
                                      date=_hace(i), qty_sold=D("10"))
    galleta = Product.objects.create(tenant=tenant, name="Galletas craqueladas naranja",
                                     price=D("1500"), is_active=True, category=None)
    StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=galleta,
                             on_hand=D("3"), avg_cost=D("500"))
    DailySales.objects.create(tenant=tenant, product=galleta, warehouse=warehouse,
                              date=_hace(17), qty_sold=D("0"), closing_stock=D("5"))
    DailySales.objects.create(tenant=tenant, product=galleta, warehouse=warehouse,
                              date=_hace(1), qty_sold=D("2"), closing_stock=D("3"))

    call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

    fm = ForecastModel.objects.filter(product=galleta, is_active=True).first()
    assert fm is not None, "la galleta se vende y quedo sin modelo"
    assert Forecast.objects.filter(product=galleta, forecast_date__gt=datetime.date.today()).exists()
