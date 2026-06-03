import math
import logging
from datetime import timedelta
from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import (
    _q3, _compute_metrics, _average_metrics,
    _try_import_statsmodels, _fill_gaps,
    HW_MIN_DAYS, HW_SEASONAL_PERIOD,
)

logger = logging.getLogger(__name__)


def _has_closed_weekday(daily_series, min_occurrences=4, sale_threshold=0.10):
    """True si algun dia de la semana esta sistematicamente cerrado.

    Un DOW se considera "cerrado" si aparece >= min_occurrences veces en la
    serie y en menos del sale_threshold (10%) de esas veces hubo venta. Ese
    patron rompe la estacionalidad de Holt-Winters (ver _holt_winters_forecast).
    """
    by_dow = {}  # dow -> [n_ocurrencias, n_con_venta]
    for item in daily_series:
        d, qty = item[0], item[1]
        if not hasattr(d, "weekday"):
            continue
        dow = d.weekday()
        cell = by_dow.setdefault(dow, [0, 0])
        cell[0] += 1
        if float(qty) > 0:
            cell[1] += 1
    for dow, (n, sold) in by_dow.items():
        if n >= min_occurrences and (sold / n) < sale_threshold:
            return True
    return False


def _holt_winters_forecast(daily_series, horizon_days=14, stockout_dates=None):
    """
    Holt-Winters triple exponential smoothing with weekly seasonality.
    Returns dict with forecasts, params, algorithm, rmse. None if unavailable.
    """
    ExponentialSmoothing = _try_import_statsmodels()
    if ExponentialSmoothing is None:
        logger.info("statsmodels not installed, skipping Holt-Winters")
        return None

    # ── Bug 2 (22/05/26): HW se auto-descarta si hay dias cerrados ───────
    # Holt-Winters con seasonal_periods=7 asume que los 7 dias de la semana
    # forman un ciclo regular. Cuando el local CIERRA un dia (ej. Marbrava
    # no abre domingos -> esos dias quedan en 0), HW se desestabiliza:
    #   - aditivo: componente estacional muy negativa -> empuja dias flojos
    #     (sabado) a valores negativos -> clampeados a 0.
    #   - multiplicativo: factores extremos -> predicciones que oscilan
    #     disparatadamente (sabado 1175, jueves 0).
    # En cambio el moving-average ponderado maneja los dias cerrados
    # correctamente via dow_factors (factor 0 para el dia cerrado, factor
    # real para los demas). Solucion: si la serie tiene un dia de semana
    # sistematicamente cerrado, HW retorna None y deja competir a los
    # algoritmos que SI lo manejan bien.
    if _has_closed_weekday(daily_series):
        return None

    filled = _fill_gaps(daily_series, stockout_dates=stockout_dates)
    if len(filled) < HW_MIN_DAYS:
        return None

    # Clamp to small positive for stability
    values = [max(v, 0.01) for v in filled]

    try:
        model = ExponentialSmoothing(
            values,
            trend="add",
            seasonal="add",
            seasonal_periods=HW_SEASONAL_PERIOD,
            initialization_method="estimated",
        )
        fit = model.fit(optimized=True, remove_bias=True)

        pred = fit.forecast(horizon_days)

        params = {
            "smoothing_level": round(float(fit.params.get("smoothing_level", 0)), 4),
            "smoothing_trend": round(float(fit.params.get("smoothing_trend", 0)), 4),
            "smoothing_seasonal": round(float(fit.params.get("smoothing_seasonal", 0)), 4),
        }

        # Residuals for confidence interval
        residuals = fit.resid
        rmse = 0.0
        if residuals is not None and len(residuals) > 0:
            rmse = math.sqrt(sum(float(r)**2 for r in residuals) / len(residuals))

        last_date = daily_series[-1][0]
        forecasts = []
        for i in range(horizon_days):
            fc_date = last_date + timedelta(days=i + 1)
            predicted = max(0.0, float(pred[i]))
            margin = rmse * 1.28  # ~80% confidence
            lower = max(0.0, predicted - margin)
            upper = predicted + margin

            forecasts.append({
                "date": fc_date,
                "qty_predicted": _q3(predicted),
                "lower_bound": _q3(lower),
                "upper_bound": _q3(upper),
            })

        return {
            "algorithm": "holt_winters",
            "forecasts": forecasts,
            "params": params,
            "rmse": round(rmse, 3),
        }

    except (ValueError, RuntimeError, FloatingPointError, Exception) as e:
        logger.warning("Holt-Winters failed: %s", e)
        return None


def _backtest_holt_winters(daily_series, test_days=7, stockout_dates=None, n_folds=3):
    """Walk-forward cross-validation for Holt-Winters with n_folds folds."""
    min_train = HW_MIN_DAYS
    if len(daily_series) < min_train + test_days:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}

    fold_metrics = []
    total = len(daily_series)
    for fold in range(n_folds):
        test_end = total - fold * test_days
        test_start = test_end - test_days
        if test_start < min_train:
            break
        train = daily_series[:test_start]
        test = daily_series[test_start:test_end]
        hw_result = _holt_winters_forecast(train, horizon_days=test_days,
                                            stockout_dates=stockout_dates)
        if hw_result is None:
            continue
        actuals = [float(item[1]) for item in test]
        predictions = [float(f["qty_predicted"]) for f in hw_result["forecasts"]]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


@register
class HoltWinters(ForecastAlgorithm):
    name = "holt_winters"
    min_data_points = 28
    demand_patterns = None  # all

    def forecast(self, daily_series, horizon_days=14, stockout_dates=None, **kwargs):
        result = _holt_winters_forecast(daily_series, horizon_days=horizon_days,
                                         stockout_dates=stockout_dates)
        if result is None:
            return None
        n = len(daily_series)
        return {
            "algorithm": "holt_winters",
            "forecasts": result["forecasts"],
            "params": result["params"],
            "metrics": {"mae": 0, "mape": 0, "rmse": 0, "bias": 0},
            "data_points": n,
            "confidence_base": Decimal("80.00"),
        }

    def backtest(self, daily_series, test_days=7, n_folds=3, stockout_dates=None, **kwargs):
        return _backtest_holt_winters(daily_series, test_days=test_days,
                                      stockout_dates=stockout_dates, n_folds=n_folds)
