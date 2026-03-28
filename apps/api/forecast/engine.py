"""
forecast.engine
===============
Prediction engine — multi-algorithm with auto-selection.

Algorithms (by data availability):
  - Category Prior:     0-6 days   (Bayesian shrinkage from category average)
  - Simple Average:     7-13 days  (plain mean, wide intervals)
  - Moving Average:     14+ days   (weighted exponential decay + DOW factors)
  - Theta Method:       14+ days   (M3 competition winner, SES + linear drift)
  - Adaptive MA:        21+ days   (auto-optimized α, DOW + month factors)
  - Croston / SBA:      14+ days   (intermittent demand only)
  - Holt-Winters:       28+ days   (triple exponential smoothing, weekly season)
  - HW Damped:          28+ days   (damped trend prevents divergence)
  - ETS:                28+ days   (state-space error/trend/season auto-select)
  - Ensemble:           28+ days   (weighted average of viable candidates)

Additional features:
  - Stockout-censored data cleaning (clean_series)
  - Demand pattern classification (smooth/intermittent/lumpy)
  - Empirical prediction intervals
  - Month-position factors (payday effect)
  - Monthly seasonality (180+ days, annual cycle)
  - Year-over-year growth adjustment (365+ days)
  - Linear trend detection
  - Bias auto-correction
  - Holiday learning (learned_multiplier)
  - Price elasticity signal
  - Confidence decay for stale models
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import math
import logging

logger = logging.getLogger(__name__)

D0 = Decimal("0.000")

HW_MIN_DAYS = 28          # Need >= 4 full weeks for seasonal_periods=7
HW_SEASONAL_PERIOD = 7    # Weekly seasonality


def _q3(v):
    return Decimal(str(v)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLEANING — Stockout detection + Outlier dampening
# ══════════════════════════════════════════════════════════════════════════════

def clean_series(daily_series, stockout_dates=None, holiday_dates=None):
    """
    Pre-process training data:
    1. Replace stockout zeros with same-weekday interpolation (weight 0.5)
    2. Dampen outliers using IQR method (weight 0.7)
       — Holiday dates are excluded from IQR so seasonal spikes aren't clipped.

    Args:
        daily_series: sorted list of (date, qty_sold) tuples
        stockout_dates: set of dates marked as stockout (from DailySales.is_stockout)
        holiday_dates: set of dates that are holidays/events (excluded from IQR)

    Returns:
        list of (date, qty, weight) tuples where weight < 1.0 for imputed values.
    """
    if not daily_series:
        return []

    stockout_dates = stockout_dates or set()
    holiday_dates = holiday_dates or set()
    result = []

    # Group values by weekday for interpolation
    dow_values = {}
    for d, q in daily_series:
        if d not in stockout_dates and float(q) > 0:
            dow_values.setdefault(d.weekday(), []).append(float(q))

    # IQR for outlier detection — exclude holidays so seasonal spikes survive
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
        iqr_limit = q3_val + 1.5 * iqr

    for d, q in daily_series:
        qty = float(q)
        weight = 1.0

        if d in stockout_dates and qty == 0:
            # Interpolate from same weekday
            dow_vals = dow_values.get(d.weekday(), [])
            if dow_vals:
                qty = sum(dow_vals[-3:]) / len(dow_vals[-3:])
                weight = 0.5
            else:
                qty = sum(all_nonzero) / len(all_nonzero) if all_nonzero else 0
                weight = 0.3
        elif d not in holiday_dates and qty > iqr_limit and iqr_limit < float("inf"):
            # Dampen outlier — but never dampen holiday spikes
            qty = iqr_limit
            weight = 0.7

        result.append((d, _q3(qty), weight))

    return result


# ══════════════════════════════════════════════════════════════════════════════
# DEMAND PATTERN CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════

def classify_demand_pattern(daily_series):
    """
    Classify demand pattern using ADI-CV² framework.

    Returns:
        (pattern, adi, cv2) where pattern is one of:
        - "smooth": regular demand (ADI < 1.32)
        - "intermittent": infrequent but consistent sizes (ADI >= 1.32, CV² < 0.49)
        - "lumpy": infrequent with variable sizes (ADI >= 1.32, CV² >= 0.49)
        - "insufficient": not enough non-zero observations
    """
    non_zero = [(d, float(q)) for d, q, *_ in daily_series if float(q) > 0]
    if len(non_zero) < 3:
        return "insufficient", 0, 0

    # ADI = average demand interval (days between non-zero demands)
    intervals = []
    for i in range(1, len(non_zero)):
        intervals.append((non_zero[i][0] - non_zero[i - 1][0]).days)
    adi = sum(intervals) / len(intervals) if intervals else 1.0

    # CV² of non-zero demand sizes
    sizes = [q for _, q in non_zero]
    mean_size = sum(sizes) / len(sizes)
    if mean_size <= 0:
        return "insufficient", adi, 0

    variance = sum((s - mean_size) ** 2 for s in sizes) / len(sizes)
    cv2 = variance / (mean_size ** 2)

    if adi >= 1.32:
        return ("lumpy" if cv2 >= 0.49 else "intermittent"), round(adi, 2), round(cv2, 3)
    return "smooth", round(adi, 2), round(cv2, 3)


# ══════════════════════════════════════════════════════════════════════════════
# LEVEL 1: WEIGHTED MOVING AVERAGE
# ══════════════════════════════════════════════════════════════════════════════

def weighted_moving_average(daily_series, window=21):
    """
    Weighted moving average with exponential decay + day-of-week factors.
    Accepts (date, qty) or (date, qty, weight) tuples.
    """
    if not daily_series:
        return {"avg_daily": D0, "weights": [], "day_of_week_factors": {}}

    recent = daily_series[-window:]
    n = len(recent)
    decay = 0.9
    raw_weights = [decay ** (n - 1 - i) for i in range(n)]
    weight_sum = sum(raw_weights)

    weighted_sum = Decimal("0")
    weight_details = []
    for i, item in enumerate(recent):
        d, qty = item[0], item[1]
        data_weight = item[2] if len(item) >= 3 else 1.0
        w = Decimal(str(raw_weights[i] / weight_sum * data_weight))
        weighted_sum += Decimal(str(qty)) * w
        weight_details.append((d, float(w), float(qty)))

    # Re-normalize
    total_w = sum(wt for _, wt, _ in weight_details)
    if total_w > 0 and abs(total_w - 1.0) > 0.01:
        weighted_sum = Decimal("0")
        for i, (d, w, q) in enumerate(weight_details):
            norm_w = w / total_w
            weighted_sum += Decimal(str(q)) * Decimal(str(norm_w))
            weight_details[i] = (d, norm_w, q)

    avg_daily = _q3(weighted_sum)

    # Day-of-week factors
    dow_totals = {}
    for item in daily_series:
        d, qty = item[0], float(item[1])
        dow_totals.setdefault(d.weekday(), []).append(qty)

    overall_avg = float(avg_daily) if avg_daily > 0 else 1.0
    dow_factors = {}
    for dow in range(7):
        values = dow_totals.get(dow, [])
        if values:
            dow_avg = sum(values) / len(values)
            dow_factors[dow] = round(dow_avg / overall_avg, 3) if overall_avg > 0 else 1.0
        else:
            dow_factors[dow] = 1.0

    return {
        "avg_daily": avg_daily,
        "weights": weight_details,
        "day_of_week_factors": dow_factors,
    }


# ══════════════════════════════════════════════════════════════════════════════
# LEVEL 2: HOLT-WINTERS (Triple Exponential Smoothing)
# ══════════════════════════════════════════════════════════════════════════════

def _try_import_statsmodels():
    """Import statsmodels lazily - returns None if not installed."""
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        return ExponentialSmoothing
    except ImportError:
        return None


def _fill_gaps(daily_series, stockout_dates=None):
    """
    Convert sparse (date, qty[, weight]) to continuous daily float list.
    For stockout dates: interpolate from same-weekday values instead of 0.0,
    so Holt-Winters doesn't learn spurious zero-demand patterns.
    """
    if not daily_series:
        return []
    stockout_dates = stockout_dates or set()
    series_map = {item[0]: float(item[1]) for item in daily_series}
    start = daily_series[0][0]
    end = daily_series[-1][0]
    n_days = (end - start).days + 1

    # Pre-compute same-weekday averages for interpolation
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
            # Interpolate from same-weekday average
            result.append(dow_avg.get(d.weekday(), global_avg))
        else:
            result.append(series_map[d])
    return result


def holt_winters_forecast(daily_series, horizon_days=14, stockout_dates=None):
    """
    Holt-Winters triple exponential smoothing with weekly seasonality.
    Returns dict with forecasts, params, algorithm, rmse. None if unavailable.
    """
    ExponentialSmoothing = _try_import_statsmodels()
    if ExponentialSmoothing is None:
        logger.info("statsmodels not installed, skipping Holt-Winters")
        return None

    filled = _fill_gaps(daily_series, stockout_dates=stockout_dates)
    if len(filled) < HW_MIN_DAYS:
        return None

    # Clamp to small positive for stability
    values = [max(v, 0.01) for v in filled]

    try:
        model = ExponentialSmoothing(
            values,
            trend="add",
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
        }

        # Residuals for confidence interval
        residuals = fit.resid
        rmse = 0.0
        if residuals is not None and len(residuals) > 0:
            rmse = math.sqrt(sum(float(r)**2 for r in residuals) / len(residuals))

        last_date = daily_series[-1][0]
        forecasts = []
        for i in range(horizon_days):
            fc_date = last_date + timedelta(days=i + 1)
            predicted = max(0.0, float(pred[i]))
            margin = rmse * 1.28  # ~80% confidence
            lower = max(0.0, predicted - margin)
            upper = predicted + margin

            forecasts.append({
                "date": fc_date,
                "qty_predicted": _q3(predicted),
                "lower_bound": _q3(lower),
                "upper_bound": _q3(upper),
            })

        return {
            "algorithm": "holt_winters",
            "forecasts": forecasts,
            "params": params,
            "rmse": round(rmse, 3),
        }

    except (ValueError, RuntimeError, FloatingPointError, Exception) as e:
        logger.warning("Holt-Winters failed: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# CROSTON'S METHOD (Intermittent Demand)
# ══════════════════════════════════════════════════════════════════════════════

def croston_forecast(daily_series, alpha=0.15, horizon_days=14, use_sba=False):
    """
    Croston's method for intermittent demand.
    Separately smooths demand size and inter-arrival interval.

    Args:
        daily_series: sorted (date, qty[, weight]) tuples
        alpha: smoothing parameter
        horizon_days: days ahead to forecast
        use_sba: if True, apply Syntetos-Boylan Adjustment (debiased Croston)
    """
    non_zero = [(d, float(q)) for d, *rest in daily_series
                for q in [rest[0] if rest else 0] if float(q) > 0]

    if len(non_zero) < 3:
        return None

    # Initialize with first 3 non-zero observations
    sizes = [q for _, q in non_zero]
    intervals = []
    for i in range(1, len(non_zero)):
        intervals.append((non_zero[i][0] - non_zero[i - 1][0]).days)

    if not intervals:
        return None

    z_hat = sum(sizes[:3]) / min(3, len(sizes))          # demand size estimate
    p_hat = sum(intervals[:3]) / min(3, len(intervals))  # interval estimate

    # Smooth through the series
    for i in range(1, len(non_zero)):
        interval = intervals[i - 1] if i - 1 < len(intervals) else p_hat
        size = sizes[i]
        z_hat = alpha * size + (1 - alpha) * z_hat
        p_hat = alpha * interval + (1 - alpha) * p_hat

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


def backtest_croston(daily_series, test_days=7, use_sba=False, n_folds=3):
    """Walk-forward cross-validation for Croston with n_folds folds."""
    min_train = test_days + 7
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
        result = croston_forecast(train, horizon_days=test_days, use_sba=use_sba)
        if result is None:
            continue
        actuals = [float(item[1]) for item in test]
        predictions = [float(f["qty_predicted"]) for f in result["forecasts"]]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


# ══════════════════════════════════════════════════════════════════════════════
# EMPIRICAL PREDICTION INTERVALS
# ══════════════════════════════════════════════════════════════════════════════

def compute_prediction_intervals(actuals, predictions, confidence=0.80):
    """
    Compute empirical prediction intervals from backtest residuals.
    Returns (lower_offset, upper_offset) — add to predicted value.
    """
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


# ══════════════════════════════════════════════════════════════════════════════
# MONTH-POSITION FACTORS (Payday effect)
# ══════════════════════════════════════════════════════════════════════════════

def compute_month_position_factors(daily_series, min_days=45):
    """
    Detect monthly demand patterns (payday effect, Chile: salary 25th-30th).

    Groups days into 5 buckets by day-of-month.
    Returns dict {bucket: factor} or None if pattern is not significant.
    """
    if len(daily_series) < min_days:
        return None

    buckets = {"early": [], "mid_early": [], "mid": [], "mid_late": [], "late": []}
    for item in daily_series:
        d, q = item[0], float(item[1])
        day = d.day
        if day <= 5:
            buckets["early"].append(q)
        elif day <= 12:
            buckets["mid_early"].append(q)
        elif day <= 19:
            buckets["mid"].append(q)
        elif day <= 25:
            buckets["mid_late"].append(q)
        else:
            buckets["late"].append(q)

    overall_avg = sum(float(item[1]) for item in daily_series) / len(daily_series)
    if overall_avg <= 0:
        return None

    factors = {}
    for name, values in buckets.items():
        if values:
            factors[name] = round(sum(values) / len(values) / overall_avg, 3)
        else:
            factors[name] = 1.0

    # Only return if meaningful variation exists
    vals = list(factors.values())
    min_val = min(vals)
    if min_val <= 0 or max(vals) / min_val < 1.15:
        return None

    return factors


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


# ══════════════════════════════════════════════════════════════════════════════
# MONTHLY SEASONALITY (Annual cycle)
# ══════════════════════════════════════════════════════════════════════════════

SEASONALITY_MIN_DAYS = 180  # ~6 months minimum


def compute_monthly_seasonality(daily_series, min_days=SEASONALITY_MIN_DAYS):
    """
    Compute month-of-year demand factors from historical data.

    Groups all data by calendar month, computes average daily demand per month,
    then normalizes against the overall average.

    Returns:
        dict {month_number: factor} (1-12) or None if insufficient data.
        Factor > 1.0 means above-average month, < 1.0 below-average.
    """
    if len(daily_series) < min_days:
        return None

    monthly_values = {}  # month -> list of daily quantities
    for item in daily_series:
        d = item[0]
        qty = float(item[1])
        monthly_values.setdefault(d.month, []).append(qty)

    # Need data for at least 6 distinct months
    if len(monthly_values) < 6:
        return None

    overall_avg = sum(float(item[1]) for item in daily_series) / len(daily_series)
    if overall_avg <= 0:
        return None

    factors = {}
    for month in range(1, 13):
        values = monthly_values.get(month, [])
        if values:
            month_avg = sum(values) / len(values)
            factors[month] = round(month_avg / overall_avg, 3)
        else:
            factors[month] = 1.0

    # Validation: require meaningful variation AND statistical reliability
    vals_with_data = [(m, v) for m, v in factors.items() if monthly_values.get(m)]
    if not vals_with_data:
        return None

    vals = [v for _, v in vals_with_data]
    min_val = min(vals)
    if min_val <= 0 or max(vals) / min_val < 1.20:
        return None

    # Shrink factors for months with few observations (< 15 days)
    # toward 1.0 to avoid overfitting to a single atypical month
    for month in range(1, 13):
        n_obs = len(monthly_values.get(month, []))
        if 0 < n_obs < 15:
            # Shrinkage: blend toward 1.0 proportional to data scarcity
            shrink = n_obs / 15.0  # 0..1
            factors[month] = round(1.0 + (factors[month] - 1.0) * shrink, 3)

    return factors


def apply_monthly_seasonality(forecasts, monthly_factors):
    """Apply month-of-year seasonality factors to forecast list."""
    if not monthly_factors:
        return
    for fc in forecasts:
        month = fc["date"].month
        factor = monthly_factors.get(month, 1.0)
        if factor != 1.0:
            fc["qty_predicted"] = _q3(float(fc["qty_predicted"]) * factor)
            fc["lower_bound"] = _q3(max(0, float(fc["lower_bound"]) * factor))
            fc["upper_bound"] = _q3(float(fc["upper_bound"]) * factor)


# ══════════════════════════════════════════════════════════════════════════════
# YEAR-OVER-YEAR GROWTH
# ══════════════════════════════════════════════════════════════════════════════

YOY_MIN_DAYS = 365


def compute_yoy_growth(daily_series, min_days=YOY_MIN_DAYS):
    """
    Compare this year's demand vs same period last year to detect growth/decline.

    Returns:
        dict {growth_rate, this_year_avg, last_year_avg} or None.
        growth_rate is a multiplier: 1.15 = +15% growth.
    """
    if len(daily_series) < min_days:
        return None

    today = daily_series[-1][0]
    one_year_ago = today - timedelta(days=365)

    # Split into last-year and this-year windows (90-day comparison)
    this_year_start = today - timedelta(days=90)
    last_year_start = one_year_ago - timedelta(days=90)
    last_year_end = one_year_ago

    this_year = [float(item[1]) for item in daily_series
                 if this_year_start <= item[0] <= today]
    last_year = [float(item[1]) for item in daily_series
                 if last_year_start <= item[0] <= last_year_end]

    if len(this_year) < 30 or len(last_year) < 30:
        return None

    this_avg = sum(this_year) / len(this_year)
    last_avg = sum(last_year) / len(last_year)

    if last_avg <= 0:
        return None

    growth_rate = this_avg / last_avg

    # Clamp to reasonable range (50%-200%)
    growth_rate = max(0.5, min(2.0, growth_rate))

    # Only report if change is > 10%
    if abs(growth_rate - 1.0) < 0.10:
        return None

    return {
        "growth_rate": round(growth_rate, 3),
        "this_year_avg": round(this_avg, 3),
        "last_year_avg": round(last_avg, 3),
    }


def apply_yoy_adjustment(forecasts, yoy_info, damping=0.5):
    """
    Apply year-over-year growth adjustment to forecasts.
    Uses damping to avoid over-correcting (default: 50% of observed growth).
    """
    if not yoy_info:
        return
    raw_rate = yoy_info["growth_rate"]
    # Damped adjustment: move halfway toward the observed growth
    factor = 1.0 + (raw_rate - 1.0) * damping

    for fc in forecasts:
        fc["qty_predicted"] = _q3(float(fc["qty_predicted"]) * factor)
        fc["lower_bound"] = _q3(max(0, float(fc["lower_bound"]) * factor))
        fc["upper_bound"] = _q3(float(fc["upper_bound"]) * factor)


# ══════════════════════════════════════════════════════════════════════════════
# CONFIDENCE DECAY
# ══════════════════════════════════════════════════════════════════════════════

def compute_confidence_decay(trained_at, base_confidence, half_life_days=14):
    """
    Reduce confidence score for models that haven't been retrained recently.

    Exponential decay: confidence halves every `half_life_days`.
    Floor at 20% of base confidence.

    Args:
        trained_at: date when the model was last trained
        base_confidence: Decimal confidence from model selection
        half_life_days: days until confidence is halved (default: 14)

    Returns:
        Decimal adjusted confidence
    """
    today = date.today()

    if hasattr(trained_at, 'date') and callable(trained_at.date):
        # datetime object → extract date
        days_since = (today - trained_at.date()).days
    elif isinstance(trained_at, date):
        days_since = (today - trained_at).days
    else:
        return base_confidence

    if days_since <= 1:
        return base_confidence

    decay = 0.5 ** (days_since / half_life_days)
    floor = float(base_confidence) * 0.2
    decayed = max(floor, float(base_confidence) * decay)

    return Decimal(str(round(decayed, 2)))


# ══════════════════════════════════════════════════════════════════════════════
# LINEAR TREND DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def detect_trend(daily_series, min_days=28):
    """
    Detect linear trend via OLS on weekly aggregates.

    Returns:
        dict {slope_per_day, r_squared, direction} or None if no significant trend.
        direction: "up", "down", or "flat"
    """
    if len(daily_series) < min_days:
        return None

    # Aggregate to weekly totals
    weekly = {}
    for item in daily_series:
        d = item[0]
        iso_week = d.isocalendar()[0] * 100 + d.isocalendar()[1]
        weekly.setdefault(iso_week, []).append(float(item[1]))

    if len(weekly) < 4:
        return None

    # Convert to (x, y) where x = week index, y = weekly avg
    weeks = sorted(weekly.keys())
    xs = list(range(len(weeks)))
    ys = [sum(weekly[w]) / len(weekly[w]) for w in weeks]

    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_x2 = sum(x * x for x in xs)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return None

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # R-squared
    y_mean = sum_y / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # Convert weekly slope to daily
    slope_per_day = slope / 7.0

    # Significance check
    mean_daily = sum(float(item[1]) for item in daily_series) / len(daily_series)
    if r_squared < 0.3 or mean_daily <= 0:
        return None
    if abs(slope_per_day) / mean_daily < 0.005:  # less than 0.5% per day
        return None

    if slope_per_day > 0:
        direction = "up"
    elif slope_per_day < 0:
        direction = "down"
    else:
        direction = "flat"

    return {
        "slope_per_day": round(slope_per_day, 4),
        "r_squared": round(r_squared, 3),
        "direction": direction,
    }


def apply_trend_adjustment(forecasts, trend_info, avg_daily):
    """Multiply forecasts by trend factor: 1 + slope_per_day * days_ahead / avg_daily."""
    if not trend_info or float(avg_daily) <= 0:
        return
    slope = trend_info["slope_per_day"]
    avg = float(avg_daily)

    for i, fc in enumerate(forecasts):
        days_ahead = i + 1
        factor = 1.0 + slope * days_ahead / avg
        factor = max(0.5, min(2.0, factor))  # clamp to avoid extreme adjustments
        fc["qty_predicted"] = _q3(float(fc["qty_predicted"]) * factor)
        fc["lower_bound"] = _q3(max(0, float(fc["lower_bound"]) * factor))
        fc["upper_bound"] = _q3(float(fc["upper_bound"]) * factor)


# ══════════════════════════════════════════════════════════════════════════════
# PRICE ELASTICITY SIGNAL
# ══════════════════════════════════════════════════════════════════════════════

def detect_price_change_impact(daily_series, revenue_series=None):
    """
    Detect if price changes correlate with demand changes.

    Args:
        daily_series: sorted (date, qty_sold, ...) tuples
        revenue_series: sorted (date, revenue) tuples from DailySales

    Returns:
        dict {is_price_sensitive, events} or None
    """
    if revenue_series is None or len(revenue_series) < 14:
        return None

    # Compute daily average price = revenue / qty
    price_map = {}
    for d, rev in revenue_series:
        rev_f = float(rev)
        # Find matching qty
        for item in daily_series:
            if item[0] == d and float(item[1]) > 0:
                price_map[d] = rev_f / float(item[1])
                break

    if len(price_map) < 10:
        return None

    dates = sorted(price_map.keys())
    events = []

    for i in range(1, len(dates)):
        prev_price = price_map[dates[i - 1]]
        curr_price = price_map[dates[i]]

        if prev_price <= 0:
            continue

        pct_change = (curr_price - prev_price) / prev_price

        if abs(pct_change) > 0.10:  # price changed > 10%
            # Look at demand 7 days after
            after_start = dates[i]
            after_end = after_start + timedelta(days=7)
            before_start = dates[i] - timedelta(days=7)

            demand_before = [float(item[1]) for item in daily_series
                            if before_start <= item[0] < dates[i] and float(item[1]) > 0]
            demand_after = [float(item[1]) for item in daily_series
                           if after_start <= item[0] <= after_end and float(item[1]) > 0]

            if demand_before and demand_after:
                avg_before = sum(demand_before) / len(demand_before)
                avg_after = sum(demand_after) / len(demand_after)
                demand_change = (avg_after - avg_before) / avg_before if avg_before > 0 else 0

                # Price up + demand down = price sensitive
                if pct_change > 0.10 and demand_change < -0.15:
                    events.append({
                        "date": str(dates[i]),
                        "price_change_pct": round(pct_change * 100, 1),
                        "demand_change_pct": round(demand_change * 100, 1),
                    })

    return {
        "is_price_sensitive": len(events) > 0,
        "events": events[:5],  # last 5 events
    }


# ══════════════════════════════════════════════════════════════════════════════
# GENERATE FORECAST — Moving Average
# ══════════════════════════════════════════════════════════════════════════════

def generate_daily_forecasts(avg_daily, dow_factors, start_date, horizon_days=14,
                             month_factors=None):
    """Generate day-by-day forecasts from moving average with weekly + monthly seasonality."""
    forecasts = []
    for i in range(1, horizon_days + 1):
        forecast_date = start_date + timedelta(days=i)
        dow = forecast_date.weekday()
        factor = Decimal(str(dow_factors.get(dow, 1.0)))

        # Month-position factor
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


# ══════════════════════════════════════════════════════════════════════════════
# DAYS TO STOCKOUT
# ══════════════════════════════════════════════════════════════════════════════

def calculate_days_to_stockout(current_stock, daily_forecasts,
                               conservative=False):
    """Calculate days until stock reaches zero.

    When *conservative* is True the upper_bound is used instead of the
    mean prediction so the alert fires earlier — appropriate for models
    that are still learning (low / very_low confidence).
    """
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


# ══════════════════════════════════════════════════════════════════════════════
# BACKTEST
# ══════════════════════════════════════════════════════════════════════════════

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
    mape = sum(pct_errors) / len(pct_errors) if pct_errors else 0
    bias = sum(errors) / n

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


def backtest_moving_average(daily_series, test_days=7, window=21, n_folds=3):
    """Walk-forward cross-validation with n_folds folds."""
    min_train = max(test_days + 7, window + 7)
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
        result = weighted_moving_average(train, window=window)
        avg = float(result["avg_daily"])
        dow_factors = result["day_of_week_factors"]
        actuals = [float(item[1]) for item in test]
        predictions = [avg * dow_factors.get(item[0].weekday(), 1.0) for item in test]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


def backtest_holt_winters(daily_series, test_days=7, stockout_dates=None, n_folds=3):
    """Walk-forward cross-validation for Holt-Winters with n_folds folds."""
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
        hw_result = holt_winters_forecast(train, horizon_days=test_days, stockout_dates=stockout_dates)
        if hw_result is None:
            continue
        actuals = [float(item[1]) for item in test]
        predictions = [float(f["qty_predicted"]) for f in hw_result["forecasts"]]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


# ══════════════════════════════════════════════════════════════════════════════
# SIMPLE AVERAGE (Sparse data)
# ══════════════════════════════════════════════════════════════════════════════

def simple_average(daily_series, horizon_days=14):
    """
    Plain arithmetic mean for sparse products (7-13 days of data).
    No weighting, no day-of-week factors. Wide confidence intervals (±50%).
    """
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


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY PRIOR FORECAST (Bayesian shrinkage)
# ══════════════════════════════════════════════════════════════════════════════

def category_prior_forecast(daily_series, category_avg, category_dow_factors,
                            horizon_days=14, shrinkage_k=14, **kwargs):
    """
    Forecast for sparse products (< min_days) using category-level prior.
    Blends product's own limited data with category average via Bayesian shrinkage.

    No hardcoded factors — only uses empirical data from the category profile
    and the product's own (limited) sales history.
    """
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
            predicted = train_blended * float(dow_factors.get(item[0].weekday(), dow_factors.get(str(item[0].weekday()), 1.0)))
            err = abs(predicted - actual)
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


# ══════════════════════════════════════════════════════════════════════════════
# ENSEMBLE FORECAST
# ══════════════════════════════════════════════════════════════════════════════

def ensemble_forecast(candidates, demand_pattern=None):
    """
    Weighted ensemble of multiple model forecasts.

    For smooth demand: Weight = 1 / (MAPE + 1).
    For intermittent/lumpy: Weight = 1 / (MAE + 1) because MAPE explodes
    when actuals are zero or near-zero.

    Only viable when >= 2 candidates with MAPE < 100 (or MAE < 100 for intermittent).
    """
    use_mae = demand_pattern in ("intermittent", "lumpy")
    metric_key = "mae" if use_mae else "mape"
    viable = [c for c in candidates if c["metrics"][metric_key] < 100]
    if len(viable) < 2:
        return None

    weights = [1.0 / (c["metrics"][metric_key] + 1) for c in viable]
    total_w = sum(weights)
    weights = [w / total_w for w in weights]

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


# ══════════════════════════════════════════════════════════════════════════════
# HOLIDAY ADJUSTMENTS
# ══════════════════════════════════════════════════════════════════════════════

def apply_holiday_adjustments(forecasts, holidays):
    """
    Post-process forecasts by applying holiday demand multipliers.
    Uses learned_multiplier when available (blended with configured).
    """
    holiday_map = {}
    for h in holidays:
        configured = float(h.demand_multiplier) if hasattr(h, 'demand_multiplier') else float(h.get('demand_multiplier', 1))
        learned = None
        if hasattr(h, 'learned_multiplier') and h.learned_multiplier is not None:
            learned = float(h.learned_multiplier)
        elif isinstance(h, dict) and h.get('learned_multiplier') is not None:
            learned = float(h['learned_multiplier'])

        # Blend: 60% learned + 40% configured
        if learned is not None:
            mult = 0.6 * learned + 0.4 * configured
        else:
            mult = configured

        try:
            pre_days = int(h.pre_days) if hasattr(h, 'pre_days') else int(h.get('pre_days', 1))
        except (ValueError, TypeError):
            pre_days = 1
        pre_mult = float(h.pre_multiplier) if hasattr(h, 'pre_multiplier') else float(h.get('pre_multiplier', 1))
        h_date = h.date if hasattr(h, 'date') and isinstance(h.date, date) else h.get('date') if isinstance(h, dict) else None

        if h_date is None:
            continue

        holiday_map[h_date] = mult
        for d in range(1, pre_days + 1):
            pre_date = h_date - timedelta(days=d)
            if pre_date not in holiday_map:
                holiday_map[pre_date] = pre_mult

    for fc in forecasts:
        fc_date = fc["date"]
        mult = holiday_map.get(fc_date)
        if mult and mult != 1:
            mult_d = Decimal(str(mult))
            fc["qty_predicted"] = _q3(fc["qty_predicted"] * mult_d)
            fc["lower_bound"] = _q3(fc["lower_bound"] * mult_d)
            fc["upper_bound"] = _q3(fc["upper_bound"] * mult_d)

    return forecasts


# ══════════════════════════════════════════════════════════════════════════════
# BIAS CORRECTION
# ══════════════════════════════════════════════════════════════════════════════

def apply_bias_correction(forecasts, recent_accuracy, avg_daily):
    """
    Auto-correct forecasts based on recent prediction errors.
    Uses day-of-week specific bias when enough data exists,
    falling back to global bias otherwise.

    Args:
        forecasts: list of forecast dicts (must have 'date' key)
        recent_accuracy: list of ForecastAccuracy dicts with 'error', 'date', 'was_stockout'
        avg_daily: Decimal — current average daily demand

    Returns:
        bias_correction dict {global, dow} applied (0 if none)
    """
    if not recent_accuracy or float(avg_daily) <= 0:
        return 0.0

    errors = [
        (a["date"], float(a["error"]))
        for a in recent_accuracy
        if not a.get("was_stockout")
    ]
    if len(errors) < 5:
        return 0.0

    # Global bias
    all_errors = [e for _, e in errors]
    mean_bias = sum(all_errors) / len(all_errors)

    # Day-of-week bias (only when we have date info)
    dow_errors: dict[int, list[float]] = {}
    for d, err in errors:
        if hasattr(d, "weekday"):
            dow_errors.setdefault(d.weekday(), []).append(err)

    dow_bias = {}
    for dow, errs in dow_errors.items():
        if len(errs) >= 2:
            dow_mean = sum(errs) / len(errs)
            if abs(dow_mean) / float(avg_daily) >= 0.10:
                dow_bias[dow] = dow_mean * 0.5

    # Apply: prefer DOW-specific correction, fallback to global
    global_correction = 0.0
    if abs(mean_bias) / float(avg_daily) >= 0.10:
        global_correction = mean_bias * 0.5

    applied_any = False
    for fc in forecasts:
        fc_date = fc.get("date")
        if fc_date and hasattr(fc_date, "weekday") and fc_date.weekday() in dow_bias:
            correction = dow_bias[fc_date.weekday()]
        else:
            correction = global_correction

        if correction != 0:
            applied_any = True
            fc["qty_predicted"] = _q3(max(0, float(fc["qty_predicted"]) - correction))
            fc["lower_bound"] = _q3(max(0, float(fc["lower_bound"]) - correction))
            fc["upper_bound"] = _q3(max(0, float(fc["upper_bound"]) - correction))

    if not applied_any:
        return 0.0

    return {"global": round(global_correction, 3), "dow": {k: round(v, 3) for k, v in dow_bias.items()}}


# ══════════════════════════════════════════════════════════════════════════════
# DAMPED TREND (Holt-Winters with damped trend)
# ══════════════════════════════════════════════════════════════════════════════

def holt_winters_damped_forecast(daily_series, horizon_days=14, stockout_dates=None):
    """
    Holt-Winters with damped additive trend + weekly seasonality.
    The damping parameter φ prevents trend from diverging into the future,
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


