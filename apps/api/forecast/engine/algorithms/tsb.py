"""
TSB (Teunter-Syntetos-Babai) — el que sí se entera de que dejaste de vender.

El problema medido
------------------
Croston, en producción el 31-ago-2026 sobre 30 días de comparaciones reales:

    algoritmo      n     WAPE    sesgo
    croston       335    251%    +95%
    croston_sba   637    220%    +93%

Un sesgo de +95% no es ruido: es sugerir sistemáticamente casi el doble de lo
que se vende, todos los días, en 39 productos.

La causa está en una sola línea de croston.py:

    for i in range(1, len(non_zero)):   # <-- SOLO los días con venta

Croston estima dos cosas: cuánto se vende cuando se vende (`z`) y cada cuántos
días se vende (`p`). Pero solo actualiza ambas **en los días que hubo venta**.
Una racha de ceros no le dice nada: se queda congelado en el último nivel alto
que vio. El helado de verano sigue pronosticando verano en pleno julio, y el
syrup que dejó de salir sigue pidiéndose.

Qué cambia TSB
--------------
En vez de estimar el intervalo entre ventas, estima la PROBABILIDAD de que un
día cualquiera tenga demanda — y la actualiza **todos los días, incluidos los
ceros**:

    día con venta:  z ← α·y + (1-α)·z      p ← β·1 + (1-β)·p     (p sube)
    día sin venta:  z queda igual           p ← β·0 + (1-β)·p     (p BAJA)

    pronóstico diario = p · z

Esa asimetría es todo el arreglo: durante una racha seca `p` decae solo, así
que el pronóstico se apaga gradualmente en vez de quedarse pegado. Y si el
producto vuelve a venderse, `p` sube de nuevo sin necesidad de reentrenar
nada.

Referencia: Teunter, Syntetos & Babai (2011), "Intermittent demand: Linking
forecasting to inventory obsolescence". Es el reemplazo estándar de Croston
justo para este caso — productos que pueden morirse.

Notas de implementación
-----------------------
- `α` y `β` se tunean por separado en el backtest. β controla qué tan rápido
  se apaga: alto olvida demasiado rápido y mata productos vivos de rotación
  lenta; bajo tarda en reaccionar. El grid lo decide con datos.
- El init de `p` es la frecuencia observada en la serie y el de `z` la mediana
  de las ventas no-cero — mediana y no promedio, por lo mismo que en Croston:
  una venta excepcional no debe fijar el nivel.
- Se respeta el peso del punto (`clean_series` marca los datos imputados con
  peso 0.5) bajando el alpha efectivo, igual que Croston.
"""
import math
from datetime import timedelta
from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import _q3, D0, _compute_metrics, _average_metrics


