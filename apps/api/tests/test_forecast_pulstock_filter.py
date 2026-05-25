"""
Tests de Fase 3: filtro de entrenamiento por venta real en Pulstock.

CONTEXTO
========
Importamos 13 meses de historia de Fudo a DailySales con `forecast_only=True`.
Esa historia alimenta a los modelos (estacionalidad, patron semanal) pero el
catalogo de Pulstock no necesariamente matchea 1:1 con Fudo. Resultado:
productos como variantes "SL", "Iris cream" descontinuados, "Cafe para llevar"
sin rotacion tienen historia Fudo pero no venden actualmente en Pulstock,
generando forecasts y purchase suggestions fantasma.

REGLA NUEVA
===========
Un producto entra al pool de entrenamiento solo si:
- Tiene al menos 1 DailySales con forecast_only=False y qty_sold>0, O
- Es ingrediente de receta activa (siempre se entrena para purchase suggestions)

Cuando un producto vuelve a vender en Pulstock, automaticamente entra al pool
en el siguiente train (sin intervencion manual).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product, Recipe, RecipeLine, Unit
from forecast.models import DailySales, ForecastModel


@pytest.fixture
def units_simple(db, tenant):
    u, _ = Unit.objects.get_or_create(
        tenant=tenant, code="UN",
        defaults={"name": "Unidad", "family": "COUNT"},
    )
    return u


@pytest.fixture
def product_solo_fudo(db, tenant, units_simple, warehouse_a):
    """Producto que vendia en Fudo pero NUNCA en Pulstock."""
    p = Product.objects.create(
        tenant=tenant, name="Iris cream syrup (descontinuado)",
        unit_obj=units_simple, is_active=True,
    )
    today = date.today()
    # Solo historia Fudo (forecast_only=True)
    for i in range(60, 30, -1):
        DailySales.objects.create(
            tenant=tenant, product=p, warehouse=warehouse_a,
            date=today - timedelta(days=i),
            qty_sold=Decimal("3"), forecast_only=True,
        )
    return p


@pytest.fixture
def product_con_venta_pulstock(db, tenant, units_simple, warehouse_a):
    """Producto que vende activamente en Pulstock (con historia Fudo previa)."""
    p = Product.objects.create(
        tenant=tenant, name="Capuccino",
        unit_obj=units_simple, is_active=True,
    )
    today = date.today()
    # Historia Fudo
    for i in range(60, 30, -1):
        DailySales.objects.create(
            tenant=tenant, product=p, warehouse=warehouse_a,
            date=today - timedelta(days=i),
            qty_sold=Decimal("5"), forecast_only=True,
        )
    # Venta real Pulstock ultimos 25 dias
    for i in range(25, 0, -1):
        DailySales.objects.create(
            tenant=tenant, product=p, warehouse=warehouse_a,
            date=today - timedelta(days=i),
            qty_sold=Decimal("4"), forecast_only=False,
        )
    return p


@pytest.fixture
def ingrediente_solo_fudo(db, tenant, units_simple, warehouse_a, product_con_venta_pulstock):
    """Ingrediente de receta activa sin venta Pulstock pero usado via receta."""
    p = Product.objects.create(
        tenant=tenant, name="Leche (insumo)",
        unit_obj=units_simple, is_active=True,
    )
    # Crear receta: Capuccino usa Leche
    r = Recipe.objects.create(
        tenant=tenant, product=product_con_venta_pulstock, is_active=True,
    )
    RecipeLine.objects.create(
        tenant=tenant, recipe=r, ingredient=p,
        qty=Decimal("0.2"), unit=units_simple,
    )
    today = date.today()
    # Solo historia Fudo del ingrediente
    for i in range(60, 30, -1):
        DailySales.objects.create(
            tenant=tenant, product=p, warehouse=warehouse_a,
            date=today - timedelta(days=i),
            qty_sold=Decimal("1"), forecast_only=True,
        )
    return p


@pytest.mark.django_db
class TestPulstockFilter:

    def test_producto_solo_fudo_no_se_entrena(
        self, tenant, units_simple, warehouse_a, product_solo_fudo,
    ):
        """Producto con solo historia Fudo (forecast_only=True) NO debe
        tener modelo activo despues del train."""
        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)

        actives = ForecastModel.objects.filter(
            tenant=tenant, product=product_solo_fudo, is_active=True,
        )
        assert actives.count() == 0, (
            f"Producto solo-Fudo NO debe tener modelo activo. "
            f"Tiene {actives.count()}: {list(actives.values('algorithm', 'is_active'))}"
        )

    def test_producto_con_venta_pulstock_si_se_entrena(
        self, tenant, units_simple, warehouse_a, product_con_venta_pulstock,
    ):
        """Producto con venta real en Pulstock SI debe entrenarse."""
        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)

        actives = ForecastModel.objects.filter(
            tenant=tenant, product=product_con_venta_pulstock, is_active=True,
        )
        assert actives.count() == 1, (
            f"Producto con venta Pulstock debe tener 1 modelo activo, "
            f"tiene {actives.count()}"
        )

    def test_ingrediente_sin_venta_pulstock_si_se_entrena(
        self, tenant, units_simple, warehouse_a,
        product_con_venta_pulstock, ingrediente_solo_fudo,
    ):
        """Un ingrediente de receta activa SIEMPRE se entrena, incluso si
        no tiene venta directa en Pulstock (se consume via receta del padre)."""
        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)

        actives = ForecastModel.objects.filter(
            tenant=tenant, product=ingrediente_solo_fudo, is_active=True,
        )
        assert actives.count() >= 1, (
            "Ingrediente de receta activa debe entrenarse aunque no tenga "
            "venta directa en Pulstock"
        )

    def test_modelo_activo_previo_se_desactiva_si_pierde_elegibilidad(
        self, tenant, units_simple, warehouse_a, product_solo_fudo,
    ):
        """Si un producto tenia modelo activo (de antes de Fase 3) y ya no
        califica (sin venta Pulstock, no es ingrediente), debe desactivarse
        en el siguiente train."""
        # Simular modelo activo legacy
        ForecastModel.objects.create(
            tenant=tenant, product=product_solo_fudo, warehouse=warehouse_a,
            algorithm="croston_sba", version=1, is_active=True,
            model_params={}, data_points=30,
            metrics={"wape": 999.0},
            demand_pattern="intermittent", confidence_label="low",
        )

        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)

        m = ForecastModel.objects.get(
            tenant=tenant, product=product_solo_fudo, warehouse=warehouse_a,
        )
        assert m.is_active is False, (
            "Modelo activo de producto sin venta Pulstock debe desactivarse"
        )

    def test_auto_recovery_cuando_vuelve_a_vender(
        self, tenant, units_simple, warehouse_a, product_solo_fudo,
    ):
        """Cuando un producto NO calificado registra venta en Pulstock,
        el siguiente train lo entrena automaticamente (sin intervencion)."""
        # Primer train: sin venta Pulstock -> no se entrena
        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)
        assert not ForecastModel.objects.filter(
            tenant=tenant, product=product_solo_fudo, is_active=True,
        ).exists()

        # Ahora el producto vuelve a vender en Pulstock
        today = date.today()
        for i in range(20, 0, -1):
            DailySales.objects.create(
                tenant=tenant, product=product_solo_fudo, warehouse=warehouse_a,
                date=today - timedelta(days=i),
                qty_sold=Decimal("2"), forecast_only=False,
            )

        # Segundo train: ya tiene venta Pulstock -> se entrena
        call_command("train_forecast_models", tenant=tenant.id, verbosity=0)
        actives = ForecastModel.objects.filter(
            tenant=tenant, product=product_solo_fudo, is_active=True,
        )
        assert actives.count() == 1, (
            "Auto-recovery: producto que vuelve a vender Pulstock debe "
            "re-entrenarse en el siguiente train"
        )
