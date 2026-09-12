# -*- coding: utf-8 -*-
"""
tests/test_histeresis_algoritmo.py — el algoritmo de anoche defiende el puesto.

Medido en produccion el 12/09/26 (15 noches, cola): la noche que cambia el
algoritmo, el nivel publicado salta 89% ponderado, contra 12% cuando no cambia
nada. Y la regla del kept-path dejaba entrar a un candidato hasta 10% PEOR que
el titular. Ahora el titular compite esta misma noche con el mismo backtest que
los demas, y solo se lo reemplaza si el ganador le saca MARGEN_CAMBIO_ALGORITMO.
"""
import datetime

import pytest
from django.utils import timezone

from forecast import services
from forecast.engine.selection import MARGEN_CAMBIO_ALGORITMO, choose_best
from forecast.models import ForecastModel


def _cand(alg, wape, wape_total=None, fc_total=10.0):
    return {
        "algorithm": alg,
        "forecasts": [{"qty_predicted": fc_total / 7} for _ in range(7)],
        "metrics": {
            "wape": wape, "wape_total": wape if wape_total is None else wape_total,
            "mase": 0.9, "mae": 1.0, "tracking_signal": 0,
        },
    }


class TestChooseBestConTitular:

    def test_sin_titular_elige_igual_que_antes(self):
        c = [_cand("theta", 40), _cand("ets", 38)]
        assert choose_best(c, "smooth")["algorithm"] == "ets"

    def test_smooth_conserva_al_titular_si_el_ganador_no_saca_margen(self):
        c = [_cand("theta", 40), _cand("ets", 38)]
        assert choose_best(c, "smooth", prev_algorithm="theta")["algorithm"] == "theta"

    def test_smooth_un_ganador_con_margen_claro_reemplaza(self):
        c = [_cand("theta", 40), _cand("ets", 40 * MARGEN_CAMBIO_ALGORITMO - 1)]
        assert choose_best(c, "smooth", prev_algorithm="theta")["algorithm"] == "ets"

    def test_ganar_justo_por_el_margen_no_alcanza(self):
        c = [_cand("theta", 40), _cand("ets", 40 * MARGEN_CAMBIO_ALGORITMO)]
        assert choose_best(c, "smooth", prev_algorithm="theta")["algorithm"] == "theta"

    def test_intermitente_la_vara_es_wape_total(self):
        # adaptive_ma gana por wape_total (47 contra 50) pero no por 15%.
        c = [_cand("theta", 60, wape_total=50), _cand("adaptive_ma", 58, wape_total=47)]
        assert choose_best(c, "intermittent")["algorithm"] == "adaptive_ma"
        assert choose_best(c, "intermittent", prev_algorithm="theta")["algorithm"] == "theta"

    def test_titular_colapsado_no_se_protege(self):
        # theta tiene mejor metrica pero su forecast suma 0: el filtro anti-colapso manda.
        c = [_cand("theta", 30, wape_total=20, fc_total=0.0), _cand("adaptive_ma", 58, wape_total=47)]
        assert choose_best(c, "intermittent", prev_algorithm="theta")["algorithm"] == "adaptive_ma"

    def test_titular_sin_metrica_evaluable_no_se_protege(self):
        c = [_cand("theta", 999), _cand("ets", 80)]
        assert choose_best(c, "smooth", prev_algorithm="theta")["algorithm"] == "ets"

    def test_titular_que_ya_no_compite_no_bloquea(self):
        c = [_cand("theta", 40), _cand("ets", 38)]
        assert choose_best(c, "smooth", prev_algorithm="croston")["algorithm"] == "ets"


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
        tenant=tenant, product=product, warehouse_id=warehouse.id, algorithm="theta",
        version=1, model_params={}, metrics={"wape": 40.0}, trained_at=timezone.now(),
        data_points=60, demand_pattern="smooth", is_active=True,
    )
    datos.update(cambios)
    return ForecastModel.objects.create(**datos)


@pytest.mark.django_db
class TestEntrenamientoPasaElTitular:

    def test_le_pasa_al_selector_el_algoritmo_de_anoche(self, tenant, product, warehouse, monkeypatch, espia_selector):
        _titular(tenant, product, warehouse)
        _entrenar(tenant, product, warehouse, monkeypatch, "smooth")
        assert espia_selector["prev_algorithm"] == "theta"

    def test_sin_modelo_activo_no_hay_titular(self, tenant, product, warehouse, monkeypatch, espia_selector):
        _entrenar(tenant, product, warehouse, monkeypatch, "smooth")
        assert espia_selector["prev_algorithm"] is None

    def test_cambio_de_patron_libera_al_titular(self, tenant, product, warehouse, monkeypatch, espia_selector):
        _titular(tenant, product, warehouse, algorithm="adaptive_ma")
        _entrenar(tenant, product, warehouse, monkeypatch, "intermittent")
        assert espia_selector["prev_algorithm"] is None

    def test_algoritmo_ya_no_elegible_libera_al_titular(self, tenant, product, warehouse, monkeypatch, espia_selector):
        # Croston no es elegible en smooth.
        _titular(tenant, product, warehouse, algorithm="croston_sba")
        _entrenar(tenant, product, warehouse, monkeypatch, "smooth")
        assert espia_selector["prev_algorithm"] is None

    def test_racha_de_cortacircuitos_libera_al_titular(self, tenant, product, warehouse, monkeypatch, espia_selector):
        _titular(tenant, product, warehouse,
                 model_params={"circuit_breaker_streak": services.BREAKER_STREAK_FORCE_RETRAIN})
        _entrenar(tenant, product, warehouse, monkeypatch, "smooth")
        assert espia_selector["prev_algorithm"] is None
