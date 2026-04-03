"""
forecast.engine — refactored as a package with strategy pattern.

All public symbols are re-exported here for backward compatibility.
"""
# Register all algorithms
from . import algorithms  # noqa: F401 — triggers @register decorators

# Core selection
from .selection import select_best_model
from .patterns import classify_demand_pattern
from .registry import ALGORITHM_REGISTRY

# Utilities
from .utils import (
    clean_series,
    generate_daily_forecasts,
    calculate_days_to_stockout,
    compute_prediction_intervals,
    apply_empirical_intervals,
    _q3,
    _compute_metrics,
    _average_metrics,
    _fill_gaps,
    _try_import_statsmodels,
    _try_import_ets,
    D0,
    HW_MIN_DAYS,
    HW_SEASONAL_PERIOD,
    _get_month_bucket,
)

# Enhancements
from .enhancements import (
    compute_month_position_factors,
    compute_monthly_seasonality,
    apply_monthly_seasonality,
    compute_bimodal_seasonality,
    compute_yoy_growth,
    apply_yoy_adjustment,
    compute_confidence_decay,
    detect_trend,
    apply_trend_adjustment,
    detect_price_change_impact,
    apply_holiday_adjustments,
    compute_holiday_learned_multiplier,
    apply_bias_correction,
)

# Individual algorithm functions (backward compat)
from .algorithms.simple_average import SimpleAverage
from .algorithms.weighted_moving_average import WeightedMovingAverage
from .algorithms.theta import ThetaForecast
from .algorithms.adaptive_moving_average import AdaptiveMovingAverage
from .algorithms.croston import CrostonForecast, CrostonSBA
from .algorithms.holt_winters import HoltWinters
from .algorithms.holt_winters_damped import HoltWintersDamped
from .algorithms.ets import ETSForecast
from .algorithms.ensemble import EnsembleForecast
from .algorithms.category_prior import CategoryPrior
from .algorithms.croston_bootstrap import croston_bootstrap_intervals

# Legacy function names — delegate to class instances
def simple_average(daily_series, horizon_days=14):
    return SimpleAverage().forecast(daily_series, horizon_days=horizon_days)

def weighted_moving_average(daily_series, window=21):
    from .algorithms.weighted_moving_average import _weighted_moving_average
    return _weighted_moving_average(daily_series, window=window)

def theta_forecast(daily_series, horizon_days=14):
    return ThetaForecast().forecast(daily_series, horizon_days=horizon_days)

def adaptive_moving_average(daily_series, horizon_days=14, month_factors=None):
    return AdaptiveMovingAverage().forecast(daily_series, horizon_days=horizon_days, month_factors=month_factors)

def croston_forecast(daily_series, alpha=0.15, horizon_days=14, use_sba=False):
    cls = CrostonSBA if use_sba else CrostonForecast
    return cls().forecast(daily_series, horizon_days=horizon_days, alpha=alpha)

def holt_winters_forecast(daily_series, horizon_days=14, stockout_dates=None):
    return HoltWinters().forecast(daily_series, horizon_days=horizon_days, stockout_dates=stockout_dates)

def holt_winters_damped_forecast(daily_series, horizon_days=14, stockout_dates=None):
    return HoltWintersDamped().forecast(daily_series, horizon_days=horizon_days, stockout_dates=stockout_dates)

def ets_forecast(daily_series, horizon_days=14, stockout_dates=None):
    return ETSForecast().forecast(daily_series, horizon_days=horizon_days, stockout_dates=stockout_dates)

def ensemble_forecast(candidates, demand_pattern=None):
    return EnsembleForecast().forecast([], candidates=candidates, demand_pattern=demand_pattern)

def category_prior_forecast(daily_series, category_avg, category_dow_factors,
                            horizon_days=14, shrinkage_k=14, **kwargs):
    return CategoryPrior().forecast(
        daily_series, horizon_days=horizon_days,
        category_avg=category_avg, category_dow_factors=category_dow_factors,
        shrinkage_k=shrinkage_k, **kwargs,
    )

# Backtest functions
def backtest_moving_average(daily_series, test_days=7, window=21, n_folds=3):
    return WeightedMovingAverage().backtest(daily_series, test_days=test_days, window=window, n_folds=n_folds)

def backtest_theta(daily_series, test_days=7, n_folds=3):
    return ThetaForecast().backtest(daily_series, test_days=test_days, n_folds=n_folds)

def backtest_adaptive_ma(daily_series, test_days=7, n_folds=3, month_factors=None):
    return AdaptiveMovingAverage().backtest(daily_series, test_days=test_days, n_folds=n_folds, month_factors=month_factors)

def backtest_croston(daily_series, test_days=7, use_sba=False, n_folds=3):
    cls = CrostonSBA if use_sba else CrostonForecast
    return cls().backtest(daily_series, test_days=test_days, n_folds=n_folds)

def backtest_holt_winters(daily_series, test_days=7, stockout_dates=None, n_folds=3):
    return HoltWinters().backtest(daily_series, test_days=test_days, stockout_dates=stockout_dates, n_folds=n_folds)

def backtest_hw_damped(daily_series, test_days=7, stockout_dates=None, n_folds=3):
    return HoltWintersDamped().backtest(daily_series, test_days=test_days, stockout_dates=stockout_dates, n_folds=n_folds)

def backtest_ets(daily_series, test_days=7, stockout_dates=None, n_folds=3):
    return ETSForecast().backtest(daily_series, test_days=test_days, stockout_dates=stockout_dates, n_folds=n_folds)