def backtest_hw_damped(daily_series, test_days=7, stockout_dates=None, n_folds=3):
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
        result = holt_winters_damped_forecast(train, horizon_days=test_days, stockout_dates=stockout_dates)
        if result is None:
            continue
        actuals = [float(item[1]) for item in test]
        predictions = [float(f["qty_predicted"]) for f in result["forecasts"]]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


# ══════════════════════════════════════════════════════════════════════════════
# THETA METHOD (Assimakopoulos & Nikolopoulos, 2000)
# ══════════════════════════════════════════════════════════════════════════════

def theta_forecast(daily_series, horizon_days=14):
    """
    Theta Method — ganador de la competencia de forecasting M3.

    Descompone la serie en 2 "theta lines":
      - θ=0: trend lineal (captura la dirección)
      - θ=2: serie amplificada (captura nivel local)
    El forecast es el promedio de ambas.

    Simple, robusto, y compite con modelos mucho más complejos.
    Requiere >= 14 días de datos.
    """
    if len(daily_series) < 14:
        return None

    values = [float(item[1]) for item in daily_series]
    n = len(values)

    # Step 1: Linear trend via OLS
    xs = list(range(n))
    sum_x = sum(xs)
    sum_y = sum(values)
    sum_xy = sum(x * y for x, y in zip(xs, values))
    sum_x2 = sum(x * x for x in xs)
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return None

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # Step 2: Simple Exponential Smoothing on the series
    # Optimize alpha by minimizing in-sample MSE
    best_alpha = 0.1
    best_mse = float("inf")
    for alpha_candidate in [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]:
        ses = values[0]
        mse = 0.0
        for i in range(1, n):
            err = values[i] - ses
            mse += err ** 2
            ses = alpha_candidate * values[i] + (1 - alpha_candidate) * ses
        mse /= (n - 1)
        if mse < best_mse:
            best_mse = mse
            best_alpha = alpha_candidate

    # Rerun SES with optimal alpha to get final level
    ses = values[0]
    for i in range(1, n):
        ses = best_alpha * values[i] + (1 - best_alpha) * ses

    # Step 3: Forecast = average of θ=0 line (trend) and θ=2 line (SES extrapolation)
    last_date = daily_series[-1][0]
    forecasts = []
    for h in range(1, horizon_days + 1):
        # θ=0 line: linear trend extrapolation
        trend_val = intercept + slope * (n - 1 + h)
        # θ=2 line: SES level (constant for all h, plus half the trend drift)
        ses_val = ses + slope * h * 0.5
        # Theta forecast = average
        predicted = max(0.0, (trend_val + ses_val) / 2.0)
        margin = math.sqrt(best_mse) * 1.28
        fc_date = last_date + timedelta(days=h)
        forecasts.append({
            "date": fc_date,
            "qty_predicted": _q3(predicted),
            "lower_bound": _q3(max(0, predicted - margin)),
            "upper_bound": _q3(predicted + margin),
        })

    return {
        "algorithm": "theta",
        "forecasts": forecasts,
        "params": {
            "alpha": best_alpha,
            "slope": round(slope, 4),
            "intercept": round(intercept, 4),
            "ses_level": round(ses, 3),
        },
        "data_points": n,
        "confidence_base": Decimal("72.00"),
    }


