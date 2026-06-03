"""
Fixes 01/06/26 (Mario) — colapso de "helado ingrediente" (90 u/día reales,
forecast 0). Dos causas y dos fixes:

  1. apply_bias_correction sin tope → una accuracy ruidosa (mean_bias=426 con
     avg_daily=141) generaba corrección > demanda → clampeaba el forecast a 0.
     Fix: tope MAX_BIAS_CORRECTION_FRAC del avg_daily.
  2. _collapse_guard no corría en el path de derivados (train_ingredient_product)
     → nada rescataba el forecast colapsado. Fix: aplicar el guard también ahí.
"""
from datetime import date, timedelta
from decimal import Decimal

from forecast.engine.enhancements import apply_bias_correction, MAX_BIAS_CORRECTION_FRAC
from forecast.services import _collapse_guard


def _fc(today, n, qty):
    return [
        {
            "date": today + timedelta(days=i + 1),
            "qty_predicted": Decimal(str(qty)),
            "lower_bound": Decimal(str(qty)) * Decimal("0.7"),
            "upper_bound": Decimal(str(qty)) * Decimal("1.3"),
        }
        for i in range(n)
    ]


def _acc(today, n, error):
    """n días de accuracy con el mismo error (predicted - actual)."""
    return [
        {"date": today - timedelta(days=i + 1), "error": float(error), "was_stockout": False}
        for i in range(n)
    ]


class TestBiasCorrectionCap:
    def test_garbage_bias_does_not_zero_forecast(self):
        """Caso helado: avg_daily=141, error sistemático 426 → NO debe zerear."""
        today = date(2026, 6, 1)
        avg = Decimal("141")
        forecasts = _fc(today, 14, 141)
        accuracy = _acc(today, 10, 426)  # sobre-predicción absurda (>avg)
        result = apply_bias_correction(forecasts, accuracy, avg)
        assert result != 0.0, "debió aplicar corrección (capada), no skip"
        # Con tope 0.5*avg=70.5 → 141-70.5=70.5; nunca 0.
        for fc in forecasts:
            assert float(fc["qty_predicted"]) >= float(avg) * MAX_BIAS_CORRECTION_FRAC - 0.01
            assert float(fc["qty_predicted"]) > 0, "el forecast jamás debe colapsar a 0 por bias"
        # La corrección global guardada está capada.
        assert abs(result["global"]) <= float(avg) * MAX_BIAS_CORRECTION_FRAC + 0.01

    def test_normal_over_prediction_still_corrects(self):
        """Regresión: un sesgo razonable se sigue corrigiendo (sin romper lo previo)."""
        today = date(2026, 6, 1)
        forecasts = _fc(today, 7, 20)
        accuracy = _acc(today, 7, 5)  # over-pred moderado, < avg(10)... cap=5
        result = apply_bias_correction(forecasts, accuracy, Decimal("10"))
        assert result != 0.0
        assert float(forecasts[0]["qty_predicted"]) < 20.0, "debe reducir el over-pred"

    def test_under_prediction_increases(self):
        """Sub-predicción (error negativo) → debe AUMENTAR el forecast."""
        today = date(2026, 6, 1)
        forecasts = _fc(today, 7, 6)
        accuracy = _acc(today, 7, -4)  # under-pred
        before = float(forecasts[0]["qty_predicted"])
        result = apply_bias_correction(forecasts, accuracy, Decimal("10"))
        assert result != 0.0
        assert float(forecasts[0]["qty_predicted"]) > before, "under-pred debe subir el forecast"

    def test_cap_magnitude_never_exceeds_fraction(self):
        """El tope se respeta para cualquier sesgo gigante."""
        today = date(2026, 6, 1)
        avg = Decimal("100")
        forecasts = _fc(today, 7, 100)
        accuracy = _acc(today, 8, 9999)
        result = apply_bias_correction(forecasts, accuracy, avg)
        assert abs(result["global"]) <= float(avg) * MAX_BIAS_CORRECTION_FRAC + 0.01


class TestDerivedCollapseGuard:
    def test_guard_rescues_collapsed_derived(self):
        """Forecast ~0 con consumo real alto → el guard lo reemplaza por WMA."""
        today = date(2026, 6, 1)
        # consumo real ~90/día los últimos 21 días
        raw_series = [(today - timedelta(days=i + 1), 90.0) for i in range(21)]
        collapsed = _fc(today, 14, 0.001)
        best = {"forecasts": collapsed, "params": {}}
        out = _collapse_guard(best, raw_series, today, 14, product=None)
        fc_total = sum(float(f["qty_predicted"]) for f in out["forecasts"][:14])
        assert fc_total > 100, f"el guard debió rescatar (fc_total={fc_total})"
        assert out["params"].get("circuit_breaker"), "debe registrar el circuit_breaker"

    def test_guard_leaves_healthy_derived(self):
        """Forecast sano que acompaña la demanda → el guard NO interviene."""
        today = date(2026, 6, 1)
        raw_series = [(today - timedelta(days=i + 1), 90.0) for i in range(21)]
        healthy = _fc(today, 14, 90)
        best = {"forecasts": healthy, "params": {}}
        out = _collapse_guard(best, raw_series, today, 14, product=None)
        assert not out["params"].get("circuit_breaker"), "no debe disparar en forecast sano"
        assert float(out["forecasts"][0]["qty_predicted"]) == 90.0

    def test_guard_ignores_dormant_product(self):
        """Producto dormido (consumo real bajo) → no rescata aunque forecast sea 0."""
        today = date(2026, 6, 1)
        raw_series = [(today - timedelta(days=i + 1), 0.0) for i in range(21)]
        collapsed = _fc(today, 14, 0.0)
        best = {"forecasts": collapsed, "params": {}}
        out = _collapse_guard(best, raw_series, today, 14, product=None)
        assert not out["params"].get("circuit_breaker"), "dormido legítimo, no rescatar"
