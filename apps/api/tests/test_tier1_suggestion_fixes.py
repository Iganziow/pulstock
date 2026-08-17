"""
tests/test_tier1_suggestion_fixes.py — tres arreglos chicos de alto impacto.

1. Heartbeats en el pipeline nocturno (dead man's switch). CronHeartbeat y el
   chequeo en /health/deep existían desde abril, pero NINGÚN comando escribía
   heartbeats: el monitor vigilaba un pulso que nadie emitía y "cron ok" era
   verdad vacía con 0 registrados.

2. B2 — el lookup de proveedor filtraba por estados CONFIRMED/RECEIVED que
   jamás existieron (los reales: DRAFT/POSTED/VOID) → siempre vacío → todas
   las sugerencias corrían con lead time por defecto.

3. Tope al pesimismo de la banda superior. Chocolate Premium (17/08/26):
   consumo real 48/día, pronóstico 29/día, banda superior 177/día. El modelo
   estaba en "low" → la sugerencia usaba la banda → pedir 1.400 unidades
   teniendo 1.300 en stock.
"""
import datetime
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product
from core.heartbeat import with_heartbeat
from core.models import CronHeartbeat
from inventory.models import StockItem
from forecast.models import ForecastModel, Forecast, DailySales, SuggestionLine
from forecast.services import generate_suggestions, _find_best_supplier
from purchases.models import Purchase, PurchaseLine

TODAY = date.today()
D = Decimal


# ══════════════════════════════════════════════════════════════════════════
# 1. Heartbeats
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
def test_heartbeat_ok_registra_duracion():
    @with_heartbeat("tarea_de_prueba", expected_max_age_minutes=60)
    def tarea():
        return 42

    assert tarea() == 42
    hb = CronHeartbeat.objects.get(task_name="tarea_de_prueba")
    assert hb.last_result == "ok"
    assert hb.last_error == ""
    assert hb.expected_max_age_minutes == 60
    assert not hb.is_stale


@pytest.mark.django_db
def test_heartbeat_fallo_guarda_error_y_relanza():
    """El cron log tiene que conservar su traceback: el decorador registra el
    fallo pero NO se traga la excepción."""
    @with_heartbeat("tarea_que_falla")
    def tarea():
        raise RuntimeError("se cayó la base")

    with pytest.raises(RuntimeError):
        tarea()
    hb = CronHeartbeat.objects.get(task_name="tarea_que_falla")
    assert hb.last_result == "failed"
    assert "se cayó la base" in hb.last_error


@pytest.mark.django_db
def test_los_comandos_del_pipeline_emiten_heartbeat(tenant):
    """El fin del monitor vacío: correr un comando real deja pulso."""
    call_command("track_forecast_accuracy", "--tenant", str(tenant.id), verbosity=0)
    hb = CronHeartbeat.objects.get(task_name="track_forecast_accuracy")
    assert hb.last_result == "ok"


# ══════════════════════════════════════════════════════════════════════════
# 2. B2 — proveedor por estado real
# ══════════════════════════════════════════════════════════════════════════

def _compra(tenant, store, warehouse, owner, product, status, supplier, qty=10):
    po = Purchase.objects.create(
        tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
        supplier_name=supplier, status=status,
    )
    PurchaseLine.objects.create(
        tenant=tenant, purchase=po, product=product,
        qty=D(str(qty)), unit_cost=D("100"),
    )
    return po


@pytest.mark.django_db
def test_b2_encuentra_proveedor_de_compras_posteadas(tenant, store, warehouse, owner, product):
    _compra(tenant, store, warehouse, owner, product, "POSTED", "Lácteos Sur", qty=50)
    _compra(tenant, store, warehouse, owner, product, "POSTED", "Distribuidora Norte", qty=10)
    assert _find_best_supplier(tenant, [product.id]) == "Lácteos Sur"


@pytest.mark.django_db
def test_b2_ignora_borradores_y_anuladas(tenant, store, warehouse, owner, product):
    _compra(tenant, store, warehouse, owner, product, "DRAFT", "Borrador SpA")
    _compra(tenant, store, warehouse, owner, product, "VOID", "Anulada Ltda")
    assert _find_best_supplier(tenant, [product.id]) == ""


# ══════════════════════════════════════════════════════════════════════════
# 3. Tope a la banda superior
# ══════════════════════════════════════════════════════════════════════════

def _prod(tenant, name):
    return Product.objects.create(
        tenant=tenant, name=name, sku=f"SKU-{name}",
        price=D("1000.00"), is_active=True,
    )


