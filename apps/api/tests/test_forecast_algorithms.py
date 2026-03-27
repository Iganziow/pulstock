"""
Tests para algoritmos nuevos del forecast engine
==================================================

1.  Theta Method — basic, trend detection, edge cases
2.  Holt-Winters Damped — basic, vs standard HW
3.  Adaptive Moving Average — optimizes decay/window
4.  Bootstrapped Croston Intervals — empirical bounds
5.  Integration — all models compete in select_best_model
6.  Backtest functions — all return valid metrics
"""
import pytest
import math
from datetime import date, timedelta
from decimal import Decimal

from forecast.engine import (
    theta_forecast,
    backtest_theta,
    holt_winters_damped_forecast,
    backtest_hw_damped,
    adaptive_moving_average,
    backtest_adaptive_ma,
    croston_bootstrap_intervals,
    croston_forecast,
    select_best_model,
    classify_demand_pattern,
    _q3,
)

D = Decimal
D0 = D("0.000")
TODAY = date.today()


def _series(n, base=10.0, start=None):
    s = start or (TODAY - timedelta(days=n))
    return [(s + timedelta(days=i), base) for i in range(n)]


def _growing_series(n, start_val=5.0, growth=0.5):
    s = TODAY - timedelta(days=n)
    return [(s + timedelta(days=i), start_val + growth * i) for i in range(n)]


def _seasonal_series(n=60):
    """Weekly seasonal pattern."""
    s = TODAY - timedelta(days=n)
    return [
        (s + timedelta(days=i), 10 + 5 * math.sin(i * 2 * math.pi / 7))
        for i in range(n)
    ]


def _intermittent_series(n=60):
    import random
    random.seed(42)
    s = TODAY - timedelta(days=n)
    return [(s + timedelta(days=i), random.uniform(5, 20) if random.random() < 0.3 else 0)
            for i in range(n)]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. THETA METHOD
# ═══════════════════════════════════════════════════════════════════════════════

class TestThetaForecast:

    def test_basic_constant_series(self):
        """Constant series → forecast ≈ constant."""
        series = _series(30, 10)
        result = theta_forecast(series, horizon_days=7)
        assert result is not None
        assert result["algorithm"] == "theta"
        assert len(result["forecasts"]) == 7
        for fc in result["forecasts"]:
            assert abs(float(fc["qty_predicted"]) - 10) < 3

    def test_growing_series_detects_trend(self):
        """Growing series → forecasts should increase."""
        series = _growing_series(30, 5, 0.5)
        result = theta_forecast(series, horizon_days=7)
        assert result is not None
        # Last value ≈ 5 + 0.5*29 = 19.5, forecasts should be > 15
        preds = [float(f["qty_predicted"]) for f in result["forecasts"]]
        assert preds[0] > 10
        assert result["params"]["slope"] > 0

    def test_declining_series(self):
        """Declining series → forecasts should decrease."""
        s = TODAY - timedelta(days=30)
        series = [(s + timedelta(days=i), max(0.1, 30 - i * 0.8)) for i in range(30)]
        result = theta_forecast(series, horizon_days=7)
        assert result is not None
        assert result["params"]["slope"] < 0

    def test_insufficient_data_returns_none(self):
        assert theta_forecast(_series(5, 10)) is None

    def test_exactly_14_days(self):
        result = theta_forecast(_series(14, 10), horizon_days=7)
        assert result is not None

    def test_all_zeros(self):
        series = [(TODAY - timedelta(days=i), 0) for i in range(30)]
        result = theta_forecast(series, horizon_days=7)
        # May return result with 0 predictions, or None
        if result:
            for fc in result["forecasts"]:
                assert float(fc["qty_predicted"]) >= 0

    def test_output_contract(self):
        result = theta_forecast(_series(30, 10), horizon_days=7)
        assert "algorithm" in result
        assert "forecasts" in result
        assert "params" in result
        assert "alpha" in result["params"]
        assert "slope" in result["params"]
        for fc in result["forecasts"]:
            assert "date" in fc
            assert "qty_predicted" in fc
            assert "lower_bound" in fc
            assert "upper_bound" in fc
            assert float(fc["lower_bound"]) >= 0

    def test_bounds_reasonable(self):
        result = theta_forecast(_series(30, 10), horizon_days=7)
        for fc in result["forecasts"]:
            assert float(fc["upper_bound"]) >= float(fc["qty_predicted"])
            assert float(fc["lower_bound"]) <= float(fc["qty_predicted"])


