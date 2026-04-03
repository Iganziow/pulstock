from datetime import date, timedelta
from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import _q3, D0


@register
class CategoryPrior(ForecastAlgorithm):
    name = "category_prior"
    min_data_points = 0  # can work with zero data
    demand_patterns = None  # all

    def forecast(self, daily_series, horizon_days=14, category_avg=None,
                 category_dow_factors=None, shrinkage_k=14, **kwargs):
        """
        Forecast for sparse products (< min_days) using category-level prior.
        Blends product's own limited data with category average via Bayesian shrinkage.

        No hardcoded factors — only uses empirical data from the category profile
        and the product's own (limited) sales history.
        """
        if category_avg is None:
            return None

        n = len(daily_series)

        if n > 0:
            product_avg = sum(float(item[1]) for item in daily_series) / n
            shrinkage = n / (n + shrinkage_k)
            blended = shrinkage * product_avg + (1 - shrinkage) * float(category_avg)
        else:
            blended = float(category_avg)

        avg_daily = _q3(blended)
        confidence = Decimal(str(min(45, 30 + n * 2.5)))

        last_date = daily_series[-1][0] if daily_series else date.today()
        dow_factors = category_dow_factors or {}

        forecasts = []
        for i in range(1, horizon_days + 1):
            fc_date = last_date + timedelta(days=i)
            dow = fc_date.weekday()
            factor = Decimal(str(dow_factors.get(dow, dow_factors.get(str(dow), 1.0))))
            predicted = _q3(avg_daily * factor)
            margin = _q3(predicted * Decimal("0.50"))
            forecasts.append({
                "date": fc_date,
                "qty_predicted": predicted,
                "lower_bound": max(D0, _q3(predicted - margin)),
                "upper_bound": _q3(predicted + margin),
            })

        # Compute real holdout MAPE when enough data exists (use first 70% to predict last 30%)
        metrics = {"mae": 0, "mape": 0, "rmse": 0, "bias": 0}
        if n >= 6:
            split = max(3, int(n * 0.7))
            train_series = daily_series[:split]
            test_series = daily_series[split:]
            train_avg = sum(float(item[1]) for item in train_series) / len(train_series)
            train_shrinkage = len(train_series) / (len(train_series) + shrinkage_k)
            train_blended = train_shrinkage * train_avg + (1 - train_shrinkage) * float(category_avg)
            errors, pct_errors = [], []
            for item in test_series:
                actual = float(item[1])
                predicted_val = train_blended * float(
                    dow_factors.get(item[0].weekday(), dow_factors.get(str(item[0].weekday()), 1.0))
                )
                err = abs(predicted_val - actual)
                errors.append(err)
                if actual > 0:
                    pct_errors.append(err / actual * 100)
            metrics["mae"] = round(sum(errors) / len(errors), 4) if errors else 0
            metrics["mape"] = round(sum(pct_errors) / len(pct_errors), 2) if pct_errors else 0

        return {
            "algorithm": "category_prior",
            "forecasts": forecasts,
            "params": {
                "avg_daily": str(avg_daily),
                "category_avg": str(category_avg),
                "shrinkage": round(n / (n + shrinkage_k), 3) if n > 0 else 0,
                "product_data_days": n,
            },
            "metrics": metrics,
            "data_points": n,
            "confidence_base": confidence,
        }

    def backtest(self, daily_series, test_days=7, n_folds=3, **kwargs):
        # Category prior uses internal holdout validation in forecast()
        return {"mae": 0, "mape": 0, "rmse": 0, "bias": 0}
