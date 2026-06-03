import math
from datetime import timedelta
from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import _q3, _compute_metrics, _average_metrics


def _theta_forecast(daily_series, horizon_days=14):
    """
    Theta Method — ganador de la competencia de forecasting M3.

    Descompone la serie en 2 "theta lines":
      - theta=0: trend lineal (captura la direccion)
      - theta=2: serie amplificada (captura nivel local)
    El forecast es el promedio de ambas.

    Simple, robusto, y compite con modelos mucho mas complejos.
    Requiere >= 14 dias de datos.
    """
    if len(daily_series) < 14:
        return None

    values = [float(item[1]) for item in daily_series]
    n = len(values)

    # Step 1: Linear trend via OLS
    xs = list(range(n))
    sum_x = sum(xs)
    sum_y = sum(values)
    sum_xy = sum(x * y for x, y in zip(xs, values))
    sum_x2 = sum(x * x for x in xs)
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return None

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # Step 2: Simple Exponential Smoothing on the series
    # Optimize alpha by minimizing in-sample MSE
    best_alpha = 0.1
    best_mse = float("inf")
    for alpha_candidate in [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]:
        ses = values[0]
        mse = 0.0
        for i in range(1, n):
            err = values[i] - ses
            mse += err ** 2
            ses = alpha_candidate * values[i] + (1 - alpha_candidate) * ses
        mse /= (n - 1)
        if mse < best_mse:
            best_mse = mse
            best_alpha = alpha_candidate

    # Rerun SES with optimal alpha to get final level
    ses = values[0]
    for i in range(1, n):
        ses = best_alpha * values[i] + (1 - best_alpha) * ses

    # Step 3: Forecast = average of theta=0 line (trend) and theta=2 line (SES extrapolation)
    last_date = daily_series[-1][0]
    forecasts = []
    for h in range(1, horizon_days + 1):
        # theta=0 line: linear trend extrapolation
        trend_val = intercept + slope * (n - 1 + h)
        # theta=2 line: SES level (constant for all h, plus half the trend drift)
        ses_val = ses + slope * h * 0.5
        # Theta forecast = average
        predicted = max(0.0, (trend_val + ses_val) / 2.0)
        margin = math.sqrt(best_mse) * 1.28
        fc_date = last_date + timedelta(days=h)
        forecasts.append({
            "date": fc_date,
            "qty_predicted": _q3(predicted),
            "lower_bound": _q3(max(0, predicted - margin)),
            "upper_bound": _q3(predicted + margin),
        })

    return {
        "algorithm": "theta",
        "forecasts": forecasts,
        "params": {
            "alpha": best_alpha,
            "slope": round(slope, 4),
            "intercept": round(intercept, 4),
            "ses_level": round(ses, 3),
        },
        "data_points": n,
        "confidence_base": Decimal("72.00"),
    }


def _backtest_theta(daily_series, test_days=7, n_folds=3):
    """Walk-forward cross-validation for Theta method."""
    min_train = 14
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
        result = _theta_forecast(train, horizon_days=test_days)
        if result is None:
            continue
        actuals = [float(item[1]) for item in test]
        predictions = [float(f["qty_predicted"]) for f in result["forecasts"]]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


@register
class ThetaForecast(ForecastAlgorithm):
    name = "theta"
    min_data_points = 14
    demand_patterns = None  # all

    def forecast(self, daily_series, horizon_days=14, **kwargs):
        return _theta_forecast(daily_series, horizon_days=horizon_days)

    def backtest(self, daily_series, test_days=7, n_folds=3, **kwargs):
        return _backtest_theta(daily_series, test_days=test_days, n_folds=n_folds)
