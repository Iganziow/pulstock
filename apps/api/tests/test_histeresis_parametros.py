# -*- coding: utf-8 -*-
"""
tests/test_histeresis_parametros.py — alpha y beta de anoche defienden el puesto.

Medido en produccion el 12/09/26 (15 noches): cuando el algoritmo se conserva
pero la grilla elige otro alpha/beta, el nivel publicado salta 22% de mediana.
El Capuccino caramelo alternaba alpha 0.20 <-> 0.05 noche por medio, y su nivel
0.14 <-> 0.22 con el. Ahora, cuando el algoritmo titular gana su puesto, su
grilla conserva los parametros de anoche salvo que otro punto le gane por
MARGEN_CAMBIO_PARAMETROS. La competencia de algoritmo se juzga con el titular
tuneado libre: retener los parametros dentro de ella lo hacia perder mas.
"""
import datetime

import pytest
from django.utils import timezone

from forecast import services
from forecast.engine import selection, utils
from forecast.engine.algorithms.croston import CrostonForecast, _backtest_croston
from forecast.engine.algorithms.tsb import TSBForecast, _backtest_tsb
from forecast.engine.registry import ALGORITHM_REGISTRY
from forecast.engine.utils import MARGEN_CAMBIO_PARAMETROS, elegir_parametros
from forecast.models import ForecastModel


def _m(wape_total, mae=1.0):
    return {"wape_total": wape_total, "mae": mae}


class TestElegirParametros:

    def test_sin_previos_gana_el_mejor(self):
        r = {0.05: _m(50), 0.10: _m(40), 0.20: _m(45)}
        assert elegir_parametros(r, None)[0] == 0.10

    def test_conserva_los_previos_si_el_mejor_no_saca_margen(self):
        r = {0.05: _m(50), 0.10: _m(40), 0.20: _m(42)}
        assert elegir_parametros(r, 0.20)[0] == 0.20

    def test_reemplaza_con_mejora_clara(self):
        r = {0.05: _m(50), 0.10: _m(30), 0.20: _m(42)}
        assert elegir_parametros(r, 0.20)[0] == 0.10

    def test_ganar_justo_por_el_margen_no_alcanza(self):
        r = {0.10: _m(42 * MARGEN_CAMBIO_PARAMETROS), 0.20: _m(42)}
        assert elegir_parametros(r, 0.20)[0] == 0.20

    def test_previos_fuera_de_la_grilla_no_protegen(self):
        r = {0.05: _m(50), 0.10: _m(40)}
        assert elegir_parametros(r, 0.99)[0] == 0.10

    def test_previos_sin_evidencia_no_protegen(self):
        r = {0.10: _m(40), 0.20: _m(999, mae=0.1)}
        assert elegir_parametros(r, 0.20)[0] == 0.10

    def test_sin_wape_total_en_nadie_se_compara_el_mae(self):
        r = {0.10: _m(999, mae=0.95), 0.20: _m(999, mae=1.0)}
        assert elegir_parametros(r, 0.20)[0] == 0.20
        r = {0.10: _m(999, mae=0.5), 0.20: _m(999, mae=1.0)}
        assert elegir_parametros(r, 0.20)[0] == 0.10

    def test_empate_exacto(self):
        r = {0.05: _m(40), 0.10: _m(40), 0.20: _m(40)}
        assert elegir_parametros(r, None)[0] == 0.05, "sin previos, el primero de la grilla (como siempre)"
        assert elegir_parametros(r, 0.20)[0] == 0.20, "con previos, los previos"

    def test_devuelve_las_metricas_del_elegido(self):
        r = {0.10: _m(40, mae=2.0), 0.20: _m(42, mae=3.0)}
        params, metricas = elegir_parametros(r, 0.20)
        assert params == 0.20 and metricas["mae"] == 3.0

    def test_grilla_vacia(self):
        assert elegir_parametros({}, 0.2) == (None, None)

    def test_el_margen_se_lee_al_llamar(self, monkeypatch):
        monkeypatch.setattr(utils, "MARGEN_CAMBIO_PARAMETROS", 1.0)
        r = {0.10: _m(41), 0.20: _m(42)}
        assert elegir_parametros(r, 0.20)[0] == 0.10


def _serie_plana(n=70, v=5.0):
    hoy = datetime.date(2026, 9, 11)
    return [(hoy - datetime.timedelta(days=n - 1 - i), v) for i in range(n)]


