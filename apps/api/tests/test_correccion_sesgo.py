# -*- coding: utf-8 -*-
"""
tests/test_correccion_sesgo.py — el sesgo se corrige y la correccion LLEGA a
la tabla.

Lo que habia, verificado en produccion el 07/09/26: los cuatro post-procesos
(tendencia, correccion de sesgo, estacionalidad mensual y ano-contra-ano) se
calculaban, se guardaban en `model_params` y no llegaban a la tabla
`Forecast`. `train_product_model` los aplicaba, guardaba, y a continuacion
`_regen_from_existing` reescribia las filas con el algoritmo crudo. 107 de
188 modelos activos tenian una correccion de sesgo guardada que no estaba en
ninguna fila publicada; en los adaptive_ma la fila era exactamente el
algoritmo crudo.

Medido con el backtest fiel sobre 8 semanas de Marbrava (224 productos):

    variante                       WAPE cola   sesgo cola   mejoran/empeoran
    sin correccion                   158,9%       +38,5%          --
    la vieja (resta amortiguada)     157,8%       +36,9%        58 / 23
    solo mediana del cociente        144,7%       +14,4%        97 / 16
    acuerdo de los dos (esta)        152,7%       +29,2%        86 / 20

La de mediana sola gana en el agregado y pierde donde importa: convierte
productos sin sesgo en sub-predictores del 13 al 51% (Helado vainilla, +1%
de sesgo, quedaba en -51%), y sub-predecir es quiebre. La regla del acuerdo
corrige cuando la mediana y la razon de totales apuntan al mismo lado.
"""
import datetime
import os
from decimal import Decimal

import pytest
from django.core.management import call_command

from forecast import services
from forecast.engine.calibracion import factor_de_sesgo, aplicar_factor_de_sesgo
from forecast.models import DailySales, Forecast, ForecastAccuracy, ForecastModel

D = Decimal
HOY = datetime.date.today()


class TestLaRegla:
    def test_sobrepredice_siempre_se_corrige_a_la_baja(self):
        f = factor_de_sesgo([(10, 4)] * 12)
        assert f["factor"] == 0.7, f          # 1 + 0,5 x (0,4 - 1)
        assert f["mediana"] == 0.4 and f["totales"] == 0.4

    def test_subpredice_siempre_se_corrige_al_alza(self):
        assert factor_de_sesgo([(2, 5)] * 12)["factor"] == 1.75

    def test_producto_a_rafagas_no_se_toca(self):
        """El dia tipico queda muy bajo la prediccion pero el total calza: la
        mediana dice 'corrige a la baja' y los totales dicen que no. Es el
        caso de Helado vainilla, que corrigiendo por mediana quedaba en -51%
        de sesgo."""
        assert factor_de_sesgo([(1, 0)] * 20 + [(1, 12)] * 4) is None

    def test_sin_sesgo_ni_datos_no_se_toca(self):
        assert factor_de_sesgo([(10, 10)] * 12) is None
        assert factor_de_sesgo([(10, 4)] * 4) is None      # menos de 5 dias
        assert factor_de_sesgo([]) is None
        assert factor_de_sesgo([(0, 5)] * 20) is None      # sin prediccion > 0

    def test_umbral_y_topes(self):
        assert factor_de_sesgo([(10, 9.5)] * 12) is None   # 2,5%: ruido
        assert factor_de_sesgo([(10, 0)] * 12)["factor"] == 0.5     # piso
        assert factor_de_sesgo([(1, 100)] * 12)["factor"] == 2.0    # techo

    def test_aplicar_escala_prediccion_y_banda(self):
        fcs = [{"qty_predicted": D("10"), "lower_bound": D("6"), "upper_bound": D("14")}]
        aplicar_factor_de_sesgo(fcs, {"factor": 0.7})
        assert fcs[0]["qty_predicted"] == D("7.000")
        assert fcs[0]["lower_bound"] == D("4.200") and fcs[0]["upper_bound"] == D("9.800")
        sin = [{"qty_predicted": D("10"), "lower_bound": D("6"), "upper_bound": D("14")}]
        aplicar_factor_de_sesgo(sin, None)
        assert sin[0]["qty_predicted"] == D("10")


def _historia(tenant, product, warehouse, dias=60):
    patron = [7, 6, 8, 7, 9, 6, 7]
    for i in range(1, dias + 1):
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=HOY - datetime.timedelta(days=i), qty_sold=D(str(patron[i % 7])),
        )


def _midio(tenant, product, warehouse, pred, real, dias=28):
    for i in range(1, dias + 1):
        ForecastAccuracy.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=HOY - datetime.timedelta(days=i), qty_predicted=D(str(pred)),
            qty_actual=D(str(real)), error=D(str(pred)) - D(str(real)), algorithm="theta",
        )