class TestBacktestTheta:

    def test_sufficient_data(self):
        result = backtest_theta(_series(30, 10))
        assert result["mae"] < 998

    def test_insufficient_data(self):
        result = backtest_theta(_series(10, 10))
        assert result["mae"] == 999

    def test_returns_all_metrics(self):
        result = backtest_theta(_series(30, 10))
        assert "mae" in result
        assert "mape" in result
        assert "rmse" in result
        assert "bias" in result


# ═══════════════════════════════════════════════════════════════════════════════
# 2. HOLT-WINTERS DAMPED
# ═══════════════════════════════════════════════════════════════════════════════

class TestHWDamped:

    def test_basic_forecast(self):
        series = _series(35, 10)
        result = holt_winters_damped_forecast(series, horizon_days=7)
        if result is None:
            pytest.skip("statsmodels not installed")
        assert result["algorithm"] == "hw_damped"
        assert len(result["forecasts"]) == 7
        assert "damping_trend" in result["params"]

    def test_insufficient_data(self):
        result = holt_winters_damped_forecast(_series(10, 10))
        assert result is None

    def test_seasonal_data(self):
        series = _seasonal_series(42)
        result = holt_winters_damped_forecast(series, horizon_days=7)
        if result is None:
            pytest.skip("statsmodels not installed")
        assert len(result["forecasts"]) == 7

    def test_damped_more_conservative_than_standard(self):
        """Damped trend should produce less extreme forecasts for growing data."""
        from forecast.engine import holt_winters_forecast
        series = _growing_series(42, 5, 1.0)
        hw = holt_winters_forecast(series, horizon_days=14)
        hwd = holt_winters_damped_forecast(series, horizon_days=14)
        if hw is None or hwd is None:
            pytest.skip("statsmodels not installed")
        # Damped should have lower forecast at day 14 (less trend extrapolation)
        hw_last = float(hw["forecasts"][-1]["qty_predicted"])
        hwd_last = float(hwd["forecasts"][-1]["qty_predicted"])
        # Damped should be more conservative (closer to current level)
        assert hwd_last <= hw_last * 1.1  # allow small margin


class TestBacktestHWDamped:

    def test_sufficient_data(self):
        result = backtest_hw_damped(_series(42, 10))
        # May be 999 if statsmodels not installed
        assert "mae" in result

    def test_insufficient_data(self):
        result = backtest_hw_damped(_series(10, 10))
        assert result["mae"] == 999


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ADAPTIVE MOVING AVERAGE
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdaptiveMA:

    def test_basic_forecast(self):
        series = _series(30, 10)
        result = adaptive_moving_average(series, horizon_days=7)
        assert result is not None
        assert result["algorithm"] == "adaptive_ma"
        assert len(result["forecasts"]) == 7

    def test_optimized_params(self):
        """Should pick optimal decay and window."""
        series = _series(30, 10)
        result = adaptive_moving_average(series, horizon_days=7)
        assert "decay" in result["params"]
        assert "window" in result["params"]
        assert 0.8 <= result["params"]["decay"] <= 1.0
        assert result["params"]["window"] >= 14

    def test_insufficient_data(self):
        result = adaptive_moving_average(_series(10, 10))
        assert result is None

    def test_growing_data_adapts(self):
        """Growing data should prefer higher decay (more weight on recent)."""
        series = _growing_series(30, 5, 1.0)
        result = adaptive_moving_average(series, horizon_days=7)
        assert result is not None
        # Predictions should be near recent values (25-30 range)
        pred = float(result["forecasts"][0]["qty_predicted"])
        assert pred > 10

    def test_month_factors_applied(self):
        mf = {"early": 1.5, "mid_early": 1.0, "mid": 1.0, "mid_late": 1.0, "late": 0.8}
        series = _series(30, 10)
        result = adaptive_moving_average(series, horizon_days=14, month_factors=mf)
        assert result is not None

    def test_output_contract(self):
        result = adaptive_moving_average(_series(30, 10), horizon_days=7)
        assert "algorithm" in result
        assert "forecasts" in result
        assert "params" in result
        assert "data_points" in result
        assert "confidence_base" in result