class TestGrillas:
    """En una serie plana todos los alpha/beta dan el mismo pronostico, asi
    que la grilla empata: sin previos gana el primero, con previos los previos."""

    def test_croston_conserva_el_alpha_de_anoche_en_empate(self):
        s = _serie_plana()
        assert _backtest_croston(s, n_folds=8)["best_alpha"] == 0.05
        assert _backtest_croston(s, n_folds=8, prev_alpha=0.30)["best_alpha"] == 0.30

    def test_tsb_conserva_alpha_y_beta_de_anoche_en_empate(self):
        s = _serie_plana()
        m = _backtest_tsb(s, n_folds=8)
        assert (m["best_alpha"], m["best_beta"]) == (0.05, 0.02)
        m = _backtest_tsb(s, n_folds=8, prev_alpha=0.30, prev_beta=0.20)
        assert (m["best_alpha"], m["best_beta"]) == (0.30, 0.20)

    def test_previos_fuera_de_la_grilla_o_incompletos_no_rompen(self):
        s = _serie_plana()
        assert _backtest_croston(s, n_folds=8, prev_alpha=0.77)["best_alpha"] == 0.05
        m = _backtest_tsb(s, n_folds=8, prev_alpha=0.30, prev_beta=None)
        assert (m["best_alpha"], m["best_beta"]) == (0.05, 0.02)

    def test_las_clases_pasan_los_previos_a_su_grilla(self):
        s = _serie_plana()
        assert CrostonForecast().backtest(s, n_folds=8, prev_alpha=0.30)["best_alpha"] == 0.30
        m = TSBForecast().backtest(s, n_folds=8, prev_alpha=0.30, prev_beta=0.20)
        assert (m["best_alpha"], m["best_beta"]) == (0.30, 0.20)


