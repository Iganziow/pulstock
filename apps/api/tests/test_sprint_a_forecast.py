"""
Sprint A del motor de forecast (jul 2026) — fixes quirúrgicos:

1. Kept-path compara contra wape_real (producción) cuando existe, no contra
   el WAPE "fósil" del backtest congelado (caso Syrup amaretto 421%).
2. (DESCARTADO conscientemente) Restringir theta/ets/hw a smooth: ya se
   intentó el 01/06/26 y se revirtió (hundía las métricas de ~15
   intermitentes). El semi-colapso se ataca con el fix 4 (wape_total en la
   selección) — ver TestSemiCollapseLosesByRate.
3. Croston usa el alpha tuneado por el grid (antes siempre 0.15) + init por
   mediana (antes primeras 3 obs del régimen más viejo → sub-forecast).
4. wape_total (|Σpred−Σreal|/Σreal): métrica primaria en intermitente/lumpy —
   el acierto día-a-día premia sub-predecir (caso Carne Mechada 42%).
5. Circuit breaker banda simétrica [0.5, 2.5] con blend 0.7×WMA + 0.3×modelo
   (antes solo rescataba <30% — el 42% pasaba "legal" y el 421% no tenía red).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from forecast.engine.algorithms.croston import CrostonForecast, CrostonSBA
from forecast.engine.selection import choose_best
from forecast.engine.utils import _compute_metrics
from forecast.services import _collapse_guard


# ─────────────────────────────────────────────────────────────────────────────
# Fix 4 (reemplazo quirúrgico del descartado fix 2): un theta SEMI-colapsado
# (predice el 30% del nivel — pasa el filtro anti-colapso-total) pierde la
# selección en lumpy porque su wape_total es horrible, aunque su MASE diario
# "se vea" mejor.
# ─────────────────────────────────────────────────────────────────────────────

def _candidate(algorithm, *, daily_qty, mase, wape_total, mae, horizon=14):
    today = date(2026, 7, 1)
    return {
        "algorithm": algorithm,
        "forecasts": [
            {"date": today + timedelta(days=i + 1), "qty_predicted": daily_qty,
             "lower_bound": daily_qty, "upper_bound": daily_qty}
            for i in range(horizon)
        ],
        "params": {},
        "metrics": {"mase": mase, "wape_total": wape_total, "mae": mae,
                    "wape": 60.0, "mape": 60.0, "tracking_signal": 0},
        "data_points": 60,
        "confidence_base": Decimal("65.00"),
    }


class TestSemiCollapseLosesByRate:
    def test_semi_collapsed_theta_loses_to_croston_in_lumpy(self):
        # theta semi-colapsado: predice poco → MASE diario bajo (0.5) pero
        # tasa desastrosa (wape_total 70). Croston clava la tasa (15).
        theta = _candidate("theta", daily_qty=1.0, mase=0.5, wape_total=70.0, mae=1.0)
        croston = _candidate("croston_sba", daily_qty=3.3, mase=0.9, wape_total=15.0, mae=2.0)
        best = choose_best([theta, croston], "lumpy")
        assert best["algorithm"] == "croston_sba", (
            "con wape_total primario, el semi-colapso pierde aunque su MASE diario sea mejor"
        )

    def test_theta_with_good_rate_can_still_win(self):
        # theta con tasa BUENA (legítimo en lumpy — por esto no se lo veta):
        # gana el override si su wape_total es claramente mejor.
        theta = _candidate("theta", daily_qty=3.2, mase=0.6, wape_total=8.0, mae=1.2)
        croston = _candidate("croston_sba", daily_qty=3.3, mase=0.9, wape_total=20.0, mae=2.0)
        best = choose_best([theta, croston], "lumpy")
        assert best["algorithm"] == "theta"


# ─────────────────────────────────────────────────────────────────────────────
# Fix 3: Croston usa best_alpha
# ─────────────────────────────────────────────────────────────────────────────

def _intermittent_series(days=60, every=4, qty=6.0):
    today = date(2026, 7, 1)
    return [
        (today - timedelta(days=days - i), qty if i % every == 0 else 0.0)
        for i in range(days)
    ]


class TestCrostonAlpha:
    def test_forecast_uses_tuned_alpha(self):
        series = _intermittent_series()
        res = CrostonForecast().forecast(series, horizon_days=7, best_alpha=0.30)
        assert res["params"]["alpha"] == 0.30

    def test_forecast_defaults_when_no_tuned_alpha(self):
        series = _intermittent_series()
        res = CrostonSBA().forecast(series, horizon_days=7)
        assert res["params"]["alpha"] == 0.15

    def test_median_init_resists_old_regime(self):
        """Serie cuyo régimen viejo era chico (2) y el actual es grande (10):
        el init por mediana arranca del nivel típico, no de las primeras 3
        ventas del régimen muerto → forecast más cerca del régimen actual."""
        today = date(2026, 7, 1)
        series = []
        for i in range(60):
            d = today - timedelta(days=60 - i)
            if i % 3 != 0:
                series.append((d, 0.0))
            else:
                series.append((d, 2.0 if i < 15 else 10.0))  # 5 eventos viejos, 15 nuevos
        res = CrostonForecast().forecast(series, horizon_days=7)
        avg_daily = float(res["params"]["avg_daily"].replace(",", ".")) if isinstance(res["params"]["avg_daily"], str) else float(res["params"]["avg_daily"])
        # tasa real reciente ≈ 10/3 ≈ 3.33/día; con init de primeras 3 (todas
        # de 2.0) y alpha 0.15 quedaba muy por debajo. Exigimos ≥ 2.2/día.
        assert avg_daily >= 2.2, f"avg_daily={avg_daily} — init sigue anclado al régimen viejo"


# ─────────────────────────────────────────────────────────────────────────────
# Fix 4: wape_total
# ─────────────────────────────────────────────────────────────────────────────

class TestWapeTotal:
    def test_measures_rate_not_daily_hits(self):
        # Real: 10 unidades en 3 días (lumpy). Predecir 0 "gana" por MAE
        # diario, pero por tasa es un desastre; predecir 3.33/día es la tasa.
        m_zeros = _compute_metrics([10, 0, 0], [0, 0, 0])
        m_rate = _compute_metrics([10, 0, 0], [3.33, 3.33, 3.34])
        assert m_zeros["mae"] < m_rate["mae"]            # el sesgo del día a día
        assert m_zeros["wape_total"] == 100.0            # tasa: 0 de 10
        assert m_rate["wape_total"] == 0.0               # tasa clavada
        assert m_rate["wape_total"] < m_zeros["wape_total"]

    def test_sentinel_and_zero_cases(self):
        assert _compute_metrics([0, 0], [0, 0])["wape_total"] == 0
        assert _compute_metrics([0, 0], [5, 5])["wape_total"] == 999


# ─────────────────────────────────────────────────────────────────────────────
# Fix 5: breaker simétrico con blend
# ─────────────────────────────────────────────────────────────────────────────

def _fc(today, horizon, qty):
    return [{"date": today + timedelta(days=i + 1),
             "qty_predicted": qty, "lower_bound": qty, "upper_bound": qty}
            for i in range(horizon)]


def _flat_series(today, days, qty):
    return [(today - timedelta(days=days - i), qty) for i in range(days)]


class TestSymmetricBreaker:
    def test_underforecast_42pct_now_fires(self):
        """El caso Carne Mechada: forecast al 42% del real. Antes pasaba
        'legal' (umbral 30%); ahora la banda [0.5, 2.5] lo corrige."""
        today = date(2026, 7, 1)
        raw = _flat_series(today, 30, 10.0)          # demanda real 10/día
        best = {"forecasts": _fc(today, 14, 4.2), "params": {}, "algorithm": "theta"}
        out = _collapse_guard(best, raw, today, 14)
        assert out["params"].get("circuit_breaker"), "42% debe disparar ahora"
        q = float(out["forecasts"][0]["qty_predicted"])
        assert q > 4.2, f"el blend debe subir el forecast hacia la demanda, q={q}"

    def test_overshoot_fires_and_blends_down(self):
        """El caso Syrup amaretto: la demanda cayó y el forecast quedó pegado
        arriba (>2.5×). Antes no había rescate por sobre-forecast."""
        today = date(2026, 7, 1)
        raw = _flat_series(today, 30, 2.0)           # demanda real 2/día
        best = {"forecasts": _fc(today, 14, 10.0), "params": {}, "algorithm": "croston_sba"}
        out = _collapse_guard(best, raw, today, 14)
        cb = out["params"].get("circuit_breaker")
        assert cb and cb["reason"] == "overshoot_vs_recent_demand"
        q = float(out["forecasts"][0]["qty_predicted"])
        assert q < 10.0, "el blend debe bajar el sobre-forecast"
        assert q > 2.0, "pero no colapsarlo al WMA puro (blend 70/30)"

    def test_within_band_untouched(self):
        today = date(2026, 7, 1)
        raw = _flat_series(today, 30, 10.0)
        best = {"forecasts": _fc(today, 14, 8.0), "params": {}, "algorithm": "adaptive_ma"}
        out = _collapse_guard(best, raw, today, 14)   # ratio 0.8 → dentro de banda
        assert "circuit_breaker" not in out["params"]
        assert float(out["forecasts"][0]["qty_predicted"]) == 8.0


# ─────────────────────────────────────────────────────────────────────────────
# Fix 1: kept-path usa wape_real (integración)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def noisy_product(db, tenant, warehouse_a):
    from catalog.models import Product, Unit
    from forecast.models import DailySales
    u, _ = Unit.objects.get_or_create(
        tenant=tenant, code="UN", defaults={"name": "Unidad", "family": "COUNT"},
    )
    p = Product.objects.create(tenant=tenant, name="Syrup-like", unit_obj=u, is_active=True)
    today = date.today()
    noise = [1, 5, 2, 6, 3]
    for i in range(70, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() == 6:
            continue
        DailySales.objects.create(
            tenant=tenant, product=p, warehouse=warehouse_a,
            date=d, qty_sold=Decimal(str(noise[i % len(noise)])), forecast_only=False,
        )
    return p


@pytest.mark.django_db
class TestKeptPathUsesWapeReal:
    def test_fossil_wape_beaten_by_wape_real(self, tenant, warehouse_a, noisy_product):
        """Modelo viejo con WAPE fósil imbatible (5%) PERO wape_real horrible
        (300%, medido en producción) → el kept-path debe soltarlo."""
        from django.core.management import call_command
        from forecast.models import ForecastModel
        legacy = ForecastModel.objects.create(
            tenant=tenant, product=noisy_product, warehouse=warehouse_a,
            algorithm="adaptive_ma", version=1, is_active=True,
            model_params={"avg_daily": "3"},
            metrics={"wape": 5.0, "mae": 0.1, "mape": 5,
                     "wape_real": 300.0, "wape_real_samples": 14},
            data_points=60, demand_pattern="smooth",
            confidence_label="high", confidence_reason="(fósil)",
        )
        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)
        active = ForecastModel.objects.filter(
            tenant=tenant, product=noisy_product, is_active=True,
        ).first()
        assert active is not None
        assert active.id != legacy.id, (
            "Con wape_real=300% el modelo fósil debe ser reemplazado aunque "
            "su WAPE de backtest congelado (5%) sea imbatible."
        )

    def test_without_wape_real_kept_still_protects(self, tenant, warehouse_a, noisy_product):
        """Sin wape_real (modelo joven), el kept sigue usando el WAPE de
        backtest y conserva un modelo imbatible — no rompemos la estabilidad."""
        from django.core.management import call_command
        from forecast.models import ForecastModel
        legacy = ForecastModel.objects.create(
            tenant=tenant, product=noisy_product, warehouse=warehouse_a,
            algorithm="adaptive_ma", version=1, is_active=True,
            model_params={"avg_daily": "3"},
            metrics={"wape": 5.0, "mae": 0.1, "mape": 5},
            data_points=60, demand_pattern="smooth",
            confidence_label="high", confidence_reason="(joven)",
        )
        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)
        active = ForecastModel.objects.filter(
            tenant=tenant, product=noisy_product, is_active=True,
        ).first()
        assert active is not None and active.id == legacy.id
