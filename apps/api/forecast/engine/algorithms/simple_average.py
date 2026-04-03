from datetime import timedelta
from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import _q3, D0


@register
class SimpleAverage(ForecastAlgorithm):
    name = "simple_avg"
    min_data_points = 7
    demand_patterns = None  # all

    def forecast(self, daily_series, horizon_days=14, **kwargs):
        if not daily_series:
            return None
        avg = sum(float(item[1]) for item in daily_series) / len(daily_series)
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
        return {
            "algorithm": "simple_avg",
            "forecasts": forecasts,
            "params": {"avg_daily": str(avg_daily)},
            "metrics": {"mae": 0, "mape": 0, "rmse": 0, "bias": 0},
            "data_points": len(daily_series),
            "confidence_base": Decimal("45.00"),
        }

    def backtest(self, daily_series, test_days=7, n_folds=3, **kwargs):
        return {"mae": 0, "mape": 0, "rmse": 0, "bias": 0}

    def is_eligible(self, n_points, demand_pattern):
        return 7 <= n_points < 14
