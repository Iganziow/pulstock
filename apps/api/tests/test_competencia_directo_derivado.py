# -*- coding: utf-8 -*-
"""
tests/test_competencia_directo_derivado.py — el derivado tiene que ganarse
el puesto cada noche, igual que el directo, y con una medicion honesta.

Lo que habia (medido en Marbrava el 05/09/26):

  1. El backtest del derivado era TAUTOLOGICO: comparaba "ventas reales de
     los padres x receta" contra "consumo real del ingrediente", que es la
     expansion de receta de esas mismas ventas. WAPE guardado 0,0%-13% en 12
     de 14 derivados. Con eso le ganaba a cualquier directo y se activaba.
  2. Una vez activo, `make_active=ya_activo` en el comando lo reactivaba
     cada noche aunque el kept-path hubiera preferido al directo: trinquete.
  3. El derivado guarda demand_pattern="smooth" fijo; en un ingrediente
     intermitente el kept-path veia "cambio de patron" y lo saltaba.

Ahora el derivado se mide con las predicciones que sus padres PUBLICARON
(ForecastAccuracy) x receta, contra el consumo real, con ceros: la misma
vara que el backtest del directo. Y la competencia es simetrica: 15% de
margen para desplazar al titular en los dos sentidos.

Estos tests ejercitan el camino real del comando de entrenamiento con una
receta de verdad. La "calidad" de los padres se controla sembrando sus
filas de ForecastAccuracy: padres que acertaron -> derivado bueno; padres
que predijeron el triple -> derivado malo.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Recipe, RecipeLine
from forecast.models import DailySales, Forecast, ForecastAccuracy, ForecastModel

D = Decimal
PATRON = [7, 6, 8, 7, 9, 6, 7]


def _dia(i):
    return datetime.date.today() - datetime.timedelta(days=i)


def _historia(tenant, warehouse, padre, ingrediente, receta_qty, dias=60):
    """El padre vende un patron semanal; el ingrediente consume EXACTAMENTE
    padre x receta (como lo produce aggregate_daily_sales via StockMove)."""
    for i in range(1, dias + 1):
        q = D(str(PATRON[i % 7]))
        DailySales.objects.create(tenant=tenant, product=padre, warehouse=warehouse, date=_dia(i), qty_sold=q)
        DailySales.objects.create(tenant=tenant, product=ingrediente, warehouse=warehouse, date=_dia(i),
                                  qty_sold=q * receta_qty)


def _padre_predijo(tenant, warehouse, padre, factor, dias=30):
    """Siembra la accuracy del padre: predijo `factor` x lo que vendio."""
    ForecastAccuracy.objects.filter(tenant=tenant, product=padre, warehouse=warehouse).delete()
    for i in range(1, dias + 1):
        real = D(str(PATRON[i % 7]))
        pred = real * D(str(factor))
        ForecastAccuracy.objects.create(
            tenant=tenant, product=padre, warehouse=warehouse, date=_dia(i),
            qty_predicted=pred, qty_actual=real, error=pred - real,
            abs_pct_error=abs(pred - real) / real * 100 if real else D("0"),
            algorithm="seasonal_naive",
        )


def _entrenar(tenant):
    call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)


def _activo(product):
    return ForecastModel.objects.filter(product=product, is_active=True).first()


def _preparar(tenant, warehouse, product, product_b, receta_qty=D("2")):
    ingrediente, padre = product, product_b
    receta = Recipe.objects.create(tenant=tenant, product=padre, is_active=True)
    RecipeLine.objects.create(tenant=tenant, recipe=receta, ingredient=ingrediente, qty=receta_qty)
    _historia(tenant, warehouse, padre, ingrediente, receta_qty)
    return ingrediente, padre


@pytest.mark.django_db
class TestBacktestHonestoDelDerivado:
    def test_el_wape_del_derivado_refleja_lo_que_predijeron_sus_padres(
        self, tenant, store, warehouse, product, product_b,
    ):
        """Con padres que predijeron el TRIPLE, el derivado no puede medir 0%."""
        ingrediente, padre = _preparar(tenant, warehouse, product, product_b)
        _padre_predijo(tenant, warehouse, padre, factor=3)
        _entrenar(tenant)   # noche 1: el padre gana modelo; el derivado aun no tiene padres pronosticados
        _entrenar(tenant)   # noche 2: el derivado se entrena (candidato o activo)
        derivado = ForecastModel.objects.filter(product=ingrediente, algorithm="ingredient_derived").order_by("-version").first()
        assert derivado is not None, "el derivado no se entreno"
        wape = (derivado.metrics or {}).get("wape")
        assert wape is not None and 150 <= wape <= 250, (
            "padres que predijeron 3x deberian dar WAPE ~200%%, no %s (backtest tautologico?)" % wape
        )
        assert derivado.model_params.get("backtest_source") == "padres_publicados"
        assert derivado.model_params.get("backtest_days") >= 7

    def test_sin_padres_medidos_no_hay_backtest(self, tenant, store, warehouse, product, product_b):
        """Sin ForecastAccuracy de los padres el derivado queda 'sin backtest'
        (999), como antes cuando faltaba historia: no se activa por un 0% falso."""
        ingrediente, padre = _preparar(tenant, warehouse, product, product_b)
        _entrenar(tenant)
        _entrenar(tenant)
        derivado = ForecastModel.objects.filter(product=ingrediente, algorithm="ingredient_derived").order_by("-version").first()
        assert derivado is not None
        assert (derivado.metrics or {}).get("wape") == 999
        assert _activo(ingrediente).algorithm != "ingredient_derived"


@pytest.mark.django_db
class TestCompetenciaSimetrica:
    def test_el_derivado_bueno_le_gana_al_directo_y_conserva_el_puesto(
        self, tenant, store, warehouse, product, product_b,
    ):
        ingrediente, padre = _preparar(tenant, warehouse, product, product_b)
        _padre_predijo(tenant, warehouse, padre, factor=1)     # los padres acertaron
        _entrenar(tenant)
        _entrenar(tenant)
        assert _activo(ingrediente).algorithm == "ingredient_derived", "con padres perfectos el derivado debe ganar"
        _entrenar(tenant)
        assert _activo(ingrediente).algorithm == "ingredient_derived", "y conservar el puesto la noche siguiente"

    def test_el_directo_recupera_el_puesto_cuando_los_padres_se_vuelven_malos(
        self, tenant, store, warehouse, product, product_b,
    ):
        ingrediente, padre = _preparar(tenant, warehouse, product, product_b)
        _padre_predijo(tenant, warehouse, padre, factor=1)
        _entrenar(tenant)
        _entrenar(tenant)
        assert _activo(ingrediente).algorithm == "ingredient_derived"

        # Los padres empezaron a predecir el triple (como Chai en agosto).
        # El titular se juzga por el error que midio ANOCHE (una noche de
        # rezago): la primera noche re-mide al derivado, la segunda lo
        # desplaza.
        _padre_predijo(tenant, warehouse, padre, factor=3)
        _entrenar(tenant)
        _entrenar(tenant)
        activo = _activo(ingrediente)
        assert activo is not None
        assert activo.algorithm != "ingredient_derived", (
            "el derivado mide ~200%% y el directo ~20%%, pero sigue activo: "
            "el trinquete `make_active=ya_activo` volvio a pisar al directo"
        )
        # y el derivado sigue entrenandose como candidato, listo para volver
        cand = ForecastModel.objects.filter(product=ingrediente, algorithm="ingredient_derived", is_active=False).exists()
        assert cand, "el derivado desplazado tiene que seguir como candidato"

    def test_el_derivado_vuelve_cuando_los_padres_vuelven_a_acertar(
        self, tenant, store, warehouse, product, product_b,
    ):
        """La simetria: desplazado no es para siempre."""
        ingrediente, padre = _preparar(tenant, warehouse, product, product_b)
        _padre_predijo(tenant, warehouse, padre, factor=3)
        _entrenar(tenant)
        _entrenar(tenant)
        assert _activo(ingrediente).algorithm != "ingredient_derived"
        _padre_predijo(tenant, warehouse, padre, factor=1)
        _entrenar(tenant)
        assert _activo(ingrediente).algorithm == "ingredient_derived"

    def test_siempre_hay_un_activo_que_escribe_pronosticos(self, tenant, store, warehouse, product, product_b):
        """Nunca puede quedar el ingrediente sin filas de Forecast (el bug de
        los mudos): gane quien gane, el activo escribe."""
        ingrediente, padre = _preparar(tenant, warehouse, product, product_b)
        for noche, factor in enumerate([1, 1, 3, 3, 3, 1, 1]):
            _padre_predijo(tenant, warehouse, padre, factor=factor)
            _entrenar(tenant)
            act = _activo(ingrediente)
            assert act is not None, "noche %d sin activo" % noche
            assert Forecast.objects.filter(model=act, forecast_date__gt=datetime.date.today()).exists(), (
                "noche %d: el activo (%s) no tiene pronosticos futuros" % (noche, act.algorithm)
            )
            assert ForecastModel.objects.filter(product=ingrediente, is_active=True).count() == 1


@pytest.mark.django_db
class TestVaraVigente:
    def test_wape_real_manda_si_hay_muestras(self):
        from forecast.services import _wape_vigente
        assert _wape_vigente({"wape": 10, "wape_real": 80, "wape_real_samples": 7}) == 80
        assert _wape_vigente({"wape": 10, "wape_real": 80, "wape_real_samples": 6}) == 10
        assert _wape_vigente({"wape": 10}) == 10
        assert _wape_vigente({}) == 999
        assert _wape_vigente(None) == 999
