"""
Tests del cap de MAPE individual a 200% en ForecastAccuracy.

Bug detectado el 08/05/26: el algoritmo `ingredient_derived` reportaba
MAPE de 64.389% en producción por la división por qty_actual cercano a
cero. El fix capea el MAPE individual a 200%.

Cubre:
  - track_forecast_accuracy aplica el cap a registros nuevos
  - backfill_mape_cap aplica el cap a registros existentes
  - El cap NO toca registros ya bajo 200%
  - Los registros con qty_actual=0 siguen con abs_pct_error=NULL
  - Backfill es idempotente
"""
from decimal import Decimal
from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from forecast.models import (
    DailySales, Forecast, ForecastAccuracy, ForecastModel,
)
from catalog.models import Product
from core.models import Warehouse


# ── Helpers ─────────────────────────────────────────────────────────────────


@pytest.fixture
def warehouse_for_forecast(db, tenant, store):
    return Warehouse.objects.create(tenant=tenant, store=store, name="Bodega Forecast")


def _make_model(tenant, product, warehouse, algo="moving_avg"):
    return ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm=algo, version=1,
        model_params={}, metrics={},
        data_points=10, demand_pattern="smooth",
        is_active=True, confidence_label="medium",
    )


def _make_forecast(tenant, product, warehouse, model, fc_date, qty):
    return Forecast.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, model=model,
        forecast_date=fc_date, qty_predicted=Decimal(str(qty)),
        confidence=Decimal("65"),
    )


def _make_daily_sales(tenant, product, warehouse, ds_date, qty):
    return DailySales.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        date=ds_date, qty_sold=Decimal(str(qty)),
    )


# ── track_forecast_accuracy: cap aplicado a nuevos ─────────────────────────


@pytest.mark.django_db
class TestTrackForecastAccuracyCap:

    def test_explosive_mape_capped_at_200(
        self, tenant, product, warehouse_for_forecast,
    ):
        """Predicción 100, real 0.001 → MAPE bruto = 9.999.900% → capped a 200."""
        target_date = date.today() - timedelta(days=1)
        model = _make_model(tenant, product, warehouse_for_forecast)
        _make_forecast(tenant, product, warehouse_for_forecast, model,
                       target_date, qty="100")
        _make_daily_sales(tenant, product, warehouse_for_forecast,
                          target_date, qty="0.001")

        call_command(
            "track_forecast_accuracy",
            f"--date={target_date.isoformat()}",
            f"--tenant={tenant.id}",
            stdout=StringIO(),
        )

        acc = ForecastAccuracy.objects.get(
            tenant=tenant, product=product, date=target_date,
        )
        assert acc.qty_predicted == Decimal("100.000")
        assert acc.qty_actual == Decimal("0.001")
        assert acc.abs_pct_error == Decimal("200.00"), (
            f"Esperaba cap a 200%. Got: {acc.abs_pct_error}. "
            f"El fix de track_forecast_accuracy.py no se aplicó."
        )

    def test_normal_mape_under_cap_unchanged(
        self, tenant, product, warehouse_for_forecast,
    ):
        """Predicción 100, real 90 → MAPE = 11,11% (no se toca)."""
        target_date = date.today() - timedelta(days=1)
        model = _make_model(tenant, product, warehouse_for_forecast)
        _make_forecast(tenant, product, warehouse_for_forecast, model,
                       target_date, qty="100")
        _make_daily_sales(tenant, product, warehouse_for_forecast,
                          target_date, qty="90")

        call_command(
            "track_forecast_accuracy",
            f"--date={target_date.isoformat()}",
            f"--tenant={tenant.id}",
            stdout=StringIO(),
        )

        acc = ForecastAccuracy.objects.get(
            tenant=tenant, product=product, date=target_date,
        )
        # 11.11... → quantize a 11.11
        assert acc.abs_pct_error == Decimal("11.11")

    def test_qty_actual_zero_keeps_null_mape(
        self, tenant, product, warehouse_for_forecast,
    ):
        """Si qty_actual=0, abs_pct_error queda NULL (no calculable).
        El cap no debe inventarle un valor."""
        target_date = date.today() - timedelta(days=1)
        model = _make_model(tenant, product, warehouse_for_forecast)
        _make_forecast(tenant, product, warehouse_for_forecast, model,
                       target_date, qty="50")
        _make_daily_sales(tenant, product, warehouse_for_forecast,
                          target_date, qty="0")

        call_command(
            "track_forecast_accuracy",
            f"--date={target_date.isoformat()}",
            f"--tenant={tenant.id}",
            stdout=StringIO(),
        )

        acc = ForecastAccuracy.objects.get(
            tenant=tenant, product=product, date=target_date,
        )
        assert acc.qty_actual == Decimal("0.000")
        assert acc.abs_pct_error is None, (
            "qty_actual=0 → MAPE no calculable. abs_pct_error tiene que ser NULL."
        )


# ── backfill_mape_cap: aplica retroactivamente ─────────────────────────────


