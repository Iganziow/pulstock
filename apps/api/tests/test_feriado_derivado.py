# -*- coding: utf-8 -*-
"""
tests/test_feriado_derivado.py — el derivado de receta recibe el feriado UNA vez.

El pronostico de un ingrediente derivado se arma con lo PUBLICADO por sus
bebidas (train_ingredient_product lee sus filas de Forecast), y esas filas ya
pasaron por save_forecasts: ya traen el multiplicador del feriado. Hasta el
08/10/26 save_forecasts se lo aplicaba de nuevo al ingrediente.

Medido en produccion: el lunes 12-oct (x0,8) las bebidas de la leche
deslactosada sumaban 119 y se publicaba (119 + 43) x 0,8 = 130; la rampa de
Fiestas Patrias (x1,7 el 17-sep) quedaba en x2,89. Del 7-sep al 4-oct los tres
derivados del nucleo publicaron con 73% de error semanal contra 35% de la suma
cruda de sus bebidas.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product, Recipe, RecipeLine
from forecast import services
from forecast.models import DailySales, Forecast, ForecastModel, Holiday
from inventory.models import StockItem

D = Decimal
DOMINGO = 6


def hoy():
    # Se pide en cada test y no al importar: la suite puede cruzar medianoche.
    return datetime.date.today()


def _feriado_en_dia_habil(minimo=4):
    """Un dia de semana (no domingo) dentro del horizonte, con margen para que
    sus dos dias de rampa previa tambien caigan adentro y no en domingo."""
    d = hoy() + datetime.timedelta(days=minimo)
    while any((d - datetime.timedelta(days=k)).weekday() == DOMINGO for k in range(3)):
        d += datetime.timedelta(days=1)
    return d


def _feriado(fecha, mult="0.50", pre_days=2, pre_mult="1.50"):
    return Holiday.objects.create(
        tenant=None, name="Feriado de prueba", date=fecha,
        demand_multiplier=D(mult), pre_days=pre_days, pre_multiplier=D(pre_mult),
        ramp_type="instant",
    )


def _semana():
    return [{"date": hoy() + datetime.timedelta(days=i), "qty_predicted": D("10"),
             "lower_bound": D("7"), "upper_bound": D("13")} for i in range(1, 15)]


def _publicado(product):
    return {f.forecast_date: f.qty_predicted
            for f in Forecast.objects.filter(product=product, forecast_date__gt=hoy())}


@pytest.mark.django_db
class TestEnSaveForecasts:
    def test_el_derivado_no_recibe_el_feriado(self, tenant, store, warehouse, product):
        h = _feriado(_feriado_en_dia_habil())
        fm = ForecastModel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            algorithm="ingredient_derived", is_active=True, model_params={}, metrics={},
        )
        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})
        pub = _publicado(product)
        for k in (0, 1, 2):
            d = h.date - datetime.timedelta(days=k)
            assert pub[d] == D("10.000"), (
                "%s: el derivado se ajusto por feriado (%s): ya lo traen sus bebidas" % (d, pub[d]))

    def test_el_organico_si(self, tenant, store, warehouse, product):
        """Control: para el resto de los modelos el feriado se sigue aplicando."""
        h = _feriado(_feriado_en_dia_habil())
        fm = ForecastModel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            algorithm="theta", is_active=True, model_params={}, metrics={},
        )
        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})
        pub = _publicado(product)
        assert pub[h.date] == D("5.000")                                      # x0,5
        assert pub[h.date - datetime.timedelta(days=1)] == D("15.000")         # rampa x1,5
        assert pub[h.date - datetime.timedelta(days=2)] == D("15.000")


@pytest.mark.django_db
def test_de_punta_a_punta_el_ingrediente_es_la_suma_de_sus_bebidas(tenant, store, warehouse):
    """Por el entrenamiento real: la bebida trae el feriado y su rampa una vez,
    y el ingrediente queda exactamente en bebida x receta todos los dias, el del
    feriado y los de la rampa incluidos. Antes, en esos dias, quedaba en
    bebida x receta x multiplicador."""
    bebida = Product.objects.create(tenant=tenant, name="Latte T", price=D("3000"), is_active=True)
    leche = Product.objects.create(tenant=tenant, name="Leche T", price=D("0"), is_active=True)
    receta = Recipe.objects.create(tenant=tenant, product=bebida, is_active=True)
    RecipeLine.objects.create(tenant=tenant, recipe=receta, ingredient=leche, qty=D("200"))
    StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=leche,
                             on_hand=D("50000"), avg_cost=D("1"))
    abiertos = 0
    for i in range(1, 61):                                     # la bebida vende; el domingo cierra
        d = hoy() - datetime.timedelta(days=i)
        if d.weekday() == DOMINGO:
            continue
        vendido = D(str(8 + i % 5))
        DailySales.objects.create(tenant=tenant, product=bebida, warehouse=warehouse,
                                  date=d, qty_sold=vendido)
        # La leche se consume con la receta, pero solo hay 8 dias de consumo
        # registrado: menos que los dias minimos de un modelo organico. Asi el
        # entrenamiento la pronostica derivada y activa, como a la deslactosada
        # en produccion, y sin candidato organico ni correccion de sesgo de por
        # medio: tiene que quedar EXACTA en bebida x receta. (Sin ningun consumo,
        # `demand_stopped` la daria por muerta y la pondria en 0.)
        abiertos += 1
        if abiertos <= 8:
            DailySales.objects.create(tenant=tenant, product=leche, warehouse=warehouse,
                                      date=d, qty_sold=vendido * D("200"))
    h = _feriado(_feriado_en_dia_habil())

    call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

    fm = ForecastModel.objects.get(product=leche, is_active=True)
    assert fm.algorithm == "ingredient_derived", "precondicion: la leche se pronostica derivada"
    de_bebida, de_leche = _publicado(bebida), _publicado(leche)
    comunes = sorted(set(de_bebida) & set(de_leche))
    assert h.date in comunes, "precondicion: el feriado cae dentro del horizonte publicado"
    assert de_bebida[h.date] > 0, "precondicion: la bebida vende el dia del feriado"
    for d in comunes:
        esperado = (de_bebida[d] * D("200")).quantize(D("0.001"))
        assert abs(de_leche[d] - esperado) <= D("0.01"), (
            "%s: leche %s, bebida x receta %s (feriado %s)" % (d, de_leche[d], esperado, h.date))
