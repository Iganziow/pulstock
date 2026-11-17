# -*- coding: utf-8 -*-
"""
tests/test_dia_incierto.py — un día que a veces abre y a veces no se pronostica
por lo que se espera vender, no por lo que se vende si abre.

Caso real, Marbrava, octubre de 2026: el sábado cerró cinco veces seguidas
(26-sep a 17-oct) y el dueño no sabe con anticipación si el próximo abre.
Producción publicaba ~1.000 unidades para cada sábado cerrado. El detector de
días cerrados recién lo marca cuando abrió menos del 10% de 8 semanas.

Regla: el punto del sábado x la fracción de los últimos 8 sábados (sin
feriados) en que abrió, si cerró al menos 2. Medido sobre los 8 sábados del
29-ago al 17-oct con lo publicado la noche anterior: error absoluto del núcleo
en esos días 6.561 -> 5.079.
"""
import datetime
from decimal import Decimal

import pytest

from forecast import services
from forecast.models import DailySales, Forecast, ForecastModel, Holiday

D = Decimal
SABADO, DOMINGO = 5, 6


def hoy():
    return datetime.date.today()


def _sabados_atras(n):
    """Los n sábados anteriores a ayer, del más reciente al más viejo (como
    los cuenta `fraccion_que_abre`)."""
    ayer = hoy() - datetime.timedelta(days=1)
    d = ayer - datetime.timedelta(days=(ayer.weekday() - SABADO) % 7)
    return [d - datetime.timedelta(weeks=i) for i in range(n)]


def _historia(tenant, warehouse, product, sabados_cerrados=(), semanas=12):
    """Vende todos los días salvo el domingo y los sábados indicados."""
    cerrados = set(sabados_cerrados)
    for i in range(1, semanas * 7 + 1):
        d = hoy() - datetime.timedelta(days=i)
        if d.weekday() == DOMINGO or d in cerrados:
            continue
        DailySales.objects.create(tenant=tenant, product=product, warehouse=warehouse,
                                  date=d, qty_sold=D("10"))


def _semana():
    return [{"date": hoy() + datetime.timedelta(days=i), "qty_predicted": D("10"),
             "lower_bound": D("7"), "upper_bound": D("13")} for i in range(1, 15)]


def _modelo(tenant, product, warehouse, algoritmo="theta"):
    return ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm=algoritmo, is_active=True, model_params={}, metrics={},
    )


def _publicado(product):
    return {f.forecast_date: f for f in Forecast.objects.filter(product=product, forecast_date__gt=hoy())}


@pytest.mark.django_db
class TestFraccionQueAbre:
    def test_cinco_cierres_de_ocho(self, tenant, warehouse, product):
        """Lo de Marbrava al 24-oct: abrió 3 de los últimos 8 sábados."""
        _historia(tenant, warehouse, product, sabados_cerrados=_sabados_atras(5))
        assert services.fraccion_que_abre(tenant.id, warehouse.id, closed_dows={DOMINGO}) == {
            SABADO: 3 / 8}

    def test_un_cierre_aislado_no_pondera(self, tenant, warehouse, product):
        _historia(tenant, warehouse, product, sabados_cerrados=_sabados_atras(1))
        assert services.fraccion_que_abre(tenant.id, warehouse.id, closed_dows={DOMINGO}) == {}

    def test_el_cierre_por_feriado_no_cuenta(self, tenant, warehouse, product):
        """Dos sábados cerrados, uno de ellos feriado: queda un solo cierre
        "propio" del sábado, que no alcanza. Y se cuenta hacia atrás hasta
        juntar 8 sábados que no son feriado."""
        s = _sabados_atras(10)
        _historia(tenant, warehouse, product, sabados_cerrados=[s[0], s[2]])
        Holiday.objects.create(tenant=None, name="Feriado de prueba", date=s[2])
        assert services.fraccion_que_abre(tenant.id, warehouse.id, closed_dows={DOMINGO}) == {}

        services._DIA_INCIERTO_CACHE.clear(); services._FECHAS_OPERADAS_CACHE.clear()
        DailySales.objects.filter(date=s[4]).delete()          # un segundo cierre real
        assert services.fraccion_que_abre(tenant.id, warehouse.id, closed_dows={DOMINGO}) == {
            SABADO: 6 / 8}

    def test_el_domingo_cerrado_lo_maneja_su_propia_regla(self, tenant, warehouse, product):
        _historia(tenant, warehouse, product)
        assert DOMINGO not in services.fraccion_que_abre(
            tenant.id, warehouse.id, closed_dows={DOMINGO})

    def test_unas_vacaciones_no_son_un_patron(self, tenant, warehouse, product):
        """Dos semanas sin vender nada: cada día de la semana "cerró" 2 de 8,
        pero no hay nada que decir del sábado ni de ningún otro día."""
        _historia(tenant, warehouse, product)
        s = _sabados_atras(4)
        DailySales.objects.filter(date__gt=s[3], date__lte=s[1]).delete()
        assert services.fraccion_que_abre(tenant.id, warehouse.id, closed_dows={DOMINGO}) == {}

    def test_la_historia_cortada_no_apaga_el_pronostico(self, tenant, warehouse, product):
        """El local dejó de registrar ventas hace 10 semanas (o los datos se
        cortaron): no es que cierre todos los días."""
        _historia(tenant, warehouse, product, semanas=20)
        DailySales.objects.filter(date__gte=hoy() - datetime.timedelta(weeks=10)).delete()
        assert services.fraccion_que_abre(tenant.id, warehouse.id, closed_dows={DOMINGO}) == {}

    def test_un_negocio_nuevo_no_cerro_antes_de_existir(self, tenant, warehouse, product):
        """Con 3 semanas de historia, los sábados de antes no son cierres."""
        _historia(tenant, warehouse, product, semanas=3)
        assert services.fraccion_que_abre(tenant.id, warehouse.id, closed_dows={DOMINGO}) == {}


