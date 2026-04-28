"""
Tests del fix "días cerrados" en el modelo de forecast.

Mario reportó: "no se trabajan los domingos" pero el forecast predecía
3.0 unidades para domingos. La causa: dow_factors[6] caía a 1.0 cuando
no había datos de ventas en domingos, en vez de detectar que el local
está cerrado.

Fix: si el rango del dataset cubre >= 4 ocurrencias de un DOW pero
NO hay ningún registro de venta para ese DOW, asumimos local cerrado
y forzamos factor=0 → forecast=0 ese día.
"""
import datetime
from decimal import Decimal

import pytest


def _series_skipping_sundays(weeks=8, daily_qty=2.0):
    """Genera serie diaria saltándose los domingos (weekday=6)."""
    series = []
    start = datetime.date(2026, 1, 5)  # lunes
    for i in range(weeks * 7):
        d = start + datetime.timedelta(days=i)
        if d.weekday() == 6:  # domingo
            continue
        series.append((d, Decimal(str(daily_qty))))
    return series


class TestWMAClosedDayDetection:
    """weighted_moving_average debe detectar días sin ventas como cerrados."""

    def test_sunday_factor_is_zero_when_never_sold(self):
        from forecast.engine.algorithms.weighted_moving_average import (
            _weighted_moving_average,
        )
        series = _series_skipping_sundays(weeks=8)
        result = _weighted_moving_average(series, window=21)
        dow_factors = result["day_of_week_factors"]
        # 8 semanas × 1 domingo = 8 ocurrencias, mucho más del threshold de 4.
        # → factor 0 (cerrado).
        assert dow_factors[6] == 0.0, \
            f"Domingo deberia ser 0 (cerrado), quedo en {dow_factors[6]}"
        # Otros días con ventas: factor cerca de 1.0 (no exactamente porque
        # avg_daily se calcula con weighted recent, pero rango razonable).
        for d in range(6):
            assert 0.5 <= dow_factors[d] <= 2.0, \
                f"Lun-Sab deberian tener factor cerca 1.0, dia {d}={dow_factors[d]}"

    def test_few_data_no_false_positive(self):
        """Con poca data (< 4 ocurrencias del DOW), no asumir cerrado."""
        from forecast.engine.algorithms.weighted_moving_average import (
            _weighted_moving_average,
        )
        # Solo 2 semanas de datos: solo 2 ocurrencias de domingo.
        # No debería asumirlos como cerrados (puede ser coincidencia).
        series = _series_skipping_sundays(weeks=2)
        result = _weighted_moving_average(series, window=14)
        dow_factors = result["day_of_week_factors"]
        # Domingo: < 4 ocurrencias → fallback a 1.0 (neutral)
        assert dow_factors[6] == 1.0


class TestAdaptiveMAClosedDayDetection:
    """adaptive_moving_average debe respetar el mismo principio."""

    def test_sunday_factor_zero(self):
        from forecast.engine.algorithms.adaptive_moving_average import (
            _adaptive_moving_average,
        )
        series = _series_skipping_sundays(weeks=8)
        result = _adaptive_moving_average(series, horizon_days=14)
        if result is None:
            pytest.skip("adaptive_ma no convergio con esta data")
        dow_factors = result["params"]["dow_factors"]
        # Las keys son strings en el output. Domingo = "6"
        assert dow_factors.get("6") == 0.0 or dow_factors.get(6) == 0.0


class TestForecastZeroOnClosedDay:
    """generate_daily_forecasts: si dow_factor=0, qty_predicted=0."""

    def test_qty_zero_when_factor_zero(self):
        from forecast.engine.utils import generate_daily_forecasts
        # avg_daily=10, todos los días factor 1.0 excepto domingo factor 0
        dow_factors = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 0.0}
        start = datetime.date(2026, 1, 4)  # domingo
        forecasts = generate_daily_forecasts(
            Decimal("10"), dow_factors, start, horizon_days=14,
        )
        # forecast[5] cae en domingo (start + 6 días = sábado, +7 = domingo siguiente)
        for fc in forecasts:
            if fc["date"].weekday() == 6:
                assert fc["qty_predicted"] == Decimal("0.000"), \
                    f"Domingo debe predecir 0, predijo {fc['qty_predicted']}"
                assert fc["lower_bound"] == Decimal("0.000")
                assert fc["upper_bound"] == Decimal("0.000")
            else:
                assert fc["qty_predicted"] > 0, \
                    f"Lun-Sab deben predecir >0, dia {fc['date']} predijo {fc['qty_predicted']}"