def _modelo(tenant, warehouse, product, conf="low"):
    return ForecastModel.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        algorithm="theta", version=1, model_params={},
        metrics={"wape": 60.0, "rmse": 0.0}, data_points=200,
        is_active=True, confidence_label=conf,
    )


def _forecasts(tenant, warehouse, product, model, punto, banda):
    for d in range(1, 15):
        Forecast.objects.create(
            tenant=tenant, warehouse=warehouse, product=product, model=model,
            forecast_date=TODAY + timedelta(days=d),
            qty_predicted=D(str(punto)), lower_bound=D("0"),
            upper_bound=D(str(banda)),
            days_to_stockout=2, confidence=D("50.00"),
        )


def _consumo_real(tenant, warehouse, product, por_dia):
    for i in range(1, 31):
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=TODAY - timedelta(days=i), qty_sold=D(str(por_dia)),
        )


def _stock0(tenant, warehouse, product):
    StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=product,
                             on_hand=D("0"), avg_cost=D("500"))


def _linea(tenant, product):
    return SuggestionLine.objects.filter(
        suggestion__tenant=tenant, product=product,
    ).first()


@pytest.mark.django_db
class TestBandaSuperiorCap:
    def test_banda_inflada_se_acota_al_consumo_real(self, tenant, warehouse):
        """EL CASO CHOCOLATE PREMIUM: punto 5/día, banda 40/día, consumo real
        6/día. El pedido debe salir del consumo real acotado (~9/día máx),
        no de la banda."""
        p = _prod(tenant, "Choc")
        _forecasts(tenant, warehouse, p, _modelo(tenant, warehouse, p, "low"),
                   punto=5, banda=40)
        _consumo_real(tenant, warehouse, p, por_dia=6)
        _stock0(tenant, warehouse, p)

        generate_suggestions(tenant, TODAY, threshold=7, target_days=7)
        l = _linea(tenant, p)
        assert l is not None
        # Sin tope, la demanda diaria sería 40; con tope, ≤ 1,5×6 = 9.
        assert float(l.avg_daily_demand) <= 9.1, (
            f"la banda inflada no se acotó: avg_daily={l.avg_daily_demand}")
        assert float(l.avg_daily_demand) >= 5.0, "nunca por debajo del punto"

    def test_nunca_recorta_por_debajo_del_pronostico_puntual(self, tenant, warehouse):
        """Consumo real bajito (1/día) NO arrastra el pedido por debajo de lo
        que el propio modelo predice (5/día): solo se recorta el exceso de la
        banda, no al modelo."""
        p = _prod(tenant, "Punto")
        _forecasts(tenant, warehouse, p, _modelo(tenant, warehouse, p, "low"),
                   punto=5, banda=40)
        _consumo_real(tenant, warehouse, p, por_dia=1)
        _stock0(tenant, warehouse, p)

        generate_suggestions(tenant, TODAY, threshold=7, target_days=7)
        l = _linea(tenant, p)
        assert l is not None
        assert abs(float(l.avg_daily_demand) - 5.0) < 0.1, (
            f"debió quedar en el punto (5/día): {l.avg_daily_demand}")

    def test_sin_consumo_reciente_respeta_la_banda(self, tenant, warehouse):
        """Producto nuevo sin historial: no hay base para acotar, se mantiene
        el comportamiento conservador (banda completa)."""
        p = _prod(tenant, "Nuevo")
        _forecasts(tenant, warehouse, p, _modelo(tenant, warehouse, p, "low"),
                   punto=5, banda=12)
        _stock0(tenant, warehouse, p)

        generate_suggestions(tenant, TODAY, threshold=7, target_days=7)
        l = _linea(tenant, p)
        assert l is not None
        assert float(l.avg_daily_demand) >= 11.9, (
            f"sin consumo reciente debía usar la banda (12/día): {l.avg_daily_demand}")

    def test_confianza_alta_usa_el_punto_como_siempre(self, tenant, warehouse):
        p = _prod(tenant, "Confiable")
        _forecasts(tenant, warehouse, p, _modelo(tenant, warehouse, p, "high"),
                   punto=5, banda=40)
        _consumo_real(tenant, warehouse, p, por_dia=6)
        _stock0(tenant, warehouse, p)

        generate_suggestions(tenant, TODAY, threshold=7, target_days=7)
        l = _linea(tenant, p)
        assert l is not None
        assert abs(float(l.avg_daily_demand) - 5.0) < 0.1