def backtest_theta(daily_series, test_days=7, n_folds=3):
    """Walk-forward cross-validation for Theta method."""
    min_train = 14
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
        result = theta_forecast(train, horizon_days=test_days)
        if result is None:
            continue
        actuals = [float(item[1]) for item in test]
        predictions = [float(f["qty_predicted"]) for f in result["forecasts"]]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


# ══════════════════════════════════════════════════════════════════════════════
# ADAPTIVE SMOOTHING (Auto-optimize α for WMA)
# ══════════════════════════════════════════════════════════════════════════════

def adaptive_moving_average(daily_series, horizon_days=14, month_factors=None):
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

            # DOW factors
            dow_totals = {}
            for item in train:
                dow_totals.setdefault(item[0].weekday(), []).append(float(item[1]))
            overall = avg if avg > 0 else 1.0
            dow_factors = {
                dow: round(sum(vals) / len(vals) / overall, 3) if vals else 1.0
                for dow, vals in [(d, dow_totals.get(d, [])) for d in range(7)]
            }

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


def backtest_adaptive_ma(daily_series, test_days=7, n_folds=3, month_factors=None):
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
        result = adaptive_moving_average(train, horizon_days=test_days, month_factors=month_factors)
        if result is None:
            continue
        actuals = [float(item[1]) for item in test]
        predictions = [float(f["qty_predicted"]) for f in result["forecasts"]]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