def _serie_intermitente(n=84):
    hoy = datetime.date(2026, 9, 11)
    vals = [6, 0, 0, 8, 0, 0, 7] * (n // 7)
    return [(hoy - datetime.timedelta(days=n - 1 - i), float(v)) for i, v in enumerate(vals)]


class TestSeleccion:
    """La competencia se corre con todos tuneados libres. Solo si el titular
    gana, su grilla vuelve a correr con los previos, y lo publicado sale de
    esos parametros."""

    @pytest.fixture
    def espias(self, monkeypatch):
        llamadas = {"tsb": [], "croston": []}

        class EspiaTSB(TSBForecast):
            def backtest(self, daily_series, test_days=7, n_folds=3, **kw):
                llamadas["tsb"].append(dict(kw))
                return super().backtest(daily_series, test_days=test_days, n_folds=n_folds, **kw)

        class EspiaCroston(CrostonForecast):
            def backtest(self, daily_series, test_days=7, n_folds=3, **kw):
                llamadas["croston"].append(dict(kw))
                return super().backtest(daily_series, test_days=test_days, n_folds=n_folds, **kw)

        monkeypatch.setitem(ALGORITHM_REGISTRY, "tsb", EspiaTSB)
        monkeypatch.setitem(ALGORITHM_REGISTRY, "croston", EspiaCroston)
        return llamadas

    def test_la_competencia_es_con_todos_libres(self, espias):
        selection.select_best_model(
            _serie_intermitente(), demand_pattern="intermittent",
            prev_algorithm="tsb", prev_params={"best_alpha": 0.3, "best_beta": 0.2},
        )
        assert "prev_alpha" not in espias["tsb"][0], "la primera corrida del titular es libre"
        assert all("prev_alpha" not in kw for kw in espias["croston"]), "los demas nunca reciben previos"

    def test_si_el_titular_gana_su_grilla_vuelve_a_correr_con_los_previos(self, espias):
        best = selection.select_best_model(
            _serie_plana(), demand_pattern="intermittent",
            prev_algorithm="tsb", prev_params={"best_alpha": 0.3, "best_beta": 0.2},
        )
        assert best["algorithm"] == "tsb"
        assert len(espias["tsb"]) == 2
        assert (espias["tsb"][1]["prev_alpha"], espias["tsb"][1]["prev_beta"]) == (0.3, 0.2)
        # En serie plana la grilla empata, asi que quedan los de anoche: en las
        # metricas publicadas Y en el pronostico.
        assert (best["metrics"]["best_alpha"], best["metrics"]["best_beta"]) == (0.3, 0.2)
        assert (best["params"]["alpha"], best["params"]["beta"]) == (0.3, 0.2)

    def test_si_el_titular_pierde_no_hay_segunda_corrida(self, espias, monkeypatch):
        monkeypatch.setattr(selection, "MARGEN_CAMBIO_ALGORITMO", 1.0)
        best = selection.select_best_model(
            _serie_intermitente(), demand_pattern="intermittent",
            prev_algorithm="croston", prev_params={"best_alpha": 0.3, "best_beta": None},
        )
        if best["algorithm"] != "croston":
            assert len(espias["croston"]) == 1
        else:
            assert len(espias["croston"]) == 2

    def test_sin_titular_nadie_recibe_previos(self, espias):
        selection.select_best_model(_serie_intermitente(), demand_pattern="intermittent")
        assert len(espias["tsb"]) == 1 and len(espias["croston"]) == 1
        assert "prev_alpha" not in espias["tsb"][0]

    def test_previos_vacios_no_hacen_nada(self, espias):
        selection.select_best_model(
            _serie_plana(), demand_pattern="intermittent",
            prev_algorithm="tsb", prev_params={"best_alpha": None, "best_beta": None},
        )
        assert len(espias["tsb"]) == 1


class _Capturado(Exception):
    pass


@pytest.fixture
def espia_selector(monkeypatch):
    recibido = {}

    def falso(*args, **kwargs):
        recibido.update(kwargs)
        raise _Capturado

    monkeypatch.setattr(services, "select_best_model", falso)
    return recibido


def _serie_falsa(patron):
    hoy = datetime.date(2026, 9, 11)
    raw = [(hoy - datetime.timedelta(days=i), 5.0) for i in range(60, 0, -1)]
    return {
        "ds_qs": None, "raw_series": raw, "cleaned": raw, "stockout_dates": set(),
        "promo_dates": set(), "closed_dows": set(), "demand_pattern": patron,
        "adi": 1.0, "cv2": 0.1, "month_factors": None,
    }


def _entrenar(tenant, product, warehouse, monkeypatch, patron):
    monkeypatch.setattr(services, "armar_serie_entrenamiento", lambda *a, **k: _serie_falsa(patron))
    with pytest.raises(_Capturado):
        services.train_product_model(
            tenant, product, warehouse.id, datetime.date(2026, 9, 11),
            14, 7, 21, {}, {"skipped": 0, "kept": 0},
        )


def _titular(tenant, product, warehouse, **cambios):
    datos = dict(
        tenant=tenant, product=product, warehouse_id=warehouse.id, algorithm="tsb",
        version=1, model_params={}, metrics={"wape": 40.0}, trained_at=timezone.now(),
        data_points=60, demand_pattern="intermittent", is_active=True,
    )
    datos.update(cambios)
    return ForecastModel.objects.create(**datos)


@pytest.mark.django_db
class TestEntrenamientoPasaLosParametrosDelTitular:

    def test_le_pasa_los_tuneados_de_metrics(self, tenant, product, warehouse, monkeypatch, espia_selector):
        _titular(tenant, product, warehouse, metrics={"wape": 40.0, "best_alpha": 0.3, "best_beta": 0.2})
        _entrenar(tenant, product, warehouse, monkeypatch, "intermittent")
        assert espia_selector["prev_algorithm"] == "tsb"
        assert espia_selector["prev_params"] == {"best_alpha": 0.3, "best_beta": 0.2}

    def test_modelo_viejo_sin_tuneados_cae_a_model_params(self, tenant, product, warehouse, monkeypatch, espia_selector):
        _titular(tenant, product, warehouse, algorithm="croston_sba", model_params={"alpha": "0.2"})
        _entrenar(tenant, product, warehouse, monkeypatch, "intermittent")
        assert espia_selector["prev_params"] == {"best_alpha": 0.2, "best_beta": None}

    def test_titular_liberado_no_pasa_parametros(self, tenant, product, warehouse, monkeypatch, espia_selector):
        # tsb no es elegible en smooth: el titular se libera y con el sus parametros.
        _titular(tenant, product, warehouse, metrics={"wape": 40.0, "best_alpha": 0.3, "best_beta": 0.2})
        _entrenar(tenant, product, warehouse, monkeypatch, "smooth")
        assert espia_selector["prev_algorithm"] is None
        assert espia_selector["prev_params"] is None

    def test_sin_modelo_activo_no_hay_parametros(self, tenant, product, warehouse, monkeypatch, espia_selector):
        _entrenar(tenant, product, warehouse, monkeypatch, "intermittent")
        assert espia_selector["prev_params"] is None
