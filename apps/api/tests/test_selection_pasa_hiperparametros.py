# -*- coding: utf-8 -*-
"""
tests/test_selection_pasa_hiperparametros.py — lo que el backtest tunea tiene
que llegar al pronostico final.

Encontrado revisando el motor el 02/09/26: select_best_model propagaba
`best_alpha` (Sprint A, jul-2026) pero NO `best_beta`. TSB tunea las dos en
su grid (alpha suaviza el tamano, beta la probabilidad de que un dia tenga
demanda), y beta es justo la que controla que tan rapido se apaga un producto
que dejo de venderse -- el motivo por el que TSB existe. Sin esto, el grid
elegia una beta y el pronostico final usaba siempre la de fabrica (0.10).

Mismo defecto que ya se arreglo para alpha en Croston: "antes se descartaba y
el forecast final usaba siempre el default".
"""
import datetime
from decimal import Decimal

import pytest

from forecast.engine import selection as S
from forecast.engine.algorithms.tsb import TSBForecast

D = Decimal
INICIO = datetime.date(2026, 6, 1)


def _serie(valores):
    return [(INICIO + datetime.timedelta(days=i), D(str(v))) for i, v in enumerate(valores)]


@pytest.fixture
def solo_tsb(monkeypatch):
    """Deja a TSB solo en el registro: asi el ganador es TSB si o si y se
    puede mirar que parametros le llegaron."""
    monkeypatch.setattr(S, "ALGORITHM_REGISTRY", {"tsb": TSBForecast})


class TestLaBetaTuneadaLlegaAlPronostico:
    def test_beta_del_backtest_es_la_beta_del_forecast(self, solo_tsb):
        # Demanda intermitente con racha seca al final: el grid tiene motivo
        # para preferir una beta distinta de la de fabrica.
        serie = _serie([6, 0, 0, 8, 0, 0, 7] * 8 + [0] * 21)

        best = S.select_best_model(serie, horizon=14, test_days=7,
                                   demand_pattern="intermittent")

        assert best["algorithm"] == "tsb"
        tuneada = best["metrics"].get("best_beta")
        assert tuneada is not None, "el backtest de TSB no devolvio best_beta"
        assert best["params"]["beta"] == pytest.approx(tuneada), (
            "el backtest eligio beta=%s pero el pronostico final uso beta=%s: "
            "select_best_model no le pasa best_beta al forecast"
            % (tuneada, best["params"]["beta"])
        )

    def test_alpha_sigue_llegando(self, solo_tsb):
        """La otra mitad no puede romperse al arreglar esta."""
        serie = _serie([6, 0, 0, 8, 0, 0, 7] * 8)
        best = S.select_best_model(serie, horizon=14, test_days=7,
                                   demand_pattern="intermittent")
        assert best["params"]["alpha"] == pytest.approx(best["metrics"]["best_alpha"])


class TestLosDemasNoSeCaen:
    def test_pasar_best_beta_a_un_algoritmo_que_no_la_usa_no_revienta(self):
        """Todos los forecast() aceptan **kwargs; si alguno dejara de hacerlo,
        el selector reventaria con TypeError para TODOS los productos."""
        from forecast.engine import ALGORITHM_REGISTRY
        serie = _serie([5, 6, 4, 7, 5, 6, 5] * 6)
        for name, cls in ALGORITHM_REGISTRY.items():
            if name in ("ensemble", "category_prior"):
                continue  # los maneja services.py aparte, igual que el selector
            algo = cls()
            try:
                algo.forecast(serie, horizon_days=7, best_alpha=0.2, best_beta=0.05,
                              window=21, month_factors=None, stockout_dates=None,
                              demand_pattern="smooth")
            except TypeError as e:
                pytest.fail("%s no acepta los kwargs del selector: %s" % (name, e))