def _pronosticos(n=7):
    return [{"date": HOY + datetime.timedelta(days=i), "qty_predicted": D("10"),
             "lower_bound": D("7"), "upper_bound": D("13")} for i in range(1, n + 1)]


def _filas(product):
    return list(Forecast.objects.filter(product=product, forecast_date__gt=HOY).order_by("forecast_date"))


@pytest.mark.django_db
class TestEnElEmbudo:
    def _modelo(self, tenant, product, warehouse):
        _historia(tenant, product, warehouse)
        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)
        return ForecastModel.objects.get(product=product, is_active=True)

    def test_la_correccion_llega_a_la_tabla(self, tenant, store, warehouse, product):
        """Lo que fallaba: se guardaba en params y la fila publicada no la tenia."""
        fm = self._modelo(tenant, product, warehouse)
        _midio(tenant, product, warehouse, pred=10, real=4)

        services.save_forecasts(tenant, product, warehouse.id, fm, _pronosticos(), D("70"), {})

        for f in _filas(product):
            assert f.qty_predicted == D("7.000"), (
                "%s: la prediccion publicada es %s, no la corregida (10 x 0,7)"
                % (f.forecast_date, f.qty_predicted))
        fm.refresh_from_db()
        assert fm.model_params["sesgo"]["factor"] == 0.7

    def test_producto_sin_sesgo_no_se_toca(self, tenant, store, warehouse, product):
        fm = self._modelo(tenant, product, warehouse)
        _midio(tenant, product, warehouse, pred=10, real=10)
        services.save_forecasts(tenant, product, warehouse.id, fm, _pronosticos(), D("70"), {})
        assert all(f.qty_predicted == D("10.000") for f in _filas(product))
        fm.refresh_from_db()
        assert "sesgo" not in (fm.model_params or {})

    def test_el_derivado_de_receta_queda_fuera(self, tenant, store, warehouse, product):
        """El derivado aplica su propia correccion en train_ingredient_product
        y esa SI llega a la tabla: corregir de nuevo seria doble descuento."""
        fm = self._modelo(tenant, product, warehouse)
        fm.algorithm = "ingredient_derived"
        fm.save(update_fields=["algorithm"])
        _midio(tenant, product, warehouse, pred=10, real=4)
        services.save_forecasts(tenant, product, warehouse.id, fm, _pronosticos(), D("70"), {})
        assert all(f.qty_predicted == D("10.000") for f in _filas(product))

    def test_interruptor_de_apagado(self, tenant, store, warehouse, product, monkeypatch):
        fm = self._modelo(tenant, product, warehouse)
        _midio(tenant, product, warehouse, pred=10, real=4)
        monkeypatch.setenv("FORECAST_SESGO_OFF", "1")
        services.save_forecasts(tenant, product, warehouse.id, fm, _pronosticos(), D("70"), {})
        assert all(f.qty_predicted == D("10.000") for f in _filas(product))

    def test_la_banda_sigue_conteniendo_la_prediccion(self, tenant, store, warehouse, product):
        """Las dos correcciones conviven: primero se escala el punto, despues
        se calibran los cuantiles sobre el punto ya corregido."""
        fm = self._modelo(tenant, product, warehouse)
        _midio(tenant, product, warehouse, pred=10, real=4)
        services.save_forecasts(tenant, product, warehouse.id, fm, _pronosticos(14), D("70"), {})
        filas = _filas(product)
        assert filas
        for f in filas:
            assert f.lower_bound <= f.qty_predicted <= f.upper_bound, (
                "%s: %s fuera de [%s, %s]" % (f.forecast_date, f.qty_predicted, f.lower_bound, f.upper_bound))

    def test_la_corrida_nocturna_completa_publica_la_correccion(self, tenant, store, warehouse, product):
        """De punta a punta por el comando real: es el camino donde el regen
        borraba la correccion."""
        _historia(tenant, product, warehouse)
        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)
        fm = ForecastModel.objects.get(product=product, is_active=True)
        sin_correccion = {f.forecast_date: f.qty_predicted for f in _filas(product)}

        # El modelo predijo el doble de lo que se vendio, 28 dias seguidos.
        for i in range(1, 29):
            ForecastAccuracy.objects.update_or_create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=HOY - datetime.timedelta(days=i),
                defaults={"qty_predicted": D("20"), "qty_actual": D("10"),
                          "error": D("10"), "algorithm": fm.algorithm},
            )
        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

        con_correccion = {f.forecast_date: f.qty_predicted for f in _filas(product)}
        comunes = [d for d in con_correccion if d in sin_correccion and sin_correccion[d] > 0]
        assert comunes, "no hay dias comparables"
        assert any(con_correccion[d] < sin_correccion[d] for d in comunes), (
            "la corrida nocturna publico lo mismo que sin correccion: el regen la volvio a pisar"
        )
        activo = ForecastModel.objects.get(product=product, is_active=True)
        assert (activo.model_params or {}).get("sesgo", {}).get("factor") == 0.75
