import math
from datetime import timedelta
from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import _q3, _compute_metrics, _average_metrics, D0


def _croston_forecast(daily_series, alpha=0.15, horizon_days=14, use_sba=False):
    """
    Croston's method for intermittent demand.
    Separately smooths demand size and inter-arrival interval.

    Args:
        daily_series: sorted (date, qty[, weight]) tuples
        alpha: smoothing parameter
        horizon_days: days ahead to forecast
        use_sba: if True, apply Syntetos-Boylan Adjustment (debiased Croston)
    """
    non_zero = []
    for item in daily_series:
        d, q = item[0], float(item[1])
        w = item[2] if len(item) >= 3 else 1.0
        if q > 0:
            non_zero.append((d, q, float(w)))

    if len(non_zero) < 3:
        return None

    # Initialize with first 3 non-zero observations
    sizes = [q for _, q, *_ in non_zero]
    weights = [w for _, _, w in non_zero]
    intervals = []
    for i in range(1, len(non_zero)):
        intervals.append((non_zero[i][0] - non_zero[i - 1][0]).days)

    if not intervals:
        return None

    z_hat = sum(sizes[:3]) / min(3, len(sizes))          # demand size estimate
    p_hat = sum(intervals[:3]) / min(3, len(intervals))  # interval estimate

    # Smooth through the series — weight-adjusted alpha (interpolated data has less influence)
    for i in range(1, len(non_zero)):
        interval = intervals[i - 1] if i - 1 < len(intervals) else p_hat
        size = sizes[i]
        w = weights[i]
        effective_alpha = alpha * w  # Lower alpha for interpolated data (w=0.5)
        z_hat = effective_alpha * size + (1 - effective_alpha) * z_hat
        p_hat = effective_alpha * interval + (1 - effective_alpha) * p_hat

    # Daily demand rate
    daily_rate = z_hat / p_hat if p_hat > 0 else 0

    # SBA adjustment (debias)
    if use_sba:
        daily_rate *= (1 - alpha / 2)

    avg_daily = _q3(max(0, daily_rate))

    # Confidence interval from variance of non-zero sizes
    if len(sizes) >= 3:
        mean_sz = sum(sizes) / len(sizes)
        var_sz = sum((s - mean_sz) ** 2 for s in sizes) / len(sizes)
        std_sz = math.sqrt(var_sz) / p_hat if p_hat > 0 else 0
    else:
        std_sz = float(avg_daily) * 0.5

    last_date = daily_series[-1][0]
    forecasts = []
    for i in range(1, horizon_days + 1):
        fc_date = last_date + timedelta(days=i)
        lower = max(D0, _q3(float(avg_daily) - 1.28 * std_sz))
        upper = _q3(float(avg_daily) + 1.28 * std_sz)
        forecasts.append({
            "date": fc_date,
            "qty_predicted": avg_daily,
            "lower_bound": lower,
            "upper_bound": upper,
        })

    algo = "croston_sba" if use_sba else "croston"
    return {
        "algorithm": algo,
        "forecasts": forecasts,
        "params": {
            "avg_daily": str(avg_daily),
            "z_hat": round(z_hat, 3),
            "p_hat": round(p_hat, 3),
            "alpha": alpha,
            "sba": use_sba,
        },
        "metrics": {"mae": 0, "mape": 0, "rmse": 0, "bias": 0},
        "data_points": len(daily_series),
        "confidence_base": Decimal("65.00"),
    }


def _backtest_croston(daily_series, test_days=7, use_sba=False, n_folds=3):
    """Walk-forward cross-validation for Croston with alpha grid search."""
    min_train = test_days + 7
    if len(daily_series) < min_train + test_days:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0, "best_alpha": 0.15}

    best_metrics = None
    best_alpha = 0.15

    for alpha in [0.05, 0.10, 0.15, 0.20, 0.30]:
        fold_metrics = []
        total = len(daily_series)
        for fold in range(n_folds):
            test_end = total - fold * test_days
            test_start = test_end - test_days
            if test_start < min_train:
                break
            train = daily_series[:test_start]
            test = daily_series[test_start:test_end]
            result = _croston_forecast(train, alpha=alpha, horizon_days=test_days, use_sba=use_sba)
            if result is None:
                continue
            actuals = [float(item[1]) for item in test]
            predictions = [float(f["qty_predicted"]) for f in result["forecasts"]]
            fold_metrics.append(_compute_metrics(actuals, predictions))

        if not fold_metrics:
            continue
        avg = _average_metrics(fold_metrics)
        if best_metrics is None or avg["mae"] < best_metrics["mae"]:
            best_metrics = avg
            best_alpha = alpha

    if best_metrics is None:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0, "best_alpha": 0.15}
    best_metrics["best_alpha"] = best_alpha
    return best_metrics


@register
class CrostonForecast(ForecastAlgorithm):
    name = "croston"
    min_data_points = 14
    demand_patterns = ["intermittent", "lumpy"]

    def forecast(self, daily_series, horizon_days=14, **kwargs):
        return _croston_forecast(daily_series, horizon_days=horizon_days, use_sba=False)

    def backtest(self, daily_series, test_days=7, n_folds=3, **kwargs):
        return _backtest_croston(daily_series, test_days=test_days, use_sba=False,
                                 n_folds=n_folds)


@register
class CrostonSBA(ForecastAlgorithm):
    name = "croston_sba"
    min_data_points = 14
    demand_patterns = ["intermittent", "lumpy"]

    def forecast(self, daily_series, horizon_days=14, **kwargs):
        return _croston_forecast(daily_series, horizon_days=horizon_days, use_sba=True)

    def backtest(self, daily_series, test_days=7, n_folds=3, **kwargs):
        return _backtest_croston(daily_series, test_days=test_days, use_sba=True,
                                 n_folds=n_folds)