# ══════════════════════════════════════════════════════════════════════════════
# BOOTSTRAPPED INTERVALS FOR CROSTON
# ══════════════════════════════════════════════════════════════════════════════

def croston_bootstrap_intervals(daily_series, base_forecast, n_boot=200, confidence=0.80):
    """
    Generate bootstrapped prediction intervals for Croston forecasts.
    Resamples non-zero demand sizes and intervals to build empirical distribution.

    Returns adjusted forecasts with bootstrapped lower/upper bounds.
    """
    non_zero = [(d, float(q)) for d, q, *_ in daily_series if float(q) > 0]
    if len(non_zero) < 5 or not base_forecast:
        return base_forecast

    import random

    sizes = [q for _, q in non_zero]
    intervals_days = []
    for i in range(1, len(non_zero)):
        intervals_days.append((non_zero[i][0] - non_zero[i - 1][0]).days)
    if not intervals_days:
        return base_forecast

    horizon = len(base_forecast["forecasts"])
    boot_rates = []

    random.seed(42)  # deterministic for reproducibility
    for _ in range(n_boot):
        # Resample sizes and intervals
        boot_sizes = [random.choice(sizes) for _ in range(len(sizes))]
        boot_intervals = [random.choice(intervals_days) for _ in range(len(intervals_days))]
        mean_size = sum(boot_sizes) / len(boot_sizes)
        mean_interval = sum(boot_intervals) / len(boot_intervals)
        if mean_interval > 0:
            boot_rates.append(mean_size / mean_interval)
        else:
            boot_rates.append(mean_size)

    boot_rates.sort()
    lo_idx = int(len(boot_rates) * (1 - confidence) / 2)
    hi_idx = int(len(boot_rates) * (1 + confidence) / 2)
    lo_idx = max(0, min(lo_idx, len(boot_rates) - 1))
    hi_idx = max(0, min(hi_idx, len(boot_rates) - 1))

    lower_rate = boot_rates[lo_idx]
    upper_rate = boot_rates[hi_idx]

    for fc in base_forecast["forecasts"]:
        fc["lower_bound"] = _q3(max(0, lower_rate))
        fc["upper_bound"] = _q3(upper_rate)

    base_forecast["params"]["bootstrap_samples"] = n_boot
    return base_forecast


