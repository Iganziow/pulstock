"""
tests/test_periodo_de_gracia.py — un algoritmo nuevo tiene que poder entrar.

El margen anti-parpadeo (`MARGEN_CAMBIO_ALGORITMO = 0.85`) existe para que dos
opciones CONOCIDAS no se turnen noche a noche. Pero a un algoritmo recien
registrado lo deja afuera aunque sea mejor: para que se lo vea una sola vez tiene
que ganarle al titular por 15%, y sin entrar nunca junta evidencia de que merece
entrar. Circulo cerrado.

Medido: `nivel_dia_semana` le gana el backtest a seasonal_naive en 4 de los 5
productos grandes y aun asi, en 3 noches de sombra, solo publicaba distinto en 3
a 6 productos. A la Leche entera le gana por 10% y el margen pide 15%.

La exencion es acotada y temporal: solo los nombres de `ALGORITMOS_EN_GRACIA`,
que se vacia en cuanto el algoritmo tenga noches medidas.
"""
from forecast.engine.selection import (
    ALGORITMOS_EN_GRACIA, MARGEN_CAMBIO_ALGORITMO, choose_best,
)


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


def test_el_recien_llegado_entra_con_la_misma_mejora():
    """Los numeros reales de la Leche entera: 48,0 contra 43,2."""
    titular = _cand("seasonal_naive", 48.0)
    nuevo = _cand("nivel_dia_semana", 43.2)
    elegido = choose_best([titular, nuevo], "smooth", prev_algorithm="seasonal_naive")
    assert elegido["algorithm"] == "nivel_dia_semana"


def test_el_recien_llegado_NO_entra_si_es_peor():
    """La gracia lo exime del margen, no de ganar la seleccion."""
    titular = _cand("seasonal_naive", 40.0)
    nuevo = _cand("nivel_dia_semana", 90.0)
    elegido = choose_best([titular, nuevo], "smooth", prev_algorithm="seasonal_naive")
    assert elegido["algorithm"] == "seasonal_naive"


def test_cuando_el_nuevo_ya_es_titular_el_margen_lo_protege_a_el():
    """La exencion no abre una puerta giratoria: una vez adentro, es titular y
    el margen juega a su favor."""
    titular = _cand("nivel_dia_semana", 48.0)
    retador = _cand("seasonal_naive", 43.2)
    elegido = choose_best([titular, retador], "smooth", prev_algorithm="nivel_dia_semana")
    assert elegido["algorithm"] == "nivel_dia_semana"


def test_la_lista_de_gracia_es_chica_y_explicita():
    """Si esto crece, dejo de ser un periodo de gracia."""
    assert ALGORITMOS_EN_GRACIA == frozenset({"nivel_dia_semana"})