@pytest.mark.django_db
class TestBackfillMapeCap:

    @pytest.fixture
    def mixed_records(self, tenant, product, warehouse_for_forecast):
        """Crea 4 registros con MAPE varios: bajo, en el límite, alto, NULL."""
        d = date.today() - timedelta(days=10)
        records = []
        # Bajo (no se debe tocar)
        records.append(ForecastAccuracy.objects.create(
            tenant=tenant, product=product, warehouse=warehouse_for_forecast,
            date=d, qty_predicted=Decimal("100"), qty_actual=Decimal("90"),
            error=Decimal("10"), abs_pct_error=Decimal("11.11"),
            algorithm="moving_avg",
        ))
        # En el cap exacto (no se debe tocar)
        records.append(ForecastAccuracy.objects.create(
            tenant=tenant, product=product, warehouse=warehouse_for_forecast,
            date=d - timedelta(days=1),
            qty_predicted=Decimal("300"), qty_actual=Decimal("100"),
            error=Decimal("200"), abs_pct_error=Decimal("200.00"),
            algorithm="moving_avg",
        ))
        # Explosivo (se debe capar)
        records.append(ForecastAccuracy.objects.create(
            tenant=tenant, product=product, warehouse=warehouse_for_forecast,
            date=d - timedelta(days=2),
            qty_predicted=Decimal("100"), qty_actual=Decimal("0.001"),
            error=Decimal("99.999"), abs_pct_error=Decimal("99999.99"),
            algorithm="ingredient_derived",
        ))
        # NULL (qty_actual=0) — no se debe tocar
        records.append(ForecastAccuracy.objects.create(
            tenant=tenant, product=product, warehouse=warehouse_for_forecast,
            date=d - timedelta(days=3),
            qty_predicted=Decimal("50"), qty_actual=Decimal("0"),
            error=Decimal("50"), abs_pct_error=None,
            algorithm="ingredient_derived",
        ))
        return records

    def test_dry_run_no_changes(self, mixed_records):
        """Sin --apply, no cambia nada en la DB."""
        out = StringIO()
        call_command("backfill_mape_cap", stdout=out)

        # El registro explosivo sigue con su valor original
        rec = ForecastAccuracy.objects.get(pk=mixed_records[2].pk)
        assert rec.abs_pct_error == Decimal("99999.99")

    def test_apply_caps_exploded_records(self, mixed_records):
        """Con --apply, los > 200 bajan a 200, el resto queda igual."""
        out = StringIO()
        call_command("backfill_mape_cap", "--apply", stdout=out)

        # Bajo: sin cambio
        assert ForecastAccuracy.objects.get(pk=mixed_records[0].pk).abs_pct_error == Decimal("11.11")
        # En el cap exacto: sin cambio
        assert ForecastAccuracy.objects.get(pk=mixed_records[1].pk).abs_pct_error == Decimal("200.00")
        # Explosivo: capeado
        assert ForecastAccuracy.objects.get(pk=mixed_records[2].pk).abs_pct_error == Decimal("200.00")
        # NULL: sigue NULL
        assert ForecastAccuracy.objects.get(pk=mixed_records[3].pk).abs_pct_error is None

    def test_idempotent(self, mixed_records):
        """Correr backfill 2 veces no cambia nada en la 2da."""
        call_command("backfill_mape_cap", "--apply", stdout=StringIO())
        snapshot = {
            r.pk: r.abs_pct_error
            for r in ForecastAccuracy.objects.all()
        }
        # Segunda corrida
        out = StringIO()
        call_command("backfill_mape_cap", "--apply", stdout=out)
        # Nada nuevo capeado (mensaje "Nada que hacer" o equivalente)
        for r in ForecastAccuracy.objects.all():
            assert r.abs_pct_error == snapshot[r.pk], (
                f"Backfill no es idempotente: pk={r.pk} cambió tras 2da corrida"
            )

    def test_cross_tenant_filter(
        self, tenant, product, warehouse_for_forecast, db,
    ):
        """--tenant=N solo capea ese tenant, no toca otros."""
        from core.models import Tenant
        from stores.models import Store as Sm
        # Tenant B con un registro explosivo
        tenant_b = Tenant.objects.create(name="Otro", slug="otro-tenant")
        store_b = Sm.objects.create(tenant=tenant_b, name="Local B")
        warehouse_b = Warehouse.objects.create(tenant=tenant_b, store=store_b, name="W")
        product_b = Product.objects.create(
            tenant=tenant_b, name="P", price=Decimal("100"), is_active=True,
        )
        rec_b = ForecastAccuracy.objects.create(
            tenant=tenant_b, product=product_b, warehouse=warehouse_b,
            date=date.today() - timedelta(days=1),
            qty_predicted=Decimal("100"), qty_actual=Decimal("0.001"),
            error=Decimal("99.999"), abs_pct_error=Decimal("99999.99"),
            algorithm="ingredient_derived",
        )
        rec_a = ForecastAccuracy.objects.create(
            tenant=tenant, product=product, warehouse=warehouse_for_forecast,
            date=date.today() - timedelta(days=1),
            qty_predicted=Decimal("100"), qty_actual=Decimal("0.001"),
            error=Decimal("99.999"), abs_pct_error=Decimal("99999.99"),
            algorithm="ingredient_derived",
        )

        # Solo backfill del tenant A
        call_command("backfill_mape_cap", f"--tenant={tenant.id}", "--apply",
                     stdout=StringIO())

        rec_a.refresh_from_db()
        rec_b.refresh_from_db()
        assert rec_a.abs_pct_error == Decimal("200.00"), "tenant A debió capearse"
        assert rec_b.abs_pct_error == Decimal("99999.99"), (
            "tenant B NO debe haberse tocado"
        )
