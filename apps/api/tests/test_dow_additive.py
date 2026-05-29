"""
Tests F8 — estacionalidad DOW aditiva para demanda intermitente (Mario 29/05/26).

El multiplicativo (predicted = avg × factor) aplana la señal del finde
cuando avg_daily es bajo (intermitentes): avg=0.5 × factor_sábado=2.0 = 1.0,
perdiendo el pico real. El aditivo (avg + offset) lo preserva: 0.5 + 1.5 = 2.0.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from forecast.engine.utils import predict_dow_base, generate_daily_forecasts
from forecast.engine.algorithms.weighted_moving_average import (
    _weighted_moving_average, WeightedMovingAverage,
)


class TestPredictDowBase:
    def test_multiplicative_is_default(self):
        # avg=0.5, factor sábado (dow=5) = 2.0 → 1.0 (multiplicativo)
        assert predict_dow_base(0.5, 5, {5: 2.0}) == pytest.approx(1.0)

    def test_additive_preserves_weekend_signal(self):
        # avg=0.5, offset sábado +1.5 → 2.0 (aditivo preserva la magnitud)
        out = predict_dow_base(0.5, 5, {5: 2.0}, dow_additive={5: 1.5})
        assert out == pytest.approx(2.0)

    def test_additive_never_negative(self):
        # offset muy negativo no puede dar predicción < 0
        assert predict_dow_base(0.5, 0, {}, dow_additive={0: -5.0}) == 0.0

    def test_closed_day_is_zero_both_modes(self):
        assert predict_dow_base(3.0, 6, {6: 0.0}, closed_dows={6}) == 0.0
        assert predict_dow_base(3.0, 6, {6: 2.0}, dow_additive={6: 5.0}, closed_dows={6}) == 0.0


class TestGenerateDailyForecastsAdditive:
    def test_additive_mode_applied(self):
        start = date(2026, 5, 25)  # lunes
        # avg 0.5, sábado (dow5) offset +2 → sábado debe predecir ~2.5, no ~0.5×factor
        fc = generate_daily_forecasts(
            Decimal("0.5"), {d: 1.0 for d in range(7)},
            start, horizon_days=7,
            dow_additive={d: (2.0 if d == 5 else 0.0) for d in range(7)},
        )
        by_dow = {f["date"].weekday(): float(f["qty_predicted"]) for f in fc}
        assert by_dow[5] == pytest.approx(2.5), f"sábado={by_dow[5]}"   # 0.5 + 2.0
        assert by_dow[1] == pytest.approx(0.5), f"martes={by_dow[1]}"    # 0.5 + 0.0

    def test_multiplicative_unchanged_backcompat(self):
        start = date(2026, 5, 25)
        fc = generate_daily_forecasts(
            Decimal("2.0"), {d: (3.0 if d == 5 else 1.0) for d in range(7)},
            start, horizon_days=7,
        )
        by_dow = {f["date"].weekday(): float(f["qty_predicted"]) for f in fc}
        assert by_dow[5] == pytest.approx(6.0)   # 2.0 × 3.0
        assert by_dow[1] == pytest.approx(2.0)   # 2.0 × 1.0


class TestWMAComputesAdditive:
    def _intermittent_series(self):
        """Serie intermitente: vende ~0 entre semana, picos el sábado."""
        base = date(2026, 1, 5)  # lunes
        series = []
        for i in range(70):  # 10 semanas
            d = base + timedelta(days=i)
            if d.weekday() == 5:      # sábado: pico
                qty = 3.0
            elif d.weekday() == 4:    # viernes: algo
                qty = 1.0
            else:
                qty = 0.0
            series.append((d, qty))
        return series

    def test_wma_returns_additive_and_closed(self):
        res = _weighted_moving_average(self._intermittent_series())
        assert "day_of_week_additive" in res
        assert "closed_dows" in res
        add = res["day_of_week_additive"]
        # El sábado (5) debe tener offset aditivo POSITIVO (vende más que el día típico)
        assert add.get(5, 0) > 0, f"sábado additive={add.get(5)}"

    def test_intermittent_weekend_higher_with_additive(self):
        """En demanda intermitente, el forecast del sábado con modo aditivo
        debe ser MAYOR que con multiplicativo (preserva el pico)."""
        series = self._intermittent_series()
        algo = WeightedMovingAverage()
        fc_mult = algo.forecast(series, horizon_days=14, demand_pattern="smooth")
        fc_add = algo.forecast(series, horizon_days=14, demand_pattern="intermittent")

        sat_mult = max(float(f["qty_predicted"]) for f in fc_mult["forecasts"]
                       if f["date"].weekday() == 5)
        sat_add = max(float(f["qty_predicted"]) for f in fc_add["forecasts"]
                      if f["date"].weekday() == 5)
        assert fc_add["params"]["dow_mode"] == "additive"
        assert fc_mult["params"]["dow_mode"] == "multiplicative"
        assert sat_add >= sat_mult, f"aditivo sábado={sat_add} debería >= multiplicativo={sat_mult}"


@pytest.mark.django_db
class TestForecastPipelineWithAdditive:
    """Smoke: el pipeline de selección pasa demand_pattern y no rompe."""

    def test_select_best_model_passes_pattern(self):
        from forecast.engine.selection import select_best_model
        base = date(2026, 1, 5)
        series = []
        for i in range(70):
            d = base + timedelta(days=i)
            qty = 3.0 if d.weekday() == 5 else (1.0 if d.weekday() == 4 else 0.0)
            series.append((d, qty))
        best = select_best_model(series, demand_pattern="intermittent")
        # No debe romper y debe elegir algún algoritmo válido
        assert best is not None
        assert "algorithm" in best
