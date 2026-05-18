"""
Tests del filtro de productos con receta activa en forecast (Mario 18/05/26).

Mario lo pidió: productos como "Flat white", "Macchiato" (que TIENEN receta
y se arman al vender) no deben aparecer en /forecast con "Sin stock 0"
porque su stock real son los ingredientes.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from catalog.models import Product, Recipe
from inventory.models import StockItem
from forecast.models import ForecastModel, Forecast
from forecast.services import (
    get_product_forecasts, get_stockout_alerts, get_dashboard_kpis,
    get_products_with_active_recipe,
)


@pytest.fixture
def forecast_subscription(tenant):
    from billing.models import Plan, Subscription
    from django.utils import timezone
    plan, _ = Plan.objects.get_or_create(
        code="pro", defaults={
            "name": "Pro", "price_clp": 25000, "has_forecast": True,
        },
    )
    if not plan.has_forecast:
        plan.has_forecast = True
        plan.save(update_fields=["has_forecast"])
    now = timezone.now()
    Subscription.objects.get_or_create(
        tenant=tenant,
        defaults={
            "plan": plan, "status": "active",
            "current_period_start": now,
            "current_period_end": now + timezone.timedelta(days=30),
        },
    )


def _make_product(tenant, name, sku=None):
    return Product.objects.create(
        tenant=tenant, name=name, sku=sku or f"SKU-{name}",
        price=Decimal("1000.00"), is_active=True,
    )


def _make_recipe(tenant, product, is_active=True):
    """Marca al producto como producto-receta (Flat white, Macchiato, etc.)."""
    return Recipe.objects.create(
        tenant=tenant, product=product, is_active=is_active,
    )


def _make_forecast_model(tenant, warehouse, product, avg_daily="5.0"):
    return ForecastModel.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        algorithm="moving_avg", version=1,
        model_params={"avg_daily": avg_daily},
        metrics={"mape": 15.0},
        data_points=30, is_active=True,
    )


def _make_forecast(tenant, warehouse, product, model, forecast_date, days_to_stockout=3):
    return Forecast.objects.create(
        tenant=tenant, warehouse=warehouse, product=product, model=model,
        forecast_date=forecast_date,
        qty_predicted=Decimal("5.000"),
        lower_bound=Decimal("3.000"), upper_bound=Decimal("7.000"),
        days_to_stockout=days_to_stockout,
        confidence=Decimal("75.00"),
    )


# ────────────────────────────────────────────────────────────────────────────
# Helper get_products_with_active_recipe
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_helper_returns_only_active_recipe_products(tenant):
    p_recipe = _make_product(tenant, "Flat white")
    p_recipe_inactive = _make_product(tenant, "Bebida vieja sin uso")
    p_no_recipe = _make_product(tenant, "Café tolva caturra")

    _make_recipe(tenant, p_recipe, is_active=True)
    _make_recipe(tenant, p_recipe_inactive, is_active=False)
    # p_no_recipe sin Recipe

    ids = get_products_with_active_recipe(tenant.id)
    assert p_recipe.id in ids
    assert p_recipe_inactive.id not in ids
    assert p_no_recipe.id not in ids


# ────────────────────────────────────────────────────────────────────────────
# get_product_forecasts (lista en /dashboard/forecast)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_forecast_list_excludes_recipe_products(tenant, warehouse):
    p_ingrediente = _make_product(tenant, "Café tolva caturra")
    p_receta = _make_product(tenant, "Flat white")
    _make_recipe(tenant, p_receta)

    m1 = _make_forecast_model(tenant, warehouse, p_ingrediente)
    m2 = _make_forecast_model(tenant, warehouse, p_receta)

    today = date.today()
    _make_forecast(tenant, warehouse, p_ingrediente, m1, today + timedelta(days=1), 5)
    _make_forecast(tenant, warehouse, p_receta, m2, today + timedelta(days=1), 2)

    data = get_product_forecasts(tenant.id, [warehouse.id])
    names = {r["product_name"] for r in data["results"]}
    assert "Café tolva caturra" in names
    assert "Flat white" not in names, "producto con receta no debe aparecer"
    assert data["count"] == 1


@pytest.mark.django_db
def test_forecast_list_includes_recipe_when_inactive(tenant, warehouse):
    """Si la receta es is_active=False, el producto SI aparece (vuelve a tener stock propio)."""
    p = _make_product(tenant, "Bebida ex-receta")
    _make_recipe(tenant, p, is_active=False)
    m = _make_forecast_model(tenant, warehouse, p)
    _make_forecast(tenant, warehouse, p, m, date.today() + timedelta(days=1), 5)

    data = get_product_forecasts(tenant.id, [warehouse.id])
    names = {r["product_name"] for r in data["results"]}
    assert "Bebida ex-receta" in names


# ────────────────────────────────────────────────────────────────────────────
# get_stockout_alerts
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_alerts_exclude_recipe_products(tenant, warehouse):
    p_ing = _make_product(tenant, "Leche entera")
    p_rec = _make_product(tenant, "Latte")
    _make_recipe(tenant, p_rec)

    m1 = _make_forecast_model(tenant, warehouse, p_ing)
    m2 = _make_forecast_model(tenant, warehouse, p_rec)

    tomorrow = date.today() + timedelta(days=1)
    _make_forecast(tenant, warehouse, p_ing, m1, tomorrow, 2)   # CRITICAL
    _make_forecast(tenant, warehouse, p_rec, m2, tomorrow, 1)   # CRITICAL pero con receta

    data = get_stockout_alerts(tenant.id, [warehouse.id])
    names = {a["product_name"] for a in data["alerts"]}
    assert "Leche entera" in names
    assert "Latte" not in names
    assert data["count"] == 1
    assert data["critical"] == 1


# ────────────────────────────────────────────────────────────────────────────
# get_dashboard_kpis
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_kpis_exclude_recipe_products_from_at_risk(tenant, warehouse):
    p_ing = _make_product(tenant, "Azúcar")
    p_rec = _make_product(tenant, "Cortado")
    _make_recipe(tenant, p_rec)

    m1 = _make_forecast_model(tenant, warehouse, p_ing)
    m2 = _make_forecast_model(tenant, warehouse, p_rec)

    tomorrow = date.today() + timedelta(days=1)
    _make_forecast(tenant, warehouse, p_ing, m1, tomorrow, 2)
    _make_forecast(tenant, warehouse, p_rec, m2, tomorrow, 1)

    kpis = get_dashboard_kpis(tenant.id, [warehouse.id])
    # at_risk_7d cuenta SOLO ingredientes — Cortado no se cuenta
    assert kpis["at_risk_7d"] == 1
    assert kpis["imminent_3d"] == 1
