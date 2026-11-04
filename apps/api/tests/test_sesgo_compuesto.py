# -*- coding: utf-8 -*-
"""
tests/test_sesgo_compuesto.py — la correccion de sesgo se compone (04/11/26).

El defecto, medido en prod el 2-nov: factor_de_sesgo mide sobre lo PUBLICADO
(que ya trae el factor de anoche) y aplica el resultado sobre el CRUDO. Con el
amortiguado al 50% queda clavado a medio camino: Helado vainilla con factor
0,84 = 1 + 0,5 x (0,68 - 1), publicando +47% sobre lo real noche tras noche.
"""
import datetime
from decimal import Decimal

import pytest

from forecast import services
from forecast.engine.calibracion import objetivo_de_sesgo, siguiente_factor
from forecast.models import Forecast, ForecastAccuracy, ForecastModel

D = Decimal
HOY = datetime.date.today()


class TestLaRegla:
    def test_el_objetivo_es_real_sobre_crudo_sin_amortiguar(self):
        o = objetivo_de_sesgo([(10, 4)] * 12)
        assert o["objetivo"] == 0.4

    def test_si_mediana_y_totales_discrepan_no_hay_objetivo(self):
        # rafagas: dia tipico bajo, total arriba
        assert objetivo_de_sesgo([(10, 0)] * 8 + [(10, 60)] * 4) is None

    def test_el_factor_avanza_medio_camino_y_converge(self):
        """Lo que la regla vieja no hacia: con el crudo 2,5 veces lo real, el
        factor llega a 0,4 en vez de quedarse en 0,7."""
        objetivo = objetivo_de_sesgo([(10, 4)] * 12)
        f = 1.0
        for _ in range(8):
            f = siguiente_factor(f, objetivo)["factor"]
        assert f == pytest.approx(0.4, abs=0.01)

    def test_sin_evidencia_vuelve_hacia_1(self):
        assert siguiente_factor(0.6, None)["factor"] == 0.8
        assert siguiente_factor(0.97, None) is None, "a menos del umbral es 1"

    def test_el_piso_es_0_3(self):
        o = objetivo_de_sesgo([(10, 0.1)] * 12)
        assert o["objetivo"] == 0.3

    def test_no_sobrepasa(self):
        """El objetivo no depende del factor: aunque el factor ya este en el
        objetivo, no lo empuja mas alla."""
        o = objetivo_de_sesgo([(10, 4)] * 12)
        assert siguiente_factor(0.4, o) is not None
        assert siguiente_factor(0.4, o)["factor"] == 0.4


def _modelo(tenant, product, warehouse, params=None, trained_at=None, activo=True):
    fm = ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, algorithm="theta",
        demand_pattern="intermittent", is_active=activo, model_params=params or {},
        **({"trained_at": trained_at} if trained_at else {}),
    )
    return fm


def _publico(tenant, product, warehouse, fm, dias, pred, real):
    """Dias pasados en que `fm` publico `pred` y se vendio `real`."""
    for i in range(1, dias + 1):
        d = HOY - datetime.timedelta(days=i)
        Forecast.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, model=fm,
            forecast_date=d, qty_predicted=D(str(pred)),
            generated_at=datetime.datetime.combine(d - datetime.timedelta(days=1), datetime.time(4, 30),
                                                   tzinfo=datetime.timezone.utc),
        )
        ForecastAccuracy.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, date=d,
            qty_predicted=D(str(pred)), qty_actual=D(str(real)),
            error=D(str(pred)) - D(str(real)), algorithm="theta",
        )


def _pronosticos(n=7):
    return [{"date": HOY + datetime.timedelta(days=i), "qty_predicted": D("10"),
             "lower_bound": D("7"), "upper_bound": D("13")} for i in range(1, n + 1)]


def _guardar(tenant, product, warehouse, fm):
    services.save_forecasts(tenant, product, warehouse.id, fm, _pronosticos(), D("70"), {})
    fm.refresh_from_db()
    return fm


@pytest.fixture(autouse=True)
def _sin_mezcla(monkeypatch):
    monkeypatch.setenv("FORECAST_MEZCLA_OFF", "1")


