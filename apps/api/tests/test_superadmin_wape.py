"""
Tests del WAPE (Weighted Absolute Percentage Error) en superadmin
forecast metrics.

Mario pidió (13/05/26) sumar WAPE como métrica complementaria al MAPE,
visible SOLO en superadmin (uso interno). Más estable para demanda
intermitente que MAPE.

Fórmula: WAPE = Σ|error| / Σ|actual| × 100
"""
from decimal import Decimal
from datetime import timedelta, date

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Product
from core.models import Warehouse, User
from forecast.models import ForecastAccuracy


@pytest.fixture
def superadmin_user(db, tenant, store):
    """Superadmin con permiso para ver el endpoint."""
    user = User.objects.create_user(
        username="superadmin_test", password="x",
        tenant=tenant, active_store=store,
        role=User.Role.OWNER, is_superuser=True, is_staff=True,
    )
    return user


@pytest.fixture
def superadmin_client(superadmin_user):
    client = APIClient()
    client.force_authenticate(user=superadmin_user)
    return client


@pytest.fixture
def warehouse_acc(db, tenant, store):
    return Warehouse.objects.create(
        tenant=tenant, store=store, name="W-Acc",
    )


def _create_accuracy(
    tenant, product, warehouse, *, date_, predicted, actual,
    algorithm="simple_avg",
):
    """Helper para crear ForecastAccuracy con error y abs_pct_error calculados."""
    actual_dec = Decimal(str(actual))
    error = Decimal(str(predicted)) - actual_dec
    abs_pct = None
    if actual_dec > 0:
        abs_pct = (abs(error) / actual_dec * 100).quantize(Decimal("0.01"))
    return ForecastAccuracy.objects.create(
        tenant=tenant,
        product=product,
        warehouse=warehouse,
        date=date_,
        qty_predicted=Decimal(str(predicted)),
        qty_actual=Decimal(str(actual)),
        error=error,
        abs_pct_error=abs_pct,
        algorithm=algorithm,
        was_stockout=False,
    )


