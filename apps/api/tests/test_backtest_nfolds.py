"""
F21.2 (18/06/26): el backtest usa 8 folds (antes 3).

Con 3 folds × 7 días el estimado evaluaba solo ~21 días → oscilaba noche a
noche por una sola semana atípica. Con 8 folds (~56 días) el estimado es más
estable. El cambio es centralizado en selection.N_FOLDS y se pasa explícito a
cada algoritmo.
"""
from datetime import date, timedelta

from forecast.engine import selection
from forecast.engine.algorithms.adaptive_moving_average import AdaptiveMovingAverage
from forecast.engine.algorithms.croston import _backtest_croston


def test_n_folds_constant_is_8():
    assert selection.N_FOLDS == 8


def test_select_best_model_forwards_8_folds(monkeypatch):
    """La selección pasa n_folds=8 a cada backtest (no se queda en el default 3)."""
    captured = []

    def spy(self, daily_series, test_days=7, n_folds=3, **kwargs):
        captured.append(n_folds)
        return {"mae": 999, "mape": 999, "wape": 999, "rmse": 999,
                "bias": 0, "mase": 999, "smape": 999, "tracking_signal": 0}

    monkeypatch.setattr(AdaptiveMovingAverage, "backtest", spy)
    series = [(date(2026, 1, 1) + timedelta(days=i), 10.0) for i in range(70)]
    selection.select_best_model(series, demand_pattern="smooth")
    assert captured, "adaptive_ma.backtest no fue invocado"
    assert all(nf == 8 for nf in captured), f"esperaba n_folds=8, got {captured}"


def test_croston_backtest_runs_with_8_folds():
    """Con 70 días e intermitencia, Croston corre los 8 folds y devuelve métricas
    válidas (no 'insuficiente')."""
    base = date(2026, 1, 1)
    series = [(base + timedelta(days=i), float(2 if i % 6 == 0 else 0)) for i in range(70)]
    m = _backtest_croston(series, test_days=7, n_folds=8)
    assert m["mae"] < 998, f"esperaba métricas válidas, got {m}"


def test_short_history_auto_caps_folds():
    """Producto con poca historia: el loop corta solo, sin error (usa menos folds)."""
    base = date(2026, 1, 1)
    # 30 días → no alcanza para 8 folds completos; debe cortar sin romper.
    series = [(base + timedelta(days=i), float(2 if i % 5 == 0 else 0)) for i in range(30)]
    m = _backtest_croston(series, test_days=7, n_folds=8)
    # No exige métricas válidas (puede ser poca data), pero NO debe explotar.
    assert "mae" in m
