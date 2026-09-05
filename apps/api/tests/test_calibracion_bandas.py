# -*- coding: utf-8 -*-
"""
tests/test_calibracion_bandas.py — las bandas tienen que cubrir lo que dicen.

Medido en Marbrava el 04/09/26: las bandas "del 80%" cubrian el 43% de los
dias reales, con el piso por encima de la realidad el 48% de las veces y
anchos de 0,6x a 18x la prediccion. Validado fuera de muestra con datos de
produccion: la calibracion empirica sube la cobertura a 92% y baja el ancho
de theta de 8,3x a 1,0x.
"""
import datetime
import random
from decimal import Decimal

import pytest
from django.core.management import call_command

from forecast import services
from forecast.engine.calibracion import (
    aplicar_calibracion, cuantil, factores_de_calibracion,
)
from forecast.models import DailySales, Forecast, ForecastAccuracy, ForecastModel

D = Decimal


class TestLaFuncionPura:
    def test_cuantiles(self):
        assert cuantil([1, 2, 3, 4, 5], 0.5) == 3
        assert cuantil([1, 2, 3, 4, 5], 0.0) == 1
        assert cuantil([1, 2, 3, 4, 5], 1.0) == 5
        assert cuantil([], 0.5) is None

    def test_modelo_que_sobrepredice_baja_el_techo_por_debajo_de_la_prediccion(self):
        """El caso de Croston: el 85% de los dias reales bajo el piso."""
        razones = [0.3, 0.5, 0.4, 0.6, 0.2, 0.5, 0.4, 0.3, 0.7, 0.5, 0.4, 0.6]
        f = factores_de_calibracion(razones)
        assert f["q_hi"] < 1.0, "la realidad esta siempre bajo la prediccion: el techo tiene que decirlo"
        assert f["q_lo"] >= 0.0

    def test_pocos_datos_devuelve_None_y_no_toca_nada(self):
        assert factores_de_calibracion([0.5] * 9) is None
        fcs = [{"qty_predicted": D("10"), "lower_bound": D("7"), "upper_bound": D("13")}]
        aplicar_calibracion(fcs, None)
        assert fcs[0]["upper_bound"] == D("13")

    def test_tope_y_piso_del_techo(self):
        assert factores_de_calibracion([50.0] * 20)["q_hi"] == 3.0, "tope: una banda de 50x no dice nada"
        assert factores_de_calibracion([0.01] * 20)["q_hi"] == 0.25, "piso: el techo no puede colapsar a cero"

    def test_dias_cerrados_quedan_en_cero(self):
        fcs = [{"qty_predicted": D("0"), "lower_bound": D("0"), "upper_bound": D("0")},
               {"qty_predicted": D("10"), "lower_bound": D("7"), "upper_bound": D("13")}]
        aplicar_calibracion(fcs, {"q_lo": 0.5, "q_hi": 1.5, "n": 20})
        assert fcs[0]["upper_bound"] == D("0")
        assert fcs[1]["lower_bound"] == D("5.000") and fcs[1]["upper_bound"] == D("15.000")

    def test_cobertura_sintetica_cerca_del_80(self):
        """Lo que promete la tecnica: calibrada con una mitad, la banda cubre
        ~80% de la otra mitad. Distribucion sesgada a proposito (el modelo
        sobre-predice), como en produccion."""
        rnd = random.Random(7)
        razones = [rnd.lognormvariate(-0.4, 0.5) for _ in range(400)]
        f = factores_de_calibracion(razones[:200])
        dentro = sum(1 for r in razones[200:] if f["q_lo"] <= r <= f["q_hi"])
        assert 0.70 <= dentro / 200 <= 0.90, "cobertura fuera de muestra: %.2f" % (dentro / 200)


def _historia(tenant, product, warehouse, dias=60):
    hoy = datetime.date.today()
    patron = [7, 6, 8, 7, 9, 6, 7]
    for i in range(1, dias + 1):
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=hoy - datetime.timedelta(days=i), qty_sold=D(str(patron[i % 7])),
        )


