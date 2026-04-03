"""
Auto model selection — trains eligible algorithms, backtests, picks best.
"""
from datetime import date
from decimal import Decimal
import logging

from .registry import ALGORITHM_REGISTRY
from .patterns import classify_demand_pattern
from .utils import D0
from .algorithms.croston_bootstrap import croston_bootstrap_intervals

logger = logging.getLogger(__name__)


def select_best_model(daily_series, window=21, horizon=14, test_days=7,
                      month_factors=None, demand_pattern=None, stockout_dates=None):
    """
    Train all eligible models, backtest each, return the best one.

    Returns dict:
        algorithm, forecasts, params, metrics, data_points, confidence_base,
        demand_pattern
    """
    n = len(daily_series)
    today = daily_series[-1][0] if daily_series else date.today()

    if demand_pattern is None:
        demand_pattern, adi, cv2 = classify_demand_pattern(daily_series)
    else:
        adi, cv2 = 0, 0

    candidates = []
    ensemble_algo = None

    # Common kwargs for algorithms that need them
    extra_kwargs = {
        "window": window,
        "month_factors": month_factors,
        "stockout_dates": stockout_dates,
    }

    for algo_cls in ALGORITHM_REGISTRY.values():
        algo = algo_cls()

        # Ensemble is handled specially after other candidates
        if algo.name == "ensemble":
            ensemble_algo = algo
            continue

        # Category prior is handled by services.py directly, not auto-selection
        if algo.name == "category_prior":
            continue

        if not algo.is_eligible(n, demand_pattern):
            continue

        # Backtest
        metrics = algo.backtest(daily_series, test_days=test_days, **extra_kwargs)
        if metrics["mae"] >= 998:
            continue

        # Forecast
        result = algo.forecast(daily_series, horizon_days=horizon, **extra_kwargs)
        if result is None:
            continue

        result["metrics"] = metrics
        result.setdefault("data_points", n)

        # Apply bootstrapped intervals for Croston variants
        if algo.name in ("croston", "croston_sba"):
            result = croston_bootstrap_intervals(daily_series, result)

        candidates.append(result)

    # When adaptive_ma is available, remove redundant moving_avg (same family)
    has_adaptive = any(c["algorithm"] == "adaptive_ma" for c in candidates)
    if has_adaptive:
        candidates = [c for c in candidates if c["algorithm"] != "moving_avg"]

    if not candidates:
        return {
            "algorithm": "none",
            "forecasts": [],
            "params": {},
            "metrics": {"mae": 0, "mape": 0, "rmse": 0, "bias": 0},
            "data_points": n,
            "confidence_base": D0,
            "demand_pattern": demand_pattern,
        }

    # Ensemble (>= 2 viable candidates, >= 28 days)
    if ensemble_algo and len(candidates) >= 2 and n >= 28:
        ens = ensemble_algo.forecast(
            daily_series, horizon_days=horizon,
            candidates=candidates, demand_pattern=demand_pattern,
        )
        if ens:
            candidates.append(ens)

    # Pick best: for intermittent use MAE (MAPE unreliable with zeros)
    if demand_pattern in ("intermittent", "lumpy"):
        best = min(candidates, key=lambda c: (c["metrics"]["mae"], c["metrics"]["mape"]))
    else:
        best = min(candidates, key=lambda c: (c["metrics"]["mape"], c["metrics"]["mae"]))
    best["demand_pattern"] = demand_pattern

    logger.info(
        "Model selection: %d candidates. Winner: %s (MAPE=%.1f%%, MAE=%.3f, pattern=%s)",
        len(candidates), best["algorithm"],
        best["metrics"]["mape"], best["metrics"]["mae"], demand_pattern,
    )

    return best
