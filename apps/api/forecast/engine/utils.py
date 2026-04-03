"""
Shared utilities for forecast engine.

Includes: quantize, data cleaning, gap filling, metrics, forecast generation,
prediction intervals, days-to-stockout, statsmodels lazy imports.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import math
import logging

logger = logging.getLogger(__name__)

D0 = Decimal("0.000")
HW_MIN_DAYS = 28
HW_SEASONAL_PERIOD = 7


def _q3(v):
    return Decimal(str(v)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# ── Lazy imports ─────────────────────────────────────────────────────────────

def _try_import_statsmodels():
    """Import statsmodels lazily - returns None if not installed."""
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        return ExponentialSmoothing
    except ImportError:
        return None


def _try_import_ets():
    """Import ETSModel lazily — requires statsmodels >= 0.12."""
    try:
        from statsmodels.tsa.exponential_smoothing.ets import ETSModel
        return ETSModel
    except ImportError:
        return None


# ── Data cleaning ────────────────────────────────────────────────────────────

def clean_series(daily_series, stockout_dates=None, holiday_dates=None, promo_dates=None):
    """
    Pre-process training data:
    1. Replace stockout zeros with same-weekday interpolation (weight 0.5)
    2. Dampen outliers using percentile method (weight 0.7)
    3. Reduce weight of promo days (weight 0.6)
    """
    if not daily_series:
        return []

    stockout_dates = stockout_dates or set()
    holiday_dates = holiday_dates or set()
    promo_dates = promo_dates or set()
    result = []

    dow_values = {}
    for d, q in daily_series:
        if d not in stockout_dates and float(q) > 0:
            dow_values.setdefault(d.weekday(), []).append(float(q))

    all_nonzero = [
        float(q) for d, q in daily_series
        if float(q) > 0 and d not in holiday_dates
    ]
    q1, q3_val, iqr_limit = 0, float("inf"), float("inf")
    if len(all_nonzero) >= 4:
        sorted_vals = sorted(all_nonzero)
        n = len(sorted_vals)
        q1 = sorted_vals[n // 4]
        q3_val = sorted_vals[(3 * n) // 4]
        iqr = q3_val - q1
        p975 = sorted_vals[min(int(n * 0.975), n - 1)]
        iqr_limit = max(q3_val + 2.0 * iqr, p975)

    for d, q in daily_series:
        qty = float(q)
        weight = 1.0

        if d in stockout_dates and qty == 0:
            dow_vals = dow_values.get(d.weekday(), [])
            if dow_vals:
                qty = sum(dow_vals[-3:]) / len(dow_vals[-3:])
                weight = 0.5
            else:
                qty = sum(all_nonzero) / len(all_nonzero) if all_nonzero else 0
                weight = 0.3
        elif d not in holiday_dates and qty > iqr_limit and iqr_limit < float("inf"):
            qty = iqr_limit
            weight = 0.7

        if d in promo_dates and weight == 1.0:
            weight = 0.6

        result.append((d, _q3(qty), weight))

    return result


# ── Gap filling ──────────────────────────────────────────────────────────────

def _fill_gaps(daily_series, stockout_dates=None):
    """Convert sparse (date, qty[, weight]) to continuous daily float list."""
    if not daily_series:
        return []
    stockout_dates = stockout_dates or set()
    series_map = {item[0]: float(item[1]) for item in daily_series}
    start = daily_series[0][0]
    end = daily_series[-1][0]
    n_days = (end - start).days + 1

    dow_values: dict[int, list[float]] = {}
    for d, qty in series_map.items():
        if d not in stockout_dates and qty > 0:
            dow_values.setdefault(d.weekday(), []).append(qty)
    dow_avg = {
        dow: sum(vals) / len(vals)
        for dow, vals in dow_values.items() if vals
    }
    global_avg = sum(dow_avg.values()) / len(dow_avg) if dow_avg else 0.0

    result = []
    for i in range(n_days):
        d = start + timedelta(days=i)
        if d in series_map and d not in stockout_dates:
            result.append(series_map[d])
        elif d in stockout_dates or d not in series_map:
            result.append(dow_avg.get(d.weekday(), global_avg))
        else:
            result.append(series_map[d])
    return result


# ── Metrics ──────────────────────────────────────────────────────────────────

def _compute_metrics(actuals, predictions):
    """Compute MAE, MAPE, RMSE, bias from paired lists."""
    n = len(actuals)
    if n == 0:
        return {"mae": 0, "mape": 0, "rmse": 0, "bias": 0}

    errors, abs_errors, pct_errors, sq_errors = [], [], [], []
    for actual, predicted in zip(actuals, predictions):
        err = predicted - actual
        errors.append(err)
        abs_errors.append(abs(err))
        sq_errors.append(err ** 2)
        if actual > 0:
            pct_errors.append(abs(err) / actual * 100)

    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(sq_errors) / n)
    bias = sum(errors) / n

    if pct_errors:
        mape = sum(pct_errors) / len(pct_errors)
    elif all(a == 0 for a in actuals):
        mape = 999
    else:
        mape = 0

    return {
        "mae": round(mae, 3),
        "mape": round(mape, 1),
        "rmse": round(rmse, 3),
        "bias": round(bias, 3),
    }


def _average_metrics(fold_metrics):
    """Average metrics across walk-forward folds."""
    n = len(fold_metrics)
    if n == 0:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return {
        "mae": round(sum(f["mae"] for f in fold_metrics) / n, 3),
        "mape": round(sum(f["mape"] for f in fold_metrics) / n, 1),
        "rmse": round(sum(f["rmse"] for f in fold_metrics) / n, 3),
        "bias": round(sum(f["bias"] for f in fold_metrics) / n, 3),
    }


# ── Month-position helpers ───────────────────────────────────────────────────

def _get_month_bucket(day_of_month):
    """Map day-of-month to bucket name."""
    if day_of_month <= 5:
        return "early"
    elif day_of_month <= 12:
        return "mid_early"
    elif day_of_month <= 19:
        return "mid"
    elif day_of_month <= 25:
        return "mid_late"
    return "late"


# ── Forecast generation ──────────────────────────────────────────────────────

def generate_daily_forecasts(avg_daily, dow_factors, start_date, horizon_days=14,
                             month_factors=None):
    """Generate day-by-day forecasts from moving average with weekly + monthly seasonality."""
    forecasts = []
    for i in range(1, horizon_days + 1):
        forecast_date = start_date + timedelta(days=i)
        dow = forecast_date.weekday()
        factor = Decimal(str(dow_factors.get(dow, 1.0)))

        if month_factors:
            bucket = _get_month_bucket(forecast_date.day)
            mf = Decimal(str(month_factors.get(bucket, 1.0)))
            factor = factor * mf

        predicted = _q3(avg_daily * factor)
        margin = _q3(predicted * Decimal("0.30"))
        lower = max(D0, _q3(predicted - margin))
        upper = _q3(predicted + margin)
        forecasts.append({
            "date": forecast_date,
            "qty_predicted": predicted,
            "lower_bound": lower,
            "upper_bound": upper,
        })
    return forecasts


# ── Prediction intervals ────────────────────────────────────────────────────

def compute_prediction_intervals(actuals, predictions, confidence=0.80):
    """Compute empirical prediction intervals from backtest residuals."""
    if len(actuals) < 4:
        return None
    residuals = sorted(a - p for a, p in zip(actuals, predictions))
    n = len(residuals)
    alpha = 1 - confidence
    lower_idx = max(0, int(n * alpha / 2))
    upper_idx = min(n - 1, int(n * (1 - alpha / 2)))
    return residuals[lower_idx], residuals[upper_idx]


def apply_empirical_intervals(forecasts, intervals):
    """Replace static intervals with empirical ones on a forecast list."""
    if not intervals:
        return
    lower_off, upper_off = intervals
    for fc in forecasts:
        predicted = float(fc["qty_predicted"])
        fc["lower_bound"] = _q3(max(0, predicted + lower_off))
        fc["upper_bound"] = _q3(max(0, predicted + upper_off))


# ── Days to stockout ─────────────────────────────────────────────────────────

def calculate_days_to_stockout(current_stock, daily_forecasts, conservative=False):
    """Calculate days until stock reaches zero."""
    if current_stock <= 0:
        return 0
    if not daily_forecasts:
        return None
    qty_key = "upper_bound" if conservative else "qty_predicted"
    cursor = float(current_stock)
    for i, fc in enumerate(daily_forecasts):
        cursor -= float(fc.get(qty_key, fc["qty_predicted"]))
        if cursor <= 0:
            return i + 1
    return None
