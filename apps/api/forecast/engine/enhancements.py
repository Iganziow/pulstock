"""
Forecast enhancement functions — applied as post-processing.

Includes: month-position factors, monthly/bimodal seasonality, YoY growth,
trend detection, bias correction, holiday adjustments, holiday learning,
price elasticity, confidence decay.
"""
from datetime import date, timedelta
from decimal import Decimal
import math

from .utils import _q3, _get_month_bucket

SEASONALITY_MIN_DAYS = 180
YOY_MIN_DAYS = 365


# ── Month-position factors (payday effect) ───────────────────────────────────

def compute_month_position_factors(daily_series, min_days=45):
    """Detect monthly demand patterns (payday effect, Chile: salary 25th-30th)."""
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

    vals = list(factors.values())
    min_val = min(vals)
    if min_val <= 0 or max(vals) / min_val < 1.15:
        return None

    return factors


# ── Monthly seasonality (annual cycle) ───────────────────────────────────────

def compute_monthly_seasonality(daily_series, min_days=SEASONALITY_MIN_DAYS):
    """Compute month-of-year demand factors from historical data."""
    if len(daily_series) < min_days:
        return None

    monthly_values = {}
    for item in daily_series:
        d = item[0]
        qty = float(item[1])
        monthly_values.setdefault(d.month, []).append(qty)

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

    vals_with_data = [(m, v) for m, v in factors.items() if monthly_values.get(m)]
    if not vals_with_data:
        return None

    vals = [v for _, v in vals_with_data]
    min_val = min(vals)
    if min_val <= 0 or max(vals) / min_val < 1.20:
        return None

    for month in range(1, 13):
        n_obs = len(monthly_values.get(month, []))
        if 0 < n_obs < 15:
            shrink = n_obs / 15.0
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


# ── Bimodal seasonality ──────────────────────────────────────────────────────

def compute_bimodal_seasonality(daily_series, min_days=120):
    """Detect bimodal seasonality (warm Oct-Mar vs cold Apr-Sep for Chile)."""
    if len(daily_series) < min_days:
        return None

    warm_months = {10, 11, 12, 1, 2, 3}

    warm_vals, cold_vals = [], []
    monthly_values = {}
    for item in daily_series:
        d, qty = item[0], float(item[1])
        monthly_values.setdefault(d.month, []).append(qty)
        if d.month in warm_months:
            warm_vals.append(qty)
        else:
            cold_vals.append(qty)

    if not warm_vals or not cold_vals:
        return None
    if len(monthly_values) < 4:
        return None

    warm_avg = sum(warm_vals) / len(warm_vals)
    cold_avg = sum(cold_vals) / len(cold_vals)
    if cold_avg <= 0 or warm_avg <= 0:
        return None

    ratio = max(warm_avg, cold_avg) / min(warm_avg, cold_avg)
    if ratio < 2.0:
        return None

    overall_avg = sum(float(item[1]) for item in daily_series) / len(daily_series)
    if overall_avg <= 0:
        return None

    factors = {}
    for month in range(1, 13):
        values = monthly_values.get(month, [])
        if values:
            month_avg = sum(values) / len(values)
            raw = month_avg / overall_avg
            factors[month] = round(max(0.1, min(4.0, raw)), 3)
        else:
            if month in warm_months:
                factors[month] = round(warm_avg / overall_avg, 3)
            else:
                factors[month] = round(cold_avg / overall_avg, 3)

    return factors


# ── Year-over-year growth ────────────────────────────────────────────────────

def compute_yoy_growth(daily_series, min_days=YOY_MIN_DAYS):
    """Compare this year's demand vs same period last year."""
    if len(daily_series) < min_days:
        return None

    today = daily_series[-1][0]
    one_year_ago = today - timedelta(days=365)

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
    growth_rate = max(0.5, min(2.0, growth_rate))
    if abs(growth_rate - 1.0) < 0.10:
        return None

    return {
        "growth_rate": round(growth_rate, 3),
        "this_year_avg": round(this_avg, 3),
        "last_year_avg": round(last_avg, 3),
    }


def apply_yoy_adjustment(forecasts, yoy_info, damping=0.5):
    """Apply year-over-year growth adjustment to forecasts."""
    if not yoy_info:
        return
    raw_rate = yoy_info["growth_rate"]
    factor = 1.0 + (raw_rate - 1.0) * damping
    for fc in forecasts:
        fc["qty_predicted"] = _q3(float(fc["qty_predicted"]) * factor)
        fc["lower_bound"] = _q3(max(0, float(fc["lower_bound"]) * factor))
        fc["upper_bound"] = _q3(float(fc["upper_bound"]) * factor)


# ── Confidence decay ─────────────────────────────────────────────────────────

def compute_confidence_decay(trained_at, base_confidence, half_life_days=14):
    """Reduce confidence score for stale models. Exponential decay."""
    today = date.today()

    if hasattr(trained_at, 'date') and callable(trained_at.date):
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


# ── Linear trend detection ───────────────────────────────────────────────────

