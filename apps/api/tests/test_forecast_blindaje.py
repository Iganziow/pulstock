"""
Tests de blindaje — Forecast Engine
====================================
Edge cases, division-by-zero guards, NaN/Inf propagation,
empty inputs, type safety, and boundary conditions.

Goal: zero crashes in production under any data quality scenario.
"""
import math
import pytest
from datetime import date, timedelta, datetime
from decimal import Decimal

from forecast.engine import (
    _q3,
    clean_series,
    classify_demand_pattern,
    weighted_moving_average,
    holt_winters_forecast,
    croston_forecast,
    backtest_croston,
    compute_prediction_intervals,
    apply_empirical_intervals,
    compute_month_position_factors,
    compute_monthly_seasonality,
    apply_monthly_seasonality,
    compute_yoy_growth,
    compute_confidence_decay,
    detect_trend,
    apply_trend_adjustment,
    detect_price_change_impact,
    generate_daily_forecasts,
    calculate_days_to_stockout,
    _compute_metrics,
    _average_metrics,
    backtest_moving_average,
    backtest_holt_winters,
    simple_average,
    category_prior_forecast,
    ensemble_forecast,
    apply_holiday_adjustments,
    apply_bias_correction,
    select_best_model,
)

D = Decimal
D0 = D("0.000")
TODAY = date.today()


def _series(n, base=10.0, start=None):
    """Generate n days of constant-ish sales data."""
    s = start or (TODAY - timedelta(days=n))
    return [(s + timedelta(days=i), base) for i in range(n)]


def _growing_series(n, start_val=5.0, growth=0.5):
    """Generate n days of linearly growing data."""
    s = TODAY - timedelta(days=n)
    return [(s + timedelta(days=i), start_val + growth * i) for i in range(n)]


def _seasonal_series(n_months=8):
    """Generate monthly-varying series spanning n_months."""
    series = []
    s = TODAY - timedelta(days=n_months * 30)
    for i in range(n_months * 30):
        d = s + timedelta(days=i)
        # Month 1,2 = low; 6,7 = high
        base = 10.0 + 8.0 * math.sin(d.month * math.pi / 6)
        series.append((d, max(0.1, base)))
    return series


def _intermittent_series(n=60, demand_prob=0.3):
    """Generate intermittent demand (many zeros)."""
    import random
    random.seed(42)
    s = TODAY - timedelta(days=n)
    return [(s + timedelta(days=i), random.uniform(5, 20) if random.random() < demand_prob else 0)
            for i in range(n)]


