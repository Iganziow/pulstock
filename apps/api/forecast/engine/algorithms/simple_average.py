"""
simple_avg — el promedio pelado, para cuando no hay con qué hacer otra cosa.

Es el único algoritmo elegible entre 7 y 13 días de historia: el resto pide 14 o
más, y `category_prior` entra por otra vía. O sea que acá no gana una competencia,
compite solo. Por eso tiene que cuidarse a sí mismo.

El día dominante (20/09/26)
---------------------------
Caso real de Marbrava. La `empanada camarón queso` tenía una sola fila de venta en
toda su historia:

    2026-09-04   vendido 3   merma 494   →  demanda efectiva 497
    2026-09-15   vendido 0   merma 0     →  0

Los 494 fueron una corrección de inventario cargada como merma, no demanda. Pero
en un restaurante la merma cuenta como demanda, así que la serie entró con un 497
y nueve ceros. El promedio pelado daba 49,7 · 45,2 · 41,4 al día según cuántos
ceros hubiera detrás, y la sugerencia de compra pedía **28 empanadas**.

El amortiguador de atípicos que ya existe (`clean_series`, recorte por percentiles)
no podía hacer nada: pide al menos 4 días con venta para estimar el límite, y acá
había uno. Justo en la ventana donde trabaja este algoritmo, la protección general
no alcanza.

La regla: **un solo día no puede pesar más que todos los demás juntos**. Si pesa
más, se recorta al nivel del día más alto que queda. Para la empanada eso deja el
pronóstico en cero, que es la lectura honesta de "un evento y nada más": el
producto vendió 3 unidades una vez en un mes. Cero es mejor respuesta que 28.

El recorte queda anotado en `params` para que se pueda auditar, en vez de pasar
callado.
"""
from datetime import timedelta
from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import _q3, D0


def recortar_dia_dominante(valores):
    """Recorta el día que pesa más que todos los demás juntos.

    Devuelve `(valores, recorte)`. `recorte` es None si no hubo nada que hacer,
    o `(antes, despues)` con el valor original y el recortado.

    Se compara contra la SUMA del resto, no contra el promedio ni la mediana: es
    la prueba que menos supuestos hace sobre la forma de la serie, y con nueve
    ceros detrás es la única que distingue "un evento" de "un nivel".
    """
    if len(valores) < 2:
        return valores, None
    ordenados = sorted(valores)
    mayor, resto = ordenados[-1], ordenados[:-1]
    if mayor <= 0 or mayor <= sum(resto):
        return valores, None
    tope = max(resto)
    return [min(v, tope) for v in valores], (mayor, tope)


@register
class SimpleAverage(ForecastAlgorithm):
    name = "simple_avg"
    min_data_points = 7
    demand_patterns = None  # all

    def forecast(self, daily_series, horizon_days=14, **kwargs):
        if not daily_series:
            return None
        valores, recorte = recortar_dia_dominante(
            [float(item[1]) for item in daily_series]
        )
        avg = sum(valores) / len(valores)
        avg_daily = _q3(avg)
        last_date = daily_series[-1][0]
        forecasts = []
        for i in range(1, horizon_days + 1):
            fc_date = last_date + timedelta(days=i)
            margin = _q3(avg_daily * Decimal("0.50"))
            forecasts.append({
                "date": fc_date,
                "qty_predicted": avg_daily,
                "lower_bound": max(D0, _q3(avg_daily - margin)),
                "upper_bound": _q3(avg_daily + margin),
            })
        params = {"avg_daily": str(avg_daily)}
        if recorte:
            params["dia_dominante_recortado"] = "%s -> %s" % (
                round(recorte[0], 3), round(recorte[1], 3),
            )
        return {
            "algorithm": "simple_avg",
            "forecasts": forecasts,
            "params": params,
            "metrics": {"mae": 0, "mape": 0, "rmse": 0, "bias": 0},
            "data_points": len(daily_series),
            "confidence_base": Decimal("45.00"),
        }

    def backtest(self, daily_series, test_days=7, n_folds=3, **kwargs):
        return {"mae": 0, "mape": 0, "rmse": 0, "bias": 0}

    def is_eligible(self, n_points, demand_pattern):
        return 7 <= n_points < 14