# ══════════════════════════════════════════════════════════════════════════════
# ETS — Error-Trend-Seasonality (auto-selection)
# ══════════════════════════════════════════════════════════════════════════════

def _try_import_ets():
    """Import ETSModel lazily — requires statsmodels >= 0.12."""
    try:
        from statsmodels.tsa.exponential_smoothing.ets import ETSModel
        return ETSModel
    except ImportError:
        return None


def ets_forecast(daily_series, horizon_days=14, stockout_dates=None):
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


def backtest_ets(daily_series, test_days=7, stockout_dates=None, n_folds=3):
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
        result = ets_forecast(train, horizon_days=test_days, stockout_dates=stockout_dates)
        if result is None:
            continue
        actuals = [float(item[1]) for item in test]
        predictions = [float(f["qty_predicted"]) for f in result["forecasts"]]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


# ══════════════════════════════════════════════════════════════════════════════
# AUTO MODEL SELECTION (Enhanced)
# ══════════════════════════════════════════════════════════════════════════════

def select_best_model(daily_series, window=21, horizon=14, test_days=7,
                      month_factors=None, demand_pattern=None, stockout_dates=None):
    """
    Train all eligible models, backtest each, return the best one.

    Enhanced with:
    - Croston/SBA for intermittent demand
    - Ensemble candidate
    - Month-position factors
    - Demand pattern awareness

    Returns dict:
        algorithm, forecasts, params, metrics, data_points, confidence_base,
        demand_pattern
    """
    n = len(daily_series)
    today = daily_series[-1][0] if daily_series else date.today()

    # Classify demand pattern if not provided
    if demand_pattern is None:
        demand_pattern, adi, cv2 = classify_demand_pattern(daily_series)
    else:
        adi, cv2 = 0, 0

    candidates = []

    # ── Candidate 0: Simple Average (7-13 days, sparse data) ──
    if 7 <= n < 14:
        sa = simple_average(daily_series, horizon_days=horizon)
        if sa:
            candidates.append(sa)

    # ── Candidate 1: Weighted Moving Average (>= 14 days, only if backtest passes) ──
    if n >= 14:
        ma_result = weighted_moving_average(daily_series, window=window)
        ma_metrics = backtest_moving_average(daily_series, test_days=test_days, window=window)
        if ma_metrics["mae"] < 998:
          ma_forecasts = generate_daily_forecasts(
              ma_result["avg_daily"], ma_result["day_of_week_factors"],
              today, horizon, month_factors=month_factors,
          )

          # Apply empirical intervals if we have enough backtest data
          if ma_metrics["mape"] > 0:
            train = daily_series[:-test_days]
            test = daily_series[-test_days:]
            ma_train = weighted_moving_average(train, window=window)
            actuals = [float(item[1]) for item in test]
            predictions = [
                float(ma_train["avg_daily"]) * ma_train["day_of_week_factors"].get(item[0].weekday(), 1.0)
                for item in test
            ]
            intervals = compute_prediction_intervals(actuals, predictions)
            if intervals:
                apply_empirical_intervals(ma_forecasts, intervals)

          candidates.append({
              "algorithm": "moving_avg",
              "forecasts": ma_forecasts,
              "params": {
                  "avg_daily": str(ma_result["avg_daily"]),
                  "dow_factors": {str(k): v for k, v in ma_result["day_of_week_factors"].items()},
                  "window": window,
                  "month_factors": month_factors,
              },
              "metrics": ma_metrics,
              "data_points": n,
              "confidence_base": Decimal("70.00"),
          })

    # ── Candidate 2: Theta Method (>= 14 days) ──
    if n >= 14:
        th_metrics = backtest_theta(daily_series, test_days=test_days)
        if th_metrics["mae"] < 998:
            th_result = theta_forecast(daily_series, horizon_days=horizon)
            if th_result is not None:
                th_result["metrics"] = th_metrics
                candidates.append(th_result)

    # ── Candidate 3: Adaptive Moving Average (>= 21 days) ──
    if n >= 21:
        ada_metrics = backtest_adaptive_ma(daily_series, test_days=test_days, month_factors=month_factors)
        if ada_metrics["mae"] < 998:
            ada_result = adaptive_moving_average(daily_series, horizon_days=horizon, month_factors=month_factors)
            if ada_result is not None:
                ada_result["metrics"] = ada_metrics
                candidates.append(ada_result)

    # ── Candidate 4: Holt-Winters (>= 28 days + statsmodels) ──
    if n >= HW_MIN_DAYS:
        hw_metrics = backtest_holt_winters(daily_series, test_days=test_days, stockout_dates=stockout_dates)

        if hw_metrics["mae"] < 998:  # successfully fitted
            hw_result = holt_winters_forecast(daily_series, horizon_days=horizon, stockout_dates=stockout_dates)
            if hw_result is not None:
                candidates.append({
                    "algorithm": "holt_winters",
                    "forecasts": hw_result["forecasts"],
                    "params": hw_result["params"],
                    "metrics": hw_metrics,
                    "data_points": n,
                    "confidence_base": Decimal("80.00"),
                })

    # ── Candidate 5: Holt-Winters Damped (>= 28 days + statsmodels) ──
    if n >= HW_MIN_DAYS:
        hwd_metrics = backtest_hw_damped(daily_series, test_days=test_days, stockout_dates=stockout_dates)

        if hwd_metrics["mae"] < 998:
            hwd_result = holt_winters_damped_forecast(daily_series, horizon_days=horizon, stockout_dates=stockout_dates)
            if hwd_result is not None:
                candidates.append({
                    "algorithm": "hw_damped",
                    "forecasts": hwd_result["forecasts"],
                    "params": hwd_result["params"],
                    "metrics": hwd_metrics,
                    "data_points": n,
                    "confidence_base": Decimal("82.00"),
                })

    # ── Candidate 6: ETS (>= 28 days + statsmodels) ──
    if n >= HW_MIN_DAYS:
        ets_metrics = backtest_ets(daily_series, test_days=test_days, stockout_dates=stockout_dates)
        if ets_metrics["mae"] < 998:
            ets_result = ets_forecast(daily_series, horizon_days=horizon, stockout_dates=stockout_dates)
            if ets_result is not None:
                ets_result["metrics"] = ets_metrics
                candidates.append(ets_result)

    # ── Candidate 7: Croston / SBA (>= 14 days, intermittent demand) ──
    if n >= 14 and demand_pattern in ("intermittent", "lumpy"):
        for use_sba in (False, True):
            cr_metrics = backtest_croston(daily_series, test_days=test_days, use_sba=use_sba)
            if cr_metrics["mae"] < 998:
                cr_result = croston_forecast(daily_series, horizon_days=horizon, use_sba=use_sba)
                if cr_result is not None:
                    cr_result["metrics"] = cr_metrics
                    # Apply bootstrapped intervals for better confidence bounds
                    cr_result = croston_bootstrap_intervals(daily_series, cr_result)
                    candidates.append(cr_result)

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

    # ── Candidate 4: Ensemble (>= 2 viable candidates) ──
    if len(candidates) >= 2 and n >= HW_MIN_DAYS:
        ens = ensemble_forecast(candidates, demand_pattern=demand_pattern)
        if ens:
            candidates.append(ens)

    # ── Pick best: for intermittent use MAE (MAPE unreliable with zeros) ──
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