def _tsb_forecast(daily_series, alpha=0.15, beta=0.10, horizon_days=14):
    """Núcleo TSB. `alpha` suaviza el tamaño; `beta`, la probabilidad."""
    if len(daily_series) < 7:
        return None

    valores = [(float(it[1]), (float(it[2]) if len(it) >= 3 else 1.0))
               for it in daily_series]
    no_cero = [v for v, _ in valores if v > 0]
    if len(no_cero) < 2:
        return None

    def _mediana(xs):
        s = sorted(xs)
        m = len(s) // 2
        return float(s[m]) if len(s) % 2 else (float(s[m - 1]) + float(s[m])) / 2.0

    # Init: nivel = mediana de las ventas reales; probabilidad = frecuencia
    # observada. Ambos son estimadores robustos de lo que la serie ya muestra.
    z = _mediana(no_cero)
    p = len(no_cero) / len(valores)

    # El recorrido: TODOS los días, no solo los que vendieron. Esa es la
    # diferencia con Croston y el motivo por el que este existe.
    for qty, peso in valores:
        a = alpha * peso
        b = beta * peso
        if qty > 0:
            z = a * qty + (1 - a) * z
            p = b * 1.0 + (1 - b) * p
        else:
            p = b * 0.0 + (1 - b) * p

    tasa_diaria = max(0.0, p * z)
    avg_daily = _q3(Decimal(str(tasa_diaria)))

    # Banda: desviación de los tamaños no-cero, escalada por la probabilidad.
    if len(no_cero) >= 3:
        media = sum(no_cero) / len(no_cero)
        var = sum((s - media) ** 2 for s in no_cero) / len(no_cero)
        desv = math.sqrt(var) * p
    else:
        desv = tasa_diaria * 0.5

    ultima = daily_series[-1][0]
    forecasts = []
    for i in range(1, horizon_days + 1):
        q = float(avg_daily)
        forecasts.append({
            "date": ultima + timedelta(days=i),
            "qty_predicted": avg_daily,
            "lower_bound": max(D0, _q3(Decimal(str(q - 1.28 * desv)))),
            "upper_bound": _q3(Decimal(str(q + 1.28 * desv))),
        })

    return {
        "algorithm": "tsb",
        "forecasts": forecasts,
        "params": {
            "avg_daily": str(avg_daily),
            "z": round(z, 3),
            "p": round(p, 4),
            "alpha": alpha,
            "beta": beta,
        },
        "metrics": {"mae": 0, "mape": 0, "rmse": 0, "bias": 0},
        "data_points": len(daily_series),
        "confidence_base": Decimal("65.00"),
    }


def _backtest_tsb(daily_series, test_days=7, n_folds=3):
    """Walk-forward con grid sobre alpha y beta.

    Mismo criterio de selección que Croston (Sprint A): se elige por WAPE de
    TOTALES y no por MAE diario, porque en demanda intermitente el MAE diario
    premia sub-predecir — predecir casi cero "acierta" todos los días sin
    venta y falla solo los pocos días que importan.
    """
    min_train = max(7, test_days)
    if len(daily_series) < min_train + test_days:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0,
                "best_alpha": 0.15, "best_beta": 0.10}

    mejor = None
    mejor_alpha, mejor_beta = 0.15, 0.10
    total = len(daily_series)

    for alpha in (0.05, 0.10, 0.20, 0.30):
        for beta in (0.02, 0.05, 0.10, 0.20):
            folds = []
            for fold in range(n_folds):
                fin = total - fold * test_days
                inicio = fin - test_days
                if inicio < min_train:
                    break
                r = _tsb_forecast(daily_series[:inicio], alpha=alpha, beta=beta,
                                  horizon_days=test_days)
                if r is None:
                    continue
                reales = [float(it[1]) for it in daily_series[inicio:fin]]
                preds = [float(f["qty_predicted"]) for f in r["forecasts"]]
                folds.append(_compute_metrics(reales, preds))

            if not folds:
                continue
            avg = _average_metrics(folds)
            clave = (avg.get("wape_total", 999), avg["mae"])
            clave_mejor = ((mejor.get("wape_total", 999), mejor["mae"])
                           if mejor is not None else None)
            if clave_mejor is None or clave < clave_mejor:
                mejor, mejor_alpha, mejor_beta = avg, alpha, beta

    if mejor is None:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0,
                "best_alpha": 0.15, "best_beta": 0.10}
    mejor["best_alpha"] = mejor_alpha
    mejor["best_beta"] = mejor_beta
    return mejor


@register
class TSBForecast(ForecastAlgorithm):
    name = "tsb"
    min_data_points = 14
    # Los mismos patrones que Croston: compite justo donde Croston hoy manda.
    demand_patterns = ["intermittent", "lumpy"]

    def forecast(self, daily_series, horizon_days=14, **kwargs):
        return _tsb_forecast(
            daily_series,
            alpha=kwargs.get("best_alpha") or 0.15,
            beta=kwargs.get("best_beta") or 0.10,
            horizon_days=horizon_days,
        )

    def backtest(self, daily_series, test_days=7, n_folds=3, **kwargs):
        return _backtest_tsb(daily_series, test_days=test_days, n_folds=n_folds)
