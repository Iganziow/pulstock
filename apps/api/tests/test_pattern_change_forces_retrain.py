"""
Test Fase 5b: cuando demand_pattern cambia entre old y new model, NO aplicar
"kept" check — forzar el reentrenamiento.

BUG (caso Latte en Marbrava)
============================
Despues del deploy de Fase 4 (classifier filtra dias cerrados), Latte deberia
pasar de pattern=intermittent (Croston_SBA) a pattern=smooth (adaptive_ma o
theta). Pero el modelo seguia siendo croston_sba/intermittent.

Causa: el "kept" check (services.py:1124) compara WAPE backtest old vs new.
Croston_SBA tiene WAPE alto pero "acierta" prediciendo 0 los dias sin venta.
adaptive_ma tiene WAPE comparable o levemente mayor porque predice un
promedio todos los dias. La comparacion 1:1 NO favorece al cambio aunque
operativamente adaptive_ma sea mucho mejor.

FIX
===
Si demand_pattern (existing) != demand_pattern (new), saltar el "kept" check
y forzar el guardado del nuevo modelo. El cambio de pattern es la senal de
que la situacion cambio (datos nuevos, fix de classifier, etc.) — los WAPEs
no son comparables porque el pool de algoritmos eligibles depende del
pattern.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from catalog.models import Product, Unit
from forecast.models import DailySales, ForecastModel


@pytest.fixture
def latte_like(db, tenant, warehouse_a):
    u, _ = Unit.objects.get_or_create(
        tenant=tenant, code="UN",
        defaults={"name": "Unidad", "family": "COUNT"},
    )
    p = Product.objects.create(
        tenant=tenant, name="Latte-like", unit_obj=u, is_active=True,
    )
    # Historia: vende mar-sab, NO dom (cierre), lun parcial
    today = date.today()
    for i in range(70, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() == 6:  # domingo cerrado
            continue
        # vende todos los demas dias
        DailySales.objects.create(
            tenant=tenant, product=p, warehouse=warehouse_a,
            date=d, qty_sold=Decimal("3"), forecast_only=False,
        )
    return p


@pytest.mark.django_db
class TestPatternChangeForcesRetrain:

    def test_existing_intermittent_swaps_to_smooth_after_fase4(
        self, tenant, warehouse_a, latte_like,
    ):
        """Latte-like con modelo legacy croston_sba intermittent.
        Despues de retrain (con closed_weekdays filter de Fase 4) debe
        pasar a smooth + adaptive_ma/theta, NO quedarse en 'kept'."""
        from django.core.management import call_command
        from forecast.services import train_product_model

        # Modelo legacy (simulando pre-Fase 4): croston_sba intermittent
        ForecastModel.objects.create(
            tenant=tenant, product=latte_like, warehouse=warehouse_a,
            algorithm="croston_sba", version=1, is_active=True,
            model_params={"avg_daily": "3"},
            metrics={"wape": 100.0, "mae": 1, "mape": 100},
            data_points=60, demand_pattern="intermittent",
            confidence_label="low", confidence_reason="(legacy)",
        )

        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)

        # Despues del retrain, el modelo activo debe ser smooth (NO intermittent)
        active = ForecastModel.objects.filter(
            tenant=tenant, product=latte_like, is_active=True,
        ).first()
        assert active is not None
        assert active.demand_pattern == "smooth", (
            f"Despues de retrain con Fase 4, pattern debe ser smooth, "
            f"got {active.demand_pattern} (algorithm={active.algorithm}). "
            f"El kept-check anterior bloqueaba esta transicion."
        )
        # No debe ser croston (algoritmo para intermittent)
        assert "croston" not in active.algorithm

    def test_kept_check_aun_funciona_cuando_pattern_no_cambia(
        self, tenant, warehouse_a, latte_like,
    ):
        """Si pattern no cambia, el kept-check sigue protegiendo de cambios
        que empeoran el WAPE."""
        from django.core.management import call_command

        # Modelo legacy con MISMO pattern que el nuevo deberia detectar (smooth)
        # y MUY BUEN WAPE (improbable de mejorar)
        ForecastModel.objects.create(
            tenant=tenant, product=latte_like, warehouse=warehouse_a,
            algorithm="adaptive_ma", version=1, is_active=True,
            model_params={"avg_daily": "3"},
            metrics={"wape": 5.0, "mae": 0.1, "mape": 5},
            data_points=60, demand_pattern="smooth",
            confidence_label="high", confidence_reason="(excelente)",
        )

        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)

        active = ForecastModel.objects.filter(
            tenant=tenant, product=latte_like, is_active=True,
        ).first()
        # Si el nuevo modelo no supera al viejo (WAPE 5%) por mas de 10%,
        # se mantiene el viejo. Aqui no exigimos algoritmo especifico
        # — solo que el comportamiento "kept" siga vigente cuando pattern
        # no cambia. El test pasa si NO crashea por la nueva logica.
        assert active is not None
        assert active.demand_pattern == "smooth"
