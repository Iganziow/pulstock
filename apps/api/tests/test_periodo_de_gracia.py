"""
tests/test_periodo_de_gracia.py — un algoritmo nuevo tiene que poder entrar.

El margen anti-parpadeo (`MARGEN_CAMBIO_ALGORITMO = 0.85`) existe para que dos
opciones CONOCIDAS no se turnen noche a noche. Pero a un algoritmo recien
registrado lo deja afuera aunque sea mejor: para que se lo vea una sola vez tiene
que ganarle al titular por 15%, y sin entrar nunca junta evidencia de que merece
entrar. Circulo cerrado.

El caso que lo motivo: `nivel_dia_semana` le ganaba el backtest a seasonal_naive
en 4 de los 5 productos grandes y aun asi, en 3 noches de sombra, solo publicaba
distinto en 3 a 6 productos. A la Leche entera le ganaba por 10% y el margen
pide 15%.

Ese algoritmo despues se descarto (siete noches fieles de sombra, nunca
adelante), asi que la lista quedo VACIA. El mecanismo se queda y se prueba
igual, con un nombre de prueba inyectado: lo que se prueba es la exencion, no
quien la usaba. La ultima prueba cuida que la lista no se llene y se olvide.
"""
import pytest

from forecast.engine import selection
from forecast.engine.selection import MARGEN_CAMBIO_ALGORITMO, choose_best

NUEVO = "algoritmo_de_prueba"


@pytest.fixture
def con_gracia(monkeypatch):
    """Pone a NUEVO en periodo de gracia, sin depender de la lista real."""
    monkeypatch.setattr(selection, "ALGORITMOS_EN_GRACIA", frozenset({NUEVO}))


def _cand(nombre, wape, mase=1.0):
    return {
        "algorithm": nombre,
        "metrics": {"wape": wape, "wape_total": wape, "mase": mase,
                    "bias": 0, "mae": wape, "rmse": wape},
        "forecasts": [{"date": None, "qty_predicted": 10}],
        "params": {}, "data_points": 300,
    }


def test_el_titular_sigue_protegido_contra_los_de_siempre():
    """Control: sin periodo de gracia, una mejora del 10% NO desplaza."""
    titular, retador = _cand("seasonal_naive", 48.0), _cand("theta", 43.2)
    assert 43.2 > 48.0 * MARGEN_CAMBIO_ALGORITMO      # no le saca el margen
    elegido = choose_best([titular, retador], "smooth", prev_algorithm="seasonal_naive")
    assert elegido["algorithm"] == "seasonal_naive"


def test_el_recien_llegado_entra_con_la_misma_mejora(con_gracia):
    """Los numeros reales de la Leche entera: 48,0 contra 43,2."""
    titular = _cand("seasonal_naive", 48.0)
    nuevo = _cand(NUEVO, 43.2)
    elegido = choose_best([titular, nuevo], "smooth", prev_algorithm="seasonal_naive")
    assert elegido["algorithm"] == NUEVO


def test_el_recien_llegado_NO_entra_si_es_peor(con_gracia):
    """La gracia lo exime del margen, no de ganar la seleccion."""
    titular = _cand("seasonal_naive", 40.0)
    nuevo = _cand(NUEVO, 90.0)
    elegido = choose_best([titular, nuevo], "smooth", prev_algorithm="seasonal_naive")
    assert elegido["algorithm"] == "seasonal_naive"


def test_cuando_el_nuevo_ya_es_titular_el_margen_lo_protege_a_el(con_gracia):
    """La exencion no abre una puerta giratoria: una vez adentro, es titular y
    el margen juega a su favor."""
    titular = _cand(NUEVO, 48.0)
    retador = _cand("seasonal_naive", 43.2)
    elegido = choose_best([titular, retador], "smooth", prev_algorithm=NUEVO)
    assert elegido["algorithm"] == NUEVO


def test_sin_nadie_en_gracia_el_margen_vale_para_todos():
    """Con la lista vacia -- el estado normal -- nadie se salta el margen."""
    assert selection.ALGORITMOS_EN_GRACIA == frozenset(), (
        "Si agregaste un algoritmo al periodo de gracia, acordate de sacarlo en "
        "cuanto tenga noches medidas en la sombra: si no, deja de ser un periodo "
        "de gracia y pasa a ser una excepcion permanente escondida."
    )
    titular, retador = _cand("seasonal_naive", 48.0), _cand("theta", 43.2)
    elegido = choose_best([titular, retador], "smooth", prev_algorithm="seasonal_naive")
    assert elegido["algorithm"] == "seasonal_naive"