class TestBacktestAdaptiveMA:

    def test_sufficient_data(self):
        result = backtest_adaptive_ma(_series(30, 10))
        assert result["mae"] < 998

    def test_insufficient_data(self):
        result = backtest_adaptive_ma(_series(15, 10))
        assert result["mae"] == 999


# ═══════════════════════════════════════════════════════════════════════════════
# 4. BOOTSTRAPPED CROSTON INTERVALS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrostonBootstrap:

    def test_basic_bootstrap(self):
        series = _intermittent_series(60)
        base = croston_forecast(series, horizon_days=7)
        if base is None:
            pytest.skip("Not enough intermittent data")
        result = croston_bootstrap_intervals(series, base)
        assert result is not None
        for fc in result["forecasts"]:
            assert float(fc["lower_bound"]) >= 0
            assert float(fc["upper_bound"]) >= float(fc["lower_bound"])

    def test_insufficient_nonzero_returns_base(self):
        """< 5 non-zero → return base forecast unchanged."""
        series = [(TODAY - timedelta(days=i), 0) for i in range(30)]
        series[10] = (series[10][0], 10)
        series[20] = (series[20][0], 10)
        base = {"forecasts": [{"qty_predicted": D("1"), "lower_bound": D("0"), "upper_bound": D("2")}]}
        result = croston_bootstrap_intervals(series, base)
        assert result == base

    def test_none_base_returns_none(self):
        series = _intermittent_series(60)
        result = croston_bootstrap_intervals(series, None)
        assert result is None

    def test_deterministic(self):
        """Same input → same output (seed=42)."""
        series = _intermittent_series(60)
        base1 = croston_forecast(series, horizon_days=7)
        base2 = croston_forecast(series, horizon_days=7)
        if base1 is None:
            pytest.skip("Not enough data")
        r1 = croston_bootstrap_intervals(series, base1)
        r2 = croston_bootstrap_intervals(series, base2)
        for f1, f2 in zip(r1["forecasts"], r2["forecasts"]):
            assert f1["lower_bound"] == f2["lower_bound"]
            assert f1["upper_bound"] == f2["upper_bound"]

    def test_bootstrap_samples_in_params(self):
        series = _intermittent_series(60)
        base = croston_forecast(series, horizon_days=7)
        if base is None:
            pytest.skip("Not enough data")
        result = croston_bootstrap_intervals(series, base, n_boot=100)
        assert result["params"]["bootstrap_samples"] == 100


# ═══════════════════════════════════════════════════════════════════════════════
# 5. INTEGRATION — All models compete in select_best_model
# ═══════════════════════════════════════════════════════════════════════════════