def detect_trend(daily_series, min_days=28):
    """Detect linear trend via OLS on weekly aggregates."""
    if len(daily_series) < min_days:
        return None

    weekly = {}
    for item in daily_series:
        d = item[0]
        iso_week = d.isocalendar()[0] * 100 + d.isocalendar()[1]
        weekly.setdefault(iso_week, []).append(float(item[1]))

    if len(weekly) < 4:
        return None

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

    y_mean = sum_y / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    slope_per_day = slope / 7.0

    mean_daily = sum(float(item[1]) for item in daily_series) / len(daily_series)
    if r_squared < 0.3 or mean_daily <= 0:
        return None
    if abs(slope_per_day) / mean_daily < 0.005:
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
    """Multiply forecasts by trend factor."""
    if not trend_info or float(avg_daily) <= 0:
        return
    slope = trend_info["slope_per_day"]
    avg = float(avg_daily)

    for i, fc in enumerate(forecasts):
        days_ahead = i + 1
        factor = 1.0 + slope * days_ahead / avg
        factor = max(0.5, min(2.0, factor))
        fc["qty_predicted"] = _q3(float(fc["qty_predicted"]) * factor)
        fc["lower_bound"] = _q3(max(0, float(fc["lower_bound"]) * factor))
        fc["upper_bound"] = _q3(float(fc["upper_bound"]) * factor)


# ── Price elasticity signal ──────────────────────────────────────────────────

def detect_price_change_impact(daily_series, revenue_series=None):
    """Detect if price changes correlate with demand changes."""
    if revenue_series is None or len(revenue_series) < 14:
        return None

    price_map = {}
    for d, rev in revenue_series:
        rev_f = float(rev)
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

        if abs(pct_change) > 0.10:
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

                if pct_change > 0.10 and demand_change < -0.15:
                    events.append({
                        "date": str(dates[i]),
                        "price_change_pct": round(pct_change * 100, 1),
                        "demand_change_pct": round(demand_change * 100, 1),
                    })

    return {
        "is_price_sensitive": len(events) > 0,
        "events": events[:5],
    }


# ── Holiday adjustments ──────────────────────────────────────────────────────

def apply_holiday_adjustments(forecasts, holidays, business_type=None):
    """Post-process forecasts by applying holiday demand multipliers."""
    holiday_map = {}
    for h in holidays:
        biz_mults = getattr(h, 'business_multipliers', None) or (h.get('business_multipliers') if isinstance(h, dict) else None) or {}
        if business_type and business_type in biz_mults:
            configured = float(biz_mults[business_type])
        else:
            configured = float(h.demand_multiplier) if hasattr(h, 'demand_multiplier') else float(h.get('demand_multiplier', 1))

        learned = None
        if hasattr(h, 'learned_multiplier') and h.learned_multiplier is not None:
            learned = float(h.learned_multiplier)
        elif isinstance(h, dict) and h.get('learned_multiplier') is not None:
            learned = float(h['learned_multiplier'])

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

        duration = int(getattr(h, 'duration_days', None) or (h.get('duration_days', 1) if isinstance(h, dict) else 1))
        for d in range(duration):
            event_date = h_date + timedelta(days=d)
            holiday_map[event_date] = mult

        ramp = getattr(h, 'ramp_type', None) or (h.get('ramp_type', 'instant') if isinstance(h, dict) else 'instant')
        for d in range(1, pre_days + 1):
            pre_date = h_date - timedelta(days=d)
            if pre_date not in holiday_map:
                if ramp == "linear":
                    pct = 1.0 - (d / (pre_days + 1))
                    ramped = 1.0 + (pre_mult - 1.0) * pct
                    holiday_map[pre_date] = ramped
                else:
                    holiday_map[pre_date] = pre_mult

        post_d = int(getattr(h, 'post_days', None) or (h.get('post_days', 0) if isinstance(h, dict) else 0))
        post_mult = float(getattr(h, 'post_multiplier', None) or (h.get('post_multiplier', 0.85) if isinstance(h, dict) else 0.85))
        if post_d > 0:
            for d in range(1, post_d + 1):
                post_date = h_date + timedelta(days=duration - 1 + d)
                if post_date not in holiday_map:
                    recovery = post_mult + (1.0 - post_mult) * (d / (post_d + 1))
                    holiday_map[post_date] = recovery

    for fc in forecasts:
        fc_date = fc["date"]
        mult = holiday_map.get(fc_date)
        if mult and mult != 1:
            mult_d = Decimal(str(mult))
            fc["qty_predicted"] = _q3(fc["qty_predicted"] * mult_d)
            fc["lower_bound"] = _q3(fc["lower_bound"] * mult_d)
            fc["upper_bound"] = _q3(fc["upper_bound"] * mult_d)

    return forecasts


def compute_holiday_learned_multiplier(daily_series, holiday_date, window=7):
    """Compute a learned demand multiplier for a holiday from historical data."""
    date_map = {}
    for item in daily_series:
        d = item[0]
        q = float(item[1])
        date_map[d] = q

    holiday_demand = date_map.get(holiday_date)
    if holiday_demand is None or holiday_demand <= 0:
        return None

    baseline_values = []
    for offset in range(-window, window + 1):
        if abs(offset) <= 1:
            continue
        check_date = holiday_date + timedelta(days=offset)
        val = date_map.get(check_date)
        if val is not None and val > 0:
            baseline_values.append(val)

    if len(baseline_values) < 3:
        return None

    baseline_avg = sum(baseline_values) / len(baseline_values)
    if baseline_avg <= 0:
        return None

    multiplier = holiday_demand / baseline_avg
    return max(0.2, min(5.0, round(multiplier, 2)))


# ── Bias correction ──────────────────────────────────────────────────────────

def apply_bias_correction(forecasts, recent_accuracy, avg_daily):
    """Auto-correct forecasts based on recent prediction errors."""
    if not recent_accuracy or float(avg_daily) <= 0:
        return 0.0

    errors = [
        (a["date"], float(a["error"]))
        for a in recent_accuracy
        if not a.get("was_stockout")
    ]
    if len(errors) < 5:
        return 0.0

    all_errors = [e for _, e in errors]
    mean_bias = sum(all_errors) / len(all_errors)

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
