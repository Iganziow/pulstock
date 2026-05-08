"""
Tests del fix de conversión de unidades en train_ingredient_product
y compute_ingredient_demand.

BUG DETECTADO 08/05/26
======================
Cuando una receta usa GR pero el ingrediente está en KG (ej: receta de
Mokaccino dice "28 GR de Jamón sachet" pero Jamón.unit_obj=KG), el
sistema descuenta correctamente 0.028 KG (vía sales/recipes._convert_line_qty),
pero la predicción `ingredient_derived` sumaba 28 directo —
generando una sobre-predicción 1000x que disparaba MAPE > 200%.

Fix: aplicar el mismo `_convert_line_qty` en train_ingredient_product
y compute_ingredient_demand para que predicción y realidad estén en
la misma unidad.
"""
from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.utils import timezone

from catalog.models import Product, Recipe, RecipeLine, Unit
from core.models import Warehouse
from forecast.models import Forecast, ForecastModel
from forecast.services import compute_ingredient_demand, train_ingredient_product


@pytest.fixture
def units(db, tenant):
    """Crea unidades GR y KG con conversion_factor real."""
    gr, _ = Unit.objects.get_or_create(
        tenant=tenant, code="GR",
        defaults={
            "name": "Gramo", "family": "weight",
            "conversion_factor": Decimal("1"),  # base = gramo
            "is_base": True,
        },
    )
    kg, _ = Unit.objects.get_or_create(
        tenant=tenant, code="KG",
        defaults={
            "name": "Kilogramo", "family": "weight",
            "conversion_factor": Decimal("1000"),  # 1 KG = 1000 GR
            "is_base": False,
        },
    )
    return {"GR": gr, "KG": kg}


@pytest.fixture
def warehouse_e2e(db, tenant, store):
    return Warehouse.objects.create(tenant=tenant, store=store, name="W-E2E")


@pytest.fixture
def parent_product(db, tenant):
    """Producto vendido (Mokaccino)."""
    return Product.objects.create(
        tenant=tenant, name="Mokaccino", price=Decimal("4500"),
        is_active=True, unit="UN",
    )


@pytest.fixture
def ingredient_in_kg(db, tenant, units):
    """
    Ingrediente con unit_obj = KG. Casa real de Mario:
    Jamón sachet, Salsa caramelo. La receta los usa en GR pero el
    producto está registrado como KG.
    """
    p = Product.objects.create(
        tenant=tenant, name="Jamón sachet", price=Decimal("0"),
        is_active=True, unit="KG",
        unit_obj=units["KG"],
    )
    return p


@pytest.fixture
def recipe_with_unit_mismatch(db, tenant, parent_product, ingredient_in_kg, units):
    """
    Receta que pide 28 GR de Jamón (que está en KG).
    sales/recipes.py convierte a 0.028 KG al vender.
    forecast/services.py debe convertir igual al predecir.
    """
    recipe = Recipe.objects.create(
        tenant=tenant, product=parent_product, is_active=True,
    )
    RecipeLine.objects.create(
        tenant=tenant, recipe=recipe,
        ingredient=ingredient_in_kg,
        qty=Decimal("28.0"),
        unit=units["GR"],  # ← receta en GR
    )
    return recipe


# ── Tests de compute_ingredient_demand ─────────────────────────────────────


