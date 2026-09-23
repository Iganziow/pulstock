"""
nivel_dia_semana — el nivel de esta semana, con la forma de todas las semanas.

Por que existe
--------------
`seasonal_naive` predice cada dia futuro copiando lo que se vendio el mismo dia
de la semana la vez anterior. Es simple y honesto, pero mezcla NIVEL y FORMA en
un solo numero que tiene una semana de antiguedad. O sea: es, por construccion,
un predictor atrasado una semana.

Y eso no es teorico. Medido en produccion el 21-sep-2026 sobre la ventana
30-jun a 13-sep, comparando el nivel publicado contra el real:

    producto              correlacion en fase   mejor atraso   correlacion ahi
    Leche entera                 +0,07             11 dias         +0,83
    Cafe tolva caturra           +0,05              6 dias         +0,81

La señal esta y es fuerte; llega tarde. Un promedio movil de 28 dias, que atrasa
6, le ganaba al motor completo (38% contra 48% de error en el nucleo).

Que hace distinto
-----------------
Separa las dos cosas que `seasonal_naive` tiene pegadas:

    prediccion(dia) = nivel_reciente x factor(dia de la semana)

  - el NIVEL sale de los ultimos `VENTANA_NIVEL` dias CON registro, asi que se
    mueve con el negocio en vez de arrastrar el de la semana pasada;
  - el FACTOR sale de toda la historia previa: la mediana de ese dia de la
    semana dividida por el promedio general. Mediana y no promedio para que un
    sabado excepcional no deforme todos los sabados.

Medido asi, con validacion caminando hacia adelante (solo datos anteriores al
dia que se predice) sobre demanda efectiva, en 23 productos:

    segmento    seasonal_naive   con deriva   nivel x dia   solo nivel
    nucleo            56%            60%          43%          43%
    cola              76%            86%          56%          58%

Gana en TODOS los productos evaluados. Leche entera 52% -> 38%, cafe 50% -> 39%,
jamon granel 89% -> 55%. La variante "con deriva" --escalar el dato viejo por
cuanto cambio el nivel-- se probo y resulto PEOR que no hacer nada.

Por que un algoritmo nuevo y no un parche a seasonal_naive
----------------------------------------------------------
`seasonal_naive` existe para ser el piso contra el que todo modelo se justifica.
Si le cambiamos las tripas, perdemos la vara. Su propio comentario lo dice: la
forma de meter una regla nueva es registrarla como un candidato mas, para que
"gane solo cuando gana de verdad, medida con la misma vara que el resto, y
heredando los margenes anti-flicker que ya existen".
"""
from datetime import timedelta
from decimal import Decimal
from statistics import median

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import _q3, D0, _compute_metrics, _average_metrics

# Dias con registro que definen el nivel. 14 salio de la medicion: con 7 el
# nivel se vuelve ruidoso en los productos chicos, con 28 empieza a atrasarse
# --que es justo el defecto que este algoritmo viene a corregir--.
VENTANA_NIVEL = 14

# Historia minima para creerle a un factor de dia de la semana. Con menos, el
# factor es ruido y conviene publicar el nivel pelado.
MIN_HISTORIA_FACTOR = 60

# El factor no puede deformar el nivel mas que esto. Un dia que en la historia
# aparece con el triple de venta casi siempre es un dato raro, no una costumbre.
FACTOR_MIN, FACTOR_MAX = 0.3, 2.5


def _valores(serie):
    """(fecha, cantidad) de una serie que puede traer un tercer campo de peso."""
    return [(it[0], float(it[1])) for it in serie]


def nivel_reciente(pares, hasta, ventana=VENTANA_NIVEL):
    """Promedio de los dias CON registro en la ventana previa a `hasta`.

    Se ignoran los dias sin fila a proposito: un domingo cerrado o un feriado no
    tiene que bajar el nivel de los dias que si se opera.
    """
    v = [q for d, q in pares if hasta - timedelta(days=ventana) <= d < hasta]
    return sum(v) / len(v) if v else None


def factor_dia(pares, dow, hasta):
    """Cuanto pesa ese dia de la semana contra el promedio, en la historia previa.

    None si no hay historia suficiente: ahi el que llama publica el nivel solo.
    """
    previos = [(d, q) for d, q in pares if d < hasta]
    if len(previos) < MIN_HISTORIA_FACTOR:
        return None
    base = sum(q for _, q in previos) / len(previos)
    del_dia = [q for d, q in previos if d.weekday() == dow]
    if not del_dia or base <= 0:
        return None
    return min(max(median(del_dia) / base, FACTOR_MIN), FACTOR_MAX)


def _predecir(serie, futuras):
    """Nivel reciente por factor del dia, para cada fecha futura."""
    pares = _valores(serie)
    if not pares:
        return []
    corte = pares[-1][0] + timedelta(days=1)
    nivel = nivel_reciente(pares, corte)
    if nivel is None:
        return []
    salida = []
    for f in futuras:
        fd = factor_dia(pares, f.weekday(), corte)
        salida.append(nivel * fd if fd is not None else nivel)
    return salida


@register
class NivelDiaSemana(ForecastAlgorithm):
    name = "nivel_dia_semana"
    # Dos semanas para el nivel, y el factor se apaga solo si no hay historia.
    min_data_points = 14
    demand_patterns = None  # compite en todos los patrones

    def forecast(self, daily_series, horizon_days=14, **kwargs):
        if len(daily_series) < self.min_data_points:
            return None
        ultima = daily_series[-1][0]
        futuras = [ultima + timedelta(days=i) for i in range(1, horizon_days + 1)]
        crudo = _predecir(daily_series, futuras)
        if not crudo:
            return None

        # Banda empirica: el error tipico de esta misma regla sobre la historia
        # que tenemos, no un porcentaje inventado. Mismo criterio que
        # seasonal_naive.
        pares = _valores(daily_series)
        errores = []
        for d, q in pares:
            nivel = nivel_reciente(pares, d)
            if nivel is None:
                continue
            fd = factor_dia(pares, d.weekday(), d)
            errores.append(abs(q - (nivel * fd if fd is not None else nivel)))
        banda = sorted(errores)[int(len(errores) * 0.8)] if errores else 0.0

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

        pares_ult = _valores(daily_series)
        nivel = nivel_reciente(pares_ult, pares_ult[-1][0] + timedelta(days=1))
        return {
            "algorithm": self.name,
            "forecasts": forecasts,
            "params": {
                "avg_daily": str(_q3(Decimal(str(nivel)))),
                "ventana_nivel": VENTANA_NIVEL,
                "banda_p80": str(_q3(Decimal(str(banda)))),
            },
            "data_points": len(daily_series),
            # Mas que seasonal_naive (40) y menos que un modelo con parametros:
            # entiende la semana, pero sigue siendo una regla.
            "confidence_base": Decimal("50.00"),
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
