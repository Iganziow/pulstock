import math
import logging
from datetime import timedelta
from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import (
    _q3, _compute_metrics, _average_metrics,
    _try_import_ets, _fill_gaps,
    HW_MIN_DAYS, HW_SEASONAL_PERIOD,
)

logger = logging.getLogger(__name__)


def _ets_forecast(daily_series, horizon_days=14, stockout_dates=None):
    """
    Error-Trend-Seasonality model with automatic component selection.

    Tries additive error + additive trend + additive season (AAdA)
    and falls back to no-trend / no-season if convergence fails.

    ETS is the state-space formulation of exponential smoothing, providing
    proper prediction intervals from the underlying likelihood.
    """
    ETSModel = _try_import_ets()
    if ETSModel is None:
        return None

    filled = _fill_gaps(daily_series, stockout_dates=stockout_dates)
    if len(filled) < HW_MIN_DAYS:
        return None

    values = [max(v, 0.01) for v in filled]

    # Try configurations from most complex to simplest
    configs = [
        {"error": "add", "trend": "add", "seasonal": "add",
         "seasonal_periods": HW_SEASONAL_PERIOD, "damped_trend": True},
        {"error": "add", "trend": "add", "seasonal": "add",
         "seasonal_periods": HW_SEASONAL_PERIOD, "damped_trend": False},
        {"error": "add", "trend": "add", "seasonal": None,
         "damped_trend": True},
    ]

    for cfg in configs:
        try:
            model = ETSModel(values, **cfg)
            fit = model.fit(disp=False, maxiter=500)
            pred = fit.forecast(horizon_days)

            # Get prediction intervals from the model
            try:
                pi = fit.get_prediction(start=len(values), end=len(values) + horizon_days - 1)
                ci = pi.summary_frame(alpha=0.2)  # 80% intervals
                lowers = ci["pi_lower"].values
                uppers = ci["pi_upper"].values
            except Exception:
                residuals = fit.resid
                rmse = math.sqrt(sum(float(r)**2 for r in residuals) / len(residuals)) if len(residuals) > 0 else 0
                lowers = [max(0, float(pred[i]) - rmse * 1.28) for i in range(horizon_days)]
                uppers = [float(pred[i]) + rmse * 1.28 for i in range(horizon_days)]

            last_date = daily_series[-1][0]
            forecasts = []
            for i in range(horizon_days):
                fc_date = last_date + timedelta(days=i + 1)
                predicted = max(0.0, float(pred[i]))
                forecasts.append({
                    "date": fc_date,
                    "qty_predicted": _q3(predicted),
                    "lower_bound": _q3(max(0, float(lowers[i]))),
                    "upper_bound": _q3(float(uppers[i])),
                })

            ets_cfg_label = f"E={cfg['error']},T={cfg.get('trend','N')},S={cfg.get('seasonal','N')}"
            if cfg.get("damped_trend"):
                ets_cfg_label += ",damped"

            return {
                "algorithm": "ets",
                "forecasts": forecasts,
                "params": {
                    "ets_config": ets_cfg_label,
                    "aic": round(float(fit.aic), 2) if hasattr(fit, "aic") else None,
                    "bic": round(float(fit.bic), 2) if hasattr(fit, "bic") else None,
                },
                "data_points": len(daily_series),
                "confidence_base": Decimal("85.00"),
            }

        except Exception as e:
            logger.debug("ETS config %s failed: %s", cfg, e)
            continue

    return None


def _backtest_ets(daily_series, test_days=7, stockout_dates=None, n_folds=3):
    """Walk-forward cross-validation for ETS."""
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
        result = _ets_forecast(train, horizon_days=test_days, stockout_dates=stockout_dates)
        if result is None:
            continue
        actuals = [float(item[1]) for item in test]
        predictions = [float(f["qty_predicted"]) for f in result["forecasts"]]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


@register
class ETSForecast(ForecastAlgorithm):
    name = "ets"
    min_data_points = 28
    demand_patterns = None  # all

    def forecast(self, daily_series, horizon_days=14, stockout_dates=None, **kwargs):
        return _ets_forecast(daily_series, horizon_days=horizon_days,
                             stockout_dates=stockout_dates)

    def backtest(self, daily_series, test_days=7, n_folds=3, stockout_dates=None, **kwargs):
        return _backtest_ets(daily_series, test_days=test_days,
                             stockout_dates=stockout_dates, n_folds=n_folds)