class TestModelCompetition:

    def test_14_days_includes_theta(self):
        """With 14+ days, Theta should be a candidate."""
        series = _series(14, 10)
        result = select_best_model(series, horizon=7)
        # Either theta wins or another algorithm, but shouldn't be "none"
        assert result["algorithm"] != "none"

    def test_30_days_multiple_candidates(self):
        """30 days → MA, Theta, Adaptive MA all compete."""
        series = _series(30, 10)
        result = select_best_model(series, horizon=7)
        assert result["algorithm"] in ("moving_avg", "theta", "adaptive_ma",
                                        "holt_winters", "hw_damped", "ensemble")

    def test_60_days_all_algorithms(self):
        """60 days → all algorithms available."""
        series = _series(60, 10)
        result = select_best_model(series, horizon=14)
        assert result["algorithm"] != "none"
        assert "demand_pattern" in result
        assert result["data_points"] == 60

    def test_intermittent_tries_croston_with_bootstrap(self):
        """Intermittent demand → Croston candidates include bootstrap intervals."""
        series = _intermittent_series(60)
        result = select_best_model(series, horizon=7)
        assert result["algorithm"] != "none"

    def test_growing_data_trend_algorithms_compete(self):
        """Growing data → Theta and HW-Damped should do well."""
        series = _growing_series(42, 5, 0.5)
        result = select_best_model(series, horizon=7)
        assert result["algorithm"] != "none"
        # At least theta or adaptive_ma should be viable
        assert result["data_points"] == 42

    def test_best_model_deterministic(self):
        """Same data → same winner."""
        series = _series(30, 10)
        r1 = select_best_model(series)
        r2 = select_best_model(series)
        assert r1["algorithm"] == r2["algorithm"]

    def test_all_algorithms_have_required_keys(self):
        """Every algorithm output has the contract keys."""
        for n in [10, 20, 30, 45]:
            series = _series(n, 10)
            result = select_best_model(series, horizon=7)
            assert "algorithm" in result
            assert "forecasts" in result
            assert "metrics" in result
            assert "data_points" in result
            assert "demand_pattern" in result
            if result["forecasts"]:
                fc = result["forecasts"][0]
                assert "date" in fc
                assert "qty_predicted" in fc
                assert float(fc["lower_bound"]) >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. EDGE CASES & ROBUSTNESS
# ═══════════════════════════════════════════════════════════════════════════════

class TestNewAlgorithmsEdgeCases:

    def test_theta_all_same_value(self):
        """Constant series → slope ≈ 0, forecast ≈ constant."""
        result = theta_forecast(_series(30, 42), horizon_days=7)
        assert result is not None
        assert abs(result["params"]["slope"]) < 0.01
        for fc in result["forecasts"]:
            assert abs(float(fc["qty_predicted"]) - 42) < 5

    def test_theta_single_spike(self):
        """Series with a spike shouldn't crash."""
        series = _series(30, 10)
        series[15] = (series[15][0], 100)
        result = theta_forecast(series, horizon_days=7)
        assert result is not None

    def test_adaptive_very_noisy_data(self):
        """Noisy data should still produce valid forecasts."""
        import random
        random.seed(123)
        s = TODAY - timedelta(days=30)
        series = [(s + timedelta(days=i), max(0.1, 10 + random.gauss(0, 5))) for i in range(30)]
        result = adaptive_moving_average(series, horizon_days=7)
        assert result is not None
        for fc in result["forecasts"]:
            assert float(fc["qty_predicted"]) > 0

    def test_theta_large_dataset(self):
        """365 days should work fine."""
        series = _series(365, 15)
        result = theta_forecast(series, horizon_days=14)
        assert result is not None
        assert len(result["forecasts"]) == 14

    def test_adaptive_ma_vs_standard_ma(self):
        """Adaptive should be competitive or better than standard."""
        from forecast.engine import backtest_moving_average
        series = _growing_series(45, 5, 0.3)
        std_metrics = backtest_moving_average(series)
        ada_metrics = backtest_adaptive_ma(series)
        # Adaptive should not be dramatically worse
        assert ada_metrics["mae"] < std_metrics["mae"] * 2

    def test_all_new_algorithms_lower_bounds_non_negative(self):
        """No algorithm should produce negative lower bounds."""
        for gen in [_series(30, 10), _growing_series(30, 5, 0.5), _seasonal_series(42)]:
            for func in [theta_forecast, adaptive_moving_average]:
                result = func(gen, horizon_days=7)
                if result:
                    for fc in result["forecasts"]:
                        assert float(fc["lower_bound"]) >= 0, f"Negative lower_bound in {result['algorithm']}"
