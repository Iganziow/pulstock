from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import (
    _q3, _compute_metrics, _average_metrics,
    generate_daily_forecasts,
)


def _adaptive_moving_average(daily_series, horizon_days=14, month_factors=None):
    """
    Moving Average with optimized decay parameter.
    Tests multiple decay values and picks the one with lowest backtest error.
    Also optimizes window size.
    """
    if len(daily_series) < 14:
        return None

    best_config = None
    best_mae = float("inf")

    # Grid search over decay and window
    for decay in [0.85, 0.9, 0.93, 0.95, 0.97]:
        for win in [14, 21, 28]:
            if win > len(daily_series):
                continue
            # Quick in-sample backtest (last 7 days)
            train = daily_series[:-7]
            test = daily_series[-7:]
            if len(train) < win:
                continue

            # Manual WMA with this decay
            recent = train[-win:]
            n = len(recent)
            raw_weights = [decay ** (n - 1 - i) for i in range(n)]
            w_sum = sum(raw_weights)
            avg = sum(float(item[1]) * raw_weights[i] / w_sum for i, item in enumerate(recent))

            # DOW factors. Si un día de la semana NO tuvo ventas en
            # TODO el rango (con >= 4 ocurrencias), asumimos que el
            # local no abre ese día → factor=0 (forecast=0 ese día).
            # Mario reportó: forecast predecía ventas en domingos
            # cuando la cafetería no abre ese día.
            import datetime as _dt
            dow_totals = {}
            train_dates = [item[0] for item in train]
            for item in train:
                dow_totals.setdefault(item[0].weekday(), []).append(float(item[1]))
            if train_dates:
                min_d, max_d = min(train_dates), max(train_dates)
                total_days = (max_d - min_d).days + 1
                dow_occ = {dow: 0 for dow in range(7)}
                for i in range(total_days):
                    dd = min_d + _dt.timedelta(days=i)
                    dow_occ[dd.weekday()] += 1
            else:
                dow_occ = {dow: 0 for dow in range(7)}
            overall = avg if avg > 0 else 1.0
            dow_factors = {}
            for d in range(7):
                vals = dow_totals.get(d, [])
                if vals:
                    dow_factors[d] = round(sum(vals) / len(vals) / overall, 3)
                elif dow_occ.get(d, 0) >= 4:
                    dow_factors[d] = 0.0  # día cerrado
                else:
                    dow_factors[d] = 1.0  # poca data, neutro

            # Test
            preds = [avg * dow_factors.get(item[0].weekday(), 1.0) for item in test]
            actuals = [float(item[1]) for item in test]
            mae = sum(abs(a - p) for a, p in zip(actuals, preds)) / len(actuals)

            if mae < best_mae:
                best_mae = mae
                best_config = {"decay": decay, "window": win, "avg": avg, "dow_factors": dow_factors}

    if not best_config:
        return None

    # Generate forecasts with optimal config
    avg_daily = _q3(best_config["avg"])
    today = daily_series[-1][0]
    forecasts = generate_daily_forecasts(
        avg_daily, best_config["dow_factors"], today, horizon_days,
        month_factors=month_factors,
    )

    return {
        "algorithm": "adaptive_ma",
        "forecasts": forecasts,
        "params": {
            "avg_daily": str(avg_daily),
            "decay": best_config["decay"],
            "window": best_config["window"],
            "dow_factors": {str(k): v for k, v in best_config["dow_factors"].items()},
        },
        "data_points": len(daily_series),
        "confidence_base": Decimal("73.00"),
    }


def _backtest_adaptive_ma(daily_series, test_days=7, n_folds=3, month_factors=None):
    """Walk-forward cross-validation for Adaptive MA."""
    min_train = 21
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
        result = _adaptive_moving_average(train, horizon_days=test_days, month_factors=month_factors)
        if result is None:
            continue
        actuals = [float(item[1]) for item in test]
        predictions = [float(f["qty_predicted"]) for f in result["forecasts"]]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


@register
class AdaptiveMovingAverage(ForecastAlgorithm):
    name = "adaptive_ma"
    min_data_points = 21
    demand_patterns = None  # all

    def forecast(self, daily_series, horizon_days=14, month_factors=None, **kwargs):
        return _adaptive_moving_average(daily_series, horizon_days=horizon_days,
                                        month_factors=month_factors)

    def backtest(self, daily_series, test_days=7, n_folds=3, month_factors=None, **kwargs):
        return _backtest_adaptive_ma(daily_series, test_days=test_days,
                                     n_folds=n_folds, month_factors=month_factors)