@pytest.mark.django_db
class TestComputeIngredientDemand:
    """Función usada como `ingredient_forecast_boost` (alimenta otros forecasts)."""

    def test_converts_recipe_qty_to_ingredient_unit(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """Si receta dice 28 GR pero ingrediente está en KG, la demanda
        derivada debe estar en KG (0.028 × parent_avg)."""
        # Parent vende 10/día en promedio
        ForecastModel.objects.create(
            tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
            algorithm="moving_avg", version=1, is_active=True,
            model_params={"avg_daily": "10"},  # 10 unidades de Mokaccino/día
            data_points=30, demand_pattern="smooth",
            confidence_label="medium",
        )

        demand = compute_ingredient_demand(tenant.id, [warehouse_e2e.id])
        # 10 mokaccinos × 28 GR / 1000 = 0.28 KG
        assert ingredient_in_kg.id in demand
        assert demand[ingredient_in_kg.id] == pytest.approx(0.28, rel=1e-4), (
            f"Esperaba 0.28 KG (10 mokaccinos × 0.028 KG c/u). "
            f"Obtuve {demand[ingredient_in_kg.id]}. Si está en 280, "
            f"la conversión de unidades NO se está aplicando."
        )

    def test_no_conversion_when_units_match(
        self, tenant, warehouse_e2e, parent_product, units,
    ):
        """Si receta y unit_obj coinciden, la qty pasa tal cual."""
        ingredient = Product.objects.create(
            tenant=tenant, name="Cacao", price=Decimal("0"),
            is_active=True, unit="GR", unit_obj=units["GR"],
        )
        recipe = Recipe.objects.create(
            tenant=tenant, product=parent_product, is_active=True,
        )
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=ingredient,
            qty=Decimal("5"), unit=units["GR"],
        )
        ForecastModel.objects.create(
            tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
            algorithm="moving_avg", version=1, is_active=True,
            model_params={"avg_daily": "10"},
            data_points=30, demand_pattern="smooth",
            confidence_label="medium",
        )

        demand = compute_ingredient_demand(tenant.id, [warehouse_e2e.id])
        # 10 × 5 GR = 50 GR (sin conversión, ambos en GR)
        assert demand[ingredient.id] == pytest.approx(50.0, rel=1e-4)


# ── Tests de train_ingredient_product ─────────────────────────────────────


@pytest.mark.django_db
class TestTrainIngredientProduct:
    """Función que genera Forecast diario para ingredientes derivados."""

    def test_forecast_qty_in_ingredient_unit_not_recipe_unit(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """El Forecast generado debe estar en la unidad del ingrediente
        (KG), no de la receta (GR). Tiene que coincidir con cómo
        sales/recipes.py descuenta el stock al vender."""
        today = date.today()

        # Crear forecasts diarios del PADRE (Mokaccino) que la función lee
        for i in range(1, 8):
            d = today + timedelta(days=i)
            Forecast.objects.create(
                tenant=tenant, product=parent_product,
                warehouse=warehouse_e2e,
                model=ForecastModel.objects.create(
                    tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
                    algorithm="moving_avg", version=i, is_active=False,
                    model_params={}, data_points=30,
                    demand_pattern="smooth", confidence_label="medium",
                ),
                forecast_date=d,
                qty_predicted=Decimal("10"),  # 10 mokaccinos/día
                confidence=Decimal("65"),
            )

        from inventory.models import StockItem
        stock_item = StockItem.objects.create(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
            on_hand=Decimal("5.000"), avg_cost=Decimal("100.00"),
        )

        stats = {"trained": 0, "skipped": 0, "by_algo": {}}
        train_ingredient_product(
            tenant=tenant, product=ingredient_in_kg,
            warehouse_id=warehouse_e2e.id,
            today=today, horizon=7,
            stock_items={(ingredient_in_kg.id, warehouse_e2e.id): stock_item},
            stats=stats,
        )

        assert stats["trained"] == 1, f"No se entrenó. stats={stats}"

        # Forecast debe estar en KG: 10 mokaccinos × 0.028 KG = 0.28 KG/día
        forecasts = Forecast.objects.filter(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
        ).order_by("forecast_date")
        assert forecasts.count() == 7

        for f in forecasts:
            assert f.qty_predicted == pytest.approx(Decimal("0.28"), abs=Decimal("0.001")), (
                f"Forecast del día {f.forecast_date} = {f.qty_predicted}. "
                f"Esperaba 0.280 KG. Si está en 280 (sin convertir), el bug "
                f"de conversión de unidades NO está arreglado."
            )
