import math
from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import _q3


@register
class EnsembleForecast(ForecastAlgorithm):
    name = "ensemble"
    min_data_points = 28
    demand_patterns = None  # all

    def forecast(self, daily_series, horizon_days=14, candidates=None,
                 demand_pattern=None, **kwargs):
        """
        Weighted ensemble of multiple model forecasts.

        For smooth demand: Weight = 1 / (MAPE + 1).
        For intermittent/lumpy: Weight = 1 / (MAE + 1) because MAPE explodes
        when actuals are zero or near-zero.

        Only viable when >= 2 candidates with MAPE < 100 (or MAE < 100 for intermittent).
        """
        if not candidates:
            return None

        use_mae = demand_pattern in ("intermittent", "lumpy")
        metric_key = "mae" if use_mae else "mape"
        viable = [c for c in candidates if c["metrics"][metric_key] < 100]
        if len(viable) < 2:
            return None

        # Softmax-style weighting: exp(-metric/temperature) for smoother distribution
        metrics_vals = [c["metrics"][metric_key] for c in viable]
        temperature = max(1, sum(metrics_vals) / len(metrics_vals))  # mean as temperature
        raw_weights = [math.exp(-m / temperature) for m in metrics_vals]
        total_w = sum(raw_weights)
        weights = [w / total_w for w in raw_weights]

        horizon = min(len(c["forecasts"]) for c in viable)
        if horizon == 0:
            return None
        ensemble_forecasts = []
        for day_idx in range(horizon):
            predicted = sum(
                float(c["forecasts"][day_idx]["qty_predicted"]) * w
                for c, w in zip(viable, weights)
            )
            lower_vals = [float(c["forecasts"][day_idx]["lower_bound"]) for c in viable]
            upper_vals = [float(c["forecasts"][day_idx]["upper_bound"]) for c in viable]
            # Filter out NaN/Inf
            lower_vals = [v for v in lower_vals if math.isfinite(v)]
            upper_vals = [v for v in upper_vals if math.isfinite(v)]
            lower = min(lower_vals) if lower_vals else 0
            upper = max(upper_vals) if upper_vals else float(predicted) * 1.3
            if not math.isfinite(predicted):
                predicted = 0
            ensemble_forecasts.append({
                "date": viable[0]["forecasts"][day_idx]["date"],
                "qty_predicted": _q3(predicted),
                "lower_bound": _q3(max(0, lower)),
                "upper_bound": _q3(upper),
            })

        # Ensemble metrics: weighted average of component metrics
        ens_mape = sum(c["metrics"]["mape"] * w for c, w in zip(viable, weights))
        ens_mae = sum(c["metrics"]["mae"] * w for c, w in zip(viable, weights))

        return {
            "algorithm": "ensemble",
            "forecasts": ensemble_forecasts,
            "params": {
                "models": [
                    {"algo": c["algorithm"], "weight": round(w, 3)}
                    for c, w in zip(viable, weights)
                ],
            },
            "metrics": {
                "mape": round(ens_mape, 1),
                "mae": round(ens_mae, 3),
                "rmse": 0,
                "bias": 0,
            },
            "data_points": viable[0]["data_points"],
            "confidence_base": Decimal("85.00"),
        }

    def backtest(self, daily_series, test_days=7, n_folds=3, **kwargs):
        # Ensemble does not backtest itself; it combines other candidates.
        return {"mae": 0, "mape": 0, "rmse": 0, "bias": 0}
