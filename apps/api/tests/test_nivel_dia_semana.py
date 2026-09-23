"""
tests/test_nivel_dia_semana.py — el nivel de esta semana, la forma de todas.

`seasonal_naive` copia lo que se vendio el mismo dia de la semana la vez
anterior, asi que mezcla NIVEL y FORMA en un numero de hace una semana: es, por
construccion, un predictor atrasado. Medido en produccion (30-jun a 13-sep): la
correlacion del nivel publicado con el real es +0,07 en fase y +0,83 corrido 11
dias en Leche entera, +0,05 y +0,81 corrido 6 en Cafe tolva caturra.

Este algoritmo separa las dos cosas: nivel de los ultimos 14 dias con registro,
por el factor del dia de la semana sacado de toda la historia previa.

Medido con validacion caminando hacia adelante sobre 23 productos de produccion:

    segmento    seasonal_naive   con deriva   nivel x dia   solo nivel
    nucleo            56%            60%          43%          43%
    cola              76%            86%          56%          58%
"""
import datetime
from decimal import Decimal

from forecast.engine.algorithms.nivel_dia_semana import (
    FACTOR_MAX, FACTOR_MIN, MIN_HISTORIA_FACTOR, NivelDiaSemana,
    factor_dia, nivel_reciente,
)
from forecast.engine.algorithms.seasonal_naive import SeasonalNaive

LUNES = datetime.date(2026, 6, 1)  # 2026-06-01 es lunes


def _serie(valores, desde=LUNES):
    return [(desde + datetime.timedelta(days=i), Decimal(str(v)))
            for i, v in enumerate(valores)]


def _pares(serie):
    return [(d, float(q)) for d, q in serie]


# ── las piezas ───────────────────────────────────────────────────────────────

def test_el_nivel_usa_solo_los_dias_con_registro():
    """Un domingo cerrado no tiene que bajarle el nivel a los dias que se opera."""
    s = _pares(_serie([10] * 20))
    corte = s[-1][0] + datetime.timedelta(days=1)
    assert nivel_reciente(s, corte) == 10.0


def test_el_nivel_sigue_al_negocio_y_no_a_la_semana_pasada():
    """20 dias en 10 y despues 14 en 30: el nivel tiene que ser 30, no 10."""
    s = _pares(_serie([10] * 20 + [30] * 14))
    corte = s[-1][0] + datetime.timedelta(days=1)
    assert nivel_reciente(s, corte) == 30.0


def test_sin_historia_suficiente_no_hay_factor_de_dia():
    s = _pares(_serie([10] * (MIN_HISTORIA_FACTOR - 1)))
    corte = s[-1][0] + datetime.timedelta(days=1)
    assert factor_dia(s, 0, corte) is None


def test_el_factor_reconoce_el_dia_fuerte():
    """Lunes al doble que el resto: su factor tiene que pasar de 1."""
    valores = [20 if (LUNES + datetime.timedelta(days=i)).weekday() == 0 else 10
               for i in range(90)]
    s = _pares(_serie(valores))
    corte = s[-1][0] + datetime.timedelta(days=1)
    assert factor_dia(s, 0, corte) > 1.2
    assert factor_dia(s, 2, corte) < 1.0


def test_el_factor_esta_acotado():
    """Un dia con un pico historico absurdo no puede deformar el nivel."""
    valores = [5000 if (LUNES + datetime.timedelta(days=i)).weekday() == 0 else 1
               for i in range(90)]
    s = _pares(_serie(valores))
    corte = s[-1][0] + datetime.timedelta(days=1)
    assert factor_dia(s, 0, corte) <= FACTOR_MAX
    assert factor_dia(s, 2, corte) >= FACTOR_MIN


# ── el algoritmo ─────────────────────────────────────────────────────────────

def test_el_pronostico_refleja_el_nivel_RECIENTE():
    """La propiedad que lo distingue: lo que publica sale de los ultimos 14 dias
    con registro, no de un dato de hace una semana.

    Se verifica como propiedad y no comparando contra seasonal_naive en una
    serie inventada: con datos sinteticos esa comparacion no es justa (si el
    nivel nuevo lleva 7 dias o mas, el que copia la semana pasada ya lo
    alcanzo). La evidencia de que este anda mejor esta medida sobre produccion,
    en el docstring del modulo.
    """
    serie = _serie([10] * 40 + [30] * 5)
    salida = NivelDiaSemana().forecast(serie, horizon_days=7)
    p = [float(f["qty_predicted"]) for f in salida["forecasts"]]
    esperado = (9 * 10 + 5 * 30) / 14          # los 14 dias con registro previos
    assert all(abs(x - esperado) < 2 for x in p), p


def test_seasonal_naive_publica_un_dato_de_hace_una_semana():
    """El contraste, dicho como lo que es: `seasonal_naive` copia el mismo dia
    de la semana anterior. No es un defecto de implementacion, es su regla."""
    serie = _serie([10] * 40 + [30] * 5)
    salida = SeasonalNaive().forecast(serie, horizon_days=2)
    p = [float(f["qty_predicted"]) for f in salida["forecasts"]]
    assert p == [10.0, 10.0], (
        "los dos primeros dias del horizonte copian dias que todavia valian 10: %s" % p
    )


def test_serie_corta_no_pronostica():
    assert NivelDiaSemana().forecast(_serie([5] * 10), horizon_days=7) is None


def test_sin_historia_publica_el_nivel_plano():
    """Sin factor confiable, todos los dias salen iguales: el nivel pelado."""
    salida = NivelDiaSemana().forecast(_serie([10] * 30), horizon_days=7)
    valores = {float(f["qty_predicted"]) for f in salida["forecasts"]}
    assert valores == {10.0}


def test_publica_el_horizonte_completo_y_con_banda():
    salida = NivelDiaSemana().forecast(_serie([10, 12, 8, 11, 9] * 18), horizon_days=10)
    assert len(salida["forecasts"]) == 10
    for f in salida["forecasts"]:
        assert f["lower_bound"] <= f["qty_predicted"] <= f["upper_bound"]
        assert f["lower_bound"] >= 0


def test_el_backtest_avisa_cuando_no_alcanzan_los_datos():
    m = NivelDiaSemana().backtest(_serie([10] * 15), test_days=7)
    assert m["mae"] >= 999


def test_el_backtest_de_una_serie_sana_da_un_error_creible():
    m = NivelDiaSemana().backtest(_serie([10, 12, 8, 11, 9, 10, 0] * 12), test_days=7)
    assert 0 <= m["mae"] < 999


def test_compite_en_todos_los_patrones():
    algo = NivelDiaSemana()
    assert algo.is_eligible(30, "smooth")
    assert algo.is_eligible(30, "intermittent")
    assert not algo.is_eligible(13, "smooth")