@pytest.mark.django_db
class TestEnSaveForecasts:
    def test_el_sabado_incierto_publica_lo_esperado(self, tenant, store, warehouse, product):
        _historia(tenant, warehouse, product, sabados_cerrados=_sabados_atras(5))
        fm = _modelo(tenant, product, warehouse)
        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})
        pub = _publicado(product)
        sabados = [d for d in pub if d.weekday() == SABADO]
        assert sabados
        for d in sabados:
            # El viernes de al lado parte igual (10 + lo repartido del domingo
            # cerrado) y no es incierto: es lo que el sábado vendería si abre.
            viernes = pub[d - datetime.timedelta(days=1)]
            f = pub[d]
            assert abs(f.qty_predicted - viernes.qty_predicted * D("0.375")) <= D("0.001"), (
                "sabado %s: %s, viernes %s" % (d, f.qty_predicted, viernes.qty_predicted))
            assert viernes.qty_predicted >= D("10"), "el viernes no es incierto y no se toca"
            assert f.lower_bound == 0, "con 5 cierres de 8 el piso es vender nada"
            assert f.upper_bound == viernes.upper_bound, "el techo es el de un dia abierto"
        fm.refresh_from_db()
        assert fm.model_params["dia_incierto"] == {str(SABADO): 0.375}

    def test_el_derivado_no_se_pondera_dos_veces(self, tenant, store, warehouse, product):
        """Lo arma con lo publicado por sus bebidas, que ya viene ponderado.

        Con un derivado intermitente: el `smooth` entra a la mezcla con el nivel
        de 28 dias, y ESE nivel si se pondera (ver test_mezcla_prom28,
        TestConDiaIncierto). Aca se prueba solo que la parte del modelo no se
        pondera de nuevo."""
        _historia(tenant, warehouse, product, sabados_cerrados=_sabados_atras(5))
        fm = _modelo(tenant, product, warehouse, algoritmo="ingredient_derived")
        fm.demand_pattern = "intermittent"; fm.save(update_fields=["demand_pattern"])
        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})
        sabados = [f for d, f in _publicado(product).items() if d.weekday() == SABADO]
        assert sabados and all(f.qty_predicted >= D("10") for f in sabados)

    def test_interruptor(self, tenant, store, warehouse, product, monkeypatch):
        monkeypatch.setenv("FORECAST_DIA_INCIERTO_OFF", "1")
        _historia(tenant, warehouse, product, sabados_cerrados=_sabados_atras(5))
        fm = _modelo(tenant, product, warehouse)
        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})
        sabados = [f for d, f in _publicado(product).items() if d.weekday() == SABADO]
        assert sabados and all(f.qty_predicted >= D("10") for f in sabados)
        fm.refresh_from_db()
        assert "dia_incierto" not in fm.model_params
