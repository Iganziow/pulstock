"""
tests/test_dia_dominante.py — un solo día no puede fijar el nivel.

Caso real de Marbrava. La `empanada camarón queso` tenía una sola fila de venta:

    2026-09-04   vendido 3   merma 494   →  demanda efectiva 497
    2026-09-15   vendido 0   merma 0     →  0

Los 494 fueron una corrección de inventario cargada como merma. `simple_avg`
promedió la serie entera y publicó 49,7 · 45,2 · 41,4 al día según cuántos ceros
hubiera detrás; la sugerencia de compra pedía 28 empanadas.

`clean_series` no podía ayudar: su recorte por percentiles pide al menos 4 días
con venta y acá había uno.
"""
import datetime
from decimal import Decimal

from forecast.engine.algorithms.simple_average import (
    SimpleAverage, recortar_dia_dominante,
)

D = Decimal
LUNES = datetime.date(2026, 6, 1)


def _serie(valores):
    return [(LUNES + datetime.timedelta(days=i), D(str(v)))
            for i, v in enumerate(valores)]


# ── la regla ─────────────────────────────────────────────────────────────────

def test_el_dia_que_pesa_mas_que_todo_el_resto_se_recorta():
    valores, recorte = recortar_dia_dominante([497.0] + [0.0] * 9)
    assert recorte == (497.0, 0.0)
    assert valores == [0.0] * 10


def test_una_serie_normal_no_se_toca():
    """Si ningún día domina, el promedio queda exactamente igual que antes."""
    original = [10.0, 12.0, 9.0, 11.0, 13.0, 8.0, 10.0]
    valores, recorte = recortar_dia_dominante(original)
    assert recorte is None
    assert valores == original


def test_un_pico_grande_pero_no_dominante_sobrevive():
    """40 contra 60 del resto: es un pico, no un evento. No se recorta."""
    valores, recorte = recortar_dia_dominante([40.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
    assert recorte is None
    assert max(valores) == 40.0


def test_el_recorte_deja_el_segundo_dia_mas_alto():
    """No se borra el día: se baja al nivel del más alto que queda."""
    valores, recorte = recortar_dia_dominante([500.0, 7.0, 0.0, 0.0, 0.0])
    assert recorte == (500.0, 7.0)
    assert valores == [7.0, 7.0, 0.0, 0.0, 0.0]


def test_serie_de_un_punto_o_vacia_no_explota():
    assert recortar_dia_dominante([5.0]) == ([5.0], None)
    assert recortar_dia_dominante([]) == ([], None)


def test_todo_ceros_no_explota():
    valores, recorte = recortar_dia_dominante([0.0] * 8)
    assert recorte is None
    assert valores == [0.0] * 8


# ── el algoritmo ─────────────────────────────────────────────────────────────

def test_la_empanada_ya_no_pide_28():
    """El caso que originó esto: 497 y nueve ceros."""
    salida = SimpleAverage().forecast(_serie([497] + [0] * 9), horizon_days=7)
    assert float(salida["params"]["avg_daily"]) == 0.0
    assert all(float(f["qty_predicted"]) == 0.0 for f in salida["forecasts"])
    assert salida["params"]["dia_dominante_recortado"] == "497.0 -> 0.0"


def test_sin_el_recorte_la_empanada_pedia_casi_50_al_dia():
    """La otra mitad: que el problema existía de verdad."""
    serie = _serie([497] + [0] * 9)
    promedio_pelado = sum(float(q) for _, q in serie) / len(serie)
    assert round(promedio_pelado, 1) == 49.7


def test_una_serie_sana_predice_su_promedio_de_siempre():
    """Control: el algoritmo sigue haciendo lo que hacía donde no hay atípicos."""
    salida = SimpleAverage().forecast(_serie([10, 12, 9, 11, 13, 8, 10]), horizon_days=3)
    assert float(salida["params"]["avg_daily"]) == round(73 / 7, 3)
    assert "dia_dominante_recortado" not in salida["params"]


def test_el_recorte_queda_anotado_para_auditar():
    salida = SimpleAverage().forecast(_serie([500, 7, 0, 0, 0, 0, 0]), horizon_days=2)
    assert salida["params"]["dia_dominante_recortado"] == "500.0 -> 7.0"


def test_sigue_siendo_el_unico_elegible_entre_7_y_13_dias():
    """No le cambiamos la ventana: es el algoritmo de última instancia."""
    algo = SimpleAverage()
    assert algo.is_eligible(7, "smooth")
    assert algo.is_eligible(13, "intermittent")
    assert not algo.is_eligible(6, "smooth")
    assert not algo.is_eligible(14, "smooth")
