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


def _holt_winters_damped_forecast(daily_series, horizon_days=14, stockout_dates=None):
    """
    Holt-Winters with damped additive trend + weekly seasonality.
    The damping parameter phi prevents trend from diverging into the future,
    making forecasts more conservative and realistic for longer horizons.
    """
    ExponentialSmoothing = _try_import_statsmodels()
    if ExponentialSmoothing is None:
        return None

    filled = _fill_gaps(daily_series, stockout_dates=stockout_dates)
    if len(filled) < HW_MIN_DAYS:
        return None

    values = [max(v, 0.01) for v in filled]

    try:
        model = ExponentialSmoothing(
            values,
            trend="add",
            damped_trend=True,
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
            "damping_trend": round(float(fit.params.get("damping_trend", 0)), 4),
        }

        residuals = fit.resid
        rmse = 0.0
        if residuals is not None and len(residuals) > 0:
            rmse = math.sqrt(sum(float(r)**2 for r in residuals) / len(residuals))

        last_date = daily_series[-1][0]
        forecasts = []
        for i in range(horizon_days):
            fc_date = last_date + timedelta(days=i + 1)
            predicted = max(0.0, float(pred[i]))
            margin = rmse * 1.28
            forecasts.append({
                "date": fc_date,
                "qty_predicted": _q3(predicted),
                "lower_bound": _q3(max(0, predicted - margin)),
                "upper_bound": _q3(predicted + margin),
            })

        return {
            "algorithm": "hw_damped",
            "forecasts": forecasts,
            "params": params,
            "rmse": round(rmse, 3),
        }

    except Exception as e:
        logger.warning("HW-Damped failed: %s", e)
        return None


def _backtest_hw_damped(daily_series, test_days=7, stockout_dates=None, n_folds=3):
    """Walk-forward cross-validation for Holt-Winters damped."""
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
        result = _holt_winters_damped_forecast(train, horizon_days=test_days,
                                                stockout_dates=stockout_dates)
        if result is None:
            continue
        actuals = [float(item[1]) for item in test]
        predictions = [float(f["qty_predicted"]) for f in result["forecasts"]]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


@register
class HoltWintersDamped(ForecastAlgorithm):
    name = "hw_damped"
    min_data_points = 28
    demand_patterns = None  # all

    def forecast(self, daily_series, horizon_days=14, stockout_dates=None, **kwargs):
        result = _holt_winters_damped_forecast(daily_series, horizon_days=horizon_days,
                                                stockout_dates=stockout_dates)
        if result is None:
            return None
        n = len(daily_series)
        return {
            "algorithm": "hw_damped",
            "forecasts": result["forecasts"],
            "params": result["params"],
            "metrics": {"mae": 0, "mape": 0, "rmse": 0, "bias": 0},
            "data_points": n,
            "confidence_base": Decimal("82.00"),
        }

    def backtest(self, daily_series, test_days=7, n_folds=3, stockout_dates=None, **kwargs):
        return _backtest_hw_damped(daily_series, test_days=test_days,
                                    stockout_dates=stockout_dates, n_folds=n_folds)
