# -*- coding: utf-8 -*-
"""
tests/test_factores_mes_sin_fuga.py — el backtest del adaptativo no puede ver
el futuro a traves de los factores de mes.

Auditoria del 08/09/26. `armar_serie_entrenamiento` calcula los factores de
posicion del mes (el efecto quincena/fin de mes) sobre la serie COMPLETA, y
`select_best_model` se los pasa a cada algoritmo. `_backtest_adaptive_ma`
parte la serie en pliegues de entrenamiento y prueba, pero usaba esos factores
tal cual: calculados tambien con los dias que estaba por evaluar.

Medido en Marbrava sobre los 99 productos que alcanzan a tener factores (los
otros 74 no llegan a 45 dias de serie): los factores calculados solo con el
entrenamiento difieren de los globales en 0,029 de mediana, y la nota del
adaptativo empeora 0,3 puntos de mediana y 1,7 de media al quitarle la fuga.
O sea que se estaba puntuando mejor de lo que le corresponde, y es el
algoritmo mas usado (68 de 188 modelos activos). Ningun producto cambia de
ganador con el arreglo: corrige la vara sin mover ninguna decision.

El pronostico que se publica sigue usando los factores de la serie completa,
que ahi es lo correcto: no existe un "despues" del ultimo dia.
"""
import datetime
import random
from decimal import Decimal

from forecast.engine.algorithms.adaptive_moving_average import (
    _adaptive_moving_average, _backtest_adaptive_ma,
)

HOY = datetime.date.today()


def _serie(dias=120, semilla=3, salto_fin_de_mes=6):
    """Serie con efecto de fin de mes: los dias 26+ venden bastante mas."""
    rnd = random.Random(semilla)
    filas = []
    for i in range(dias):
        d = HOY - datetime.timedelta(days=dias - i)
        base = 8 + 4 * rnd.random()
        if d.day >= 26:
            base += salto_fin_de_mes
        filas.append((d, Decimal(str(round(base, 2)))))
    return filas


FACTORES_ABSURDOS = {"early": 0.1, "mid_early": 0.1, "mid": 0.1,
                     "mid_late": 0.1, "late": 5.0}


class TestElBacktestNoUsaLosFactoresDeAfuera:
    def test_da_lo_mismo_reciba_o_no_factores(self):
        """La prueba directa de que no hay fuga: unos factores inventados,
        calculados 'con toda la serie', no pueden mover la nota."""
        serie = _serie()
        sin = _backtest_adaptive_ma(serie, month_factors=None)
        con = _backtest_adaptive_ma(serie, month_factors=FACTORES_ABSURDOS)
        assert sin == con, (
            "el backtest todavia usa los factores que le pasan: %s vs %s"
            % (sin.get("wape"), con.get("wape"))
        )

    def test_igual_con_estacionalidad_aditiva(self):
        serie = _serie()
        sin = _backtest_adaptive_ma(serie, month_factors=None, use_additive=True)
        con = _backtest_adaptive_ma(serie, month_factors=FACTORES_ABSURDOS, use_additive=True)
        assert sin == con

    def test_serie_corta_corre_sin_factores_y_no_explota(self):
        """Con menos de 45 dias, compute_month_position_factors devuelve None:
        el pliegue corre sin factores, que es lo honesto."""
        met = _backtest_adaptive_ma(_serie(dias=40), month_factors=FACTORES_ABSURDOS)
        assert "wape" in met

    def test_serie_demasiado_corta_devuelve_centinela(self):
        met = _backtest_adaptive_ma(_serie(dias=20))
        assert met["mae"] == 999


class TestElPronosticoSiLosUsa:
    def test_el_forecast_publicado_respeta_los_factores(self):
        """Lo que NO se toco: el pronostico que se publica usa los factores de
        la serie completa. Ahi no hay futuro que filtrar."""
        serie = _serie()
        sin = _adaptive_moving_average(serie, horizon_days=14, month_factors=None)
        con = _adaptive_moving_average(serie, horizon_days=14, month_factors=FACTORES_ABSURDOS)
        assert sin and con
        a = [float(f["qty_predicted"]) for f in sin["forecasts"]]
        b = [float(f["qty_predicted"]) for f in con["forecasts"]]
        assert a != b, "el pronostico deberia seguir usando los factores que recibe"
