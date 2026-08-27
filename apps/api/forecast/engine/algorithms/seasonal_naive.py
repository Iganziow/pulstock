"""
seasonal_naive — el piso contra el que todo modelo tiene que justificarse.

Predice, para cada día futuro, lo que se vendió **el mismo día de la semana**
la última vez. Sin parámetros, sin ajuste, sin nada que tunear. Un martes se
parece a un martes.

Por qué existe
--------------
Medido contra producción el 27-ago-2026, sobre 4.179 comparaciones reales de
los últimos 30 días, comparando el error de cada modelo activo contra el de
esta regla:

    algoritmo            modelo    esta regla
    ingredient_derived      40%           44%   gana el modelo
    adaptive_ma             82%          137%   gana el modelo
    theta                  107%          130%   gana el modelo
    croston_sba            269%          162%   GANA LA REGLA
    croston                449%          213%   GANA LA REGLA
    ets                   2147%         2000%   GANA LA REGLA

45 productos estaban usando algoritmos que pierden contra no hacer nada. Y no
perdían de manera inocente: sobre-predecían (croston +193%, croston_sba
+125%), o sea que le sugerían a Mario comprar el triple de lo que necesitaba.
En plata es poco —son productos de bajo volumen— pero es lo que aparece en la
lista de compra cada semana y hace que el dueño le deje de creer al sistema.

Por qué acá y no como parche
----------------------------
La tentación era escribir una guarda que revisara la precisión medida y
forzara un reemplazo. Eso habría sido lógica nueva encima de la selección, con
su propio criterio y sus propios bugs.

Pero la selección YA elige el candidato de mejor WAPE con validación
walk-forward. El problema nunca fue la selección: era que esta regla jamás
compitió. Registrándola como un candidato más, gana **solo cuando gana de
verdad**, medida con la misma vara que el resto, y heredando los márgenes
anti-flicker que ya existen. Cero lógica nueva.

Es el `sNaive` de las competencias M4/M5, donde se usa exactamente para esto:
como referencia mínima que un modelo debe superar para justificar su
existencia.
"""
from datetime import timedelta
from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import _q3, D0, _compute_metrics, _average_metrics


def _ultimo_mismo_dia(serie_por_fecha, fecha, hasta):
    """Lo vendido el mismo día de la semana más reciente antes de `hasta`.

    Retrocede semana a semana hasta encontrar un día con registro. Si el
    producto no tiene ningún dato para ese día de la semana, devuelve None y
    quien llama decide (usamos la mediana de la serie como último recurso).
    """
    d = fecha - timedelta(days=7)
    while d >= hasta:
        if d in serie_por_fecha:
            return serie_por_fecha[d]
        d -= timedelta(days=7)
    return None


def _predecir(serie, futuras):
    """Predice una lista de fechas futuras con la regla del mismo día."""
    # Los puntos son (fecha, cantidad, peso): el resto del motor los indexa
    # en vez de desempaquetarlos, y hay que hacer lo mismo. Desempaquetar
    # de a dos revienta con las series reales, que traen el peso de
    # `clean_series` como tercer campo.
    por_fecha = {it[0]: float(it[1]) for it in serie}
    if not por_fecha:
        return []
    primera = serie[0][0]
    # Último recurso cuando no hay historia de ese día de la semana: la
    # mediana de la serie. Mediana y no promedio — un solo día excepcional
    # no debe mover el piso.
    valores = sorted(por_fecha.values())
    respaldo = valores[len(valores) // 2]

    salida = []
    for f in futuras:
        v = _ultimo_mismo_dia(por_fecha, f, primera)
        salida.append(respaldo if v is None else v)
    return salida


@register
class SeasonalNaive(ForecastAlgorithm):
    name = "seasonal_naive"
    # Dos semanas: con menos, no hay un "mismo día de la semana anterior" que
    # mirar para todos los días del horizonte.
    min_data_points = 14
    demand_patterns = None  # compite en todos los patrones, ese es el punto

    def forecast(self, daily_series, horizon_days=14, **kwargs):
        if len(daily_series) < self.min_data_points:
            return None

        ultima = daily_series[-1][0]
        futuras = [ultima + timedelta(days=i) for i in range(1, horizon_days + 1)]
        crudo = _predecir(daily_series, futuras)
        if not crudo:
            return None

        # Banda empírica: el error típico de la propia regla sobre la historia
        # que tenemos, no un porcentaje inventado.
        por_fecha = {it[0]: float(it[1]) for it in daily_series}
        errores = []
        for it in daily_series:
            v = _ultimo_mismo_dia(por_fecha, it[0], daily_series[0][0])
            if v is not None:
                errores.append(abs(float(it[1]) - v))
        banda = (sorted(errores)[int(len(errores) * 0.8)] if errores else 0.0)

        forecasts = []
        for f, qty in zip(futuras, crudo):
            q = _q3(Decimal(str(qty)))
            m = _q3(Decimal(str(banda)))
            forecasts.append({
                "date": f,
                "qty_predicted": q,
                "lower_bound": max(D0, _q3(q - m)),
                "upper_bound": _q3(q + m),
            })

        return {
            "algorithm": self.name,
            "forecasts": forecasts,
            "params": {
                "regla": "mismo dia de la semana, ultima ocurrencia",
                "banda_p80": str(_q3(Decimal(str(banda)))),
            },
            "data_points": len(daily_series),
            # Deliberadamente baja: acierta sin entender nada. Que gane un
            # backtest significa que el resto anduvo peor, no que esta regla
            # sea buena. La interfaz debe seguir recomendando revisar.
            "confidence_base": Decimal("40.00"),
        }

    def backtest(self, daily_series, test_days=7, n_folds=3, **kwargs):
        """Mismo walk-forward que el resto: comparable de a de veras."""
        min_train = self.min_data_points
        if len(daily_series) < min_train + test_days:
            return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}

        folds = []
        total = len(daily_series)
        for fold in range(n_folds):
            fin = total - fold * test_days
            inicio = fin - test_days
            if inicio < min_train:
                break
            train = daily_series[:inicio]
            test = daily_series[inicio:fin]
            reales = [float(it[1]) for it in test]
            preds = _predecir(train, [it[0] for it in test])
            if not preds:
                break
            folds.append(_compute_metrics(reales, preds))

        if not folds:
            return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
        return _average_metrics(folds)
