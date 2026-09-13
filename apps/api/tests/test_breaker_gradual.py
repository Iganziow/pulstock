# -*- coding: utf-8 -*-
"""
tests/test_breaker_gradual.py — cruzar el piso del cortacircuitos ya no mueve el pronostico.

Medido en produccion el 13/09/26: Chocolate Premium subio 47% en la semana con
los parametros identicos a los de la noche anterior. Su pronostico quedo en 49%
de la demanda reciente contra un piso de 50%, y el cortacircuitos paso de no
tocar nada a mezclar 70% de promedio reciente. Ahora, por debajo del piso, el
peso del rescate crece con la distancia a la banda: justo afuera es casi cero.

El techo sigue siendo un borde a proposito: simulado sobre la copia de
produccion, la rampa por arriba empeoraba el WAPE total entre 7 y 10 puntos, y
todo era de cuatro helados de temporada pronosticados en 300% de la demanda.
"""
from datetime import date, timedelta

import pytest

from forecast import services
from forecast.services import BREAKER_BANDA, _collapse_guard, _peso_rescate

LO, HI = BREAKER_BANDA


class TestPesoRescate:

    def test_dentro_de_la_banda_no_pesa(self):
        for r in (LO, 0.8, 1.0, 2.0, HI):
            assert _peso_rescate(r) == 0.0

    def test_colapso_total_pesa_el_maximo(self):
        assert _peso_rescate(0.0) == services.BREAKER_PESO_WMA

    def test_justo_debajo_del_piso_casi_no_pesa(self):
        assert 0 < _peso_rescate(LO * 0.98) < 0.05

    def test_por_debajo_del_piso_crece_con_la_distancia(self):
        pesos = [_peso_rescate(r) for r in (0.49, 0.45, 0.4, 0.3, 0.2, 0.1)]
        assert pesos == sorted(pesos)

    def test_llega_al_maximo_a_una_rampa_de_distancia(self):
        rampa = services.BREAKER_RAMPA_PISO
        assert _peso_rescate(LO / rampa) == pytest.approx(services.BREAKER_PESO_WMA)
        assert _peso_rescate(LO / rampa / 3) == services.BREAKER_PESO_WMA, "no pasa del maximo"

    def test_el_techo_sigue_siendo_un_borde(self):
        """Los helados de temporada: el rescate fuerte por arriba los mantiene razonables."""
        assert _peso_rescate(HI * 1.01) == services.BREAKER_PESO_WMA
        assert _peso_rescate(HI * 3) == services.BREAKER_PESO_WMA

    def test_rampa_1_en_el_piso_es_el_borde_de_antes(self, monkeypatch):
        monkeypatch.setattr(services, "BREAKER_RAMPA_PISO", 1.0)
        assert _peso_rescate(LO * 0.99) == services.BREAKER_PESO_WMA
        assert _peso_rescate(1.0) == 0.0

    def test_con_rampa_en_el_techo_tambien_es_gradual(self, monkeypatch):
        monkeypatch.setattr(services, "BREAKER_RAMPA_TECHO", 2.0)
        assert 0 < _peso_rescate(HI * 1.02) < 0.05
        assert _peso_rescate(HI * 2.0) == pytest.approx(services.BREAKER_PESO_WMA)


HOY = date(2026, 7, 1)
HORIZONTE = 14
DEMANDA = 10.0


def _raw():
    return [(HOY - timedelta(days=30 - i), DEMANDA) for i in range(30)]


def _demanda_reciente():
    """Con la misma regla del cortacircuitos: los dias posteriores a
    hoy - min(horizonte, 21)."""
    corte = HOY - timedelta(days=min(HORIZONTE, 21))
    return sum(q for d, q in _raw() if d > corte)


def _qty_para(ratio):
    """Pronostico diario plano cuyo total del horizonte da `ratio` de la demanda reciente."""
    return ratio * _demanda_reciente() / HORIZONTE


def _guard(ratio):
    qty = _qty_para(ratio)
    best = {"forecasts": [{"date": HOY + timedelta(days=i + 1), "qty_predicted": qty,
                           "lower_bound": qty, "upper_bound": qty} for i in range(HORIZONTE)],
            "params": {}, "algorithm": "theta"}
    out = _collapse_guard(best, _raw(), HOY, HORIZONTE)
    return out, qty, float(out["forecasts"][0]["qty_predicted"])


class TestBlendContinuo:

    def test_cruzar_el_piso_no_hace_saltar_el_pronostico(self):
        adentro, _, q_in = _guard(LO * 1.01)
        afuera, _, q_out = _guard(LO * 0.99)
        assert "circuit_breaker" not in adentro["params"]
        assert afuera["params"].get("circuit_breaker"), "sale de la banda: la racha tiene que contar"
        assert abs(q_out - q_in) / q_in < 0.05, (
            "un 2%% de cambio en el modelo no puede mover lo publicado mas de 5%% (%.3f -> %.3f)" % (q_in, q_out))

    def test_con_rampa_1_el_piso_si_salta(self, monkeypatch):
        """El control: con el borde de antes, el mismo cruce movia el pronostico mas de 50%."""
        monkeypatch.setattr(services, "BREAKER_RAMPA_PISO", 1.0)
        _, _, q_in = _guard(LO * 1.01)
        _, _, q_out = _guard(LO * 0.99)
        assert (q_out - q_in) / q_in > 0.5

    def test_por_encima_del_techo_rescata_fuerte(self):
        adentro, _, _ = _guard(HI * 0.99)
        afuera, qty, q = _guard(HI * 1.01)
        assert "circuit_breaker" not in adentro["params"]
        cb = afuera["params"]["circuit_breaker"]
        assert cb["reason"] == "overshoot_vs_recent_demand"
        assert cb["peso_wma"] == services.BREAKER_PESO_WMA
        assert q == pytest.approx(services.BREAKER_PESO_WMA * DEMANDA + (1 - services.BREAKER_PESO_WMA) * qty, abs=0.01)

    def test_registra_el_peso_aplicado_y_mezcla_con_ese_peso(self):
        out, qty, q = _guard(0.3)
        cb = out["params"]["circuit_breaker"]
        assert cb["reason"] == "collapsed_vs_recent_demand"
        peso = _peso_rescate(0.3)
        assert cb["peso_wma"] == round(peso, 2)
        assert q == pytest.approx(peso * DEMANDA + (1 - peso) * qty, abs=0.01)

    def test_colapso_total_sigue_rescatando_fuerte(self):
        out, _, q = _guard(0.0)
        assert out["params"]["circuit_breaker"]["peso_wma"] == services.BREAKER_PESO_WMA
        assert q == pytest.approx(services.BREAKER_PESO_WMA * DEMANDA, abs=0.01)