def _mediciones(tenant, product, warehouse, dias=28):
    """28 dias en que la realidad fue el 40% o el 60% de lo predicho."""
    hoy = datetime.date.today()
    for i in range(1, dias + 1):
        pred = D("10"); real = D("4") if i % 2 else D("6")
        ForecastAccuracy.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=hoy - datetime.timedelta(days=i), qty_predicted=pred,
            qty_actual=real, error=pred - real, algorithm="theta",
        )


def _pronosticos(n=7):
    hoy = datetime.date.today()
    return [{"date": hoy + datetime.timedelta(days=i), "qty_predicted": D("10"),
             "lower_bound": D("7"), "upper_bound": D("13")} for i in range(1, n + 1)]


@pytest.mark.django_db
class TestEnElEmbudo:
    def _modelo(self, tenant, product, warehouse):
        _historia(tenant, product, warehouse)
        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)
        return ForecastModel.objects.get(product=product, is_active=True)

    def test_las_bandas_guardadas_salen_calibradas(self, tenant, store, warehouse, product):
        fm = self._modelo(tenant, product, warehouse)
        _mediciones(tenant, product, warehouse)

        services.save_forecasts(tenant, product, warehouse.id, fm, _pronosticos(), D("70"), {})

        filas = Forecast.objects.filter(product=product, forecast_date__gt=datetime.date.today())
        assert filas.exists()
        for f in filas:
            if f.qty_predicted <= 0:
                continue
            assert abs(float(f.lower_bound / f.qty_predicted) - 0.4) < 0.02, (
                "piso %s para prediccion %s: no es el cuantil 10 (0,4)" % (f.lower_bound, f.qty_predicted))
            assert abs(float(f.upper_bound / f.qty_predicted) - 0.6) < 0.02, (
                "techo %s para prediccion %s: no es el cuantil 90 (0,6)" % (f.upper_bound, f.qty_predicted))
        fm.refresh_from_db()
        assert fm.model_params["calibracion"]["n"] == 28

    def test_el_quiebre_conservador_usa_el_techo_calibrado(self, tenant, store, warehouse, product):
        """Chocolate Premium: techo de 18x -> 'quiebre en 5 dias' con 18 de
        stock. Con el techo calibrado (0,6x aca) los dias suben."""
        from inventory.models import StockItem
        fm = self._modelo(tenant, product, warehouse)
        fm.confidence_label = "low"; fm.save(update_fields=["confidence_label"])
        _mediciones(tenant, product, warehouse)
        si = StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=product,
                                      on_hand=D("30"), avg_cost=D("1"), stock_value=D("30"))
        # techo original 13/dia -> 30 de stock duran 3 dias; calibrado 6/dia -> 5 dias
        services.save_forecasts(tenant, product, warehouse.id, fm, _pronosticos(10), D("70"),
                                {(warehouse.id, product.id): si})
        dias = Forecast.objects.filter(product=product, forecast_date__gt=datetime.date.today()).first().days_to_stockout
        assert dias == 5, "dias_a_quiebre=%s: el conservador sigue usando el techo sin calibrar" % dias

    def test_sin_mediciones_conserva_la_banda_del_algoritmo(self, tenant, store, warehouse, product):
        fm = self._modelo(tenant, product, warehouse)
        services.save_forecasts(tenant, product, warehouse.id, fm, _pronosticos(), D("70"), {})
        f = Forecast.objects.filter(product=product, forecast_date__gt=datetime.date.today()).first()
        assert f.lower_bound == D("7.000") and f.upper_bound == D("13.000")

    def test_interruptor_de_apagado(self, tenant, store, warehouse, product, monkeypatch):
        monkeypatch.setenv("FORECAST_CALIBRACION_OFF", "1")
        fm = self._modelo(tenant, product, warehouse)
        _mediciones(tenant, product, warehouse)
        services.save_forecasts(tenant, product, warehouse.id, fm, _pronosticos(), D("70"), {})
        f = Forecast.objects.filter(product=product, forecast_date__gt=datetime.date.today()).first()
        assert f.upper_bound == D("13.000"), "con el interruptor puesto la banda no puede cambiar"
