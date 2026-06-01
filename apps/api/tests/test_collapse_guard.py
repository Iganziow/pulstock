"""
Test del circuit breaker anti-colapso (_collapse_guard) — Mario 31/05/26.

Caso real: "Leche deslactosada" vendía ~400 u/día pero el modelo predecía 0
(theta colapsó tras un cambio de escala del producto). El guard detecta el
colapso (forecast despreciable vs demanda real reciente) y reemplaza por un
fallback robusto. NO debe disparar en intermitentes legítimos.
"""
from datetime import date, timedelta

import pytest

from forecast.services import _collapse_guard


def _fc(today, horizon, qty):
    """Construye una lista de forecasts planos."""
    return [{"date": today + timedelta(days=i + 1),
             "qty_predicted": qty, "lower_bound": qty, "upper_bound": qty}
            for i in range(horizon)]


def _series(today, days, qty_fn):
    return [(today - timedelta(days=days - i), qty_fn(i)) for i in range(days)]


class TestCollapseGuard:
    def test_collapsed_forecast_is_rescued(self):
        """Demanda reciente ~400/día pero forecast 0 → reemplaza por fallback >0."""
        today = date(2026, 5, 31)
        horizon = 14
        # Serie reciente: vende ~400/día los últimos 12 días
        raw = _series(today, 30, lambda i: 400.0 if i >= 18 else 0.5)
        best = {"forecasts": _fc(today, horizon, 0.0), "params": {}, "algorithm": "theta"}

        out = _collapse_guard(best, raw, today, horizon)
        fc_total = sum(float(f["qty_predicted"]) for f in out["forecasts"])
        assert fc_total > 0, "el guard debe rescatar el forecast colapsado"
        assert "circuit_breaker" in out["params"]
        # El fallback debe estar en el orden de la demanda reciente (~400/día)
        avg = fc_total / horizon
        assert avg > 50, f"fallback debe reflejar el régimen reciente, avg={avg}"

    def test_normal_forecast_untouched(self):
        """Forecast que acompaña la demanda real → no se toca."""
        today = date(2026, 5, 31)
        horizon = 14
        raw = _series(today, 30, lambda i: 100.0)   # vende 100/día estable
        best = {"forecasts": _fc(today, horizon, 95.0), "params": {}, "algorithm": "moving_avg"}

        out = _collapse_guard(best, raw, today, horizon)
        assert "circuit_breaker" not in out["params"], "no debe disparar con forecast sano"
        assert float(out["forecasts"][0]["qty_predicted"]) == 95.0

    def test_intermittent_not_triggered(self):
        """Intermitente legítimo (vende de a poco): el total del forecast
        acompaña al total real → NO dispara aunque haya muchos ceros."""
        today = date(2026, 5, 31)
        horizon = 14
        # Vende 5 unidades 1 de cada 5 días (intermitente)
        raw = _series(today, 30, lambda i: 5.0 if i % 5 == 0 else 0.0)
        # Forecast intermitente coherente: ~1/día (5 cada 5 días)
        best = {"forecasts": _fc(today, horizon, 1.0), "params": {}, "algorithm": "croston"}

        out = _collapse_guard(best, raw, today, horizon)
        assert "circuit_breaker" not in out["params"], "no debe disparar en intermitente legítimo"

    def test_low_volume_not_triggered(self):
        """Producto de muy baja demanda (total < umbral) no dispara aunque fc=0."""
        today = date(2026, 5, 31)
        horizon = 14
        raw = _series(today, 30, lambda i: 0.3)  # casi nada
        best = {"forecasts": _fc(today, horizon, 0.0), "params": {}, "algorithm": "theta"}

        out = _collapse_guard(best, raw, today, horizon)
        assert "circuit_breaker" not in out["params"], "demanda chica → no rescatar (ruido)"

    def test_no_forecasts_safe(self):
        today = date(2026, 5, 31)
        best = {"forecasts": [], "params": {}}
        out = _collapse_guard(best, [], today, 14)
        assert out["forecasts"] == []