@pytest.mark.django_db
class TestEnSaveForecasts:
    def test_el_crudo_se_reconstruye_con_el_factor_de_esa_noche(self, tenant, store, warehouse, product):
        """El caso del Helado vainilla. Se publico 8 (crudo 10 x 0,8) y se
        vendio 4: el objetivo es 4/10 = 0,4, no 4/8 = 0,5."""
        hist = {(HOY - datetime.timedelta(days=i + 1)).isoformat(): 0.8 for i in range(1, 30)}
        fm = _modelo(tenant, product, warehouse, {"sesgo": {"factor": 0.8}, "sesgo_hist": hist})
        _publico(tenant, product, warehouse, fm, 28, pred=8, real=4)
        fm = _guardar(tenant, product, warehouse, fm)
        s = fm.model_params["sesgo"]
        assert s["objetivo"] == 0.4
        assert s["previo"] == 0.8
        assert s["factor"] == 0.6, "medio camino de 0,8 hacia 0,4"
        assert all(f.qty_predicted == D("6.000") for f in Forecast.objects.filter(product=product, forecast_date__gt=HOY))

    def test_guarda_el_historial_de_la_noche(self, tenant, store, warehouse, product):
        fm = _modelo(tenant, product, warehouse)
        _publico(tenant, product, warehouse, fm, 28, pred=10, real=4)
        fm = _guardar(tenant, product, warehouse, fm)
        assert fm.model_params["sesgo_hist"][HOY.isoformat()] == 0.7

    def test_dos_veces_la_misma_noche_no_avanza_dos_pasos(self, tenant, store, warehouse, product):
        """Entrenamiento y regeneracion pueden guardar el mismo producto la
        misma noche: el factor previo es el de una noche ANTERIOR."""
        fm = _modelo(tenant, product, warehouse)
        _publico(tenant, product, warehouse, fm, 28, pred=10, real=4)
        _guardar(tenant, product, warehouse, fm)
        fm = _guardar(tenant, product, warehouse, fm)
        assert fm.model_params["sesgo"]["factor"] == 0.7

    def test_un_modelo_nuevo_hereda_el_factor_del_anterior(self, tenant, store, warehouse, product):
        """Cada noche nacen ~68 modelos: sin heredar, el factor volveria a 1."""
        hist = {(HOY - datetime.timedelta(days=i)).isoformat(): 0.6 for i in range(1, 31)}
        viejo = _modelo(tenant, product, warehouse, {"sesgo": {"factor": 0.6}, "sesgo_hist": hist},
                        trained_at=datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc), activo=False)
        _publico(tenant, product, warehouse, viejo, 28, pred=6, real=4)
        nuevo = _modelo(tenant, product, warehouse)
        nuevo = _guardar(tenant, product, warehouse, nuevo)
        s = nuevo.model_params["sesgo"]
        assert s["previo"] == 0.6
        assert s["objetivo"] == 0.4          # crudo 6/0,6 = 10, real 4
        assert s["factor"] == 0.5

    def test_un_modelo_de_antes_del_historial_usa_su_factor_viejo(self, tenant, store, warehouse, product):
        """El dia del despliegue: el modelo trae factor 0,8 y no tiene
        historial. Sus noches anteriores se reconstruyen con ese 0,8, y queda
        guardado como `sesgo_legado` para las noches siguientes."""
        fm = _modelo(tenant, product, warehouse, {"sesgo": {"factor": 0.8}})
        _publico(tenant, product, warehouse, fm, 28, pred=8, real=4)
        fm = _guardar(tenant, product, warehouse, fm)
        assert fm.model_params["sesgo_legado"] == 0.8
        assert fm.model_params["sesgo"]["objetivo"] == 0.4
        assert fm.model_params["sesgo"]["factor"] == 0.6
        fm = _guardar(tenant, product, warehouse, fm)      # misma noche, otra vez
        assert fm.model_params["sesgo"]["factor"] == 0.6

    def test_el_interruptor_vuelve_a_la_regla_anterior(self, tenant, store, warehouse, product, monkeypatch):
        monkeypatch.setenv("FORECAST_SESGO_COMPUESTO_OFF", "1")
        hist = {(HOY - datetime.timedelta(days=i + 1)).isoformat(): 0.8 for i in range(1, 30)}
        fm = _modelo(tenant, product, warehouse, {"sesgo": {"factor": 0.8}, "sesgo_hist": hist})
        _publico(tenant, product, warehouse, fm, 28, pred=8, real=4)
        fm = _guardar(tenant, product, warehouse, fm)
        assert fm.model_params["sesgo"]["factor"] == 0.75, "1 + 0,5 x (4/8 - 1): la vieja"
