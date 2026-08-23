"""
Breaker-streak (jul 2026): si el circuit breaker rescata al MISMO producto
N noches consecutivas (BREAKER_STREAK_FORCE_RETRAIN=3), el modelo primario
está roto de verdad → se bypassea el kept-path y se fuerza la selección
fresca, igual que pattern_changed.

Caso real: Carne Mechada predecía 10.3 vs 465 de demanda real; el breaker lo
parchaba cada noche pero el kept-path conservaba el modelo roto (su WAPE
histórico, medido en otro régimen, "ganaba" la comparación) → nadie
reentrenaba nunca.

También cubre el agujero descubierto al implementarlo: _regen_from_existing
(último paso de AMBOS paths) re-ejecuta el algoritmo crudo y sobreescribía
los forecasts SIN pasar por el guard → el rescate del breaker se perdía.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from catalog.models import Product, Unit
from forecast.models import DailySales, ForecastModel, Forecast
from forecast.services import _regen_from_existing, BREAKER_STREAK_FORCE_RETRAIN


@pytest.fixture
def steady_product(db, tenant, warehouse_a):
    """Producto con demanda RUIDOSA (1..6, cerrado domingos): el backtest de
    cualquier modelo nuevo da WAPE alto (~40%+), así el legacy con WAPE=5%
    es imbatible y el kept-path aplica — que es lo que queremos ejercitar."""
    u, _ = Unit.objects.get_or_create(
        tenant=tenant, code="UN", defaults={"name": "Unidad", "family": "COUNT"},
    )
    p = Product.objects.create(
        tenant=tenant, name="Mechada-like", unit_obj=u, is_active=True,
    )
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


def _legacy_model(tenant, product, warehouse, *, streak, wape=5.0):
    """Modelo 'imbatible' por WAPE (5%) — normalmente el kept lo conservaría."""
    params = {"avg_daily": "3"}
    if streak:
        params["circuit_breaker"] = {"reason": "collapsed_vs_recent_demand"}
        params["circuit_breaker_streak"] = streak
    return ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm="adaptive_ma", version=1, is_active=True,
        model_params=params,
        metrics={"wape": wape, "mae": 0.1, "mape": wape},
        data_points=60, demand_pattern="smooth",
        confidence_label="high", confidence_reason="(legacy)",
    )


@pytest.mark.django_db
class TestBreakerStreakForcesRetrain:

    def test_streak_at_threshold_bypasses_kept(self, tenant, warehouse_a, steady_product):
        """streak=3 → el kept-path NO conserva el modelo aunque su WAPE sea
        imbatible: se crea un modelo nuevo (versión > 1)."""
        from django.core.management import call_command
        legacy = _legacy_model(tenant, steady_product, warehouse_a,
                               streak=BREAKER_STREAK_FORCE_RETRAIN)

        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)

        active = ForecastModel.objects.filter(
            tenant=tenant, product=steady_product, is_active=True,
        ).first()
        assert active is not None
        assert active.id != legacy.id, (
            "Con breaker-streak >= umbral el kept-path debe bypassearse y "
            "entrenarse un modelo fresco (el WAPE viejo ya no describe la realidad)."
        )
        # La serie es sana → el guard no dispara esta noche → streak muere.
        assert active.model_params.get("circuit_breaker_streak") is None

    def test_streak_below_threshold_keeps_model_and_resets(
        self, tenant, warehouse_a, steady_product,
    ):
        """streak=1 (bajo el umbral) → el kept sigue vigente; y como la serie
        es sana (guard no dispara), el streak se RESETEA en el modelo kept."""
        from django.core.management import call_command
        legacy = _legacy_model(tenant, steady_product, warehouse_a, streak=1)

        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)

        active = ForecastModel.objects.filter(
            tenant=tenant, product=steady_product, is_active=True,
        ).first()
        assert active is not None
        assert active.id == legacy.id, "Con streak < umbral el kept-path sigue protegiendo."
        active.refresh_from_db()
        assert active.model_params.get("circuit_breaker_streak") is None, (
            "Noche sin breaker → el streak debe resetearse (no quedar pegado)."
        )


@pytest.mark.django_db
class TestRegenAppliesGuard:

    def test_regen_collapse_fires_guard_and_increments_streak(
        self, tenant, warehouse_a, steady_product,
    ):
        """El regen (kept-path/fresh final) ahora pasa por el guard: serie
        'cleaned' colapsada (0s) + demanda real reciente alta → el guard
        reemplaza el forecast por WMA y el streak se incrementa prev+1."""
        fm = _legacy_model(tenant, steady_product, warehouse_a, streak=0)
        fm.algorithm = "moving_avg"
        fm.save(update_fields=["algorithm"])

        today = date.today()
        # cleaned colapsada: 30 días en 0 → el algoritmo forecastea ~0
        cleaned = [(today - timedelta(days=i), Decimal("0")) for i in range(30, 0, -1)]
        # demanda REAL reciente alta: 10/día → recent_total >> 10
        raw = [(today - timedelta(days=i), Decimal("10")) for i in range(30, 0, -1)]

        _regen_from_existing(
            tenant, steady_product, warehouse_a.id, fm,
            today, 14, 21, cleaned, {},
            raw_series=raw, prev_breaker_streak=2,
        )

        fm.refresh_from_db()
        assert fm.model_params.get("circuit_breaker") is not None
        assert fm.model_params.get("circuit_breaker_streak") == 3  # prev 2 + 1
        # Y el forecast guardado NO es el colapsado: WMA > 0
        #
        # Se mira TODO el horizonte, no solo el primer dia. Mirar `.first()`
        # ataba el test al dia de la semana en que se corre: cuando el primer
        # dia del horizonte cae en un dia cerrado del negocio (domingo en
        # Marbrava), `_apply_closed_weekdays` lo pone en 0 DESPUES del blend
        # —que es lo correcto— y el test fallaba todos los sabados por una
        # razon que no tiene nada que ver con lo que quiere probar.
        #
        # Lo que el guard promete es que el horizonte deja de estar colapsado,
        # no que un dia puntual sea positivo.
        fcs = list(Forecast.objects.filter(
            tenant=tenant, product=steady_product, warehouse_id=warehouse_a.id,
        ).order_by("forecast_date"))
        assert fcs, "el guard debe dejar forecasts guardados"
        assert max(f.qty_predicted for f in fcs) > 0, (
            "El guard debe reemplazar el forecast colapsado por WMA positivo."
        )

    def test_regen_healthy_resets_streak(self, tenant, warehouse_a, steady_product):
        """Serie sana (forecast acompaña a la demanda) → guard no dispara →
        streak y marca de breaker se limpian del modelo."""
        fm = _legacy_model(tenant, steady_product, warehouse_a, streak=2)
        fm.algorithm = "moving_avg"
        fm.save(update_fields=["algorithm"])

        today = date.today()
        series = [(today - timedelta(days=i), Decimal("3")) for i in range(30, 0, -1)]

        _regen_from_existing(
            tenant, steady_product, warehouse_a.id, fm,
            today, 14, 21, series, {},
            raw_series=series, prev_breaker_streak=2,
        )

        fm.refresh_from_db()
        assert fm.model_params.get("circuit_breaker") is None
        assert fm.model_params.get("circuit_breaker_streak") is None
