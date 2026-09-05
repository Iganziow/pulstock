# -*- coding: utf-8 -*-
"""
tests/test_adaptive_ma_ultima_semana.py — adaptive_ma tiene que enterarse de
lo que paso la ultima semana.

Ejecutado el 02/09/26 sobre el codigo de produccion: 21 dias a 10/dia
seguidos de 7 dias a CERO seguia pronosticando 10,000; 28 dias a 10 seguidos
de 7 dias a 30 seguia pronosticando 10. El grid elegia decay/window contra
la ultima semana, pero el nivel del pronostico final se tomaba del `train`
(serie sin esos 7 dias). Con 74 modelos activos en Marbrava, era el
algoritmo que mas tardaba en reaccionar a que un producto dejara (o
empezara) de venderse.
"""
import datetime
from decimal import Decimal

from forecast.engine.algorithms.adaptive_moving_average import AdaptiveMovingAverage

D = Decimal
INICIO = datetime.date(2026, 6, 1)


def _serie(valores):
    return [(INICIO + datetime.timedelta(days=i), D(str(v)), 1.0) for i, v in enumerate(valores)]


def _nivel(valores):
    r = AdaptiveMovingAverage().forecast(_serie(valores), horizon_days=7)
    return float(r["params"]["avg_daily"])


class TestReaccionaALaUltimaSemana:
    def test_una_semana_en_cero_baja_el_nivel(self):
        """El caso ejecutado en produccion: antes daba 10,000."""
        nivel = _nivel([10] * 21 + [0] * 7)
        assert nivel < 5, (
            "21 dias a 10 y 7 dias a CERO: el nivel sigue en %.3f, el modelo "
            "no vio la ultima semana" % nivel
        )

    def test_una_semana_en_alza_sube_el_nivel(self):
        nivel = _nivel([10] * 28 + [30] * 7)
        assert nivel > 12, (
            "28 dias a 10 y 7 dias a 30: el nivel sigue en %.3f" % nivel
        )

    def test_una_serie_plana_no_se_mueve(self):
        """La otra mitad: recalcular no puede inventar nada."""
        assert abs(_nivel([10] * 35) - 10.0) < 0.001

    def test_los_dias_cerrados_siguen_en_cero(self):
        """Los factores DOW tambien se recalculan: un domingo que nunca vende
        tiene que seguir pronosticando 0 (Mario, domingos cerrados)."""
        vals = []
        for i in range(42):
            d = INICIO + datetime.timedelta(days=i)
            vals.append(0 if d.weekday() == 6 else 10)
        r = AdaptiveMovingAverage().forecast(_serie(vals), horizon_days=14)
        domingos = [f for f in r["forecasts"] if f["date"].weekday() == 6]
        assert domingos and all(float(f["qty_predicted"]) == 0 for f in domingos)