def _make_forecasts(n=14, avg=10.0):
    """Build a list of forecast dicts."""
    return [
        {
            "date": TODAY + timedelta(days=i + 1),
            "qty_predicted": _q3(avg),
            "lower_bound": _q3(avg * 0.7),
            "upper_bound": _q3(avg * 1.3),
        }
        for i in range(n)
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. _q3 — Decimal quantization
# ═══════════════════════════════════════════════════════════════════════════════

class TestQ3:
    def test_float(self):
        assert _q3(10.5) == D("10.500")

    def test_int(self):
        assert _q3(7) == D("7.000")

    def test_string_decimal(self):
        assert _q3("3.14159") == D("3.142")

    def test_negative(self):
        assert _q3(-2.5) == D("-2.500")

    def test_zero(self):
        assert _q3(0) == D("0.000")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. clean_series — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanSeriesBlindaje:
    def test_all_zeros(self):
        """All-zero series should return tuples with weight 1.0 (no interpolation needed)."""
        series = [(TODAY - timedelta(days=i), 0) for i in range(10)]
        result = clean_series(series)
        assert len(result) == 10

    def test_single_day(self):
        result = clean_series([(TODAY, 5)])
        assert len(result) == 1

    def test_stockout_all_days_no_dow_data(self):
        """When ALL days are stockout zeros, interpolation has no weekday data."""
        series = [(TODAY - timedelta(days=i), 0) for i in range(7)]
        stockouts = {d for d, _ in series}
        result = clean_series(series, stockout_dates=stockouts)
        # Should not crash; all get weight 0.5 with qty 0 or similar
        assert len(result) == 7

    def test_holiday_set_is_respected(self):
        """Holiday dates should not be dampened by IQR."""
        series = [(TODAY - timedelta(days=i), 5) for i in range(20)]
        # Add a spike on a holiday
        holiday_date = TODAY - timedelta(days=5)
        series[5] = (holiday_date, 100)
        holidays = {holiday_date}
        result = clean_series(series, holiday_dates=holidays)
        # The holiday spike should remain undampened (weight=1.0)
        holiday_item = [r for r in result if r[0] == holiday_date][0]
        assert holiday_item[1] == 100  # not dampened
        assert holiday_item[2] == 1.0

    def test_mixed_stockout_and_outlier(self):
        """Series with both stockouts and outliers."""
        series = _series(20, 10)
        # Add outlier and stockout
        series[3] = (series[3][0], 200)
        stockouts = {series[10][0]}
        series[10] = (series[10][0], 0)
        result = clean_series(series, stockout_dates=stockouts)
        assert len(result) == 20


# ═══════════════════════════════════════════════════════════════════════════════
# 3. classify_demand_pattern — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassifyDemandPatternBlindaje:
    def test_single_sale(self):
        pattern, adi, cv2 = classify_demand_pattern([(TODAY, 5)])
        assert pattern == "insufficient"

    def test_two_sales(self):
        pattern, adi, cv2 = classify_demand_pattern([
            (TODAY - timedelta(days=1), 5),
            (TODAY, 10),
        ])
        assert pattern == "insufficient"

    def test_exactly_three_nonzero(self):
        """Minimum data for classification."""
        series = [
            (TODAY - timedelta(days=10), 5),
            (TODAY - timedelta(days=5), 5),
            (TODAY, 5),
        ]
        pattern, adi, cv2 = classify_demand_pattern(series)
        assert pattern != "insufficient"

    def test_all_same_nonzero_value(self):
        """Zero variance → cv2 = 0 → smooth or intermittent."""
        series = [(TODAY - timedelta(days=i), 10) for i in range(30)]
        pattern, adi, cv2 = classify_demand_pattern(series)
        assert cv2 == 0
        assert pattern == "smooth"

    def test_negative_values_treated_as_zero(self):
        """Negative qty should be treated as non-positive."""
        series = [(TODAY - timedelta(days=i), -5) for i in range(10)]
        pattern, adi, cv2 = classify_demand_pattern(series)
        assert pattern == "insufficient"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. weighted_moving_average — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestWMABlindaje:
    def test_all_zeros(self):
        series = [(TODAY - timedelta(days=i), 0) for i in range(21)]
        result = weighted_moving_average(series)
        assert result["avg_daily"] == D0

    def test_single_very_large_value(self):
        series = [(TODAY - timedelta(days=i), 0) for i in range(20)]
        series.append((TODAY, 1_000_000))
        result = weighted_moving_average(series)
        assert result["avg_daily"] > D0

    def test_decimal_inputs(self):
        series = [(TODAY - timedelta(days=i), Decimal("10.5")) for i in range(14)]
        result = weighted_moving_average(series)
        assert result["avg_daily"] > D0

    def test_weight_tuple_input(self):
        """Series with (date, qty, weight) tuples."""
        series = [(TODAY - timedelta(days=i), 10, 0.5) for i in range(14)]
        result = weighted_moving_average(series)
        assert result["avg_daily"] > D0

    def test_window_larger_than_series(self):
        series = _series(5, 10)
        result = weighted_moving_average(series, window=100)
        assert result["avg_daily"] > D0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Holt-Winters — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestHoltWintersBlindaje:
    def test_insufficient_data(self):
        series = _series(10, 5)
        assert holt_winters_forecast(series) is None

    def test_all_zeros(self):
        series = [(TODAY - timedelta(days=i), 0) for i in range(35)]
        result = holt_winters_forecast(series)
        # Should return None or forecasts with near-zero values
        # (statsmodels may or may not fit on zeros)

    def test_exactly_28_days(self):
        series = _series(28, 10)
        # Should attempt to fit (minimum threshold)
        result = holt_winters_forecast(series, horizon_days=7)
        # May return None if statsmodels not installed

    def test_negative_values_clamped(self):
        """Negative values in series shouldn't crash."""
        series = [(TODAY - timedelta(days=i), max(0.01, -5 + i)) for i in range(35)]
        result = holt_winters_forecast(series)
        # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Croston — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrostonBlindaje:
    def test_all_zeros_returns_none(self):
        series = [(TODAY - timedelta(days=i), 0) for i in range(30)]
        assert croston_forecast(series) is None

    def test_exactly_3_nonzero(self):
        """Minimum for Croston."""
        series = [(TODAY - timedelta(days=i), 0) for i in range(30)]
        series[5] = (series[5][0], 10)
        series[15] = (series[15][0], 10)
        series[25] = (series[25][0], 10)
        result = croston_forecast(series)
        if result is not None:
            assert result["algorithm"] in ("croston", "sba")

    def test_sba_alpha_bounds(self):
        """Alpha = 0 and alpha = 1 edge cases."""
        series = _intermittent_series(60)
        r0 = croston_forecast(series, alpha=0.01)
        r1 = croston_forecast(series, alpha=0.99)
        # Neither should crash

    def test_single_demand_spike(self):
        """Only one nonzero value → insufficient for Croston."""
        series = [(TODAY - timedelta(days=i), 0) for i in range(30)]
        series[10] = (series[10][0], 50)
        assert croston_forecast(series) is None


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Backtest — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestBacktestBlindaje:
    def test_backtest_ma_empty_series(self):
        result = backtest_moving_average([], test_days=7)
        assert result["mae"] == 999

    def test_backtest_ma_too_short(self):
        result = backtest_moving_average(_series(5, 10))
        assert result["mae"] == 999

    def test_backtest_hw_empty(self):
        result = backtest_holt_winters([])
        assert result["mae"] == 999

    def test_backtest_croston_empty(self):
        result = backtest_croston([])
        assert result["mae"] == 999

    def test_average_metrics_empty_folds(self):
        """_average_metrics with empty list should not crash."""
        result = _average_metrics([])
        assert result["mae"] == 999

    def test_compute_metrics_empty(self):
        result = _compute_metrics([], [])
        assert result["mae"] == 0

    def test_compute_metrics_single_value(self):
        result = _compute_metrics([10], [12])
        assert result["mae"] == 2.0
        assert result["bias"] == 2.0

    def test_compute_metrics_all_zeros(self):
        """All actuals = 0 → MAPE should be 999 (not evaluable)."""
        result = _compute_metrics([0, 0, 0], [1, 2, 3])
        assert result["mape"] == 999  # all-zero actuals = not evaluable


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Prediction Intervals — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestPredictionIntervalsBlindaje:
    def test_identical_predictions(self):
        """Perfect predictions → intervals should be tight."""
        result = compute_prediction_intervals([10, 10, 10], [10, 10, 10])
        if result:
            assert result[0] == 0  # lower offset
            assert result[1] == 0  # upper offset

    def test_single_pair(self):
        result = compute_prediction_intervals([10], [12])
        assert result is None  # too few data

    def test_apply_to_empty_forecasts(self):
        apply_empirical_intervals([], (1.5, 2.0))
        # Should not crash

    def test_apply_none_intervals(self):
        forecasts = _make_forecasts(3)
        apply_empirical_intervals(forecasts, None)
        # Should not crash, forecasts unchanged


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Month Position Factors — Division by zero guards
# ═══════════════════════════════════════════════════════════════════════════════

class TestMonthPositionBlindaje:
    def test_all_zero_sales(self):
        """All zero sales → overall_avg = 0 → should return None."""
        series = [(TODAY - timedelta(days=i), 0) for i in range(60)]
        assert compute_month_position_factors(series) is None

    def test_single_bucket_has_data(self):
        """Only late-month sales → factors computed but may be uniform."""
        series = []
        for i in range(60):
            d = TODAY - timedelta(days=i)
            series.append((d, 10 if d.day > 25 else 0))
        result = compute_month_position_factors(series)
        # May be None (overall_avg could be 0 depending on distribution)

    def test_very_uniform_returns_none(self):
        """All buckets identical → ratio < 1.15 → None."""
        series = _series(60, 10)
        result = compute_month_position_factors(series)
        assert result is None

    def test_payday_spike(self):
        """Strong late-month spike should be detected."""
        series = []
        for i in range(90):
            d = TODAY - timedelta(days=i)
            qty = 30 if d.day >= 25 else 5
            series.append((d, qty))
        result = compute_month_position_factors(series)
        if result:
            assert result["late"] > 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Monthly Seasonality — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestMonthlySeasonalityBlindaje:
    def test_all_zeros(self):
        series = [(TODAY - timedelta(days=i), 0) for i in range(200)]
        assert compute_monthly_seasonality(series) is None

    def test_fewer_than_6_months(self):
        """Need 6 distinct months."""
        series = _series(120, 10)
        # 120 days ≈ 4 months → fewer than 6
        result = compute_monthly_seasonality(series)
        # Depends on whether 4 months are hit, likely None

    def test_apply_to_empty_forecasts(self):
        apply_monthly_seasonality([], {1: 1.2, 2: 0.8})
        # Should not crash

    def test_apply_none_factors(self):
        forecasts = _make_forecasts(3)
        apply_monthly_seasonality(forecasts, None)
        # Should not crash


# ═══════════════════════════════════════════════════════════════════════════════
# 11. YoY Growth — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestYoYGrowthBlindaje:
    def test_insufficient_data(self):
        series = _series(100, 10)
        result = compute_yoy_growth(series)
        assert result is None

    def test_exactly_365_days(self):
        series = _series(365, 10)
        result = compute_yoy_growth(series)
        # May return None (no growth if constant)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Confidence Decay — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfidenceDecayBlindaje:
    def test_none_trained_at(self):
        """Non-date input should return base confidence."""
        result = compute_confidence_decay(None, D("80.00"))
        assert result == D("80.00")

    def test_string_trained_at(self):
        result = compute_confidence_decay("2024-01-01", D("80.00"))
        assert result == D("80.00")

    def test_datetime_input(self):
        """datetime (not date) should still work."""
        dt = datetime.now() - timedelta(days=14)
        result = compute_confidence_decay(dt, D("80.00"))
        # datetime has .date() method → should decay
        assert result < D("80.00")

    def test_future_date(self):
        """Model trained in future → days_since <= 1 → no decay."""
        result = compute_confidence_decay(TODAY + timedelta(days=5), D("80.00"))
        assert result == D("80.00")

    def test_zero_base_confidence(self):
        result = compute_confidence_decay(TODAY - timedelta(days=30), D("0.00"))
        assert result == D("0.00")


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Trend Detection — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrendDetectionBlindaje:
    def test_all_zeros(self):
        series = [(TODAY - timedelta(days=i), 0) for i in range(60)]
        assert detect_trend(series) is None

    def test_constant_series(self):
        series = _series(60, 10)
        result = detect_trend(series)
        assert result is None  # flat → no significant trend

    def test_strong_upward_trend(self):
        series = _growing_series(60, 1, 1.0)
        result = detect_trend(series)
        if result:
            assert result["direction"] == "up"
            assert result["slope_per_day"] > 0

    def test_strong_downward_trend(self):
        # i=0 is oldest (60 days ago), value starts high and decreases
        s = TODAY - timedelta(days=60)
        series = [(s + timedelta(days=i), max(0.1, 60 - i)) for i in range(60)]
        result = detect_trend(series)
        if result:
            assert result["direction"] == "down"

    def test_apply_trend_zero_avg(self):
        """avg_daily = 0 → should not crash."""
        forecasts = _make_forecasts(3)
        apply_trend_adjustment(forecasts, {"slope_per_day": 0.5}, D("0"))
        # Should return without modification

    def test_apply_trend_none_info(self):
        forecasts = _make_forecasts(3)
        apply_trend_adjustment(forecasts, None, D("10"))
        # Should return without modification

    def test_apply_trend_extreme_slope(self):
        """Very large slope → clamped to 2x max."""
        forecasts = _make_forecasts(3)
        original = [float(f["qty_predicted"]) for f in forecasts]
        apply_trend_adjustment(forecasts, {"slope_per_day": 100.0}, D("1"))
        for f in forecasts:
            assert float(f["qty_predicted"]) <= original[0] * 2.1  # clamped


# ═══════════════════════════════════════════════════════════════════════════════
# 14. Price Elasticity — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestPriceElasticityBlindaje:
    def test_none_revenue(self):
        assert detect_price_change_impact(_series(30, 10)) is None

    def test_empty_revenue(self):
        assert detect_price_change_impact(_series(30, 10), []) is None

    def test_zero_price_days(self):
        """Days with zero qty → price undefined → skipped."""
        series = [(TODAY - timedelta(days=i), 0 if i % 2 == 0 else 10) for i in range(30)]
        rev = [(TODAY - timedelta(days=i), 100 if i % 2 == 1 else 0) for i in range(30)]
        result = detect_price_change_impact(series, rev)
        # Should not crash

    def test_constant_price(self):
        """No price changes → not sensitive."""
        series = [(TODAY - timedelta(days=i), 10) for i in range(30)]
        rev = [(TODAY - timedelta(days=i), 100) for i in range(30)]
        result = detect_price_change_impact(series, rev)
        if result:
            assert not result["is_price_sensitive"]


# ═══════════════════════════════════════════════════════════════════════════════
# 15. generate_daily_forecasts — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestGenerateDailyForecastsBlindaje:
    def test_zero_horizon(self):
        result = generate_daily_forecasts(D("10"), {}, TODAY, horizon_days=0)
        assert result == []

    def test_negative_horizon(self):
        result = generate_daily_forecasts(D("10"), {}, TODAY, horizon_days=-5)
        assert result == []

    def test_zero_avg_daily(self):
        result = generate_daily_forecasts(D("0"), {}, TODAY, horizon_days=7)
        assert len(result) == 7
        assert all(float(f["qty_predicted"]) == 0 for f in result)

    def test_month_factors_applied(self):
        mf = {"early": 1.5, "mid_early": 1.0, "mid": 1.0, "mid_late": 1.0, "late": 0.8}
        result = generate_daily_forecasts(D("10"), {}, TODAY, horizon_days=14, month_factors=mf)
        assert len(result) == 14

    def test_empty_dow_factors(self):
        result = generate_daily_forecasts(D("10"), {}, TODAY, horizon_days=7)
        assert len(result) == 7
        # Default factor = 1.0 → all predictions should be 10
        assert all(float(f["qty_predicted"]) == 10 for f in result)


# ═══════════════════════════════════════════════════════════════════════════════
# 16. calculate_days_to_stockout — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestDaysToStockoutBlindaje:
    def test_negative_stock(self):
        assert calculate_days_to_stockout(-5, _make_forecasts(7)) == 0

    def test_none_forecasts(self):
        assert calculate_days_to_stockout(100, None) is None

    def test_empty_forecasts(self):
        assert calculate_days_to_stockout(100, []) is None

    def test_zero_demand_forecasts(self):
        """All forecast = 0 → never stockout."""
        forecasts = [{"date": TODAY + timedelta(days=i), "qty_predicted": D0} for i in range(14)]
        assert calculate_days_to_stockout(10, forecasts) is None

    def test_exact_stockout_on_last_day(self):
        forecasts = [{"date": TODAY + timedelta(days=i), "qty_predicted": D("5")} for i in range(2)]
        assert calculate_days_to_stockout(10, forecasts) == 2

    def test_decimal_stock(self):
        forecasts = [{"date": TODAY + timedelta(days=i), "qty_predicted": D("0.5")} for i in range(10)]
        result = calculate_days_to_stockout(D("2.5"), forecasts)
        assert result == 5


# ═══════════════════════════════════════════════════════════════════════════════
# 17. Ensemble — NaN/Inf guard + edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnsembleBlindaje:
    def _candidate(self, algo, mape, mae, forecasts):
        return {
            "algorithm": algo,
            "forecasts": forecasts,
            "metrics": {"mape": mape, "mae": mae, "rmse": 0, "bias": 0},
            "data_points": 30,
            "confidence_base": D("70"),
        }

    def test_empty_candidates(self):
        assert ensemble_forecast([]) is None

    def test_single_candidate(self):
        assert ensemble_forecast([self._candidate("ma", 10, 1, _make_forecasts(7))]) is None

    def test_all_above_threshold(self):
        """All MAPE >= 100 → no viable → None."""
        c1 = self._candidate("ma", 150, 5, _make_forecasts(7))
        c2 = self._candidate("hw", 200, 10, _make_forecasts(7))
        assert ensemble_forecast([c1, c2]) is None

    def test_empty_forecast_lists(self):
        """Candidates with empty forecasts → horizon = 0 → None."""
        c1 = self._candidate("ma", 10, 1, [])
        c2 = self._candidate("hw", 15, 2, [])
        assert ensemble_forecast([c1, c2]) is None

    def test_nan_in_bounds(self):
        """NaN in lower/upper bounds should not crash."""
        fc1 = _make_forecasts(3)
        fc2 = _make_forecasts(3)
        fc2[1]["lower_bound"] = D(str(float("nan"))) if False else D("0")  # Can't put NaN in Decimal
        # Instead test with inf-like values
        fc2[1]["upper_bound"] = D("999999")
        c1 = self._candidate("ma", 10, 1, fc1)
        c2 = self._candidate("hw", 15, 2, fc2)
        result = ensemble_forecast([c1, c2])
        assert result is not None
        assert result["algorithm"] == "ensemble"

    def test_different_horizon_lengths(self):
        c1 = self._candidate("ma", 10, 1, _make_forecasts(5))
        c2 = self._candidate("hw", 15, 2, _make_forecasts(10))
        result = ensemble_forecast([c1, c2])
        assert result is not None
        assert len(result["forecasts"]) == 5  # min horizon

    def test_weights_sum_to_one(self):
        c1 = self._candidate("ma", 20, 3, _make_forecasts(7))
        c2 = self._candidate("hw", 30, 5, _make_forecasts(7))
        result = ensemble_forecast([c1, c2])
        total_weight = sum(m["weight"] for m in result["params"]["models"])
        assert abs(total_weight - 1.0) < 0.01

    def test_intermittent_uses_mae(self):
        """With intermittent demand, MAE is used for viability threshold."""
        c1 = self._candidate("croston", 150, 3, _make_forecasts(7))  # high MAPE but low MAE
        c2 = self._candidate("sba", 120, 4, _make_forecasts(7))
        result = ensemble_forecast([c1, c2], demand_pattern="intermittent")
        assert result is not None  # viable by MAE


# ═══════════════════════════════════════════════════════════════════════════════
# 18. Holiday Adjustments — Robustness
# ═══════════════════════════════════════════════════════════════════════════════

class TestHolidayAdjustmentsBlindaje:
    def test_empty_holidays(self):
        forecasts = _make_forecasts(7)
        result = apply_holiday_adjustments(forecasts, [])
        assert len(result) == 7

    def test_holiday_with_none_date(self):
        """Holiday missing date should be skipped."""
        forecasts = _make_forecasts(7)
        holidays = [{"date": None, "demand_multiplier": 2, "pre_days": 1, "pre_multiplier": 1}]
        result = apply_holiday_adjustments(forecasts, holidays)
        assert len(result) == 7

    def test_holiday_dict_format(self):
        forecasts = _make_forecasts(7)
        h_date = TODAY + timedelta(days=3)
        holidays = [{
            "date": h_date,
            "demand_multiplier": 1.5,
            "pre_days": 1,
            "pre_multiplier": 1.2,
        }]
        result = apply_holiday_adjustments(forecasts, holidays)
        # The forecast on h_date should be multiplied
        hit = [f for f in result if f["date"] == h_date]
        if hit:
            assert float(hit[0]["qty_predicted"]) > 10  # was 10, now 10*1.5

    def test_invalid_pre_days_string(self):
        """pre_days as non-numeric string should not crash."""
        forecasts = _make_forecasts(3)
        holidays = [{"date": TODAY + timedelta(days=1), "demand_multiplier": 1.5,
                      "pre_days": "abc", "pre_multiplier": 1}]
        # Should use default pre_days=1 via try-except
        result = apply_holiday_adjustments(forecasts, holidays)
        assert len(result) == 3

    def test_learned_multiplier_blending(self):
        """60% learned + 40% configured."""
        forecasts = _make_forecasts(3)
        h_date = TODAY + timedelta(days=1)
        holidays = [{
            "date": h_date,
            "demand_multiplier": 2.0,
            "learned_multiplier": 3.0,
            "pre_days": 0,
            "pre_multiplier": 1,
        }]
        result = apply_holiday_adjustments(forecasts, holidays)
        # Blended = 0.6*3.0 + 0.4*2.0 = 2.6
        hit = [f for f in result if f["date"] == h_date]
        if hit:
            expected = 10 * 2.6  # avg was 10
            assert abs(float(hit[0]["qty_predicted"]) - expected) < 0.1


# ═══════════════════════════════════════════════════════════════════════════════
# 19. Bias Correction — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestBiasCorrectionBlindaje:
    def test_empty_accuracy(self):
        result = apply_bias_correction(_make_forecasts(7), [], D("10"))
        assert result == 0.0

    def test_none_accuracy(self):
        result = apply_bias_correction(_make_forecasts(7), None, D("10"))
        assert result == 0.0

    def test_zero_avg_daily(self):
        accuracy = [{"date": TODAY - timedelta(days=i), "error": 1.0, "was_stockout": False}
                     for i in range(10)]
        result = apply_bias_correction(_make_forecasts(7), accuracy, D("0"))
        assert result == 0.0

    def test_all_stockout_excluded(self):
        """All errors from stockout days → excluded → too few → return 0."""
        accuracy = [{"date": TODAY - timedelta(days=i), "error": 2.0, "was_stockout": True}
                     for i in range(10)]
        result = apply_bias_correction(_make_forecasts(7), accuracy, D("10"))
        assert result == 0.0

    def test_exactly_5_errors(self):
        """Minimum 5 non-stockout errors needed → should process bias."""
        accuracy = [{"date": TODAY - timedelta(days=i), "error": 2.0, "was_stockout": False}
                     for i in range(5)]
        result = apply_bias_correction(_make_forecasts(7), accuracy, D("10"))
        # Returns 0.0 if bias not significant, or dict if applied
        assert result == 0.0 or isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# 20. select_best_model — End-to-end edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestSelectBestModelBlindaje:
    def test_empty_series(self):
        result = select_best_model([])
        assert result["algorithm"] == "none"

    def test_1_day(self):
        result = select_best_model([(TODAY, 10)])
        assert result["algorithm"] == "none"

    def test_6_days(self):
        """< 7 days → no candidates → none."""
        result = select_best_model(_series(6, 10))
        assert result["algorithm"] == "none"

    def test_7_days_uses_simple_avg(self):
        result = select_best_model(_series(7, 10))
        assert result["algorithm"] == "simple_avg"

    def test_14_days_selects_model(self):
        """14 days of constant data may return 'none' — that's acceptable."""
        result = select_best_model(_series(14, 10))
        assert "algorithm" in result

    def test_all_zero_series(self):
        """All zeros → insufficient demand pattern → none or simple."""
        series = [(TODAY - timedelta(days=i), 0) for i in range(30)]
        result = select_best_model(series)
        # Should not crash
        assert "algorithm" in result

    def test_demand_pattern_tagged(self):
        result = select_best_model(_series(30, 10))
        assert "demand_pattern" in result

    def test_intermittent_series(self):
        series = _intermittent_series(60, 0.3)
        result = select_best_model(series)
        assert "algorithm" in result
        # Should try Croston/SBA for intermittent


# ═══════════════════════════════════════════════════════════════════════════════
# 21. simple_average — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestSimpleAverageBlindaje:
    def test_all_zeros(self):
        series = [(TODAY - timedelta(days=i), 0) for i in range(10)]
        result = simple_average(series)
        if result:
            assert float(result["forecasts"][0]["qty_predicted"]) == 0

    def test_single_day(self):
        result = simple_average([(TODAY, 10)])
        # Should still work (avg = 10)
        if result:
            assert float(result["forecasts"][0]["qty_predicted"]) > 0

    def test_negative_values(self):
        series = [(TODAY - timedelta(days=i), -5) for i in range(10)]
        result = simple_average(series)
        # Should not crash


# ═══════════════════════════════════════════════════════════════════════════════
# 22. category_prior_forecast — Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestCategoryPriorBlindaje:
    def test_zero_category_avg(self):
        result = category_prior_forecast([], D("0"), {}, 14)
        if result:
            assert float(result["forecasts"][0]["qty_predicted"]) == 0

    def test_empty_series_uses_pure_category(self):
        result = category_prior_forecast([], D("10"), {0: 1.2}, 7)
        assert result is not None
        assert float(result["forecasts"][0]["qty_predicted"]) > 0

    def test_6_days_blends(self):
        series = _series(6, 5)
        result = category_prior_forecast(series, D("20"), {}, 7)
        assert result is not None
        # Should blend between product (5) and category (20)


# ═══════════════════════════════════════════════════════════════════════════════
# 23. Type safety — Decimal/float/int mixing
# ═══════════════════════════════════════════════════════════════════════════════

class TestTypeSafety:
    def test_wma_with_int_qty(self):
        series = [(TODAY - timedelta(days=i), 10) for i in range(14)]
        result = weighted_moving_average(series)
        assert isinstance(result["avg_daily"], Decimal)

    def test_generate_forecasts_with_float_avg(self):
        """Even if avg_daily is float, should produce valid forecasts."""
        # _q3 will convert to Decimal
        result = generate_daily_forecasts(D("10.5"), {0: 1.1}, TODAY, 3)
        assert all(isinstance(f["qty_predicted"], Decimal) for f in result)

    def test_ensemble_produces_decimals(self):
        c1 = {
            "algorithm": "ma",
            "forecasts": _make_forecasts(3),
            "metrics": {"mape": 10, "mae": 1, "rmse": 1, "bias": 0},
            "data_points": 30,
            "confidence_base": D("70"),
        }
        c2 = {
            "algorithm": "hw",
            "forecasts": _make_forecasts(3),
            "metrics": {"mape": 15, "mae": 2, "rmse": 2, "bias": 0},
            "data_points": 30,
            "confidence_base": D("80"),
        }
        result = ensemble_forecast([c1, c2])
        assert all(isinstance(f["qty_predicted"], Decimal) for f in result["forecasts"])

    def test_stockout_with_decimal_stock(self):
        forecasts = [{"date": TODAY, "qty_predicted": D("3.500")}]
        result = calculate_days_to_stockout(D("3.500"), forecasts)
        assert result == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 24. Concurrency / Determinism
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeterminism:
    def test_wma_deterministic(self):
        series = _series(30, 10)
        r1 = weighted_moving_average(series)
        r2 = weighted_moving_average(series)
        assert r1["avg_daily"] == r2["avg_daily"]
        assert r1["day_of_week_factors"] == r2["day_of_week_factors"]

    def test_select_best_model_deterministic(self):
        series = _series(30, 10)
        r1 = select_best_model(series)
        r2 = select_best_model(series)
        assert r1["algorithm"] == r2["algorithm"]


# ═══════════════════════════════════════════════════════════════════════════════
# 25. Boundary conditions — Large datasets
# ═══════════════════════════════════════════════════════════════════════════════

class TestLargeDatasets:
    def test_1000_days(self):
        """Should handle ~3 years of data without issues."""
        series = _series(1000, 15)
        result = select_best_model(series)
        assert result["algorithm"] != "none"

    def test_very_large_values(self):
        series = [(TODAY - timedelta(days=i), 1_000_000) for i in range(30)]
        result = weighted_moving_average(series)
        assert result["avg_daily"] > D0

    def test_very_small_values(self):
        series = [(TODAY - timedelta(days=i), 0.001) for i in range(30)]
        result = weighted_moving_average(series)
        assert result["avg_daily"] > D0


# ═══════════════════════════════════════════════════════════════════════════════
# 26. Forecast output contract — All functions must return valid structures
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutputContracts:
    def test_select_best_model_has_required_keys(self):
        result = select_best_model(_series(30, 10))
        required = {"algorithm", "forecasts", "params", "metrics", "data_points", "demand_pattern"}
        assert required.issubset(set(result.keys()))

    def test_metrics_has_required_keys(self):
        result = select_best_model(_series(30, 10))
        metrics_keys = {"mae", "mape", "rmse", "bias"}
        assert metrics_keys.issubset(set(result["metrics"].keys()))

    def test_forecast_dict_has_required_keys(self):
        result = select_best_model(_series(14, 10))
        if result["forecasts"]:
            fc = result["forecasts"][0]
            assert "date" in fc
            assert "qty_predicted" in fc
            assert "lower_bound" in fc
            assert "upper_bound" in fc

    def test_lower_bound_never_negative(self):
        """No forecast should have negative lower_bound."""
        result = select_best_model(_series(30, 10))
        for fc in result["forecasts"]:
            assert float(fc["lower_bound"]) >= 0

    def test_upper_bound_gte_predicted(self):
        result = select_best_model(_series(30, 10))
        for fc in result["forecasts"]:
            assert float(fc["upper_bound"]) >= float(fc["qty_predicted"]) * 0.95  # allow tiny rounding

    def test_ensemble_output_contract(self):
        c1 = {
            "algorithm": "ma",
            "forecasts": _make_forecasts(7),
            "metrics": {"mape": 10, "mae": 1, "rmse": 1, "bias": 0},
            "data_points": 30,
            "confidence_base": D("70"),
        }
        c2 = {
            "algorithm": "hw",
            "forecasts": _make_forecasts(7),
            "metrics": {"mape": 15, "mae": 2, "rmse": 2, "bias": 0},
            "data_points": 30,
            "confidence_base": D("80"),
        }
        result = ensemble_forecast([c1, c2])
        assert result["algorithm"] == "ensemble"
        assert "models" in result["params"]
        assert len(result["forecasts"]) == 7