@pytest.mark.django_db
class TestWAPECalculation:
    """WAPE = Σ|error| / Σ|actual| × 100. Más estable que MAPE."""

    def test_endpoint_returns_wape_block(
        self, superadmin_client, tenant, warehouse_acc,
    ):
        """El endpoint /superadmin/forecast/ debe incluir el bloque 'wape'."""
        # Crear algo de data
        prod = Product.objects.create(
            tenant=tenant, name="Producto WAPE", price=Decimal("1000"),
            is_active=True,
        )
        today = date.today()
        _create_accuracy(tenant, prod, warehouse_acc,
                         date_=today - timedelta(days=1),
                         predicted=10, actual=8)

        resp = superadmin_client.get("/api/superadmin/forecast/")
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert "wape" in data
        assert "global_30d" in data["wape"]
        assert "global_7d" in data["wape"]
        assert "by_algorithm" in data["wape"]

    def test_wape_simple_case(
        self, superadmin_client, tenant, warehouse_acc,
    ):
        """Caso simple verificable a mano:
          - Día 1: pred=10, actual=8 → |error|=2
          - Día 2: pred=5,  actual=4 → |error|=1
          WAPE = (2+1) / (8+4) × 100 = 3/12 × 100 = 25%"""
        prod = Product.objects.create(
            tenant=tenant, name="Latte test", price=Decimal("3000"),
            is_active=True,
        )
        today = date.today()
        _create_accuracy(tenant, prod, warehouse_acc,
                         date_=today - timedelta(days=1),
                         predicted=10, actual=8)
        _create_accuracy(tenant, prod, warehouse_acc,
                         date_=today - timedelta(days=2),
                         predicted=5, actual=4)

        resp = superadmin_client.get("/api/superadmin/forecast/")
        wape = resp.json()["wape"]["global_30d"]
        assert wape == pytest.approx(25.0, abs=0.01), (
            f"Esperaba 25%, obtuve {wape}. Fórmula: 3/12*100 = 25"
        )

    def test_wape_excludes_zero_actual_days(
        self, superadmin_client, tenant, warehouse_acc,
    ):
        """Días con consumo real = 0 deben EXCLUIRSE (denominador 0).
        Si NO se excluyen, el WAPE explota igual que el MAPE.

        Setup:
          - Día 1: pred=10, actual=10  → |error|=0, sum_actual=10
          - Día 2: pred=5,  actual=0   → DEBE EXCLUIRSE
          - Día 3: pred=8,  actual=8   → |error|=0, sum_actual=8
        Si funciona bien: WAPE = 0 / 18 = 0%
        Si NO excluye: explota porque qty_actual=0 entra al divisor."""
        prod = Product.objects.create(
            tenant=tenant, name="Producto intermitente", price=Decimal("1000"),
            is_active=True,
        )
        today = date.today()
        _create_accuracy(tenant, prod, warehouse_acc,
                         date_=today - timedelta(days=1),
                         predicted=10, actual=10)
        _create_accuracy(tenant, prod, warehouse_acc,
                         date_=today - timedelta(days=2),
                         predicted=5, actual=0)  # ← debe excluirse
        _create_accuracy(tenant, prod, warehouse_acc,
                         date_=today - timedelta(days=3),
                         predicted=8, actual=8)

        resp = superadmin_client.get("/api/superadmin/forecast/")
        wape = resp.json()["wape"]["global_30d"]
        assert wape == pytest.approx(0.0, abs=0.01), (
            f"Esperaba 0% (ambas predicciones perfectas, día 0 excluido). "
            f"Obtuve {wape}. El día con actual=0 NO se está excluyendo."
        )

    def test_wape_more_stable_than_mape_intermittent(
        self, superadmin_client, tenant, warehouse_acc,
    ):
        """Demostración de la ventaja del WAPE: ingredient_derived con
        consumo intermitente. MAPE explota individualmente, WAPE no.

        Setup (Cacao en una semana real):
          Día 1: pred=10, actual=10  → error_pct individual 0%
          Día 2: pred=10, actual=0.5 → error_pct individual 1900%
          Día 3: pred=10, actual=12  → error_pct individual 16%
          Día 4: pred=10, actual=8   → error_pct individual 25%

        WAPE = (0 + 9.5 + 2 + 2) / (10 + 0.5 + 12 + 8) × 100
             = 13.5 / 30.5 × 100
             = 44.3%

        MAPE promediado individual (con cap 200%): ~485% / 4 = 121%
        WAPE ~44%: refleja mejor que el sistema 'casi siempre acierta'.
        """
        prod = Product.objects.create(
            tenant=tenant, name="Cacao test", price=Decimal("0"),
            is_active=True,
        )
        today = date.today()
        _create_accuracy(tenant, prod, warehouse_acc,
                         date_=today - timedelta(days=1),
                         predicted=10, actual=10,
                         algorithm="ingredient_derived")
        _create_accuracy(tenant, prod, warehouse_acc,
                         date_=today - timedelta(days=2),
                         predicted=10, actual="0.5",
                         algorithm="ingredient_derived")
        _create_accuracy(tenant, prod, warehouse_acc,
                         date_=today - timedelta(days=3),
                         predicted=10, actual=12,
                         algorithm="ingredient_derived")
        _create_accuracy(tenant, prod, warehouse_acc,
                         date_=today - timedelta(days=4),
                         predicted=10, actual=8,
                         algorithm="ingredient_derived")

        resp = superadmin_client.get("/api/superadmin/forecast/")
        data = resp.json()
        wape = data["wape"]["global_30d"]
        # 13.5 / 30.5 × 100 ≈ 44.26
        assert wape == pytest.approx(44.26, abs=0.5), (
            f"WAPE esperado ~44%, obtuve {wape}. Si está cerca de 100% o "
            f"explota, la fórmula no es WAPE estándar."
        )

    def test_wape_by_algorithm_breakdown(
        self, superadmin_client, tenant, warehouse_acc,
    ):
        """Ver el desglose por algoritmo — clave para saber cuál usar."""
        prod_a = Product.objects.create(
            tenant=tenant, name="P1", price=Decimal("100"), is_active=True,
        )
        prod_b = Product.objects.create(
            tenant=tenant, name="P2", price=Decimal("100"), is_active=True,
        )
        today = date.today()
        # simple_avg perfecto
        _create_accuracy(tenant, prod_a, warehouse_acc,
                         date_=today - timedelta(days=1),
                         predicted=10, actual=10, algorithm="simple_avg")
        # ingredient_derived mal
        _create_accuracy(tenant, prod_b, warehouse_acc,
                         date_=today - timedelta(days=1),
                         predicted=20, actual=5,
                         algorithm="ingredient_derived")

        resp = superadmin_client.get("/api/superadmin/forecast/")
        wapes = {row["algorithm"]: row["wape"]
                 for row in resp.json()["wape"]["by_algorithm"]}
        assert wapes.get("simple_avg") == pytest.approx(0.0, abs=0.01)
        # 15/5 × 100 = 300%
        assert wapes.get("ingredient_derived") == pytest.approx(300.0, abs=0.5)

    def test_no_data_returns_null_wape(
        self, superadmin_client, tenant,
    ):
        """Sin data, el endpoint no debe explotar — devuelve None."""
        # NO crear ForecastAccuracy
        resp = superadmin_client.get("/api/superadmin/forecast/")
        assert resp.status_code == 200
        assert resp.json()["wape"]["global_30d"] is None
