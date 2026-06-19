"""
Monitoreo (#13): el endpoint superadmin/forecast/ expone `honest_health` —
MASE sin centinelas + beat-naive% + status OK/WARN/ALERT. Reemplaza el
"entrar por SSH a mirar cómo amaneció el modelo".

Centinela (>=900) y "polluted" (>=100, ej. 333/666 viejos) se EXCLUYEN del
promedio; solo el MASE real (0<x<900, no polluted) cuenta para mediana/beat.
"""
import pytest
from rest_framework.test import APIClient

from core.models import User
from catalog.models import Product
from forecast.models import ForecastModel


@pytest.fixture
def super_client(db):
    su = User.objects.create_user(username="plat_admin_hh", password="x")
    su.is_superuser = True
    su.is_staff = True
    su.save()
    c = APIClient()
    c.force_authenticate(user=su)
    return c


def _model(tenant, category, warehouse, sku, mase):
    p = Product.objects.create(tenant=tenant, category=category, name=sku, sku=sku, is_active=True)
    return ForecastModel.objects.create(
        tenant=tenant, product=p, warehouse=warehouse,
        algorithm="croston_sba", metrics={"mase": mase, "wape": 120.0},
        demand_pattern="intermittent", confidence_label="medium", is_active=True,
    )


@pytest.mark.django_db
class TestHonestHealth:
    def test_honest_health_excludes_sentinels_and_computes_status(
        self, super_client, tenant, category, warehouse_a,
    ):
        # 3 reales que le ganan al naive + 1 polluted (333) + 1 centinela (999)
        for i, mase in enumerate([0.5, 0.6, 0.7]):
            _model(tenant, category, warehouse_a, f"OK-{i}", mase)
        _model(tenant, category, warehouse_a, "POLLUTED", 333.0)
        _model(tenant, category, warehouse_a, "SENTINEL", 999.0)

        r = super_client.get("/api/superadmin/forecast/")
        assert r.status_code == 200, r.data
        hh = r.data.get("honest_health")
        assert hh is not None, "debe exponer honest_health"
        # Solo los 3 reales cuentan (excluye 333 y 999)
        assert hh["n_evaluable"] == 3
        assert hh["polluted_count"] == 1
        assert hh["sentinel_count"] == 1
        assert hh["mase_median"] == 0.6           # mediana de [0.5,0.6,0.7]
        assert hh["beat_naive_pct"] == 100.0      # los 3 < 1.0
        assert hh["status"] == "OK"

    def test_status_alert_when_model_loses_to_naive(
        self, super_client, tenant, category, warehouse_a,
    ):
        # Todos peores que el naive (MASE > 1) → ALERT
        for i, mase in enumerate([1.5, 1.6, 1.7, 2.0]):
            _model(tenant, category, warehouse_a, f"BAD-{i}", mase)
        r = super_client.get("/api/superadmin/forecast/")
        assert r.status_code == 200, r.data
        hh = r.data["honest_health"]
        assert hh["beat_naive_pct"] == 0.0
        assert hh["status"] == "ALERT"

    def test_no_models_returns_null_health(self, super_client, db):
        r = super_client.get("/api/superadmin/forecast/")
        assert r.status_code == 200, r.data
        assert r.data.get("honest_health") is None
