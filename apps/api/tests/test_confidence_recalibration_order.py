"""
tests/test_confidence_recalibration_order.py

La etiqueta de confianza que ve Mario la escriben DOS cosas:
  - `train_forecast_models` → desde el BACKTEST (métrica del momento del
    entrenamiento).
  - `recalibrate_confidence` → desde el WAPE REAL de producción
    (ForecastAccuracy: predicho vs vendido de verdad).

Hasta el 06/08/26 la recalibración corría a las 01:30 (desde
track_forecast_accuracy) y el entrenamiento de las 02:30 la pisaba. Es decir:
cada madrugada se calculaba la calibración honesta y una hora después se
tiraba. Mario venía viendo las etiquetas optimistas del backtest.

Estos tests fijan las dos mitades del arreglo:
  1. La recalibración corre DESPUÉS del entrenamiento y tiene la última palabra.
  2. Sin datos reales NO toca la etiqueta (si no, al ponerla al final, todo
     modelo nuevo o de tenant nuevo caería a "low" aunque su backtest sea bueno).
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from forecast.models import ForecastAccuracy, ForecastModel

D = Decimal


def _modelo(tenant, warehouse, product, label="high", pattern="smooth", wape_backtest=15):
    return ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm="moving_avg", data_points=60,
        demand_pattern=pattern,
        confidence_label=label,
        metrics={"wape": wape_backtest, "mase": 0.5},
    )


def _precision(tenant, warehouse, product, dia, real, pred):
    return ForecastAccuracy.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, date=dia,
        qty_actual=D(str(real)), qty_predicted=D(str(pred)),
        error=D(str(pred)) - D(str(real)),
    )


# ── Sin evidencia real: no se toca ───────────────────────────────────────────

@pytest.mark.django_db
def test_sin_datos_reales_conserva_la_etiqueta_del_entrenamiento(tenant, warehouse, product):
    """LA REGRESIÓN QUE EVITA ESTE TEST.

    Un modelo recién entrenado con buen backtest todavía no tiene días medidos.
    Si la recalibración lo pisara con su default conservador, quedaría "low"
    sin ninguna evidencia en contra — y como ahora corre al final, nadie lo
    corregiría después.
    """
    fm = _modelo(tenant, warehouse, product, label="high")
    call_command("recalibrate_confidence", "--tenant", str(tenant.id), verbosity=0)
    fm.refresh_from_db()
    assert fm.confidence_label == "high"


@pytest.mark.django_db
def test_producto_sin_ventas_en_la_ventana_conserva_su_etiqueta(tenant, warehouse, product):
    """Rotación lenta: hay registros de precisión pero todos con venta 0.
    No hay WAPE calculable → no hay nada que corregir."""
    fm = _modelo(tenant, warehouse, product, label="medium")
    hoy = datetime.date.today()
    for i in range(1, 6):
        _precision(tenant, warehouse, product, hoy - datetime.timedelta(days=i), real=0, pred=3)
    call_command("recalibrate_confidence", "--tenant", str(tenant.id), verbosity=0)
    fm.refresh_from_db()
    assert fm.confidence_label == "medium"


# ── Con evidencia real: corrige ──────────────────────────────────────────────

@pytest.mark.django_db
def test_con_datos_reales_malos_baja_la_etiqueta(tenant, warehouse, product):
    """El backtest decía "high"; en producción falla feo → tiene que bajar."""
    fm = _modelo(tenant, warehouse, product, label="high", wape_backtest=10)
    hoy = datetime.date.today()
    for i in range(1, 8):
        # Predice 100 y se venden 10 → WAPE 900%
        _precision(tenant, warehouse, product, hoy - datetime.timedelta(days=i), real=10, pred=100)
    call_command("recalibrate_confidence", "--tenant", str(tenant.id), verbosity=0)
    fm.refresh_from_db()
    assert fm.confidence_label == "very_low"
    assert "WAPE real" in fm.confidence_reason


@pytest.mark.django_db
def test_con_datos_reales_buenos_sube_la_etiqueta(tenant, warehouse, product):
    fm = _modelo(tenant, warehouse, product, label="very_low")
    hoy = datetime.date.today()
    for i in range(1, 8):
        _precision(tenant, warehouse, product, hoy - datetime.timedelta(days=i), real=100, pred=95)
    call_command("recalibrate_confidence", "--tenant", str(tenant.id), verbosity=0)
    fm.refresh_from_db()
    assert fm.confidence_label == "high"


@pytest.mark.django_db
def test_guarda_el_wape_real_en_metrics(tenant, warehouse, product):
    """El dashboard muestra wape_real; metrics.wape sigue siendo el del backtest."""
    fm = _modelo(tenant, warehouse, product, wape_backtest=10)
    hoy = datetime.date.today()
    for i in range(1, 8):
        _precision(tenant, warehouse, product, hoy - datetime.timedelta(days=i), real=100, pred=140)
    call_command("recalibrate_confidence", "--tenant", str(tenant.id), verbosity=0)
    fm.refresh_from_db()
    assert fm.metrics["wape_real"] == 40.0
    assert fm.metrics["wape"] == 10  # el del backtest no se pisa


# ── El orden: la recalibración tiene la última palabra ───────────────────────

@pytest.mark.django_db
def test_el_entrenamiento_deja_la_etiqueta_honesta_no_la_del_backtest(
    tenant, warehouse, product, monkeypatch,
):
    """LO QUE ARREGLA ESTE CAMBIO.

    Simulamos la noche completa: el entrenamiento escribe su etiqueta desde el
    backtest y, al terminar, la recalibración la corrige con el WAPE real. Antes
    el orden era al revés y la corrección se perdía.
    """
    fm = _modelo(tenant, warehouse, product, label="medium")
    hoy = datetime.date.today()
    # Evidencia real mala: predijo 100, se vendieron 10.
    for i in range(1, 8):
        _precision(tenant, warehouse, product, hoy - datetime.timedelta(days=i), real=10, pred=100)

    # El entrenamiento real necesita mucha data; nos interesa sólo que su
    # último paso sea la recalibración. Parcheamos el procesamiento por tenant
    # para que "entrene" escribiendo la etiqueta optimista del backtest.
    from forecast.management.commands import train_forecast_models as mod

    def fake_process(self, tenant_obj, *a, **kw):
        ForecastModel.objects.filter(id=fm.id).update(confidence_label="high")

    monkeypatch.setattr(mod.Command, "_process_tenant", fake_process)
    call_command("train_forecast_models", "--tenant", str(tenant.id), verbosity=0)

    fm.refresh_from_db()
    assert fm.confidence_label == "very_low", (
        "el entrenamiento puso 'high' desde el backtest y la recalibración "
        "tenía que corregirlo con el WAPE real al final"
    )


@pytest.mark.django_db
def test_si_la_recalibracion_falla_el_entrenamiento_no_se_cae(
    tenant, warehouse, product, monkeypatch,
):
    """Los pronósticos ya están guardados y son lo crítico: la etiqueta puede
    esperar a la próxima noche."""
    from forecast.management.commands import train_forecast_models as mod

    monkeypatch.setattr(mod.Command, "_process_tenant", lambda self, *a, **kw: None)

    def boom(*a, **kw):
        raise RuntimeError("base caída")

    monkeypatch.setattr(mod, "call_command", boom)
    call_command("train_forecast_models", "--tenant", str(tenant.id), verbosity=0)
